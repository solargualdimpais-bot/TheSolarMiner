"""Scoped, confidence-aware Tuya DP reference data.

DP numbers are product-scoped. Suggestions from this module are descriptive;
they never authorize a write. Commands still require the product schema or an
explicit owner mapping in ``local_dps_map``.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

REGISTRY_VERSION = 4


def _dp(dp_id: int, semantic: str, label: str, data_type: str, *, unit: str | None = None,
        scale: float | None = None, confidence: str = "UNKNOWN", source: str = "", read: bool = True,
        write: bool = False, minimum: float | None = None, maximum: float | None = None,
        enum_values: tuple[str, ...] = (), families: tuple[str, ...] = ()) -> dict[str, Any]:
    if not families:
        lowered = semantic.casefold()
        if "curtain" in lowered:
            families = ("curtain_controller",)
        elif lowered in {"current", "active_power", "voltage", "daily_accumulated_energy"} or "coefficient" in lowered:
            families = ("energy_monitor_switch",)
        elif lowered in {"brightness", "colour_temperature", "colour_data", "light_scene", "light_mode", "light_switch", "light_countdown", "music_data"}:
            families = ("lighting",)
        elif lowered.startswith(("switch", "countdown", "master_switch", "power_on_state", "child_lock")):
            families = ("smart_switch",)
        else:
            families = ("tuya_candidate",)
    return {"dps_id": dp_id, "semantic_code": semantic, "display_name": label,
            "data_type": data_type, "unit": unit, "scale": scale, "minimum": minimum,
            "maximum": maximum, "enum_values": list(enum_values), "read_supported": read,
            "write_supported": write, "device_families": list(families), "confidence": confidence,
            "source": source, "validation_status": "reference_only"}


_OFFICIAL_SWITCH = "Tuya Developer Platform: Smart Switch Product Function Definition"
_OWNER_NOTES = "Owner-provided device observations in the supplied DPS proposal"
_COMMUNITY = "Community-reported Tuya DPS template; device-specific validation required"


@lru_cache(maxsize=1)
def _community_profiles_by_product_id() -> dict[str, list[dict[str, Any]]]:
    """Load bundled community DPS references, indexed by exact Tuya product ID."""
    path = Path(__file__).with_name("tuya_community_catalog.json")
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    records = catalog.get("records", []) if isinstance(catalog, dict) else []
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        for product in record.get("products", []) if isinstance(record.get("products"), list) else []:
            product_id = str(product.get("id") or "").strip() if isinstance(product, dict) else ""
            if not product_id:
                continue
            result.setdefault(product_id, []).append({"record": record, "product": product,
                                                       "source": catalog.get("source", {})})
    return result


def _community_dp_reference(product_id: str, dp_id: int) -> dict[str, Any] | None:
    """Return a non-authorizing community hint only for an exact Product ID."""
    candidates: list[dict[str, Any]] = []
    for match in _community_profiles_by_product_id().get(product_id, []):
        record = match["record"]
        for dp in record.get("dps", []) if isinstance(record.get("dps"), list) else []:
            if isinstance(dp, dict) and str(dp.get("id")) == str(dp_id):
                candidates.append({**dp, "config": record.get("config"),
                                   "device_name": record.get("name"),
                                   "manufacturer": match["product"].get("manufacturer"),
                                   "model": match["product"].get("model"),
                                   "repository": match["source"].get("repository"),
                                   "commit": match["source"].get("commit")})
    if not candidates:
        return None
    # A reused PID with conflicting community meanings is not a safe hint.
    meanings = {(str(item.get("type") or "").casefold(), str(item.get("unit") or "").casefold(),
                 json.dumps(item.get("range"), sort_keys=True)) for item in candidates}
    configs = {str(item.get("config") or "") for item in candidates}
    labels_by_config: dict[str, set[str]] = {}
    generic_names = {"sensor", "value", "option", "button", "switch"}
    for item in candidates:
        label = str(item.get("entity_name") or item.get("name") or "").strip()
        if label and label.casefold() not in generic_names:
            labels_by_config.setdefault(str(item.get("config") or ""), set()).add(label.casefold())
    if len(meanings) != 1 or (len(configs) > 1 and len({tuple(sorted(x)) for x in labels_by_config.values()}) > 1):
        return None
    result = dict(candidates[0])
    result["related_fields"] = sorted({str(item.get("entity_name") or item.get("name") or "")
                                       for item in candidates if item.get("entity_name") or item.get("name")})
    result["reference_labels"] = sorted({label for labels in labels_by_config.values() for label in labels})
    return result


def _community_dp_ids(product_id: str) -> set[int]:
    """Return IDs in exact-product community profiles for display only."""
    result: set[int] = set()
    for match in _community_profiles_by_product_id().get(product_id, []):
        dps = match["record"].get("dps", [])
        for dp in dps if isinstance(dps, list) else []:
            try:
                identifier = int(dp.get("id")) if isinstance(dp, dict) else 0
            except (TypeError, ValueError):
                identifier = 0
            if identifier > 0:
                result.add(identifier)
    return result

# Tuya's official DLQ (circuit-breaker) category standard is code-based: it
# names common functions such as ``switch``, ``daily_energy``, ``cur_current_a``
# and ``fault``, but does not assign one universal DP number to every product.
# Resolve these concepts through the exact device schema's code -> dp_id map.
# Category references describe/read; they never authorize a command by themselves.
_DLQ_SCHEMA_CONCEPTS: dict[str, dict[str, Any]] = {
    "switch": {"semantic_code": "switch", "display_name": "Interruptor", "data_type": "boolean"},
    "daily_energy": {"semantic_code": "daily_energy", "display_name": "Consumo diário", "data_type": "raw", "unit": "kWh"},
    "month_energy": {"semantic_code": "monthly_energy", "display_name": "Consumo mensal", "data_type": "raw", "unit": "kWh"},
    "total_ele": {"semantic_code": "total_energy", "display_name": "Energia total", "data_type": "integer", "unit": "kWh", "scale": 1},
    "total_forward_energy": {"semantic_code": "total_forward_energy", "display_name": "Energia ativa total", "data_type": "integer", "unit": "kWh", "scale": 2},
    "cur_voltage_a": {"semantic_code": "voltage_phase_a", "display_name": "Tensão · fase A", "data_type": "integer", "unit": "V", "scale": 1},
    "cur_voltage_b": {"semantic_code": "voltage_phase_b", "display_name": "Tensão · fase B", "data_type": "integer", "unit": "V", "scale": 1},
    "cur_voltage_c": {"semantic_code": "voltage_phase_c", "display_name": "Tensão · fase C", "data_type": "integer", "unit": "V", "scale": 1},
    "cur_current_a": {"semantic_code": "current_phase_a", "display_name": "Corrente · fase A", "data_type": "integer", "unit": "mA", "scale": 0},
    "cur_current_b": {"semantic_code": "current_phase_b", "display_name": "Corrente · fase B", "data_type": "integer", "unit": "mA", "scale": 0},
    "cur_current_c": {"semantic_code": "current_phase_c", "display_name": "Corrente · fase C", "data_type": "integer", "unit": "mA", "scale": 0},
    "cur_activepower_a": {"semantic_code": "active_power_phase_a", "display_name": "Potência ativa · fase A", "data_type": "integer", "unit": "W", "scale": 1},
    "cur_activepower_b": {"semantic_code": "active_power_phase_b", "display_name": "Potência ativa · fase B", "data_type": "integer", "unit": "W", "scale": 1},
    "cur_activepower_c": {"semantic_code": "active_power_phase_c", "display_name": "Potência ativa · fase C", "data_type": "integer", "unit": "W", "scale": 1},
    "cur_voltage": {"semantic_code": "voltage", "display_name": "Tensão", "data_type": "integer", "unit": "V"},
    "cur_current": {"semantic_code": "current", "display_name": "Corrente", "data_type": "integer", "unit": "mA"},
    "cur_power": {"semantic_code": "active_power", "display_name": "Potência ativa", "data_type": "integer", "unit": "W"},
    "fault": {"semantic_code": "fault", "display_name": "Falhas e alarmes", "data_type": "bitmap"},
    "breaker_current_status": {"semantic_code": "connection_mode", "display_name": "Estado de ligação", "data_type": "enum"},
    "alarm_range_setting": {"semantic_code": "alarm_thresholds", "display_name": "Limites dos alarmes", "data_type": "string"},
    "alarm_set_1": {"semantic_code": "alarm_setting_1", "display_name": "Configuração de alarme 1", "data_type": "raw"},
    "alarm_set_2": {"semantic_code": "alarm_setting_2", "display_name": "Configuração de alarme 2", "data_type": "raw"},
}


def _category_schema_concept(category: str, entry: dict[str, Any]) -> dict[str, Any] | None:
    """Interpret documented category codes while retaining the product DP ID."""
    category_key = re.sub(r"[^a-z0-9]", "", category.casefold())
    code = str(entry.get("code") or "").casefold()
    concept = _DLQ_SCHEMA_CONCEPTS.get(code) if category_key == "dlq" else None
    if category_key in {"kg", "cz", "pc"}:
        if re.fullmatch(r"switch(?:_[1-6])?", code):
            suffix = code.partition("_")[2]
            concept = {"semantic_code": f"switch_{suffix}" if suffix else "switch",
                       "display_name": f"Interruptor {suffix}" if suffix else "Interruptor", "data_type": "boolean"}
        elif re.fullmatch(r"countdown(?:_[1-6])?", code):
            suffix = code.partition("_")[2]
            concept = {"semantic_code": code, "display_name": f"Temporizador {suffix}" if suffix else "Temporizador",
                       "data_type": "integer", "unit": "s", "scale": 0}
        else:
            concept = {"add_ele": {"semantic_code": "accumulated_energy", "display_name": "Energia acumulada", "data_type": "integer", "unit": "kWh", "scale": 3},
                       "cur_current": {"semantic_code": "current", "display_name": "Corrente", "data_type": "integer", "unit": "mA", "scale": 0},
                       "cur_power": {"semantic_code": "active_power", "display_name": "Potência ativa", "data_type": "integer", "unit": "W", "scale": 1},
                       "cur_voltage": {"semantic_code": "voltage", "display_name": "Tensão", "data_type": "integer", "unit": "V", "scale": 1},
                       "fault": {"semantic_code": "fault", "display_name": "Falhas e alarmes", "data_type": "bitmap"}}.get(code)
    elif category_key in {"cl", "clkg"}:
        if code in {"control", "control_2", "mach_operate"}:
            concept = {"semantic_code": "curtain_control", "display_name": "Controlo da cortina", "data_type": "enum"}
        elif code.startswith("percent_control") or code == "position":
            concept = {"semantic_code": "curtain_position", "display_name": "Posição da cortina", "data_type": "integer", "unit": "%", "scale": 0}
        elif code in {"countdown", "countdown_set"}:
            concept = {"semantic_code": "countdown", "display_name": "Temporizador", "data_type": "enum"}
        elif code in {"control_back", "control_back_mode", "opposite"}:
            concept = {"semantic_code": "motor_direction", "display_name": "Direção do motor", "data_type": "enum"}
    elif category_key in {"dj", "xdd", "fwd", "dc", "dd", "tgq", "tgkg"}:
        if code in {"switch_led", "switch"}:
            concept = {"semantic_code": "light_switch", "display_name": "Interruptor da luz", "data_type": "boolean"}
        elif code in {"work_mode", "light_mode"}:
            concept = {"semantic_code": "light_mode", "display_name": "Modo de iluminação", "data_type": "enum"}
        elif code in {"bright_value", "brightness"}:
            concept = {"semantic_code": "brightness", "display_name": "Brilho", "data_type": "integer"}
        elif code in {"temp_value", "colour_temperature"}:
            concept = {"semantic_code": "colour_temperature", "display_name": "Temperatura de cor", "data_type": "integer"}
        elif code in {"countdown", "light_countdown"}:
            concept = {"semantic_code": "countdown", "display_name": "Temporizador", "data_type": "integer", "unit": "s", "scale": 0}
    if concept is None and category_key != "dlq":
        return None
    if concept is None:
        # The product code remains authoritative where present. For translated
        # display names, accept only a short curated set of exact equivalents;
        # never infer from a bare numeric DP or a vague word like "energy".
        name = str(entry.get("name") or entry.get("desc") or "")
        normalized_name = unicodedata.normalize("NFKD", name.casefold())
        normalized_name = "".join(char for char in normalized_name if not unicodedata.combining(char))
        normalized_name = re.sub(r"[^a-z0-9]+", " ", normalized_name).strip()
        name_aliases = {
            "interruptor": "switch", "relay": "switch", "rele": "switch", "estado do rele": "switch",
            "daily electricity consumption data": "daily_energy", "daily electricity": "daily_energy",
            "consumo diario de eletricidade": "daily_energy", "energia diaria": "daily_energy",
            "monthly electricity consumption data": "month_energy", "consumo mensal de eletricidade": "month_energy",
            "total electricity": "total_ele", "energia total": "total_ele", "energia acumulada total": "total_ele",
            "forward total active electricity": "total_forward_energy", "energia ativa total": "total_forward_energy",
            "phase a voltage": "cur_voltage_a", "tensao fase a": "cur_voltage_a",
            "phase b voltage": "cur_voltage_b", "tensao fase b": "cur_voltage_b",
            "phase c voltage": "cur_voltage_c", "tensao fase c": "cur_voltage_c",
            "phase a current": "cur_current_a", "corrente fase a": "cur_current_a",
            "phase b current": "cur_current_b", "corrente fase b": "cur_current_b",
            "phase c current": "cur_current_c", "corrente fase c": "cur_current_c",
            "phase a active power": "cur_activepower_a", "potencia ativa fase a": "cur_activepower_a",
            "phase b active power": "cur_activepower_b", "potencia ativa fase b": "cur_activepower_b",
            "phase c active power": "cur_activepower_c", "potencia ativa fase c": "cur_activepower_c",
            "fault alert": "fault", "alarme de falha": "fault", "alerta de falha": "fault",
        }
        alias_code = name_aliases.get(normalized_name)
        concept = _DLQ_SCHEMA_CONCEPTS.get(alias_code or "")
    if concept is None:
        return None
    declared_type = str(entry.get("type") or "").casefold()
    expected_types = {
        "boolean": {"bool", "boolean"}, "raw": {"raw"},
        "integer": {"value", "integer", "int", "number"},
        "bitmap": {"fault", "bitmap"}, "enum": {"enum"}, "string": {"string", "char"},
    }.get(str(concept.get("data_type") or ""))
    if declared_type and expected_types and declared_type not in expected_types:
        return None
    actual_values = entry.get("values")
    if isinstance(actual_values, str):
        try:
            actual_values = json.loads(actual_values)
        except (TypeError, ValueError):
            actual_values = {}
    if not isinstance(actual_values, dict):
        actual_values = {}
    resolved = dict(concept)
    if isinstance(actual_values.get("unit"), str) and actual_values["unit"].strip():
        resolved["unit"] = actual_values["unit"].strip()
    actual_scale = actual_values.get("scale")
    if isinstance(actual_scale, (int, float)) and not isinstance(actual_scale, bool):
        resolved["scale"] = actual_scale
    return {**resolved, "confidence": "DOCUMENTED",
            "source": f"Tuya official {category_key.upper()} category standard + exact product schema",
            "validation_status": "category_reference_product_schema_resolved"}

DEFINITIONS: tuple[dict[str, Any], ...] = tuple([
    *[_dp(i, f"switch_{i}", f"Switch {i}", "boolean", confidence="DOCUMENTED",
          source=_OFFICIAL_SWITCH, write=True) for i in range(1, 7)],
    *[_dp(i, f"countdown_{i-6}", f"Countdown {i-6}", "integer", unit="s", scale=1,
          minimum=0, maximum=86400, confidence="DOCUMENTED", source=_OFFICIAL_SWITCH, write=True)
      for i in range(7, 13)],
    _dp(13, "master_switch", "Master switch", "boolean", confidence="DOCUMENTED",
        source=_OFFICIAL_SWITCH, write=True),
    _dp(14, "power_on_state", "Power-on state", "enum", enum_values=("off", "on", "memory"),
        confidence="DOCUMENTED", source=_OFFICIAL_SWITCH, write=True),
    _dp(17, "daily_accumulated_energy", "Accumulated energy", "integer", confidence="CONFIRMED",
        source=_OWNER_NOTES),
    _dp(18, "current", "Current", "integer", unit="A", scale=1000, confidence="CONFIRMED",
        source=_OWNER_NOTES),
    _dp(19, "active_power", "Active power", "integer", unit="W", scale=10, confidence="CONFIRMED",
        source=_OWNER_NOTES),
    _dp(20, "voltage", "Voltage", "integer", unit="V", scale=10, confidence="CONFIRMED",
        source=_OWNER_NOTES),
    *[_dp(i, name, name.replace("_", " ").title(), "integer", confidence="COMMUNITY_REPORTED",
          source=_COMMUNITY) for i, name in ((21, "test_bit"), (22, "voltage_coefficient"),
          (23, "current_coefficient"), (24, "power_coefficient"), (25, "electricity_coefficient"),
          (26, "fault"))],
    _dp(38, "power_on_state", "Power-on state", "enum", enum_values=("off", "on", "memory"),
        confidence="COMMUNITY_REPORTED", source=_COMMUNITY, write=True),
    _dp(39, "overcharge_switch", "Overcharge protection", "boolean", confidence="COMMUNITY_REPORTED",
        source=_COMMUNITY, write=True),
    _dp(40, "indicator_status", "Indicator status", "enum", enum_values=("none", "on", "relay", "pos"),
        confidence="COMMUNITY_REPORTED", source=_COMMUNITY, write=True),
    _dp(41, "child_lock", "Child lock", "boolean", confidence="COMMUNITY_REPORTED",
        source=_COMMUNITY, write=True),
    *[_dp(i, "unknown", f"Unknown DPS {i}", "unknown", confidence="UNKNOWN", source="")
      for i in (42, 43, 44)],
    _dp(66, "online_status", "Online status", "unknown", confidence="COMMUNITY_REPORTED", source=_COMMUNITY),
    _dp(107, "switch_type_setting", "Switch type setting", "enum", confidence="CONFIRMED",
        source=_OWNER_NOTES),
    *[_dp(i, f"pair_{pair}_mode", f"Pair K{pair*2-1}/K{pair*2} mode", "enum",
          enum_values=("switch", "curtain"), confidence="CONFIRMED", source=_OWNER_NOTES, write=False)
      for pair, i in ((1, 113), (2, 114), (3, 115))],
    _dp(118, "equipment_identifier", "Equipment identifier", "integer", confidence="CONFIRMED",
        source=_OWNER_NOTES),
    # Public community templates for curtains and lighting. They remain
    # suggestions only; product schema or explicit owner validation is needed.
    *[_dp(i, semantic, label, kind, unit=unit, scale=scale, minimum=minimum, maximum=maximum,
          enum_values=enums, confidence="COMMUNITY_REPORTED", source=_COMMUNITY,
          write=False)
      for i, semantic, label, kind, unit, scale, minimum, maximum, enums in (
          (1, "curtain_control_1", "Curtain control 1", "enum", None, None, None, None, ("open", "stop", "close", "continue")),
          (2, "curtain_position_1", "Curtain position 1", "integer", "%", 1, 0, 100, ()),
          (3, "curtain_calibration_1", "Curtain calibration 1", "unknown", None, None, None, None, ()),
          (4, "curtain_control_2", "Curtain control 2", "enum", None, None, None, None, ("open", "stop", "close", "continue")),
          (5, "curtain_position_2", "Curtain position 2", "integer", "%", 1, 0, 100, ()),
          (6, "curtain_calibration_2", "Curtain calibration 2", "unknown", None, None, None, None, ()),
          (8, "curtain_motor_direction_1", "Curtain motor direction 1", "enum", None, None, None, None, ()),
          (9, "curtain_motor_direction_2", "Curtain motor direction 2", "enum", None, None, None, None, ()),
          (10, "curtain_quick_calibration_1", "Curtain quick calibration 1", "unknown", None, None, None, None, ()),
          (11, "curtain_quick_calibration_2", "Curtain quick calibration 2", "unknown", None, None, None, None, ()),
          (12, "curtain_motor_mode_1", "Curtain motor mode 1", "enum", None, None, None, None, ()),
          (13, "curtain_motor_mode_2", "Curtain motor mode 2", "enum", None, None, None, None, ()),
          (14, "curtain_light_mode", "Curtain light mode", "enum", None, None, None, None, ()),
          (20, "light_switch", "Light switch", "boolean", None, None, None, None, ()),
          (21, "light_mode", "Light mode", "enum", None, None, None, None, ()),
          (22, "brightness", "Brightness", "integer", "%", 1, 0, 1000, ()),
          (23, "colour_temperature", "Colour temperature", "integer", None, None, None, None, ()),
          (24, "colour_data", "Colour data", "string", None, None, None, None, ()),
          (25, "light_scene", "Light scene", "string", None, None, None, None, ()),
          (26, "light_countdown", "Light countdown", "integer", "s", 1, 0, 86400, ()),
          (27, "music_data", "Music data", "string", None, None, None, None, ()),
          (28, "light_control_debug", "Light control data", "unknown", None, None, None, None, ()),
          (29, "light_debug_data", "Light debug data", "unknown", None, None, None, None, ()),
      )],
])

PRESETS: dict[str, dict[str, Any]] = {
    "energy_monitor_switch": {"label": "Energy-monitoring switch / water heater", "families": ["energy_switch", "water_heater"],
        "scope": "product schema or owner-selected preset", "signature": [1, 9, 17, 18, 19, 20],
        "minimum_matches": 4, "definitions": [1, 9, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 38, 40, 41, 42, 66]},
    "six_channel_hybrid": {"label": "Six-channel switch / curtain hybrid", "families": ["multi_switch", "curtain_controller"],
        "scope": "exact product signature required", "signature": [1, 2, 3, 4, 5, 6, 107, 113, 114, 115],
        "minimum_matches": 8, "definitions": [1, 2, 3, 4, 5, 6, 13, 14, 107, 113, 114, 115, 118]},
    "single_switch_borehole": {"label": "Single switch / borehole cabinet", "families": ["switch", "breaker"],
        "scope": "product schema or owner-selected preset", "signature": [1, 9, 41],
        "minimum_matches": 3, "definitions": [1, 9, 38, 40, 41, 42, 66]},
    "qccdz_ev_charger": {"label": "QCCDZ EV charger", "families": ["ev_charger"],
        "scope": "Tuya category QCCDZ only", "signature": [18], "minimum_matches": 1,
        "definitions": [18]},
}

_BY_ID: dict[int, dict[str, Any]] = {}
for _entry in DEFINITIONS:
    # The first entries are the official smart-switch definitions. Later
    # community templates can reuse a DP number with a different meaning.
    _BY_ID.setdefault(_entry["dps_id"], _entry)
COMMUNITY_TEMPLATES = [entry for entry in DEFINITIONS if entry["confidence"] == "COMMUNITY_REPORTED"]


def _schema_ids(device: dict[str, Any]) -> dict[str, int]:
    found: dict[str, int] = {}
    for key in ("functions", "status_spec", "category_functions", "category_status_spec"):
        values = device.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict) or not isinstance(item.get("code"), str):
                continue
            dp_id = item.get("dp_id", item.get("dpId"))
            if isinstance(dp_id, int) and not isinstance(dp_id, bool) and dp_id > 0:
                found[item["code"]] = dp_id
    return found


def _schema_mapping_conflicts(device: dict[str, Any]) -> dict[int, list[str]]:
    by_id: dict[int, set[str]] = {}
    for key in ("functions", "status_spec"):
        values = device.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict) or not isinstance(item.get("code"), str):
                continue
            dp_id = item.get("dp_id", item.get("dpId"))
            if isinstance(dp_id, int) and not isinstance(dp_id, bool) and dp_id > 0:
                by_id.setdefault(dp_id, set()).add(item["code"])
    return {dp_id: sorted(codes) for dp_id, codes in by_id.items() if len(codes) > 1}


def analyze_device(device: dict[str, Any], status: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Describe observed DPS and ranked presets without authorizing controls."""
    raw_rows = status if isinstance(status, list) else device.get("current_status", [])
    raw: dict[int, Any] = {}
    for row in raw_rows if isinstance(raw_rows, list) else []:
        if not isinstance(row, dict):
            continue
        identifier = row.get("dps_id", row.get("dp_id", row.get("dpId")))
        code = row.get("code")
        if identifier is None and isinstance(code, str) and code.startswith("dps_"):
            identifier = code[4:]
        try:
            dp_id = int(identifier)
        except (TypeError, ValueError):
            continue
        if dp_id > 0:
            raw[dp_id] = row.get("value")
    schema = _schema_ids(device)
    mapping_conflicts = _schema_mapping_conflicts(device)
    available = set(raw)
    available.update(schema.values())
    category = "".join(ch for ch in str(device.get("category") or "").casefold() if ch.isalnum())
    product_id = str(device.get("product_id") or "")
    if category == "qccdz":
        ordered = ["qccdz_ev_charger"]
    else:
        ordered = [key for key in PRESETS if key != "qccdz_ev_charger"]
    scores = []
    for key in ordered:
        preset = PRESETS[key]
        signature = preset["signature"]
        matches = len(available.intersection(signature))
        score = round(matches / max(len(signature), 1), 3)
        eligible = matches >= preset["minimum_matches"]
        scores.append({"preset_id": key, "label": preset["label"], "score": score,
                       "matched_dps": sorted(available.intersection(signature)),
                       "required_matches": preset["minimum_matches"], "eligible": eligible})
    scores.sort(key=lambda item: (item["eligible"], item["score"]), reverse=True)
    top = scores[0] if scores else None
    second = scores[1] if len(scores) > 1 else None
    explicit_preset = str(device.get("dps_preset_id") or "")
    declared_switches = {str(item.get("code")) for item in device.get("functions", [])
                         if isinstance(item, dict) and
                         re.fullmatch(r"switch_[1-6]", str(item.get("code", ""))) and
                         str(item.get("type", "")).casefold() in {"bool", "boolean"}}
    reported_switches = {str(item) for item in device.get("switch_channels", []) if isinstance(item, str)}
    observed_switches = {dp_id for dp_id, value in raw.items()
                         if 1 <= dp_id <= 6 and isinstance(value, bool)}
    kg_six_channel_signature = (category == "kg" and
                                (len(declared_switches) >= 6 or len(reported_switches) >= 6 or
                                 len(observed_switches) >= 6 or
                                 isinstance(device.get("channel_count"), int) and device["channel_count"] >= 6))
    if category == "qccdz":
        selected = next((item for item in scores if item["preset_id"] == "qccdz_ev_charger"), None)
    elif kg_six_channel_signature:
        selected = next((item for item in scores if item["preset_id"] == "six_channel_hybrid"), None)
    elif explicit_preset in PRESETS and explicit_preset != "qccdz_ev_charger":
        selected = next((item for item in scores if item["preset_id"] == explicit_preset), None)
        if selected is None:
            preset = PRESETS[explicit_preset]
            selected = {"preset_id": explicit_preset, "label": preset["label"], "eligible": True,
                        "score": 0.0, "matched_dps": [], "required_matches": preset["minimum_matches"]}
    else:
        # Incomplete or ambiguous signatures remain suggestions. KG plus a
        # declared six-channel switch profile is specific enough to apply the
        # read-only preset; the discovered schema still governs writable controls.
        selected = None
    selected_key = selected["preset_id"] if selected else None
    # A strong signature match may annotate observed DPS from the reference
    # catalog without activating the preset. Writes and dynamic entities still
    # require explicit owner selection (or a confirmed product category).
    reference_key = selected_key or (top["preset_id"] if top and top.get("eligible") else None)
    definitions = PRESETS[reference_key]["definitions"] if reference_key else []
    schema_by_id = {dp_id: code for code, dp_id in schema.items()}
    schema_entry_by_id: dict[int, dict[str, Any]] = {}
    for schema_key in ("functions", "status_spec"):
        entries = device.get(schema_key)
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            dp_id = entry.get("dp_id", entry.get("dpId"))
            if isinstance(dp_id, int) and not isinstance(dp_id, bool) and dp_id > 0:
                schema_entry_by_id[dp_id] = entry
    observed = []
    # Community DPS enrich the detail view for the exact Product ID only.
    # They are intentionally excluded from preset scoring and command routing.
    community_dp_ids = _community_dp_ids(product_id)
    display_ids = available | community_dp_ids
    for dp_id in sorted(display_ids):
        known = _BY_ID.get(dp_id) if dp_id in definitions else None
        # DP 18 means current in the energy-monitor preset but is the confirmed
        # relay only for the owner's QCCDZ EV-charger family. Keep this override
        # scoped so one profile can never relabel another profile's DP 18.
        if selected_key in {"energy_monitor_switch", "single_switch_borehole"} and dp_id in {1, 9}:
            known = {"semantic_code": "switch" if dp_id == 1 else "countdown",
                     "display_name": "Interruptor" if dp_id == 1 else "Temporizador",
                     "data_type": "boolean" if dp_id == 1 else "integer",
                     "unit": None if dp_id == 1 else "s", "scale": 1.0,
                     "confidence": "CONFIRMED", "source": _OWNER_NOTES}
        if selected_key == "six_channel_hybrid" and dp_id in {1, 2, 3, 4, 5, 6}:
            known = {"semantic_code": f"switch_{dp_id}", "display_name": f"Switch {dp_id}",
                     "data_type": "boolean", "unit": None, "scale": None,
                     "confidence": "CONFIRMED", "source": _OWNER_NOTES}
        if selected_key == "single_switch_borehole" and dp_id == 41:
            known = {"semantic_code": "child_lock", "display_name": "Child lock",
                     "data_type": "boolean", "unit": None, "scale": None,
                     "confidence": "CONFIRMED", "source": _OWNER_NOTES}
        if reference_key == "six_channel_hybrid" and dp_id == 13:
            known = {"semantic_code": "master_switch", "display_name": "Master switch",
                     "data_type": "boolean", "unit": None, "scale": None,
                     "confidence": "DOCUMENTED", "source": _OFFICIAL_SWITCH}
        if reference_key == "six_channel_hybrid" and dp_id == 14:
            known = {"semantic_code": "power_on_state", "display_name": "Power-on behavior after outage",
                     "data_type": "enum", "unit": None, "scale": None,
                     "confidence": "DOCUMENTED", "source": _OFFICIAL_SWITCH}
        if selected_key == "six_channel_hybrid" and dp_id == 118:
            known = {"semantic_code": "equipment_identifier", "display_name": "Equipment identifier",
                     "data_type": "integer", "unit": None, "scale": None,
                     "confidence": "CONFIRMED", "source": _OWNER_NOTES}
        if selected_key == "six_channel_hybrid" and dp_id in {113, 114, 115}:
            pair = dp_id - 112
            known = {"semantic_code": f"pair_{pair}_mode", "display_name": f"Pair K{pair*2-1}/K{pair*2} mode",
                     "data_type": "enum", "unit": None, "scale": None,
                     "confidence": "CONFIRMED", "source": _OWNER_NOTES}
        community_reference = _community_dp_reference(str(device.get("product_id") or ""), dp_id)
        if category == "qccdz":
            # Owner-confirmed QCCDZ EV charger map. These IDs are scoped to
            # this EV category and are descriptive only; product schema still
            # controls every writable command and its accepted value range.
            qccdz_map = {
                3: ("charger_state", "Estado do carregador", "string"),
                10: ("alarms_faults", "Alarmes e avarias", "unknown"),
                11: ("alarm_configuration_1", "Configuração de alarmes 1", "unknown"),
                12: ("alarm_configuration_2", "Configuração de alarmes 2", "unknown"),
                14: ("charging_mode", "Modo de carregamento", "enum"),
                15: ("balance_energy", "Energia de equilíbrio", "unknown"),
                16: ("clear_energy", "Limpar energia", "unknown"),
                18: ("switch", "Interruptor do carregador", "boolean"),
                20: ("clear_alarms", "Limpar alarmes", "unknown"),
                25: ("last_session_energy", "Energia da última sessão", "unknown"),
                27: ("online_status", "Estado online", "unknown"),
                101: ("operational_status", "Estado operacional", "unknown"),
                106: ("total_energy", "Energia total", "unknown"),
            }
            if dp_id in qccdz_map:
                semantic, label, data_type = qccdz_map[dp_id]
                schema_code = str(schema_by_id.get(dp_id) or "").casefold()
                exact_entry = schema_entry_by_id.get(dp_id, {})
                if community_reference and not schema_code:
                    # Exact Product ID community data supersedes category notes.
                    known = None
                elif schema_code in {"switch", "switch_1", "relay_status"}:
                    known = {"semantic_code": "switch", "display_name": "Interruptor do carregador",
                             "data_type": "boolean", "unit": None, "scale": None,
                             "confidence": "PRODUCT_SCHEMA", "source": "Exact Tuya product schema"}
                elif schema_code:
                    schema_type = str(exact_entry.get("type") or "unknown").casefold()
                    type_names = {"bool": "boolean", "boolean": "boolean", "value": "integer",
                                  "int": "integer", "integer": "integer", "enum": "enum",
                                  "raw": "raw", "string": "string", "bitmap": "bitmap"}
                    known = {"semantic_code": schema_code,
                             "display_name": str(exact_entry.get("name") or exact_entry.get("desc") or schema_code),
                             "data_type": type_names.get(schema_type, schema_type),
                             "unit": None, "scale": None, "confidence": "PRODUCT_SCHEMA",
                             "source": "Exact Tuya product schema"}
                elif not schema_code and not community_reference and dp_id not in community_dp_ids:
                    known = {"semantic_code": semantic, "display_name": label,
                             "data_type": data_type, "unit": None, "scale": None,
                             "confidence": "OWNER_CONFIRMED", "source": "Owner-provided QCCDZ EV charger map"}
                elif not schema_code and dp_id in community_dp_ids:
                    known = None
                else:
                    known = {"semantic_code": semantic, "display_name": label,
                             "data_type": data_type, "unit": None, "scale": None,
                             "confidence": "OWNER_CONFIRMED", "source": "Owner-provided QCCDZ EV charger map"}
        if category == "dlq":
            # DLQ meanings follow Tuya's category function code; DP numbering
            # belongs to the exact product schema and can differ by product.
            known = _category_schema_concept(category, schema_entry_by_id.get(dp_id, {}))
        if (known is None or (community_reference and schema_by_id.get(dp_id) is None)) and dp_id not in mapping_conflicts:
            if community_reference:
                label = (" · ".join(community_reference.get("reference_labels") or []) or
                         community_reference.get("entity_name") or community_reference.get("name") or f"DPS {dp_id}")
                known = {"semantic_code": str(label).casefold().replace(" ", "_"),
                         "display_name": str(label),
                         "data_type": str(community_reference.get("type") or "unknown"),
                         "unit": community_reference.get("unit"), "scale": community_reference.get("scale"),
                         "confidence": "COMMUNITY_REFERENCE",
                         "source": f"{community_reference.get('repository')} · {community_reference.get('config')}"}
        if dp_id in mapping_conflicts:
            known = None
        # Every semantic row is serialized with a stable shape. Category and
        # community references may omit scaling metadata, but the UI should
        # still be able to render their live raw value safely.
        if isinstance(known, dict):
            known.setdefault("unit", None)
            known.setdefault("scale", None)
            known.setdefault("data_type", "unknown")
            known.setdefault("semantic_code", "unknown")
            known.setdefault("display_name", f"DPS {dp_id}")
            known.setdefault("confidence", "UNKNOWN")
            known.setdefault("source", "")
        # Owner-edited DPS descriptions are presentation metadata scoped to the
        # exact Product ID. They never change semantic routing or write rights.
        custom_overrides = device.get("product_dps_overrides", {})
        custom = custom_overrides.get(str(dp_id)) if isinstance(custom_overrides, dict) else None
        custom_semantic = custom.get("semantic_code") if isinstance(custom, dict) else None
        expected_types = {"switch": {"bool", "boolean"}, "child_lock": {"bool", "boolean"},
                          "countdown": {"integer", "int", "number"},
                          "light_mode": {"enum"}, "relay_status": {"enum"}, "power_on_state": {"enum"}}
        writable_schema_types = {str(entry.get("type", "")).casefold() for entry in device.get("functions", [])
                                 if isinstance(entry, dict) and entry.get("dp_id", entry.get("dpId")) == dp_id}
        custom_switch_writable = bool(isinstance(custom, dict) and custom.get("write_enabled") and
                                      custom_semantic in expected_types and
                                      (bool(writable_schema_types.intersection(expected_types[custom_semantic])) or
                                       (custom_semantic in {"switch", "child_lock"} and isinstance(raw.get(dp_id), bool))))
        if isinstance(custom, dict) and isinstance(custom.get("label"), str) and custom["label"].strip():
            known = {**(known or {}), "display_name": custom["label"].strip()[:80],
                     "confidence": "OWNER_CUSTOM", "source": "Gateway Product ID mapping"}
            if isinstance(custom.get("semantic_code"), str) and custom["semantic_code"]:
                known["semantic_code"] = custom["semantic_code"]
                known["unit"] = custom.get("unit")
                known["data_type"] = custom.get("data_type") or known.get("data_type", "number")
                if isinstance(custom.get("scale"), (int, float)) and not isinstance(custom.get("scale"), bool):
                    known["scale"] = custom["scale"]
        observed.append({"dps_id": dp_id, "semantic_code": known["semantic_code"] if known else "unknown",
                         "display_name": known["display_name"] if known else f"Unknown DPS {dp_id}",
                         "data_type": known["data_type"] if known else "unknown",
                         "unit": known["unit"] if known else None, "scale": known["scale"] if known else None,
                         "confidence": known["confidence"] if known else "UNKNOWN",
                         "source": known["source"] if known else "",
                         "validation_status": "suggestion_only" if known else "unmapped",
                         "function_code": schema_by_id.get(dp_id), "raw_value": raw.get(dp_id),
                         "read_supported": bool(dp_id in raw or schema_by_id.get(dp_id)),
                         "write_supported": custom_switch_writable,
                         "community_reference": community_reference if known and community_reference else None})
    dynamic_entities = []
    if selected_key == "six_channel_hybrid":
        for pair, dp_id in enumerate((113, 114, 115), start=1):
            mode = str(raw.get(dp_id, "")).casefold()
            if mode == "switch":
                dynamic_entities.extend([{"entity_type": "switch", "channel": channel,
                                         "source_dps": [channel]} for channel in (pair * 2 - 1, pair * 2)])
            elif mode == "curtain":
                dynamic_entities.append({"entity_type": "cover", "pair": pair,
                                         "source_dps": [pair * 2 - 1, pair * 2],
                                         "supported_controls": [],
                                         "note": "Cortina detetada; posição e comandos não inferidos."})
    return {"registry_version": REGISTRY_VERSION, "product_id": str(device.get("product_id") or "")[:128],
            "product_name": str(device.get("product_name") or "")[:120], "category": str(device.get("category") or "")[:64],
            "device_kind": str(device.get("device_kind") or "unknown")[:32],
            "channel_count": device.get("channel_count") if isinstance(device.get("channel_count"), int) and not isinstance(device.get("channel_count"), bool) else None,
            "schema_source": str(device.get("schema_source") or "UNKNOWN")[:48],
            "functions": schema, "preset_id": selected_key,
            "preset_label": PRESETS[selected_key]["label"] if selected_key else None,
            "preset_scope": PRESETS[selected_key]["scope"] if selected_key else None,
            "confidence": "CONFIRMED" if selected_key and category == "qccdz" else "OWNER_CONFIRMED" if selected_key else "SUGGESTED" if top and top.get("eligible") else "UNKNOWN",
            "selection_source": "confirmed_category" if category == "qccdz" else "kg_category_and_six_channels" if kg_six_channel_signature and selected_key == "six_channel_hybrid" else "owner_selected" if selected_key else "signature_suggestion" if top and top.get("eligible") else "none",
            "write_authorized": False, "scores": scores, "dps": observed,
            "mapping_conflicts": [{"dps_id": dp_id, "codes": codes} for dp_id, codes in sorted(mapping_conflicts.items())],
            "dynamic_entities": dynamic_entities,
            "raw_dps": {str(key): value for key, value in sorted(raw.items())},
            "source_connector": "TUYA_LAN" if raw else None,
            "trust": "LIVE_UNVERIFIED" if raw else None}


