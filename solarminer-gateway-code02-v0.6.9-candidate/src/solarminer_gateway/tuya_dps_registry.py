"""Scoped, confidence-aware Tuya DP reference data.

DP numbers are product-scoped. Suggestions from this module are descriptive;
they never authorize a write. Commands still require the product schema or an
explicit owner mapping in ``local_dps_map``.
"""
from __future__ import annotations

from typing import Any

REGISTRY_VERSION = 1


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
    available = set(raw)
    available.update(schema.values())
    category = "".join(ch for ch in str(device.get("category") or "").casefold() if ch.isalnum())
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
    if category == "qccdz":
        selected = next((item for item in scores if item["preset_id"] == "qccdz_ev_charger"), None)
    elif explicit_preset in PRESETS and explicit_preset != "qccdz_ev_charger":
        selected = next((item for item in scores if item["preset_id"] == explicit_preset), None)
        if selected is None:
            preset = PRESETS[explicit_preset]
            selected = {"preset_id": explicit_preset, "label": preset["label"], "eligible": True,
                        "score": 0.0, "matched_dps": [], "required_matches": preset["minimum_matches"]}
    else:
        # Matching a DPS signature is only a suggestion. The owner must select
        # a preset (or the category must be a specifically confirmed family)
        # before those semantics become active.
        selected = None
    selected_key = selected["preset_id"] if selected else None
    definitions = PRESETS[selected_key]["definitions"] if selected_key else []
    schema_by_id = {dp_id: code for code, dp_id in schema.items()}
    observed = []
    for dp_id in sorted(available):
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
        if selected_key == "six_channel_hybrid" and dp_id == 13:
            known = {"semantic_code": "master_switch", "display_name": "Master switch",
                     "data_type": "boolean", "unit": None, "scale": None,
                     "confidence": "INFERRED", "source": _OWNER_NOTES}
        if selected_key == "six_channel_hybrid" and dp_id == 14:
            known = {"semantic_code": "unknown", "display_name": "Relay/power-on configuration",
                     "data_type": "unknown", "unit": None, "scale": None,
                     "confidence": "UNKNOWN", "source": _OWNER_NOTES}
        if selected_key == "six_channel_hybrid" and dp_id == 118:
            known = {"semantic_code": "equipment_identifier", "display_name": "Equipment identifier",
                     "data_type": "integer", "unit": None, "scale": None,
                     "confidence": "CONFIRMED", "source": _OWNER_NOTES}
        if selected_key == "six_channel_hybrid" and dp_id in {113, 114, 115}:
            pair = dp_id - 112
            known = {"semantic_code": f"pair_{pair}_mode", "display_name": f"Pair K{pair*2-1}/K{pair*2} mode",
                     "data_type": "enum", "unit": None, "scale": None,
                     "confidence": "CONFIRMED", "source": _OWNER_NOTES}
        if category == "qccdz" and dp_id == 18:
            known = {"semantic_code": "switch", "display_name": "Interruptor do carregador",
                     "data_type": "boolean", "unit": None, "scale": None,
                     "confidence": "CONFIRMED", "source": "Owner-confirmed QCCDZ category mapping"}
        observed.append({"dps_id": dp_id, "semantic_code": known["semantic_code"] if known else "unknown",
                         "display_name": known["display_name"] if known else f"Unknown DPS {dp_id}",
                         "data_type": known["data_type"] if known else "unknown",
                         "unit": known["unit"] if known else None, "scale": known["scale"] if known else None,
                         "confidence": known["confidence"] if known else "UNKNOWN",
                         "source": known["source"] if known else "",
                         "validation_status": "suggestion_only" if known else "unmapped",
                         "function_code": schema_by_id.get(dp_id), "raw_value": raw.get(dp_id),
                         "read_supported": bool(dp_id in raw or schema_by_id.get(dp_id)),
                         "write_supported": False})
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
    return {"registry_version": REGISTRY_VERSION, "preset_id": selected_key,
            "preset_label": PRESETS[selected_key]["label"] if selected_key else None,
            "preset_scope": PRESETS[selected_key]["scope"] if selected_key else None,
            "confidence": "CONFIRMED" if selected_key and category == "qccdz" else "OWNER_CONFIRMED" if selected_key else "SUGGESTED" if top and top.get("eligible") else "UNKNOWN",
            "selection_source": "confirmed_category" if category == "qccdz" else "owner_selected" if selected_key else "signature_suggestion" if top and top.get("eligible") else "none",
            "write_authorized": False, "scores": scores, "dps": observed,
            "dynamic_entities": dynamic_entities,
            "candidate_templates": COMMUNITY_TEMPLATES,
            "raw_dps": {str(key): value for key, value in sorted(raw.items())},
            "source_connector": "TUYA_LAN" if raw else None,
            "trust": "LIVE_UNVERIFIED" if raw else None}