def product_profile(device: dict[str, Any]) -> dict[str, Any]:
    """Return a reusable semantic catalog profile for this exact product schema.

    Tuya's product specification is authoritative for the product ID. Category
    and public preset matches add context only and never replace that schema.
    Raw live values are deliberately omitted from this reusable profile.
    """
    knowledge = analyze_device(device)
    functions = device.get("functions") if isinstance(device.get("functions"), list) else []
    bool_switches = {str(item.get("code")) for item in functions
                     if isinstance(item, dict) and
                     str(item.get("type", "")).casefold() in {"bool", "boolean"} and
                     re.fullmatch(r"switch(?:_[1-9]\d*)?", str(item.get("code", "")), re.IGNORECASE)}
    indexed = {int(match.group(1)) for code in bool_switches
               if (match := re.fullmatch(r"switch_([1-9]\d*)", code, re.IGNORECASE))}
    channel_count = device.get("channel_count")
    if isinstance(channel_count, bool) or not isinstance(channel_count, int) or channel_count < 0:
        channel_count = max(indexed) if indexed else (1 if "switch" in {code.casefold() for code in bool_switches} else len(bool_switches))
    schema_dps = []
    for item in knowledge.get("dps", []):
        if not isinstance(item, dict):
            continue
        schema_dps.append({key: value for key, value in item.items() if key != "raw_value"})
    category = str(device.get("category") or "")[:64]
    return {
        "product_id": str(device.get("product_id") or "")[:128],
        "product_name": str(device.get("product_name") or "")[:120],
        "category": category,
        "device_kind": str(device.get("device_kind") or "unknown")[:32],
        "channel_count": max(0, min(64, channel_count)),
        "registry_version": REGISTRY_VERSION,
        "preset_id": knowledge.get("preset_id"),
        "confidence": knowledge.get("confidence", "UNKNOWN"),
        "selection_source": knowledge.get("selection_source", "none"),
        "schema_source": str(device.get("schema_source") or "UNKNOWN")[:48],
        "dps": schema_dps,
        "functions": _schema_ids(device),
    }

