"""Energy summaries, dispatch planning and conservative control eligibility."""
from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any

from . import energy_registry

ENGINE_CONFIG_KEY = "energy_engine_config"
BATTERY_ESTIMATOR_STATE_KEY = "energy_engine_battery_estimator"
SOLAR_DAY_FORECAST_KEY = "energy_engine_solar_day_forecast"
TUYA_TELEMETRY_KEY = "energy_engine_tuya_telemetry"
DEFAULT_CONFIG: dict[str, Any] = {
    "site_location_name": None, "site_latitude": None, "site_longitude": None,
    "pv_capacity_kw": None, "pv_system_efficiency": 0.85,
    "battery_capacity_kwh": None, "minimum_soc_percent": 20.0, "maximum_soc_percent": 100.0,
    "battery_banks": [], "pv_strings": [], "loads": [],
    "automation": {"enabled": False, "commissioned": False, "surplus_margin_w": 250,
                   "decision_interval_seconds": 300, "deye_map_verified": False},
    "surplus_manager": {"enabled": False, "manual_override": False, "minimum_potential_surplus_w": 800,
                        "battery_reserve_soc_percent": 70, "priority_profile": "tesla_home"},
}
_WEATHER_CACHE: dict[str, Any] = {"key": None, "expires_at": 0.0, "value": None}
_WEATHER_LOCK = threading.Lock()


def _parse_utc(value: Any) -> datetime | None:
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def resolve_site_location(location_name: str) -> dict[str, Any]:
    """Resolve a user-entered city on the Gateway using the fixed Open-Meteo geocoder."""
    if not isinstance(location_name, str) or not 2 <= len(location_name.strip()) <= 120:
        raise ValueError("invalid_site_location_name")
    query = urllib.parse.urlencode({"name": location_name.strip(), "count": 10, "language": "pt", "format": "json"})
    request = urllib.request.Request(
        f"https://geocoding-api.open-meteo.com/v1/search?{query}",
        headers={"Accept": "application/json", "User-Agent": "SolarMiner-Gateway/location"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read(65_537)
        if len(raw) > 65_536:
            raise ValueError("site_location_response_too_large")
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, TimeoutError, urllib.error.URLError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("site_location_lookup_failed") from exc
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise ValueError("site_location_not_found")
    for result in results:
        if not isinstance(result, dict):
            continue
        latitude, longitude = result.get("latitude"), result.get("longitude")
        name, country = result.get("name"), result.get("country")
        if (isinstance(latitude, (int, float)) and not isinstance(latitude, bool)
                and isinstance(longitude, (int, float)) and not isinstance(longitude, bool)
                and math.isfinite(latitude) and math.isfinite(longitude)
                and -90 <= latitude <= 90 and -180 <= longitude <= 180
                and isinstance(name, str) and isinstance(country, str)):
            admin = result.get("admin1")
            label_parts = [name]
            if isinstance(admin, str) and admin and admin.casefold() != name.casefold():
                label_parts.append(admin)
            label_parts.append(country)
            return {"site_location_name": ", ".join(label_parts),
                    "site_latitude": float(latitude), "site_longitude": float(longitude)}
    raise ValueError("site_location_not_found")


def get_config(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT value FROM system_state WHERE key=?", (ENGINE_CONFIG_KEY,)).fetchone()
    if not row:
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        saved = json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        return json.loads(json.dumps(DEFAULT_CONFIG))
    result = {**DEFAULT_CONFIG, **saved}
    result["automation"] = {**DEFAULT_CONFIG["automation"], **(saved.get("automation") or {})}
    result["surplus_manager"] = {**DEFAULT_CONFIG["surplus_manager"], **(saved.get("surplus_manager") or {})}
    return result


def persist_tuya_telemetry(conn: sqlite3.Connection, readings: list[dict[str, Any]],
                           devices: list[dict[str, Any]]) -> int:
    """Keep the latest verified LAN status and recognized SI measurements per Tuya device."""
    row = conn.execute("SELECT value FROM system_state WHERE key=?", (TUYA_TELEMETRY_KEY,)).fetchone()
    try:
        saved = json.loads(row[0]) if row else {}
    except (TypeError, json.JSONDecodeError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    by_id = {item.get("device_id"): item for item in devices if isinstance(item, dict)}
    count = 0
    for reading in readings:
        device_id = reading.get("device_id")
        if not isinstance(device_id, str):
            continue
        previous = saved.get(device_id, {}) if isinstance(saved.get(device_id), dict) else {}
        observed_at = reading.get("observed_at") or datetime.now(timezone.utc).isoformat()
        if isinstance(observed_at, (int, float)) and not isinstance(observed_at, bool):
            try:
                observed_at = datetime.fromtimestamp(float(observed_at), timezone.utc).isoformat()
            except (OverflowError, OSError, ValueError):
                observed_at = datetime.now(timezone.utc).isoformat()
        updated = {**previous, "device_id": device_id, "name": str(reading.get("name") or previous.get("name") or "Tuya")[:120],
                   "connection_state": reading.get("connection_state", "failed"), "last_attempt_at": observed_at}
        if reading.get("connection_state") == "local_responded" and isinstance(reading.get("status"), list) and reading["status"]:
            device = by_id.get(device_id, {})
            specs = [item for item in [*(device.get("functions") or []), *(device.get("status_spec") or [])] if isinstance(item, dict)]
            labels = device.get("capability_labels") if isinstance(device.get("capability_labels"), dict) else {}
            metrics: dict[str, dict[str, Any]] = {}
            raw_status = []
            patterns = {
                "voltage": (r"(^|_)(cur_)?voltage($|_)", r"voltage|tension|tensao"),
                "current": (r"(^|_)(cur_)?current($|_)", r"current|corrente"),
                "power": (r"(^|_)(cur_)?power($|_)", r"power|potencia|watt"),
                "energy": (r"(^|_)(add_ele|total_energy|energy_total|electricity|energy)($|_)", r"energy|energia|electricity|consumo"),
            }
            for item in reading["status"]:
                if not isinstance(item, dict) or not isinstance(item.get("code"), str):
                    continue
                code, value = item["code"], item.get("value")
                raw_status.append({"code": code, "value": value})
                if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                    continue
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(numeric):
                    continue
                spec = next((candidate for candidate in specs if candidate.get("code") == code), {})
                meta = spec.get("values", {})
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except json.JSONDecodeError:
                        meta = {}
                if not isinstance(meta, dict):
                    meta = {}
                text = " ".join((code, str(spec.get("name") or ""), str(labels.get(code) or ""))).casefold()
                for field, (code_pattern, name_pattern) in patterns.items():
                    if not (re.search(code_pattern, code, re.I) or re.search(name_pattern, text, re.I)):
                        continue
                    scale = meta.get("scale", 0)
                    try:
                        numeric /= 10 ** int(scale)
                    except (TypeError, ValueError, OverflowError):
                        continue
                    unit = str(meta.get("unit") or "").strip().casefold()
                    expected = {"voltage": {"v": 1, "volt": 1, "volts": 1, "mv": 0.001},
                                "current": {"a": 1, "amp": 1, "amps": 1, "ma": 0.001},
                                "power": {"w": 1, "watt": 1, "watts": 1, "kw": 1000},
                                "energy": {"kwh": 1, "wh": 0.001}}[field]
                    if unit not in expected:
                        continue
                    numeric *= expected[unit]
                    canonical_unit = {"voltage": "V", "current": "A", "power": "W", "energy": "kWh"}[field]
                    metrics[field] = {"code": code, "value": round(numeric, 6), "unit": canonical_unit,
                                      "observed_at": observed_at, "trust": "LIVE_UNVERIFIED"}
                    count += 1
                    break
            updated.update({"verified": True, "status": raw_status, "metrics": metrics, "observed_at": observed_at})
        elif not previous.get("verified"):
            updated["verified"] = False
        saved[device_id] = updated
    conn.execute("INSERT INTO system_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (TUYA_TELEMETRY_KEY, json.dumps(saved, separators=(",", ":"), ensure_ascii=False)))
    return count


def read_tuya_telemetry(conn: sqlite3.Connection, *, max_age_seconds: int = 120) -> dict[str, dict[str, Any]]:
    row = conn.execute("SELECT value FROM system_state WHERE key=?", (TUYA_TELEMETRY_KEY,)).fetchone()
    try:
        saved = json.loads(row[0]) if row else {}
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(saved, dict):
        return {}
    now = datetime.now(timezone.utc)
    result = {}
    for device_id, item in saved.items():
        if not isinstance(item, dict):
            continue
        stamp = _parse_utc(item.get("observed_at"))
        age = (now - stamp).total_seconds() if stamp else None
        result[device_id] = {**item, "age_seconds": round(age, 1) if age is not None else None,
                             "fresh": bool(item.get("verified") and age is not None and 0 <= age <= max_age_seconds)}
    return result


def save_config(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {"site_location_name", "site_latitude", "site_longitude", "pv_capacity_kw", "pv_system_efficiency",
               "battery_capacity_kwh", "minimum_soc_percent", "maximum_soc_percent", "battery_banks", "pv_strings", "loads", "automation", "surplus_manager"}
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise ValueError("unknown_energy_engine_setting")
    existing = get_config(conn)
    merged = {**existing, **payload}
    location_name = merged.get("site_location_name")
    if location_name is not None and (not isinstance(location_name, str) or not 2 <= len(location_name.strip()) <= 120):
        raise ValueError("invalid_site_location_name")
    latitude, longitude = merged.get("site_latitude"), merged.get("site_longitude")
    if (latitude is None) != (longitude is None):
        raise ValueError("site_coordinates_must_be_set_together")
    if latitude is not None and (isinstance(latitude, bool) or not isinstance(latitude, (int, float))
                                 or not math.isfinite(latitude) or not -90 <= latitude <= 90):
        raise ValueError("invalid_site_latitude")
    if longitude is not None and (isinstance(longitude, bool) or not isinstance(longitude, (int, float))
                                  or not math.isfinite(longitude) or not -180 <= longitude <= 180):
        raise ValueError("invalid_site_longitude")
    pv_capacity = merged.get("pv_capacity_kw")
    if pv_capacity is not None and (isinstance(pv_capacity, bool) or not isinstance(pv_capacity, (int, float))
                                    or not math.isfinite(pv_capacity) or not 0.1 <= pv_capacity <= 1000):
        raise ValueError("invalid_pv_capacity_kw")
    pv_efficiency = merged.get("pv_system_efficiency", 0.85)
    if (isinstance(pv_efficiency, bool) or not isinstance(pv_efficiency, (int, float))
            or not math.isfinite(pv_efficiency) or not 0.5 <= pv_efficiency <= 1.2):
        raise ValueError("invalid_pv_system_efficiency")
    capacity = merged.get("battery_capacity_kwh")
    minimum = merged.get("minimum_soc_percent", 20)
    maximum = merged.get("maximum_soc_percent", 100)
    banks = merged.get("battery_banks", [])
    if not isinstance(banks, list) or len(banks) > 8:
        raise ValueError("invalid_battery_banks")
    normalized_banks = []
    bank_ids: set[str] = set()
    for bank in banks:
        if not isinstance(bank, dict) or set(bank) - {"id", "name", "capacity_kwh", "minimum_soc_percent", "maximum_soc_percent", "soc_source", "active"}:
            raise ValueError("invalid_battery_bank")
        identifier, name = bank.get("id"), bank.get("name")
        bank_capacity = bank.get("capacity_kwh")
        bank_min = bank.get("minimum_soc_percent", minimum)
        bank_max = bank.get("maximum_soc_percent", maximum)
        source = bank.get("soc_source", "deye_aggregate")
        active = bank.get("active", True)
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", identifier) or identifier in bank_ids:
            raise ValueError("invalid_or_duplicate_battery_bank_id")
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError("invalid_battery_bank_name")
        if isinstance(bank_capacity, bool) or not isinstance(bank_capacity, (int, float)) or not math.isfinite(bank_capacity) or not 0.1 <= bank_capacity <= 10000:
            raise ValueError("invalid_battery_bank_capacity_kwh")
        if source != "deye_aggregate":
            raise ValueError("unsupported_battery_soc_source")
        if not isinstance(active, bool):
            raise ValueError("invalid_battery_bank_active")
        if isinstance(bank_min, bool) or not isinstance(bank_min, (int, float)) or not math.isfinite(bank_min) or not 0 <= bank_min < 100:
            raise ValueError("invalid_battery_bank_minimum_soc")
        if isinstance(bank_max, bool) or not isinstance(bank_max, (int, float)) or not math.isfinite(bank_max) or not 0 < bank_max <= 100 or bank_min >= bank_max:
            raise ValueError("invalid_battery_bank_maximum_soc")
        bank_ids.add(identifier)
        normalized_banks.append({"id": identifier, "name": name.strip(), "capacity_kwh": float(bank_capacity),
                                 "minimum_soc_percent": float(bank_min), "maximum_soc_percent": float(bank_max),
                                 "soc_source": source, "active": active})
    if normalized_banks:
        active_capacity = sum(item["capacity_kwh"] for item in normalized_banks if item["active"])
        capacity = round(active_capacity, 3) if active_capacity > 0 else None
    pv_strings = merged.get("pv_strings", [])
    if not isinstance(pv_strings, list) or len(pv_strings) > 64:
        raise ValueError("invalid_pv_strings")
    normalized_pv_strings = []
    pv_string_ids: set[str] = set()
    for pv_string in pv_strings:
        if not isinstance(pv_string, dict) or set(pv_string) - {"id", "name", "manufacturer", "panel_count", "panel_power_w", "mppt", "nominal_power_kw", "active", "tilt_deg", "azimuth_deg"}:
            raise ValueError("invalid_pv_string")
        identifier, name, mppt = pv_string.get("id"), pv_string.get("name"), pv_string.get("mppt")
        nominal = pv_string.get("nominal_power_kw", 0)
        manufacturer = pv_string.get("manufacturer")
        panel_count = pv_string.get("panel_count")
        panel_power_w = pv_string.get("panel_power_w")
        active = pv_string.get("active", True)
        tilt_deg = pv_string.get("tilt_deg")
        azimuth_deg = pv_string.get("azimuth_deg")
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", identifier) or identifier in pv_string_ids:
            raise ValueError("invalid_or_duplicate_pv_string_id")
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError("invalid_pv_string_name")
        if isinstance(mppt, bool) or mppt not in {1, 2}:
            raise ValueError("invalid_pv_string_mppt")
        if isinstance(nominal, bool) or not isinstance(nominal, (int, float)) or not math.isfinite(nominal) or not 0 <= nominal <= 1000:
            raise ValueError("invalid_pv_string_nominal_power")
        has_panel_specs = any(key in pv_string for key in ("manufacturer", "panel_count", "panel_power_w"))
        if has_panel_specs:
            if not isinstance(manufacturer, str) or not manufacturer.strip() or len(manufacturer) > 120:
                raise ValueError("invalid_pv_string_manufacturer")
            if isinstance(panel_count, bool) or not isinstance(panel_count, int) or not 1 <= panel_count <= 2000:
                raise ValueError("invalid_pv_string_panel_count")
            if isinstance(panel_power_w, bool) or not isinstance(panel_power_w, (int, float)) or not math.isfinite(panel_power_w) or not 1 <= panel_power_w <= 2500:
                raise ValueError("invalid_pv_string_panel_power")
            nominal = panel_count * panel_power_w / 1000
            if nominal > 1000:
                raise ValueError("invalid_pv_string_nominal_power")
        if not isinstance(active, bool):
            raise ValueError("invalid_pv_string_active")
        has_orientation = tilt_deg is not None or azimuth_deg is not None
        if has_orientation:
            if (isinstance(tilt_deg, bool) or not isinstance(tilt_deg, (int, float))
                    or not math.isfinite(tilt_deg) or not 0 <= tilt_deg <= 90
                    or isinstance(azimuth_deg, bool) or not isinstance(azimuth_deg, (int, float))
                    or not math.isfinite(azimuth_deg) or not 0 <= azimuth_deg <= 360):
                raise ValueError("invalid_pv_string_orientation")
        pv_string_ids.add(identifier)
        normalized_string = {"id": identifier, "name": name.strip(), "mppt": mppt,
                             "nominal_power_kw": float(nominal), "active": active}
        if has_panel_specs:
            normalized_string.update({"manufacturer": manufacturer.strip(), "panel_count": panel_count,
                                      "panel_power_w": float(panel_power_w)})
        if has_orientation:
            normalized_string.update({"tilt_deg": float(tilt_deg), "azimuth_deg": float(azimuth_deg)})
        normalized_pv_strings.append(normalized_string)
    if capacity is not None and (isinstance(capacity, bool) or not isinstance(capacity, (int, float)) or not math.isfinite(capacity) or not 0.1 <= capacity <= 10000):
        raise ValueError("invalid_battery_capacity_kwh")
    if isinstance(minimum, bool) or not isinstance(minimum, (int, float)) or not math.isfinite(minimum) or not 0 <= minimum < 100:
        raise ValueError("invalid_minimum_soc_percent")
    if isinstance(maximum, bool) or not isinstance(maximum, (int, float)) or not math.isfinite(maximum) or not 0 < maximum <= 100 or minimum >= maximum:
        raise ValueError("invalid_maximum_soc_percent")
    loads = merged.get("loads", [])
    if not isinstance(loads, list) or len(loads) > 64:
        raise ValueError("invalid_flexible_loads")
    normalized_loads = []
    load_ids: set[str] = set()
    kinds = {"miner", "water_heater", "underfloor_heating", "ev_charger", "generic"}
    controls = {"tuya_smart", "tuya_breaker", "antminer_braiins", "tesla_fleet", "manual"}
    for load in loads:
        allowed_load = {"id", "name", "kind", "control_type", "rated_power_w", "minimum_power_w", "maximum_power_w", "manufacturer", "volume_l",
                        "priority", "enabled", "automatic", "tuya_device_id", "tuya_switch_code",
                        "tuya_measurement_codes", "minimum_on_seconds", "minimum_off_seconds", "requires_load_id"}
        if not isinstance(load, dict) or set(load) - allowed_load:
            raise ValueError("invalid_flexible_load")
        identifier, name, kind, control = load.get("id"), load.get("name"), load.get("kind"), load.get("control_type")
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", identifier) or identifier in load_ids:
            raise ValueError("invalid_or_duplicate_load_id")
        if not isinstance(name, str) or not name.strip() or len(name) > 120 or kind not in kinds or control not in controls:
            raise ValueError("invalid_flexible_load_identity")
        def bounded_number(key: str, low: int, high: int, default: int | None = None) -> int:
            value = load.get(key, default)
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise ValueError("invalid_flexible_load_" + key)
            return value
        rated = bounded_number("rated_power_w", 1, 100000)
        manufacturer = load.get("manufacturer", "")
        volume_l = load.get("volume_l", 0)
        if not isinstance(manufacturer, str) or len(manufacturer) > 120:
            raise ValueError("invalid_flexible_load_manufacturer")
        if isinstance(volume_l, bool) or not isinstance(volume_l, int) or not 0 <= volume_l <= 100000:
            raise ValueError("invalid_flexible_load_volume_l")
        minimum_power = bounded_number("minimum_power_w", 0, 100000, 0)
        maximum_power = bounded_number("maximum_power_w", 1, 100000, rated)
        if minimum_power > maximum_power:
            raise ValueError("invalid_flexible_load_power_range")
        if control == "antminer_braiins" and maximum_power > 2900:
            raise ValueError("antminer_maximum_power_exceeds_supported_range")
        priority = bounded_number("priority", 1, 100, 10)
        min_on = bounded_number("minimum_on_seconds", 0, 86400, 300)
        min_off = bounded_number("minimum_off_seconds", 0, 86400, 300)
        enabled = load.get("enabled", True)
        automatic = load.get("automatic", False)
        requires_load_id = load.get("requires_load_id")
        if not isinstance(enabled, bool) or not isinstance(automatic, bool):
            raise ValueError("invalid_flexible_load_flags")
        if requires_load_id is not None and (not isinstance(requires_load_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", requires_load_id)):
            raise ValueError("invalid_flexible_load_dependency")
        device_id, switch_code = load.get("tuya_device_id"), load.get("tuya_switch_code")
        measurement_codes = load.get("tuya_measurement_codes", {})
        if not isinstance(measurement_codes, dict) or set(measurement_codes) - {"voltage", "current", "power", "energy"}:
            raise ValueError("invalid_tuya_measurement_codes")
        measurement_codes = {key: value for key, value in measurement_codes.items()
                             if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value)}
        if len(measurement_codes) != len(load.get("tuya_measurement_codes", {})):
            raise ValueError("invalid_tuya_measurement_code")
        if measurement_codes and control not in {"tuya_smart", "tuya_breaker"}:
            raise ValueError("tuya_measurement_device_required")
        if control in {"tuya_smart", "tuya_breaker"}:
            if not isinstance(device_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", device_id):
                raise ValueError("tuya_device_required_for_load")
            if not isinstance(switch_code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", switch_code):
                raise ValueError("tuya_switch_code_required_for_load")
        elif device_id is not None or switch_code is not None:
            if device_id is not None and (not isinstance(device_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", device_id)):
                raise ValueError("invalid_tuya_device_id_for_load")
            if switch_code is not None and (not isinstance(switch_code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", switch_code)):
                raise ValueError("invalid_tuya_switch_code_for_load")
        load_ids.add(identifier)
        normalized_loads.append({"id": identifier, "name": name.strip(), "kind": kind, "control_type": control,
                                 "manufacturer": manufacturer.strip(), "volume_l": volume_l,
                                 "rated_power_w": rated, "minimum_power_w": minimum_power,
                                 "maximum_power_w": maximum_power, "priority": priority, "enabled": enabled,
                                 "automatic": automatic, "tuya_device_id": device_id, "tuya_switch_code": switch_code,
                                 "tuya_measurement_codes": measurement_codes,
                                 "minimum_on_seconds": min_on, "minimum_off_seconds": min_off,
                                 "requires_load_id": requires_load_id})
    for load in normalized_loads:
        if load["requires_load_id"] is not None:
            dependency = next((item for item in normalized_loads if item["id"] == load["requires_load_id"]), None)
            if (dependency is None or dependency["id"] == load["id"]
                    or dependency["control_type"] not in {"tuya_smart", "tuya_breaker"}
                    or not dependency["enabled"] or not dependency["automatic"]):
                raise ValueError("invalid_flexible_load_dependency")
    automation = merged.get("automation", DEFAULT_CONFIG["automation"])
    if not isinstance(automation, dict) or set(automation) - set(DEFAULT_CONFIG["automation"]):
        raise ValueError("invalid_energy_automation_config")
    normalized_automation = {**DEFAULT_CONFIG["automation"], **automation}
    if any(not isinstance(normalized_automation[key], bool) for key in ("enabled", "commissioned", "deye_map_verified")):
        raise ValueError("invalid_energy_automation_flags")
    margin = normalized_automation.get("surplus_margin_w")
    interval = normalized_automation.get("decision_interval_seconds")
    if isinstance(margin, bool) or not isinstance(margin, int) or not 0 <= margin <= 10000:
        raise ValueError("invalid_surplus_margin_w")
    if isinstance(interval, bool) or not isinstance(interval, int) or not 300 <= interval <= 3600:
        raise ValueError("invalid_decision_interval_seconds")
    normalized_automation["enabled"] = bool(normalized_automation["enabled"] and normalized_automation["commissioned"] and normalized_automation["deye_map_verified"])
    surplus_manager = merged.get("surplus_manager", DEFAULT_CONFIG["surplus_manager"])
    if not isinstance(surplus_manager, dict) or set(surplus_manager) - set(DEFAULT_CONFIG["surplus_manager"]):
        raise ValueError("invalid_surplus_manager_config")
    normalized_surplus_manager = {**DEFAULT_CONFIG["surplus_manager"], **surplus_manager}
    if any(not isinstance(normalized_surplus_manager[key], bool) for key in ("enabled", "manual_override")):
        raise ValueError("invalid_surplus_manager_enabled")
    potential_threshold = normalized_surplus_manager["minimum_potential_surplus_w"]
    reserve_soc = normalized_surplus_manager["battery_reserve_soc_percent"]
    if isinstance(potential_threshold, bool) or not isinstance(potential_threshold, int) or not 0 <= potential_threshold <= 100000:
        raise ValueError("invalid_minimum_potential_surplus_w")
    if isinstance(reserve_soc, bool) or not isinstance(reserve_soc, (int, float)) or not math.isfinite(reserve_soc) or not 0 <= reserve_soc <= 100:
        raise ValueError("invalid_battery_reserve_soc_percent")
    if normalized_surplus_manager["priority_profile"] not in {"tesla_home", "tesla_away"}:
        raise ValueError("invalid_surplus_priority_profile")
    result = {"site_location_name": location_name.strip() if isinstance(location_name, str) else None,
              "site_latitude": float(latitude) if latitude is not None else None,
              "site_longitude": float(longitude) if longitude is not None else None,
              "pv_capacity_kw": float(pv_capacity) if pv_capacity is not None else None,
              "pv_system_efficiency": float(pv_efficiency),
              "battery_capacity_kwh": float(capacity) if capacity is not None else None,
              "minimum_soc_percent": float(minimum), "maximum_soc_percent": float(maximum),
              "battery_banks": normalized_banks, "pv_strings": normalized_pv_strings,
              "loads": normalized_loads, "automation": normalized_automation,
              "surplus_manager": normalized_surplus_manager}
    # Keep the shared parallel-bank SOC stable when the Owner changes the
    # online capacity. The integrated discharge is stored in kWh, so scale it
    # with capacity; otherwise taking one bank offline would distort the
    # aggregate SOC instead of removing that bank's proportional energy share.
    previous_capacity = existing.get("battery_capacity_kwh")
    next_capacity = result["battery_capacity_kwh"]
    if (isinstance(previous_capacity, (int, float)) and previous_capacity > 0
            and isinstance(next_capacity, (int, float)) and next_capacity > 0
            and not math.isclose(float(previous_capacity), float(next_capacity), rel_tol=1e-9)):
        row = conn.execute("SELECT value FROM system_state WHERE key=?", (BATTERY_ESTIMATOR_STATE_KEY,)).fetchone()
        if row:
            try:
                estimator_state = json.loads(row[0])
                integrated = estimator_state.get("integrated_net_discharge_kwh")
                if isinstance(integrated, (int, float)) and math.isfinite(integrated):
                    estimator_state["integrated_net_discharge_kwh"] = round(
                        float(integrated) * float(next_capacity) / float(previous_capacity), 9)
                    conn.execute("UPDATE system_state SET value=? WHERE key=?",
                                 (json.dumps(estimator_state, separators=(",", ":")), BATTERY_ESTIMATOR_STATE_KEY))
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
    conn.execute("INSERT INTO system_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (ENGINE_CONFIG_KEY, json.dumps(result, separators=(",", ":"))))
    if {"site_latitude", "site_longitude", "pv_capacity_kw", "pv_system_efficiency"}.intersection(payload):
        # Recalculate immediately after an Owner updates the solar inputs.
        conn.execute("DELETE FROM system_state WHERE key=?", (SOLAR_DAY_FORECAST_KEY,))
    return result


def _reading_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["field"]: item for item in rows}


def _number(readings: dict[str, dict[str, Any]], field: str) -> float | None:
    value = readings.get(field, {}).get("value")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _solar_position(timestamp: datetime, latitude: float, longitude: float) -> tuple[float, float]:
    """Approximate solar zenith and azimuth (degrees from north, clockwise)."""
    stamp = timestamp.astimezone(timezone.utc)
    day = stamp.timetuple().tm_yday
    hour = stamp.hour + stamp.minute / 60 + stamp.second / 3600
    gamma = 2 * math.pi / 365 * (day - 1 + (hour - 12) / 24)
    equation_minutes = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                                  - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    declination = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
                   - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
                   - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    solar_minutes = hour * 60 + equation_minutes + 4 * longitude
    hour_angle = math.radians(solar_minutes / 4 - 180)
    lat = math.radians(latitude)
    cosine_zenith = max(-1.0, min(1.0, math.sin(lat) * math.sin(declination)
                                  + math.cos(lat) * math.cos(declination) * math.cos(hour_angle)))
    zenith = math.degrees(math.acos(cosine_zenith))
    azimuth = (math.degrees(math.atan2(math.sin(hour_angle),
                                       math.cos(hour_angle) * math.sin(lat)
                                       - math.tan(declination) * math.cos(lat))) + 180) % 360
    return zenith, azimuth


def _plane_of_array_irradiance(point: dict[str, Any], latitude: float, longitude: float,
                               tilt_deg: float, azimuth_deg: float) -> float | None:
    """Estimate tilted-plane irradiance with direct, isotropic diffuse and ground terms."""
    ghi, dni, dhi = (point.get("shortwave_radiation_w_m2"), point.get("direct_normal_irradiance_w_m2"),
                     point.get("diffuse_radiation_w_m2"))
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
           for value in (ghi, dni, dhi)):
        return None
    try:
        stamp = datetime.fromisoformat(str(point["observed_at"]).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError):
        return None
    zenith_deg, sun_azimuth_deg = _solar_position(stamp, latitude, longitude)
    if zenith_deg >= 90:
        return 0.0
    zenith, tilt, sun_azimuth, plane_azimuth = map(math.radians,
                                                   (zenith_deg, tilt_deg, sun_azimuth_deg, azimuth_deg))
    cosine_incidence = (math.cos(zenith) * math.cos(tilt)
                        + math.sin(zenith) * math.sin(tilt) * math.cos(sun_azimuth-plane_azimuth))
    albedo = 0.2
    poa = (float(dni) * max(0.0, cosine_incidence)
           + float(dhi) * (1 + math.cos(tilt)) / 2
           + float(ghi) * albedo * (1 - math.cos(tilt)) / 2)
    return max(0.0, min(2000.0, poa))


def _point_pv_irradiance(point: dict[str, Any], pv_strings: list[dict[str, Any]],
                         latitude: float | None, longitude: float | None) -> tuple[dict[str, float], float]:
    """Return per-MPPT irradiance; strings without geometry use GHI unchanged."""
    ghi = point.get("shortwave_radiation_w_m2")
    fallback = float(ghi) if isinstance(ghi, (int, float)) and not isinstance(ghi, bool) and math.isfinite(ghi) else 0.0
    capacities: dict[int, float] = {1: 0.0, 2: 0.0}
    irradiance_capacity: dict[int, float] = {1: 0.0, 2: 0.0}
    for item in pv_strings:
        try:
            channel = int(item.get("mppt"))
            capacity = float(item.get("nominal_power_kw") or
                             (float(item.get("panel_count", 0)) * float(item.get("panel_power_w", 0)) / 1000))
        except (TypeError, ValueError):
            continue
        if channel not in capacities or capacity <= 0:
            continue
        irradiation = fallback
        tilt, azimuth = item.get("tilt_deg"), item.get("azimuth_deg")
        if (latitude is not None and longitude is not None
                and isinstance(tilt, (int, float)) and not isinstance(tilt, bool)
                and isinstance(azimuth, (int, float)) and not isinstance(azimuth, bool)):
            tilted = _plane_of_array_irradiance(point, float(latitude), float(longitude), float(tilt), float(azimuth))
            if tilted is not None:
                irradiation = tilted
        capacities[channel] += capacity
        irradiance_capacity[channel] += capacity * irradiation
    by_mppt = {channel: (irradiance_capacity[channel] / capacities[channel] if capacities[channel] else fallback)
               for channel in (1, 2)}
    total_capacity = capacities[1] + capacities[2]
    effective = (irradiance_capacity[1] + irradiance_capacity[2]) / total_capacity if total_capacity else fallback
    return {str(channel): round(value, 2) for channel, value in by_mppt.items()}, round(effective, 2)


def _solar_weather(latitude: float | None, longitude: float | None) -> dict[str, Any] | None:
    """Fetch hourly solar radiation through the end of the current day, cached for 10 minutes."""
    if latitude is None or longitude is None:
        return None
    cache_key = f"{latitude:.5f},{longitude:.5f}"
    with _WEATHER_LOCK:
        if _WEATHER_CACHE["key"] == cache_key and _WEATHER_CACHE["expires_at"] > time.monotonic():
            return _WEATHER_CACHE["value"]
        query = urllib.parse.urlencode({
            "latitude": f"{latitude:.5f}", "longitude": f"{longitude:.5f}",
            "hourly": "shortwave_radiation,direct_normal_irradiance,diffuse_radiation,temperature_2m,apparent_temperature,relative_humidity_2m,cloud_cover,wind_speed_10m,weather_code", "past_hours": 4,
            "forecast_hours": 48, "timezone": "auto", "temperature_unit": "celsius", "wind_speed_unit": "kmh",
        })
        request = urllib.request.Request(
            f"https://api.open-meteo.com/v1/forecast?{query}",
            headers={"Accept": "application/json", "User-Agent": "SolarMiner-Gateway/energy-forecast"},
        )
        try:
            with urllib.request.urlopen(request, timeout=4) as response:
                raw = response.read(262_145)
            if len(raw) > 262_144:
                raise ValueError("weather_response_too_large")
            payload = json.loads(raw.decode("utf-8"))
            hourly = payload.get("hourly") if isinstance(payload, dict) else None
            times = hourly.get("time") if isinstance(hourly, dict) else None
            radiation = hourly.get("shortwave_radiation") if isinstance(hourly, dict) else None
            direct_normal = hourly.get("direct_normal_irradiance") if isinstance(hourly, dict) else None
            diffuse = hourly.get("diffuse_radiation") if isinstance(hourly, dict) else None
            temperature = hourly.get("temperature_2m") if isinstance(hourly, dict) else None
            apparent_temperature = hourly.get("apparent_temperature") if isinstance(hourly, dict) else None
            humidity = hourly.get("relative_humidity_2m") if isinstance(hourly, dict) else None
            cloud_cover = hourly.get("cloud_cover") if isinstance(hourly, dict) else None
            wind_speed = hourly.get("wind_speed_10m") if isinstance(hourly, dict) else None
            weather_codes = hourly.get("weather_code") if isinstance(hourly, dict) else None
            if not isinstance(times, list) or not isinstance(radiation, list) or len(times) != len(radiation) or len(times) > 64:
                raise ValueError("weather_response_invalid")
            if temperature is None:
                temperature = [None] * len(times)
            if apparent_temperature is None:
                apparent_temperature = [None] * len(times)
            if humidity is None:
                humidity = [None] * len(times)
            if cloud_cover is None:
                cloud_cover = [None] * len(times)
            if wind_speed is None:
                wind_speed = [None] * len(times)
            if weather_codes is None:
                weather_codes = [None] * len(times)
            for array_name, array_value in (("direct_normal_irradiance", direct_normal), ("diffuse_radiation", diffuse)):
                if array_value is None:
                    if array_name == "direct_normal_irradiance": direct_normal = [None] * len(times)
                    else: diffuse = [None] * len(times)
            optional_arrays = (direct_normal, diffuse, temperature, apparent_temperature, humidity, cloud_cover, wind_speed, weather_codes)
            if any(not isinstance(values, list) or len(values) != len(times) for values in optional_arrays):
                raise ValueError("weather_response_invalid")
            points = []
            for stamp, value, direct, diffuse_value, temp, feels, humidity_value, cloud_value, wind, code in zip(
                    times, radiation, direct_normal, diffuse, temperature, apparent_temperature, humidity, cloud_cover, wind_speed, weather_codes):
                if not isinstance(stamp, str):
                    continue
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 2000):
                    continue
                if direct is not None and (isinstance(direct, bool) or not isinstance(direct, (int, float)) or not math.isfinite(direct) or not 0 <= direct <= 2000):
                    direct = None
                if diffuse_value is not None and (isinstance(diffuse_value, bool) or not isinstance(diffuse_value, (int, float)) or not math.isfinite(diffuse_value) or not 0 <= diffuse_value <= 2000):
                    diffuse_value = None
                if temp is not None and (isinstance(temp, bool) or not isinstance(temp, (int, float)) or not math.isfinite(temp) or not -100 <= temp <= 70):
                    temp = None
                for value_name, optional_value, low, high in (("feels", feels, -100, 70), ("humidity", humidity_value, 0, 100),
                                                               ("cloud", cloud_value, 0, 100), ("wind", wind, 0, 400)):
                    if optional_value is not None and (isinstance(optional_value, bool) or not isinstance(optional_value, (int, float))
                                                       or not math.isfinite(optional_value) or not low <= optional_value <= high):
                        if value_name == "feels": feels = None
                        elif value_name == "humidity": humidity_value = None
                        elif value_name == "cloud": cloud_value = None
                        else: wind = None
                if code is not None and (isinstance(code, bool) or not isinstance(code, int) or not 0 <= code <= 99):
                    code = None
                try:
                    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        try:
                            parsed = parsed.replace(tzinfo=ZoneInfo(payload.get("timezone", "UTC")))
                        except (ZoneInfoNotFoundError, TypeError, ValueError):
                            parsed = parsed.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                points.append({"observed_at": parsed.astimezone(timezone.utc).isoformat(timespec="minutes"),
                               "shortwave_radiation_w_m2": float(value) if value is not None else None,
                               "direct_normal_irradiance_w_m2": float(direct) if direct is not None else None,
                               "diffuse_radiation_w_m2": float(diffuse_value) if diffuse_value is not None else None,
                               "temperature_c": float(temp) if temp is not None else None,
                               "apparent_temperature_c": float(feels) if feels is not None else None,
                               "relative_humidity_percent": humidity_value,
                               "cloud_cover_percent": cloud_value,
                               "wind_speed_kmh": float(wind) if wind is not None else None,
                               "weather_code": code})
            if not points:
                raise ValueError("weather_data_empty")
            result = {"provider": "Open-Meteo", "state": "available", "timezone": payload.get("timezone", "UTC"),
                      "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "hourly": points}
        except (OSError, TimeoutError, urllib.error.URLError, ValueError, UnicodeError, json.JSONDecodeError):
            result = {"provider": "Open-Meteo", "state": "unavailable", "hourly": []}
        _WEATHER_CACHE.update({"key": cache_key, "expires_at": time.monotonic() + 600, "value": result})
        return result


def _learn_solar_performance(conn: sqlite3.Connection, weather: dict[str, Any], inverter: dict[str, Any] | None,
                             battery: dict[str, Any] | None, capacity_kw: float,
                             baseline_efficiency: float, maximum_soc_percent: float,
                             battery_capacity_kwh: float | None = None,
                             mppt_capacity_kw: dict[int, float] | None = None) -> dict[str, Any]:
    """Persist a bounded EMA comparing irradiance with hourly MPPT telemetry."""
    key = "energy_engine_solar_performance"
    row = conn.execute("SELECT value FROM system_state WHERE key=?", (key,)).fetchone()
    try:
        model = json.loads(row[0]) if row else {}
    except (TypeError, json.JSONDecodeError):
        model = {}
    ratio = model.get("performance_ratio", 1.0)
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not math.isfinite(ratio):
        ratio = 1.0
    ratio = max(0.1, min(1.2, float(ratio)))
    processed = set(model.get("processed_hours", [])) if isinstance(model.get("processed_hours"), list) else set()
    profiles = model.get("mppt_voltage_profiles") if isinstance(model.get("mppt_voltage_profiles"), dict) else {}
    candidate_events = model.get("curtailment_candidates") if isinstance(model.get("curtailment_candidates"), list) else []
    performance_samples = model.get("performance_samples") if isinstance(model.get("performance_samples"), list) else []
    mppt_samples = model.get("mppt_performance_samples") if isinstance(model.get("mppt_performance_samples"), dict) else {}
    now_utc = datetime.now(timezone.utc)
    cutoff_utc = now_utc - timedelta(days=30)
    candidate_events = [item for item in candidate_events if isinstance(item, dict)
                        and _parse_utc(item.get("hour")) is not None
                        and _parse_utc(item.get("hour")) >= cutoff_utc][-720:]
    performance_samples = [item for item in performance_samples if isinstance(item, dict)
                           and isinstance(item.get("hour"), str)
                           and isinstance(item.get("ratio"), (int, float))
                           and not isinstance(item.get("ratio"), bool)
                           and math.isfinite(item["ratio"])
                           and isinstance(item.get("weight"), (int, float))
                           and not isinstance(item.get("weight"), bool)
                           and math.isfinite(item["weight"])
                           and item["weight"] > 0
                           and _parse_utc(item["hour"]) is not None
                           and _parse_utc(item["hour"]) >= cutoff_utc]
    accepted = 0
    possible_curtailment = 0
    if inverter:
        for point in weather.get("hourly", []):
            stamp_text = point.get("observed_at")
            try:
                stamp = datetime.fromisoformat(str(stamp_text).replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                stamp = stamp.astimezone(timezone.utc)
            except (TypeError, ValueError):
                continue
            hour_key = stamp.replace(minute=0, second=0, microsecond=0).isoformat(timespec="minutes")
            radiation = point.get("shortwave_radiation_w_m2")
            # Open-Meteo's hourly radiation is the mean for the preceding hour.
            if hour_key in processed or stamp > datetime.now(timezone.utc) - timedelta(minutes=20):
                continue
            if not isinstance(radiation, (int, float)) or isinstance(radiation, bool) or radiation < 120:
                processed.add(hour_key)
                continue
            start = (stamp - timedelta(hours=1)).isoformat(timespec="microseconds")
            finish = stamp.isoformat(timespec="microseconds")
            # Use each MPPT's own power channel so tracking behavior is not
            # hidden inside a total. Voltage/current averages are retained as
            # diagnostics; V×I is not substituted for inverter-reported watts.
            fields = ("pv1_input_power", "pv2_input_power", "pv1_voltage", "pv1_current",
                      "pv2_voltage", "pv2_current")
            channel_values: dict[str, list[float]] = {}
            for field in fields:
                rows = conn.execute("SELECT value_json FROM energy_readings WHERE equipment_id=? AND field=? AND observed_at>? AND observed_at<=? AND trust IN ('LIVE_UNVERIFIED','PHYSICALLY_CORROBORATED')",
                                    (inverter["id"], field, start, finish)).fetchall()
                values: list[float] = []
                for value_row in rows:
                    try:
                        value = json.loads(value_row[0])
                        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                            values.append(float(value))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        continue
                channel_values[field] = values
            cloud_fallback = min(len(channel_values.get(field, [])) for field in fields) < 10
            if not cloud_fallback:
                mppt1_kw = sum(channel_values["pv1_input_power"]) / len(channel_values["pv1_input_power"]) / 1000
                mppt2_kw = sum(channel_values["pv2_input_power"]) / len(channel_values["pv2_input_power"]) / 1000
                actual_kw = mppt1_kw + mppt2_kw
                mppt_sample = {
                    "mppt1_power_kw": round(mppt1_kw, 3), "mppt2_power_kw": round(mppt2_kw, 3),
                    "mppt1_voltage_v": round(sum(channel_values["pv1_voltage"]) / len(channel_values["pv1_voltage"]), 2),
                    "mppt1_current_a": round(sum(channel_values["pv1_current"]) / len(channel_values["pv1_current"]), 2),
                    "mppt2_voltage_v": round(sum(channel_values["pv2_voltage"]) / len(channel_values["pv2_voltage"]), 2),
                    "mppt2_current_a": round(sum(channel_values["pv2_current"]) / len(channel_values["pv2_current"]), 2),
                }
            else:
                # Deye Cloud history contains total PV and household load but
                # not per-MPPT voltage/current. It can support a lower-confidence
                # curtailment candidate when battery evidence independently
                # confirms a full, nearly idle battery.
                cloud_values: dict[str, list[float]] = {"pv_total_power": [], "load_total_power": []}
                for cloud_field in cloud_values:
                    rows = conn.execute("SELECT value_json FROM energy_readings WHERE equipment_id=? AND field=? AND observed_at>? AND observed_at<=? AND source='DEYE_CLOUD_HISTORY'",
                                        (inverter["id"], cloud_field, start, finish)).fetchall()
                    for value_row in rows:
                        try:
                            value = json.loads(value_row[0])
                            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                                cloud_values[cloud_field].append(float(value))
                        except (TypeError, ValueError, json.JSONDecodeError):
                            continue
                if not cloud_values["pv_total_power"]:
                    continue
                cloud_evidence_sufficient = min(len(cloud_values["pv_total_power"]),
                                                len(cloud_values["load_total_power"])) >= 2
                actual_kw = sum(cloud_values["pv_total_power"]) / len(cloud_values["pv_total_power"]) / 1000
                mppt1_kw, mppt2_kw = actual_kw, 0.0
                mppt_sample = {"mppt1_power_kw": round(actual_kw, 3), "mppt2_power_kw": None,
                               "mppt1_voltage_v": None, "mppt1_current_a": None,
                               "mppt2_voltage_v": None, "mppt2_current_a": None,
                               "measurement_source": "DEYE_CLOUD_HISTORY"}
            irradiance_by_mppt = point.get("pv_irradiance_by_mppt_w_m2")
            effective_irradiance = point.get("pv_effective_irradiance_w_m2", radiation)
            if isinstance(irradiance_by_mppt, dict) and mppt_capacity_kw:
                potential_kw = sum(float(mppt_capacity_kw.get(channel, 0.0))
                                   * float(irradiance_by_mppt.get(str(channel), radiation))
                                   / 1000 * baseline_efficiency for channel in (1, 2))
            else:
                potential_kw = capacity_kw * float(radiation) / 1000 * baseline_efficiency
            if potential_kw < 0.2:
                processed.add(hour_key)
                continue
            observed_ratio = max(0.1, min(1.2, actual_kw / potential_kw))
            def hourly_average(equipment: dict[str, Any] | None, field: str, minimum: int = 10) -> float | None:
                if not equipment:
                    return None
                context_rows = conn.execute("SELECT value_json FROM energy_readings WHERE equipment_id=? AND field=? AND observed_at>? AND observed_at<=? AND trust IN ('LIVE_UNVERIFIED','PHYSICALLY_CORROBORATED')",
                                            (equipment["id"], field, start, finish)).fetchall()
                context_values = []
                for context_row in context_rows:
                    try:
                        context_value = json.loads(context_row[0])
                        if isinstance(context_value, (int, float)) and not isinstance(context_value, bool) and math.isfinite(context_value):
                            context_values.append(float(context_value))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        continue
                return sum(context_values) / len(context_values) if len(context_values) >= minimum else None
            historical_soc = None
            if battery and battery_capacity_kwh:
                battery_since = (stamp - timedelta(days=30)).isoformat(timespec="microseconds")
                historical_voltage = _series(conn, [battery["id"]], "battery_voltage", battery_since, limit=50000, until=finish)
                historical_power = _series(conn, [battery["id"]], "battery_output_power", battery_since, limit=50000, until=finish)
                historical_soc, _ = _estimate_battery_soc(historical_voltage, historical_power,
                                                          battery_capacity_kwh, 0.0, maximum_soc_percent,
                                                          as_of=stamp)
            # Historical battery fullness is inferred from the Gateway's
            # voltage/charge-power anchor and integrated energy only. Do not
            # use the Deye percentage register as a substitute.
            historical_charge_w = hourly_average(battery, "battery_charge_power", 2 if cloud_fallback else 10)
            historical_load_w = (sum(cloud_values["load_total_power"]) / len(cloud_values["load_total_power"])
                                 if cloud_fallback and cloud_values["load_total_power"] else
                                 hourly_average(inverter, "load_total_power", 1 if cloud_fallback else 10))
            irradiance_bin = str(min(10, max(0, int(float(effective_irradiance) // 100))))
            profile = profiles.get(irradiance_bin, {}) if isinstance(profiles.get(irradiance_bin), dict) else {}
            voltage_support = False
            voltage_profile_available = False
            for channel in ("mppt1", "mppt2"):
                baseline_voltage = profile.get(f"{channel}_voltage_v")
                baseline_current = profile.get(f"{channel}_current_a")
                observed_voltage = mppt_sample[f"{channel}_voltage_v"]
                observed_current = mppt_sample[f"{channel}_current_a"]
                if (isinstance(baseline_voltage, (int, float)) and isinstance(baseline_current, (int, float))
                        and profile.get("samples", 0) >= 2 and baseline_voltage > 0 and baseline_current >= 0.5):
                    voltage_profile_available = True
                    # A sustained rise from this channel's learned voltage,
                    # paired with a current collapse, is a voltage signature
                    # consistent with the inverter moving away from MPP.
                    if observed_voltage >= baseline_voltage * 1.025 and observed_current <= baseline_current * 0.70:
                        voltage_support = True
            # In an off-grid installation, high modeled potential plus low PV
            # output while the battery is full and household demand is low is
            # evidence of possible inverter curtailment. Keep it as a separate
            # label and do not train panel performance downward from it.
            # Load greater than measured PV alone is ambiguous: in an off-grid
            # system it can be the only available sink while a full battery
            # prevents surplus storage. Suppress curtailment only when demand
            # could plausibly absorb nearly the entire weather potential.
            demand_supported = (historical_load_w is not None and historical_load_w >= potential_kw * 1000 * 0.90)
            curtailed = ((not cloud_fallback or cloud_evidence_sufficient)
                         and not demand_supported and observed_ratio < 0.70 and historical_soc is not None
                         and historical_soc >= maximum_soc_percent - 2
                         and historical_charge_w is not None and historical_charge_w <= 20
                         and historical_load_w is not None)
            if curtailed:
                event = {
                    "hour": hour_key, "observed_performance_ratio": round(observed_ratio, 4),
                    "weather_potential_kw": round(potential_kw, 3), "measured_mppt_power_kw": round(actual_kw, 3),
                    "battery_soc_percent": round(historical_soc, 2), "battery_charge_power_w": round(historical_charge_w, 1),
                    "house_load_power_w": round(historical_load_w, 1), **mppt_sample,
                    "evidence_source": "WEATHER_AND_DEYE_CLOUD_WITH_BATTERY_HISTORY" if cloud_fallback else "WEATHER_AND_LOCAL_MPPT_AND_BATTERY",
                    "confidence": "LOW_CONTEXT_ONLY" if cloud_fallback and not voltage_support else "MEDIUM_VOLTAGE_SUPPORTED" if voltage_support else "MEDIUM_CONTEXT",
                    "mppt_voltage_support": voltage_support if voltage_profile_available else None,
                    "state": "POSSIBLE_CURTAILMENT_VOLTAGE_SUPPORTED" if voltage_support else "POSSIBLE_CURTAILMENT_CONTEXT_ONLY",
                }
                candidate_events = [item for item in candidate_events if item.get("hour") != hour_key]
                candidate_events.append(event)
                candidate_events = candidate_events[-720:]
                model["last_curtailment_candidate"] = event
                model["curtailment_candidates"] = candidate_events
                for channel in ("mppt1", "mppt2"):
                    supported_voltages = [item.get(f"{channel}_voltage_v") for item in candidate_events
                                          if item.get("mppt_voltage_support") is True
                                          and isinstance(item.get(f"{channel}_voltage_v"), (int, float))]
                    if supported_voltages:
                        model.setdefault("mppt_empirical_curtailment_voltage_v", {})[channel] = round(
                            sum(supported_voltages) / len(supported_voltages), 2)
                model["possible_curtailment_hours"] = int(model.get("possible_curtailment_hours", 0)) + 1
                processed.add(hour_key)
                possible_curtailment += 1
                continue
            # House demand at or above PV output is evidence that the observed
            # generation was not being held back by lack of a sink. Give such
            # samples more influence, while robustly limiting single-hour spikes.
            if demand_supported:
                interpretation, sample_weight = "DEMAND_SUPPORTED_NORMAL_REFERENCE", 3.0
            elif observed_ratio >= 0.70:
                interpretation, sample_weight = "OUTPUT_WITHIN_EXPECTED_RANGE", 1.0
            else:
                interpretation, sample_weight = "LOW_OUTPUT_UNEXPLAINED_LOW_WEIGHT", 0.35
            load_sample = {"hour": hour_key, "ratio": round(observed_ratio, 4),
                           "weight": sample_weight, "classification": interpretation,
                           "measured_kw": round(actual_kw, 3), "weather_potential_kw": round(potential_kw, 3),
                           "house_load_w": round(historical_load_w, 1) if historical_load_w is not None else None,
                           "irradiance_w_m2": round(float(radiation), 1)}
            performance_samples = [item for item in performance_samples if item.get("hour") != hour_key]
            performance_samples.append(load_sample)
            performance_samples = performance_samples[-720:]
            weighted_ratios: list[tuple[float, float]] = []
            for item in performance_samples:
                sample_stamp = _parse_utc(item["hour"])
                if sample_stamp is None:
                    continue
                age_days = max(0.0, (now_utc - sample_stamp).total_seconds() / 86400)
                recency_weight = math.exp(-age_days / 10.0)
                weighted_ratios.append((max(0.1, min(1.2, float(item["ratio"]))),
                                        float(item["weight"]) * recency_weight))
            weighted_ratios.sort(key=lambda item: item[0])
            weight_total = sum(weight for _, weight in weighted_ratios)
            cumulative = 0.0
            weighted_median = observed_ratio
            for sample_ratio, sample_weight_value in weighted_ratios:
                cumulative += sample_weight_value
                if cumulative >= weight_total / 2:
                    weighted_median = sample_ratio
                    break
            ratio = max(0.1, min(1.2, ratio * 0.35 + weighted_median * 0.65))
            model["performance_samples"] = performance_samples
            model["sample_count"] = int(model.get("sample_count", 0)) + 1
            model["demand_supported_samples"] = sum(1 for item in performance_samples
                                                     if item.get("classification") == "DEMAND_SUPPORTED_NORMAL_REFERENCE")
            model["weighted_reference_ratio"] = round(weighted_median, 4)
            model["last_sample_at"] = hour_key
            model["last_mppt_sample"] = {
                **mppt_sample,
                "measured_total_kw": round(actual_kw, 3), "weather_potential_kw": round(potential_kw, 3),
                "observed_performance_ratio": round(observed_ratio, 4),
                "house_load_power_w": round(historical_load_w, 1) if historical_load_w is not None else None,
                "interpretation": interpretation,
            }
            for channel, power_kw in (() if cloud_fallback else ((1, mppt1_kw), (2, mppt2_kw))):
                channel_capacity = float((mppt_capacity_kw or {}).get(channel, 0.0) or 0.0)
                channel_irradiance = (irradiance_by_mppt.get(str(channel), radiation)
                                      if isinstance(irradiance_by_mppt, dict) else radiation)
                channel_potential = channel_capacity * float(channel_irradiance) / 1000 * baseline_efficiency
                if channel_capacity <= 0 or channel_potential < 0.1:
                    continue
                channel_rows = mppt_samples.get(str(channel), [])
                if not isinstance(channel_rows, list):
                    channel_rows = []
                channel_rows = [item for item in channel_rows if isinstance(item, dict)
                                and _parse_utc(item.get("hour")) is not None
                                and _parse_utc(item.get("hour")) >= cutoff_utc]
                channel_rows = [item for item in channel_rows if item.get("hour") != hour_key]
                channel_rows.append({"hour": hour_key,
                                     "ratio": round(max(0.1, min(1.2, power_kw / channel_potential)), 4),
                                     "weight": sample_weight, "classification": interpretation})
                mppt_samples[str(channel)] = channel_rows[-720:]
            model["mppt_performance_samples"] = mppt_samples
            if (observed_ratio >= 0.70 or demand_supported) and not cloud_fallback:
                previous = profiles.get(irradiance_bin, {}) if isinstance(profiles.get(irradiance_bin), dict) else {}
                samples = int(previous.get("samples", 0)) if isinstance(previous.get("samples", 0), int) else 0
                alpha = 1.0 if samples == 0 else 0.2
                profiles[irradiance_bin] = {
                    "samples": samples + 1,
                    **{f"{channel}_{metric}": round((1-alpha)*float(previous.get(f"{channel}_{metric}", mppt_sample[f"{channel}_{metric}"])) + alpha*mppt_sample[f"{channel}_{metric}"], 3)
                       for channel in ("mppt1", "mppt2") for metric in ("voltage_v", "current_a")},
                }
                model["mppt_voltage_profiles"] = profiles
                operating_voltage = model.setdefault("mppt_lowest_observed_operating_voltage_v", {})
                for channel in ("mppt1", "mppt2"):
                    voltage = mppt_sample[f"{channel}_voltage_v"]
                    current = mppt_sample[f"{channel}_current_a"]
                    power = mppt_sample[f"{channel}_power_kw"]
                    if current >= 0.5 and power >= 0.1:
                        prior_min = operating_voltage.get(channel)
                        operating_voltage[channel] = round(min(float(prior_min), voltage) if isinstance(prior_min, (int, float)) else voltage, 2)
            model["last_mppt_voltage_analysis"] = {
                "irradiance_bin_w_m2": irradiance_bin, "reference_samples": profile.get("samples", 0),
                "voltage_signature_supported": voltage_support if voltage_profile_available else None,
                "classification": "EMPIRICAL_ESTIMATE_NOT_MANUFACTURER_CUTOFF",
            }
            processed.add(hour_key)
            accepted += 1
    model.update({"performance_ratio": round(ratio, 4), "processed_hours": sorted(processed)[-720:],
                  "baseline_efficiency": baseline_efficiency, "capacity_kw": capacity_kw})
    mppt_reference_ratios = {}
    for channel, rows in mppt_samples.items():
        weighted = []
        for item in rows:
            stamp = _parse_utc(item.get("hour"))
            if stamp is None:
                continue
            weight = float(item.get("weight", 1.0)) * math.exp(-max(0.0, (now_utc-stamp).total_seconds()/86400) / 10.0)
            weighted.append((float(item.get("ratio", 1.0)), weight))
        weighted.sort(key=lambda item: item[0])
        threshold = sum(weight for _, weight in weighted) / 2 if weighted else 0
        rolling = 0.0
        for value, weight in weighted:
            rolling += weight
            if rolling >= threshold:
                mppt_reference_ratios[channel] = round(value, 4)
                break
    if accepted > 0 and mppt_reference_ratios and mppt_capacity_kw:
        available_capacity = [(float(mppt_capacity_kw.get(int(channel), 0)), value)
                              for channel, value in mppt_reference_ratios.items()]
        available_capacity = [(weight, value) for weight, value in available_capacity if weight > 0]
        if available_capacity:
            mppt_weighted_reference = sum(weight * value for weight, value in available_capacity) / sum(weight for weight, _ in available_capacity)
            ratio = max(0.1, min(1.2, ratio * 0.35 + mppt_weighted_reference * 0.65))
            model["performance_ratio"] = round(ratio, 4)
    conn.execute("INSERT INTO system_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, json.dumps(model, separators=(",", ":"))))
    return {"performance_ratio": ratio, "sample_count": int(model.get("sample_count", 0)),
            "weighted_reference_ratio": model.get("weighted_reference_ratio"),
            "demand_supported_samples": int(model.get("demand_supported_samples", 0)),
            "performance_samples_30d": len(performance_samples),
            "recent_performance_observations": performance_samples[-24:],
            "mppt_capacity_kw": {str(channel): round(float(value), 3)
                                 for channel, value in (mppt_capacity_kw or {}).items()},
            "mppt_weighted_reference_ratios": mppt_reference_ratios,
            "last_sample_at": model.get("last_sample_at"), "new_samples": accepted,
            "possible_curtailment_hours": int(model.get("possible_curtailment_hours", 0)),
            "possible_curtailment_hours_30d": len(candidate_events),
            "new_curtailment_candidates": possible_curtailment,
            "last_curtailment_candidate": model.get("last_curtailment_candidate"),
            "mppt_voltage_profiles": profiles,
            "mppt_empirical_curtailment_voltage_v": model.get("mppt_empirical_curtailment_voltage_v", {}),
            "mppt_lowest_observed_operating_voltage_v": model.get("mppt_lowest_observed_operating_voltage_v", {}),
            "recent_curtailment_candidates": candidate_events[-24:],
            "curtailment_events_30d": candidate_events[-720:]}


def _series(conn: sqlite3.Connection, equipment_ids: list[str], field: str, since: str, limit: int = 3000,
            until: str | None = None) -> list[dict[str, Any]]:
    if not equipment_ids:
        return []
    marks = ",".join("?" for _ in equipment_ids)
    end_clause = " AND observed_at<=?" if until is not None else ""
    params = (*equipment_ids, field, since, until, limit) if until is not None else (*equipment_ids, field, since, limit)
    rows = conn.execute(f"SELECT value_json,unit,observed_at,source,trust FROM energy_readings WHERE equipment_id IN ({marks}) AND field=? AND observed_at>=?{end_clause} ORDER BY observed_at DESC LIMIT ?",
                        params).fetchall()
    return [{"value": json.loads(r[0]), "unit": r[1], "observed_at": r[2], "source": r[3], "trust": r[4]}
            for r in reversed(rows)]


def _integrate_power_kwh(points: list[dict[str, Any]], *, until: datetime,
                         maximum_gap_seconds: int = 600) -> dict[str, Any]:
    """Integrate measured PV power without filling long gaps or importing cloud history."""
    samples: list[tuple[datetime, float]] = []
    for point in points:
        if not isinstance(point, dict) or _is_cloud_history(point):
            continue
        try:
            stamp = datetime.fromisoformat(str(point["observed_at"]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            value = float(point["value"])
            unit = str(point.get("unit") or "W").casefold()
            watts = value * 1000 if unit == "kw" else value
            if math.isfinite(watts) and watts >= 0:
                samples.append((stamp.astimezone(timezone.utc), watts))
        except (KeyError, TypeError, ValueError):
            continue
    samples = sorted({stamp: watts for stamp, watts in samples}.items())
    total_kwh = 0.0
    gaps = 0
    integrated_intervals = 0
    for (t0, p0), (t1, p1) in zip(samples, samples[1:]):
        end = min(t1, until.astimezone(timezone.utc))
        seconds = (end - t0).total_seconds()
        if seconds <= 0:
            continue
        if seconds > maximum_gap_seconds:
            gaps += 1
            continue
        if end != t1:
            ratio = seconds / (t1 - t0).total_seconds()
            p1 = p0 + (p1-p0)*ratio
        total_kwh += ((p0+p1)/2) * seconds / 3_600_000
        integrated_intervals += 1
    return {"energy_kwh": round(total_kwh, 4), "first_sample_at": samples[0][0].isoformat() if samples else None,
            "last_sample_at": samples[-1][0].isoformat() if samples else None,
            "sample_count": len(samples), "integrated_intervals": integrated_intervals, "gaps_over_limit": gaps}


def _ensure_solar_forecast_history(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS energy_solar_day_forecasts (
        local_date TEXT NOT NULL, calculated_at TEXT NOT NULL,
        estimated_total_kwh REAL NOT NULL, actual_today_kwh REAL NOT NULL,
        remaining_estimate_kwh REAL NOT NULL, confidence TEXT NOT NULL,
        potential_max_total_kwh REAL,
        PRIMARY KEY(local_date, calculated_at))""")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(energy_solar_day_forecasts)")}
    if "potential_max_total_kwh" not in columns:
        conn.execute("ALTER TABLE energy_solar_day_forecasts ADD COLUMN potential_max_total_kwh REAL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_solar_day_forecasts_time ON energy_solar_day_forecasts(calculated_at)")


def _merge_single_cloud_device_history(conn: sqlite3.Connection) -> None:
    """Attach a lone Deye Cloud backfill to the sole configured Modbus Deye.

    Older imports made a station-derived equipment ID when LAN credentials were
    absent. When there is exactly one Deye in each category, those rows are the
    same installation's history and must participate in the Gateway's series.
    Ambiguous multi-inverter setups are left untouched.
    """
    for category in ("inversores", "baterias"):
        cloud = [row[0] for row in conn.execute(
            "SELECT id FROM energy_equipment WHERE category=? AND protocol='Deye Cloud OpenAPI'", (category,))]
        local = [row[0] for row in conn.execute(
            "SELECT id FROM energy_equipment WHERE category=? AND protocol='Modbus TCP FC03'", (category,))]
        if len(cloud) != 1 or len(local) != 1:
            continue
        cloud_id, local_id = cloud[0], local[0]
        if conn.execute("SELECT 1 FROM energy_readings WHERE equipment_id=? LIMIT 1", (cloud_id,)).fetchone() is None:
            continue
        conn.execute("""DELETE FROM energy_readings AS archived WHERE archived.equipment_id=? AND EXISTS(
            SELECT 1 FROM energy_readings AS canonical WHERE canonical.equipment_id=?
              AND canonical.field=archived.field AND canonical.observed_at=archived.observed_at
              AND canonical.source=archived.source)""", (cloud_id, local_id))
        conn.execute("UPDATE energy_readings SET equipment_id=? WHERE equipment_id=?", (local_id, cloud_id))


def _dedupe_time_series(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_stamp: dict[str, dict[str, Any]] = {}
    for point in points:
        stamp = point.get("observed_at")
        value = point.get("value")
        if (isinstance(stamp, str) and isinstance(value, (int, float))
                and not isinstance(value, bool) and math.isfinite(value)):
            by_stamp[stamp] = point
    return [by_stamp[key] for key in sorted(by_stamp)]


def _is_cloud_history(point: dict[str, Any]) -> bool:
    return str(point.get("source", "")).upper() == "DEYE_CLOUD_HISTORY"


def _apply_observed_potential_floor(potential_points: list[dict[str, Any]],
                                    measured_pv: list[dict[str, Any]],
                                    adjustment_factor: float) -> list[dict[str, Any]]:
    """Apply today's learned potential adjustment and never understate measured PV.

    Weather points represent hourly power. Cloud-imported history remains useful
    for historical profiles, but is not treated as a live observation here.
    """
    measured_by_hour: dict[int, float] = {}
    for item in measured_pv:
        if _is_cloud_history(item):
            continue
        try:
            stamp = datetime.fromisoformat(str(item["observed_at"]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            value = float(item["value"])
            if math.isfinite(value) and value >= 0:
                hour_key = int(stamp.timestamp() // 3600)
                measured_by_hour[hour_key] = max(measured_by_hour.get(hour_key, 0.0),
                                                  value / 1000 if item.get("unit") == "W" else value)
        except (KeyError, TypeError, ValueError):
            continue
    factor = max(0.0, min(1.5, float(adjustment_factor)))
    result = []
    for point in potential_points:
        value = float(point["value"])
        stamp = datetime.fromisoformat(str(point["observed_at"]).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        if point.get("segment") == "forecast":
            value *= factor
        observed_floor = measured_by_hour.get(int(stamp.timestamp() // 3600), 0.0)
        result.append({**point, "value": round(max(value, observed_floor), 3)})
    return result


def _estimate_battery_autonomy(available_kwh: float | None, current_load_w: float | None,
                               history: list[dict[str, Any]], as_of: datetime | None = None) -> dict[str, Any]:
    """Project time to configured battery reserve with no solar contribution.

    The historical profile uses same-hour daily means over seven days, weighted
    toward recent days. A recent live load is blended into the current hour and
    gradually loses influence over the next few hours, so time away from home
    does not make an empty historical hour look like a reliable zero-load hour.
    """
    now = as_of or datetime.now().astimezone()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc).astimezone()
    if available_kwh is None or not math.isfinite(float(available_kwh)) or available_kwh < 0:
        return {"state": "UNAVAILABLE", "hours": None, "estimated_cutoff_at": None,
                "confidence": "LOW", "reason": "battery_energy_unavailable"}

    seven_days_ago = now - timedelta(days=7)
    per_day_hour: dict[tuple[str, int], list[float]] = {}
    recent: list[tuple[datetime, float]] = []
    valid_count = 0
    for point in history:
        value = point.get("value")
        stamp = point.get("observed_at")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            continue
        try:
            observed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            observed = observed.astimezone(now.tzinfo)
        except (TypeError, ValueError):
            continue
        if observed < seven_days_ago or observed > now + timedelta(minutes=2) or value < 0:
            continue
        valid_count += 1
        if not _is_cloud_history(point):
            recent.append((observed, float(value)))
        # Exclude the current local day from the baseline; current readings are
        # blended separately and must not be double-counted in its hourly mean.
        if observed.date() < now.date():
            per_day_hour.setdefault((observed.date().isoformat(), observed.hour), []).append(float(value))

    hourly: dict[int, float] = {}
    day_dates = sorted({day for day, _hour in per_day_hour})
    for hour in range(24):
        weighted_sum = 0.0
        total_weight = 0.0
        for day in day_dates:
            values = per_day_hour.get((day, hour))
            if not values:
                continue
            day_stamp = datetime.fromisoformat(day).replace(tzinfo=now.tzinfo)
            age_days = max(0.0, (now - day_stamp).total_seconds() / 86400)
            weight = math.exp(-age_days / 3.0)
            weighted_sum += (sum(values) / len(values)) * weight
            total_weight += weight
        if total_weight:
            hourly[hour] = weighted_sum / total_weight

    recent_cutoff = now - timedelta(minutes=15)
    recent_values = [value for stamp, value in recent if stamp >= recent_cutoff]
    live_w = (sum(recent_values) / len(recent_values)) if recent_values else (
        float(current_load_w) if isinstance(current_load_w, (int, float)) and math.isfinite(current_load_w) and current_load_w >= 0 else None)
    baseline = hourly.get(now.hour)
    if live_w is not None and baseline is not None:
        blended_current = 0.7 * live_w + 0.3 * baseline
    else:
        blended_current = live_w if live_w is not None else baseline

    if available_kwh == 0:
        return {"state": "ESTIMATED", "hours": 0.0, "estimated_cutoff_at": now.isoformat(timespec="minutes"),
                "confidence": "LOW" if valid_count < 24 else "MEDIUM", "history_days_used": len(day_dates),
                "live_load_w": round(live_w, 1) if live_w is not None else None,
                "method": "seven_day_hourly_weighted_plus_current_no_solar"}
    if blended_current is None or blended_current <= 0:
        return {"state": "UNAVAILABLE", "hours": None, "estimated_cutoff_at": None,
                "confidence": "LOW", "reason": "no_positive_load_profile",
                "history_days_used": len(day_dates), "live_load_w": round(live_w, 1) if live_w is not None else None,
                "method": "seven_day_hourly_weighted_plus_current_no_solar"}

    remaining = float(available_kwh)
    elapsed = 0.0
    step_h = 0.25
    for step in range(24 * 7 * 4):
        offset = elapsed
        hour = int((now + timedelta(hours=offset)).hour)
        hist_load = hourly.get(hour)
        if offset < 1.0:
            load_w = blended_current
        elif hist_load is not None and live_w is not None:
            # Current occupancy fades over six hours; history then drives the
            # diurnal pattern. Missing historical hours retain a cautious live estimate.
            influence = max(0.0, 1.0 - (offset - 1.0) / 6.0)
            load_w = hist_load * (1.0 - 0.45 * influence) + live_w * (0.45 * influence)
        else:
            load_w = hist_load if hist_load is not None else blended_current
        load_w = max(30.0, float(load_w))  # avoid zero-load hours implying infinite runtime
        energy = load_w * step_h / 1000.0
        if remaining <= energy:
            elapsed += max(0.0, remaining / energy) * step_h
            cutoff = now + timedelta(hours=elapsed)
            confidence = "HIGH" if len(day_dates) >= 5 and valid_count >= 500 else "MEDIUM" if len(day_dates) >= 2 else "LOW"
            return {"state": "ESTIMATED", "hours": round(elapsed, 2),
                    "estimated_cutoff_at": cutoff.isoformat(timespec="minutes"), "confidence": confidence,
                    "history_days_used": len(day_dates), "live_load_w": round(live_w, 1) if live_w is not None else None,
                    "method": "seven_day_hourly_weighted_plus_current_no_solar"}
        remaining -= energy
        elapsed += step_h
    return {"state": "BEYOND_HORIZON", "hours": round(elapsed, 1), "estimated_cutoff_at": None,
            "confidence": "LOW", "history_days_used": len(day_dates),
            "live_load_w": round(live_w, 1) if live_w is not None else None,
            "method": "seven_day_hourly_weighted_plus_current_no_solar"}


def _estimate_remaining_load_to_day_end(history: list[dict[str, Any]], current_load_w: float | None,
                                        timezone_name: str | None = None,
                                        as_of: datetime | None = None) -> dict[str, Any]:
    """Estimate remaining house energy from recent same-hour samples plus live load.

    This is an outlook, not a promise of solar surplus: it uses the local-time
    hourly load profile from the last seven days and gives the latest 15 minutes
    and current reading extra weight in the unfinished hour.
    """
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    try:
        site_tz = ZoneInfo(timezone_name) if isinstance(timezone_name, str) else datetime.now().astimezone().tzinfo
    except (ZoneInfoNotFoundError, ValueError):
        site_tz = datetime.now().astimezone().tzinfo or timezone.utc
    local_now = now.astimezone(site_tz)
    per_day_hour: dict[tuple[str, int], list[float]] = {}
    today_by_hour: dict[int, list[float]] = {}
    recent: list[tuple[datetime, float]] = []
    cutoff = now - timedelta(days=7)
    for point in history:
        value, stamp = point.get("value"), point.get("observed_at")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            continue
        try:
            observed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            observed = observed.astimezone(site_tz)
        except (TypeError, ValueError):
            continue
        if observed < cutoff.astimezone(site_tz) or observed > local_now + timedelta(minutes=2):
            continue
        if not _is_cloud_history(point):
            recent.append((observed, float(value)))
        if observed.date() < local_now.date():
            per_day_hour.setdefault((observed.date().isoformat(), observed.hour), []).append(float(value))
        elif observed.date() == local_now.date():
            today_by_hour.setdefault(observed.hour, []).append(float(value))

    hourly: dict[int, float] = {}
    hour_days: dict[int, int] = {}
    daily_profiles: dict[str, dict[int, float]] = {}
    for (day, hour), values in per_day_hour.items():
        if not values:
            continue
        ordered = sorted(values)
        daily_profiles.setdefault(day, {})[hour] = (ordered[len(ordered)//2] if len(ordered) % 2
                                                     else (ordered[len(ordered)//2-1]+ordered[len(ordered)//2])/2)
    for hour in range(24):
        weighted_values: list[tuple[float, float]] = []
        for (day, observed_hour), values in per_day_hour.items():
            if observed_hour != hour or not values:
                continue
            day_start = datetime.fromisoformat(day).replace(tzinfo=site_tz)
            age_days = max(0.0, (local_now - day_start).total_seconds() / 86400)
            weight = math.exp(-age_days / 3.0)
            ordered = sorted(values)
            median = ordered[len(ordered) // 2] if len(ordered) % 2 else (ordered[len(ordered)//2-1] + ordered[len(ordered)//2]) / 2
            weighted_values.append((median, weight))
        if weighted_values:
            hourly[hour] = sum(value * weight for value, weight in weighted_values) / sum(weight for _, weight in weighted_values)
            hour_days[hour] = len(weighted_values)

    recent_cutoff = local_now - timedelta(minutes=15)
    recent_values = [value for stamp, value in recent if stamp >= recent_cutoff]
    recent_mean_w = sum(recent_values) / len(recent_values) if recent_values else None
    current_is_valid = (isinstance(current_load_w, (int, float)) and not isinstance(current_load_w, bool)
                        and math.isfinite(current_load_w) and current_load_w >= 0)
    if current_is_valid and recent_mean_w is not None:
        # The latest reading reacts quickly to a newly switched load; recent
        # history tempers the result so one short spike does not dominate.
        live_w = 0.7 * float(current_load_w) + 0.3 * recent_mean_w
    elif recent_mean_w is not None:
        live_w = recent_mean_w
    else:
        live_w = float(current_load_w) if current_is_valid else None

    # Select historical days whose already-observed shape resembles today.
    # This lets quiet/away days and high-load/EV days contribute separately,
    # without claiming to know occupancy or identifying a specific appliance.
    observed_pattern = {}
    for hour, values in today_by_hour.items():
        if hour > local_now.hour or not values:
            continue
        ordered = sorted(values)
        observed_pattern[hour] = (ordered[len(ordered)//2] if len(ordered) % 2
                                  else (ordered[len(ordered)//2-1]+ordered[len(ordered)//2])/2)
    if live_w is not None:
        observed_pattern[local_now.hour] = live_w
    scenario_candidates: list[tuple[str, float, int]] = []
    for day, profile_by_hour in daily_profiles.items():
        pairs = [(observed, profile_by_hour[hour]) for hour, observed in observed_pattern.items()
                 if hour in profile_by_hour]
        if len(pairs) < 2:
            continue
        distance = sum(abs(math.log((observed + 150.0) / (historical + 150.0)))
                       for observed, historical in pairs) / len(pairs)
        if distance > 0.9:
            continue
        day_stamp = datetime.fromisoformat(day).replace(tzinfo=site_tz)
        age_days = max(0.0, (local_now-day_stamp).total_seconds()/86400)
        similarity = math.exp(-distance/0.45) * math.exp(-age_days/5.0)
        scenario_candidates.append((day, similarity, len(pairs)))
    scenario_candidates.sort(key=lambda item: item[1], reverse=True)
    selected_scenario = scenario_candidates[:5] if scenario_candidates else []
    if selected_scenario:
        for hour in range(24):
            samples = [(daily_profiles[day][hour], weight) for day, weight, _ in selected_scenario
                       if hour in daily_profiles[day]]
            if samples:
                hourly[hour] = sum(value*weight for value, weight in samples) / sum(weight for _, weight in samples)
                hour_days[hour] = len(samples)

    baseline_now = hourly.get(local_now.hour)
    if live_w is not None and baseline_now is not None:
        current_hour_w = 0.7 * live_w + 0.3 * baseline_now
    else:
        current_hour_w = live_w if live_w is not None else baseline_now
    if current_hour_w is None:
        return {"state": "UNAVAILABLE", "remaining_kwh": None, "confidence": "LOW",
                "reason": "NO_CURRENT_OR_HISTORICAL_LOAD", "history_days_used": 0,
                "method": "seven_day_same_hour_weighted_plus_live"}

    end_local = datetime.combine(local_now.date() + timedelta(days=1), datetime.min.time(), tzinfo=site_tz)
    cursor = local_now
    total_kwh = 0.0
    profile = []
    while cursor < end_local:
        next_hour = cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        interval_end = min(end_local, next_hour)
        duration = (interval_end - cursor).total_seconds() / 3600
        hour = cursor.hour
        if hour == local_now.hour:
            watts = current_hour_w
        else:
            watts = hourly.get(hour, current_hour_w)
        total_kwh += max(0.0, watts) * duration / 1000
        profile.append({"hour": hour, "load_power_w": round(max(0.0, watts), 1),
                        "duration_hours": round(duration, 3),
                        "history_days": hour_days.get(hour, 0),
                        "pattern_days": len(selected_scenario),
                        "source": "LIVE_PLUS_HOURLY_HISTORY" if hour == local_now.hour and baseline_now is not None
                        else "LIVE_CURRENT_FALLBACK" if hour != local_now.hour and hour not in hourly
                        else "SIMILAR_DAILY_PATTERN" if selected_scenario
                        else "WEIGHTED_HOURLY_HISTORY"})
        cursor = interval_end
    available_hours = sum(1 for hour in range(24) if hour in hourly)
    history_days_used = max(hour_days.values(), default=0)
    confidence = "HIGH" if available_hours >= 18 and history_days_used >= 5 else (
        "MEDIUM" if available_hours >= 8 and history_days_used >= 2 else "LOW")
    return {"state": "ESTIMATED", "remaining_kwh": round(total_kwh, 2),
            "live_load_w": round(live_w, 1) if live_w is not None else None,
            "history_hours_used": available_hours, "history_days_used": history_days_used,
            "confidence": confidence, "profile": profile,
            "pattern_days_used": len(selected_scenario),
            "method": "similar_observed_day_pattern_plus_weighted_hourly_history_and_live_15m"
            if selected_scenario else "seven_day_same_hour_recency_weighted_plus_live_15m_blend"}


def _engine_quarter_hour_projection(now: datetime, solar_expected: list[dict[str, Any]],
                                   solar_potential: list[dict[str, Any]], load_profile: list[dict[str, Any]],
                                   *, day_end: datetime, actual_today_kwh: float | None,
                                   expected_remaining_kwh: float | None,
                                   potential_remaining_kwh: float | None,
                                   expected_load_remaining_kwh: float | None = None,
                                   current_pv_kw: float | None = None,
                                   confidence: str = "LOW_INDICATIVE") -> dict[str, Any]:
    """Expose the Engine's daily forecast shape as a 15-minute six-hour outlook.

    Weather and load forecasts are hourly. The Engine interpolates solar power
    between its weather points, applies the same daily-forecast calibration to
    the full remaining daylight shape, and samples its existing same-hour/live
    load profile on quarter-hour boundaries. No new PWA-side forecast is made.
    """
    now_utc = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    day_end_utc = day_end.astimezone(timezone.utc) if day_end.tzinfo else day_end.replace(tzinfo=timezone.utc)
    end = min(now_utc + timedelta(hours=6), day_end_utc)

    def solar_anchors(points: list[dict[str, Any]]) -> list[tuple[datetime, float]]:
        anchors: list[tuple[datetime, float]] = []
        for point in points:
            try:
                stamp = datetime.fromisoformat(str(point.get("observed_at") or point.get("forecast_at") or "").replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                value = float(point.get("value"))
                if point.get("unit") == "W":
                    value /= 1000.0
                stamp_utc = stamp.astimezone(timezone.utc)
                if math.isfinite(value) and stamp_utc < day_end_utc and stamp_utc + timedelta(hours=1) > now_utc:
                    anchors.append((stamp_utc, max(0.0, value)))
            except (TypeError, ValueError):
                continue
        return sorted(anchors)

    expected_raw = solar_anchors(solar_expected)
    potential_raw = solar_anchors(solar_potential)

    def hourly_shape_energy(anchors: list[tuple[datetime, float]]) -> float:
        total = 0.0
        if anchors and anchors[0][0] > now_utc:
            total += anchors[0][1] * min(1.0, (anchors[0][0]-now_utc).total_seconds()/3600.0)
        for stamp, value in anchors:
            interval_start = max(now_utc, stamp)
            interval_end = min(day_end_utc, stamp + timedelta(hours=1))
            if interval_end > interval_start:
                total += value * (interval_end - interval_start).total_seconds() / 3600.0
        return total

    def scale_to_engine_total(anchors: list[tuple[datetime, float]], target: float | None) -> float:
        shape = hourly_shape_energy(anchors)
        if shape <= 1e-9 or isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(target):
            return 1.0
        return max(0.0, min(4.0, float(target) / shape))

    expected_scale = scale_to_engine_total(expected_raw, expected_remaining_kwh)
    potential_scale = scale_to_engine_total(potential_raw, potential_remaining_kwh)
    expected_anchors = [(stamp, value * expected_scale) for stamp, value in expected_raw]
    potential_anchors = [(stamp, value * potential_scale) for stamp, value in potential_raw]
    estimated_daily_total_kwh = (float(actual_today_kwh) + float(expected_remaining_kwh)
                                 if isinstance(actual_today_kwh, (int, float))
                                 and not isinstance(actual_today_kwh, bool)
                                 and isinstance(expected_remaining_kwh, (int, float))
                                 and not isinstance(expected_remaining_kwh, bool)
                                 and math.isfinite(actual_today_kwh)
                                 and math.isfinite(expected_remaining_kwh) else None)
    potential_daily_total_kwh = (float(actual_today_kwh) + float(potential_remaining_kwh)
                                 if isinstance(actual_today_kwh, (int, float))
                                 and not isinstance(actual_today_kwh, bool)
                                 and isinstance(potential_remaining_kwh, (int, float))
                                 and not isinstance(potential_remaining_kwh, bool)
                                 and math.isfinite(actual_today_kwh)
                                 and math.isfinite(potential_remaining_kwh) else None)

    def interpolate(anchors: list[tuple[datetime, float]], stamp: datetime) -> float | None:
        if not anchors:
            return None
        before = None
        for after in anchors:
            if after[0] == stamp:
                return after[1]
            if after[0] < stamp:
                before = after
                continue
            if before is None:
                return after[1]
            span = (after[0] - before[0]).total_seconds()
            if span <= 0:
                return after[1]
            ratio = (stamp - before[0]).total_seconds() / span
            return before[1] + (after[1] - before[1]) * ratio
        return before[1] if before else None

    load_anchors: list[tuple[datetime, float]] = []
    cursor = now_utc
    for item in load_profile:
        try:
            watts = float(item.get("load_power_w"))
            duration = float(item.get("duration_hours"))
            if not math.isfinite(watts) or not math.isfinite(duration) or duration <= 0:
                continue
            load_anchors.append((cursor, max(0.0, watts / 1000.0)))
            cursor += timedelta(hours=duration)
        except (TypeError, ValueError):
            continue

    def step_load(stamp: datetime) -> float | None:
        value = None
        for anchor_at, anchor_value in load_anchors:
            if anchor_at > stamp:
                break
            value = anchor_value
        return value if value is not None else (load_anchors[0][1] if load_anchors else None)

    def integrate_load(left: datetime, right: datetime) -> float:
        if right <= left:
            return 0.0
        total = 0.0
        cursor_at = left
        value = step_load(cursor_at)
        while cursor_at < right and value is not None:
            next_change = next((stamp for stamp, _ in load_anchors if stamp > cursor_at), right)
            segment_end = min(right, next_change)
            total += value * (segment_end - cursor_at).total_seconds() / 3600.0
            cursor_at = segment_end
            if cursor_at < right:
                value = step_load(cursor_at)
        return total

    # Anchor the immediate interval to actual live readings when available.
    current_expected = (max(0.0, float(current_pv_kw))
                        if isinstance(current_pv_kw, (int, float)) and not isinstance(current_pv_kw, bool)
                        and math.isfinite(current_pv_kw) else interpolate(expected_anchors, now_utc))
    current_potential = interpolate(potential_anchors, now_utc)
    current_load = step_load(now_utc)
    quarter_seconds = 15 * 60
    first = (int(now_utc.timestamp()) // quarter_seconds + 1) * quarter_seconds
    values: list[dict[str, Any]] = []
    expected_cumulative = potential_cumulative = load_cumulative = 0.0
    previous_at = now_utc
    previous_expected, previous_potential = current_expected, current_potential
    for epoch in range(first, int(end.timestamp()) + 1, quarter_seconds):
        stamp = datetime.fromtimestamp(epoch, timezone.utc)
        expected_kw = interpolate(expected_anchors, stamp)
        potential_kw = interpolate(potential_anchors, stamp)
        load_kw = step_load(stamp)
        hours = (stamp - previous_at).total_seconds() / 3600.0
        if expected_kw is not None and previous_expected is not None:
            expected_cumulative += max(0.0, (expected_kw + previous_expected) / 2.0) * hours
        if potential_kw is not None and previous_potential is not None:
            potential_cumulative += max(0.0, (potential_kw + previous_potential) / 2.0) * hours
        load_cumulative += integrate_load(previous_at, stamp)
        values.append({"forecast_at": stamp.isoformat(timespec="minutes"),
                       "minutes_ahead": round((stamp - now_utc).total_seconds() / 60),
                       "solar_expected_power_kw": round(expected_kw, 3) if expected_kw is not None else None,
                       "solar_potential_power_kw": round(potential_kw, 3) if potential_kw is not None else None,
                       "load_power_kw": round(load_kw, 3) if load_kw is not None else None,
                       "solar_expected_cumulative_kwh": round(expected_cumulative, 3) if expected_kw is not None else None,
                       "solar_potential_cumulative_kwh": round(potential_cumulative, 3) if potential_kw is not None else None,
                       "load_cumulative_kwh": round(load_cumulative, 3) if load_kw is not None else None,
                       "expected_net_cumulative_kwh": round(expected_cumulative-load_cumulative, 3)
                       if expected_kw is not None and load_kw is not None else None,
                       "potential_net_cumulative_kwh": round(potential_cumulative-load_cumulative, 3)
                       if potential_kw is not None and load_kw is not None else None,
                       "estimated_daily_pv_kwh": round(estimated_daily_total_kwh, 2)
                       if estimated_daily_total_kwh is not None else None,
                       "potential_daily_pv_kwh": round(potential_daily_total_kwh, 2)
                       if potential_daily_total_kwh is not None else None})
        previous_at = stamp
        previous_expected, previous_potential = expected_kw, potential_kw

    if not values:
        return {"state": "UNAVAILABLE", "cadence_minutes": 15, "horizon_hours": 6,
                "values": [], "confidence": "UNAVAILABLE", "reason": "No quarter-hour forecast points in the remaining daylight window."}
    expected_total, potential_total, load_total = expected_cumulative, potential_cumulative, load_cumulative
    for item in values:
        expected_used = item.get("solar_expected_cumulative_kwh")
        potential_used = item.get("solar_potential_cumulative_kwh")
        load_used = item.get("load_cumulative_kwh")
        item["solar_expected_remaining_kwh_6h"] = round(max(0.0, expected_total-float(expected_used)), 3) if expected_used is not None else None
        item["solar_potential_remaining_kwh_6h"] = round(max(0.0, potential_total-float(potential_used)), 3) if potential_used is not None else None
        item["load_remaining_kwh_6h"] = round(max(0.0, load_total-float(load_used)), 3) if load_used is not None else None
        item["expected_net_remaining_kwh_6h"] = round(float(item["solar_expected_remaining_kwh_6h"])-float(item["load_remaining_kwh_6h"]), 3) if item["solar_expected_remaining_kwh_6h"] is not None and item["load_remaining_kwh_6h"] is not None else None
        solar_day_remaining = (max(0.0, float(expected_remaining_kwh)-float(expected_used))
                               if isinstance(expected_remaining_kwh, (int, float))
                               and not isinstance(expected_remaining_kwh, bool)
                               and math.isfinite(expected_remaining_kwh) and expected_used is not None else None)
        load_day_remaining = (max(0.0, float(expected_load_remaining_kwh)-float(load_used))
                              if isinstance(expected_load_remaining_kwh, (int, float))
                              and not isinstance(expected_load_remaining_kwh, bool)
                              and math.isfinite(expected_load_remaining_kwh) and load_used is not None else None)
        item["solar_expected_remaining_to_day_end_kwh"] = round(solar_day_remaining, 3) if solar_day_remaining is not None else None
        item["load_remaining_to_day_end_kwh"] = round(load_day_remaining, 3) if load_day_remaining is not None else None
        item["solar_available_after_load_to_day_end_kwh"] = (round(solar_day_remaining-load_day_remaining, 3)
                                                              if solar_day_remaining is not None and load_day_remaining is not None else None)
    return {"state": "ESTIMATED", "cadence_minutes": 15, "horizon_hours": 6,
            "source_resolution_minutes": 60, "method": "engine_daily_forecast_shape_plus_weighted_hourly_load",
            "confidence": confidence, "expected_daily_scale": round(expected_scale, 3),
            "potential_daily_scale": round(potential_scale, 3), "values": values}


def _solar_day_forecast(conn: sqlite3.Connection, inverter: dict[str, Any] | None,
                        inverter_readings: dict[str, dict[str, Any]], weather: dict[str, Any] | None,
                        capacity_kw: float | None, efficiency: float, solar_model: dict[str, Any],
                        as_of: datetime | None = None) -> dict[str, Any]:
    """Estimate today's final PV energy from measured yield, weather, and non-curtailed history.

    This is an analytics result only. It does not allocate energy to loads or control an EV.
    """
    now = as_of.astimezone(timezone.utc) if as_of else datetime.now(timezone.utc)
    _ensure_solar_forecast_history(conn)
    timezone_name = weather.get("timezone") if isinstance(weather, dict) else None
    try:
        site_tz = ZoneInfo(timezone_name) if isinstance(timezone_name, str) else datetime.now().astimezone().tzinfo
    except (ZoneInfoNotFoundError, ValueError):
        site_tz = datetime.now().astimezone().tzinfo or timezone.utc
    local_now = now.astimezone(site_tz)
    today = local_now.date()
    calculated_at = now.isoformat(timespec="seconds")
    unavailable = {"state": "UNAVAILABLE", "estimated_total_kwh": None, "actual_today_kwh": None,
                   "remaining_estimate_kwh": None, "calculated_at": calculated_at,
                   "next_update_seconds": 600, "confidence": "UNAVAILABLE",
                   "reason": "Solar capacity, current daily energy, or a full-day forecast is unavailable.",
                   "historical_days_used": 0, "curtailment_days_excluded": 0,
                   "curtailment_hours_excluded": int(solar_model.get("possible_curtailment_hours", 0) or 0)}
    if not inverter:
        return {**unavailable, "reason": "O Gateway ainda não tem um inversor Deye configurado para a previsão solar."}
    if (not isinstance(capacity_kw, (int, float)) or isinstance(capacity_kw, bool)
            or not math.isfinite(capacity_kw) or capacity_kw <= 0):
        return {**unavailable, "reason": "Falta configurar a potência nominal FV na página Produção para calcular a previsão."}
    if not weather or weather.get("state") != "available":
        return {**unavailable, "reason": "Previsão meteorológica indisponível. Confirma a localização da casa e a ligação à Internet do Gateway."}

    # Keep a stable estimate for ten minutes; clients may poll the summary more often.
    cached_row = conn.execute("SELECT value FROM system_state WHERE key=?", (SOLAR_DAY_FORECAST_KEY,)).fetchone()
    if cached_row:
        try:
            cached = json.loads(cached_row[0])
            cached_at = datetime.fromisoformat(str(cached.get("calculated_at", "")).replace("Z", "+00:00"))
            if (cached.get("local_date") == today.isoformat() and cached_at.tzinfo is not None
                    and 0 <= (now - cached_at.astimezone(timezone.utc)).total_seconds() < 600
                    and cached.get("state") == "ESTIMATED"):
                return cached
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    counter = inverter_readings.get("pv_daily_energy")
    actual_kwh = counter.get("value") if isinstance(counter, dict) else None
    actual_at = counter.get("observed_at") if isinstance(counter, dict) else None
    try:
        actual_stamp = datetime.fromisoformat(str(actual_at).replace("Z", "+00:00"))
        if actual_stamp.tzinfo is None:
            actual_stamp = actual_stamp.replace(tzinfo=timezone.utc)
        counter_is_fresh = (0 <= (now - actual_stamp.astimezone(timezone.utc)).total_seconds() <= 1200
                            and actual_stamp.astimezone(site_tz).date() == today)
    except (TypeError, ValueError):
        counter_is_fresh = False
    valid_counter = (counter_is_fresh and not isinstance(actual_kwh, bool)
                     and isinstance(actual_kwh, (int, float)) and math.isfinite(actual_kwh)
                     and 0 <= actual_kwh <= float(capacity_kw) * 24 * 1.5)
    measurement_source = "pv_daily_energy"
    measurement_coverage = "FULL_DAILY_COUNTER"
    accumulation_start_at = None
    integration_quality = None
    if not valid_counter:
        day_start = datetime.combine(today, datetime.min.time(), tzinfo=site_tz).astimezone(timezone.utc)
        power_history = _series(conn, [inverter["id"]], "pv_total_power", day_start.isoformat(),
                                limit=50000, until=now.isoformat())
        integrated = _integrate_power_kwh(power_history, until=now)
        last_integrated_at = _parse_utc(integrated.get("last_sample_at"))
        integration_quality = integrated
        accumulation_start_at = integrated.get("first_sample_at")
        if (integrated.get("integrated_intervals", 0) > 0 and last_integrated_at is not None
                and 0 <= (now-last_integrated_at).total_seconds() <= 120):
            actual_kwh = integrated["energy_kwh"]
            measurement_source = "pv_power_integrated"
            measurement_coverage = "PARTIAL_FROM_FIRST_LIVE_SAMPLE"
        else:
            # Still calculate the weather-driven remainder and load balance,
            # while clearly marking that measured production is unavailable.
            actual_kwh = 0.0
            measurement_source = "weather_only_no_fresh_pv_meter"
            measurement_coverage = "NO_FRESH_MEASURED_PRODUCTION"

    day_end_local = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=site_tz)
    day_end = day_end_local.astimezone(timezone.utc)
    remaining_weather_kwh = 0.0
    elapsed_weather_kwh = 0.0
    forecast_hours = 0
    performance_ratio = solar_model.get("performance_ratio")
    if (isinstance(performance_ratio, bool) or not isinstance(performance_ratio, (int, float))
            or not math.isfinite(performance_ratio)):
        performance_ratio = 1.0
    performance_ratio = max(0.1, min(1.2, float(performance_ratio)))
    for point in weather.get("hourly", []):
        try:
            stamp = datetime.fromisoformat(str(point.get("observed_at", "")).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            radiation = point.get("shortwave_radiation_w_m2")
            if isinstance(radiation, bool) or not isinstance(radiation, (int, float)) or not math.isfinite(radiation) or radiation < 0:
                continue
            effective_radiation = point.get("pv_effective_irradiance_w_m2", radiation)
            if (isinstance(effective_radiation, bool) or not isinstance(effective_radiation, (int, float))
                    or not math.isfinite(effective_radiation) or effective_radiation < 0):
                effective_radiation = radiation
            point_start = stamp.astimezone(timezone.utc)
            point_end = min(day_end, point_start + timedelta(hours=1))
            elapsed_hours = (min(now, point_end) - point_start).total_seconds() / 3600
            if elapsed_hours > 0:
                elapsed_weather_kwh += float(capacity_kw) * float(effective_radiation) / 1000 * float(efficiency) * performance_ratio * elapsed_hours
            interval_start = max(now, point_start)
            interval_end = point_end
            hours = (interval_end - interval_start).total_seconds() / 3600
            if hours <= 0:
                continue
            remaining_weather_kwh += float(capacity_kw) * float(effective_radiation) / 1000 * float(efficiency) * performance_ratio * hours
            forecast_hours += 1
        except (TypeError, ValueError):
            continue
    if forecast_hours == 0 and now < day_end:
        return {**unavailable, "local_date": today.isoformat(),
                "actual_today_kwh": round(float(actual_kwh), 3),
                "reason": "The weather feed has no hourly values through the end of today."}

    # Compare today's measured trajectory with recent daily-counter trajectories.
    # Days with any detected possible curtailment are excluded as biased references.
    historical_days: dict[str, list[tuple[datetime, float]]] = {}
    since = (now - timedelta(days=35)).isoformat(timespec="microseconds")
    for sample in _series(conn, [inverter["id"]], "pv_daily_energy", since, limit=50000):
        try:
            stamp = datetime.fromisoformat(str(sample["observed_at"]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            local_stamp = stamp.astimezone(site_tz)
            value = float(sample["value"])
            if not math.isfinite(value) or value < 0 or value > float(capacity_kw) * 24 * 1.5:
                continue
            if local_stamp.date() < today:
                historical_days.setdefault(local_stamp.date().isoformat(), []).append((local_stamp, value))
        except (KeyError, TypeError, ValueError):
            continue
    curtailed_dates: set[str] = set()
    for event in solar_model.get("curtailment_events_30d", solar_model.get("recent_curtailment_candidates", [])):
        try:
            stamp = datetime.fromisoformat(str(event.get("hour", "")).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            curtailed_dates.add(stamp.astimezone(site_tz).date().isoformat())
        except (TypeError, ValueError):
            continue
    completed: list[tuple[float, float]] = []
    for day, samples in historical_days.items():
        if day in curtailed_dates or not samples:
            continue
        latest = max(stamp for stamp, _ in samples)
        if latest.hour < 16:
            continue
        prior_total = max(value for _, value in samples)
        close = [(stamp, value) for stamp, value in samples
                 if abs((stamp.hour * 60 + stamp.minute) - (local_now.hour * 60 + local_now.minute)) <= 20]
        if close:
            prior_at_time = min(close, key=lambda item: abs((item[0].hour * 60 + item[0].minute)
                                                              - (local_now.hour * 60 + local_now.minute)))[1]
            completed.append((prior_total, prior_at_time))
    history_used = len(completed)
    historical_remaining = None
    history_full_median = history_so_far_median = None
    if history_used >= 3:
        full_values = sorted(item[0] for item in completed)
        so_far_values = sorted(item[1] for item in completed)
        middle = history_used // 2
        history_full_median = full_values[middle] if history_used % 2 else (full_values[middle - 1] + full_values[middle]) / 2
        history_so_far_median = so_far_values[middle] if history_used % 2 else (so_far_values[middle - 1] + so_far_values[middle]) / 2
        if history_so_far_median > 0.25 and measurement_coverage == "FULL_DAILY_COUNTER":
            day_adjustment = max(0.5, min(1.5, float(actual_kwh) / history_so_far_median))
            historical_remaining = max(0.0, history_full_median - history_so_far_median) * day_adjustment
        elif measurement_coverage != "NO_FRESH_MEASURED_PRODUCTION":
            historical_remaining = max(0.0, history_full_median - history_so_far_median)

    # Blend today's observed trajectory with the learned installation reference.
    # When the house is consuming at least the PV output, that hour is stronger
    # evidence of normal operation and receives more weight than an unexplained dip.
    observed_performance = (max(0.0, float(actual_kwh)) / elapsed_weather_kwh
                            if elapsed_weather_kwh > 0.25 and measurement_coverage == "FULL_DAILY_COUNTER" else 1.0)
    learned_performance = solar_model.get("performance_ratio", 1.0)
    if (isinstance(learned_performance, bool) or not isinstance(learned_performance, (int, float))
            or not math.isfinite(learned_performance)):
        learned_performance = 1.0
    learned_performance = max(0.1, min(1.2, float(learned_performance)))
    current_load = inverter_readings.get("load_total_power")
    current_pv = inverter_readings.get("pv_total_power")
    load_value = current_load.get("value") if isinstance(current_load, dict) else None
    pv_value = current_pv.get("value") if isinstance(current_pv, dict) else None
    load_stamp = _parse_utc(current_load.get("observed_at")) if isinstance(current_load, dict) else None
    pv_stamp = _parse_utc(current_pv.get("observed_at")) if isinstance(current_pv, dict) else None
    demand_supported_now = (isinstance(load_value, (int, float)) and not isinstance(load_value, bool)
                            and isinstance(pv_value, (int, float)) and not isinstance(pv_value, bool)
                            and math.isfinite(load_value) and math.isfinite(pv_value)
                            and load_value >= pv_value and load_stamp is not None and pv_stamp is not None
                            and 0 <= (now-load_stamp).total_seconds() <= 120
                            and 0 <= (now-pv_stamp).total_seconds() <= 120)
    if (measurement_coverage == "FULL_DAILY_COUNTER" and elapsed_weather_kwh <= 0.25
            and history_so_far_median is not None and history_so_far_median > 0.25):
        observed_performance = max(0.0, min(1.5, float(actual_kwh) / history_so_far_median))
    observed_weight = 0.75 if demand_supported_now else 0.35
    if today.isoformat() in curtailed_dates:
        observed_weight = 0.15
    potential_adjustment = max(0.0, min(1.5,
        observed_performance * observed_weight + learned_performance * (1.0-observed_weight)))
    adjusted_potential_remaining = remaining_weather_kwh * potential_adjustment
    potential_total_kwh = float(actual_kwh) + max(0.0, adjusted_potential_remaining)

    # Weather is the forward-looking signal; the recent non-curtailed daily curve
    # contributes a bounded prior so unusually strong/weak current production adapts.
    if historical_remaining is not None:
        remaining_kwh = 0.7 * remaining_weather_kwh + 0.3 * historical_remaining
    else:
        remaining_kwh = remaining_weather_kwh
    total_kwh = float(actual_kwh) + max(0.0, remaining_kwh)
    # Learn forecast bias from completed days by comparing each historical
    # forecast made at roughly this same local time with that day's final meter.
    # Curtailment days and incomplete meter days are excluded.
    matched_forecasts: list[tuple[float, float, float, float]] = []
    final_by_day = {day: max(value for _, value in samples)
                    for day, samples in historical_days.items()
                    if day not in curtailed_dates and samples and max(stamp for stamp, _ in samples).hour >= 16}
    if final_by_day:
        forecast_rows = conn.execute(
            "SELECT local_date,calculated_at,estimated_total_kwh FROM energy_solar_day_forecasts "
            "WHERE local_date>=? AND local_date<? ORDER BY local_date,calculated_at",
            ((today - timedelta(days=30)).isoformat(), today.isoformat())).fetchall()
        forecasts_by_day: dict[str, list[tuple[datetime, float]]] = {}
        for forecast_day, forecast_at, forecast_total in forecast_rows:
            try:
                forecast_stamp = datetime.fromisoformat(str(forecast_at).replace("Z", "+00:00"))
                if forecast_stamp.tzinfo is None:
                    forecast_stamp = forecast_stamp.replace(tzinfo=timezone.utc)
                forecast_value = float(forecast_total)
                if math.isfinite(forecast_value) and forecast_value > 0:
                    forecasts_by_day.setdefault(str(forecast_day), []).append((forecast_stamp.astimezone(site_tz), forecast_value))
            except (TypeError, ValueError):
                continue
        target_minute = local_now.hour * 60 + local_now.minute
        for forecast_day, final_total in final_by_day.items():
            choices = forecasts_by_day.get(forecast_day, [])
            if not choices:
                continue
            closest = min(choices, key=lambda item: abs((item[0].hour * 60 + item[0].minute) - target_minute))
            delta_min = abs((closest[0].hour * 60 + closest[0].minute) - target_minute)
            if delta_min > 45:
                continue
            forecast_value = closest[1]
            ratio = max(0.5, min(1.5, final_total / forecast_value))
            day_stamp = datetime.fromisoformat(forecast_day).replace(tzinfo=site_tz)
            recency = math.exp(-max(0.0, (local_now-day_stamp).total_seconds()/86400) / 10.0)
            matched_forecasts.append((ratio, recency, final_total, forecast_value))
    forecast_calibration_factor = 1.0
    forecast_error_mae_kwh = None
    forecast_error_bias_kwh = None
    if len(matched_forecasts) >= 3:
        ordered_calibration = sorted(matched_forecasts, key=lambda item: item[0])
        total_calibration_weight = sum(item[1] for item in ordered_calibration)
        running_calibration_weight = 0.0
        for item in ordered_calibration:
            running_calibration_weight += item[1]
            if running_calibration_weight >= total_calibration_weight / 2:
                forecast_calibration_factor = max(0.75, min(1.25, item[0]))
                break
        errors = [estimate - actual for _, _, actual, estimate in matched_forecasts]
        forecast_error_mae_kwh = sum(abs(error) for error in errors) / len(errors)
        forecast_error_bias_kwh = sum(errors) / len(errors)
        total_kwh = max(float(actual_kwh), total_kwh * forecast_calibration_factor)
        remaining_kwh = max(0.0, total_kwh - float(actual_kwh))
    forecast_uncertainty_kwh = forecast_error_mae_kwh
    result = {"state": "ESTIMATED", "local_date": today.isoformat(),
              "estimated_total_kwh": round(total_kwh, 2), "actual_today_kwh": round(float(actual_kwh), 2),
              "measurement_source": measurement_source, "measurement_coverage": measurement_coverage,
              "accumulation_start_at": accumulation_start_at, "power_integration": integration_quality,
              "remaining_estimate_kwh": round(max(0.0, remaining_kwh), 2),
              "potential_max_total_kwh": round(potential_total_kwh, 2),
              "potential_max_remaining_kwh": round(max(0.0, adjusted_potential_remaining), 2),
              "potential_adjustment_factor": round(potential_adjustment, 3),
              "potential_adjustment_basis": ("DEMAND_SUPPORTED_CURRENT_OUTPUT" if demand_supported_now
                                             else "LEARNED_AND_CURRENT_OUTPUT"),
              "weather_remaining_kwh": round(max(0.0, remaining_weather_kwh), 2),
              "expected_load_remaining_kwh": None,
              "forecast_calibration_factor": round(forecast_calibration_factor, 3),
              "forecast_calibration_days_used": len(matched_forecasts),
              "forecast_error_mae_kwh": round(forecast_error_mae_kwh, 2) if forecast_error_mae_kwh is not None else None,
              "forecast_error_bias_kwh": round(forecast_error_bias_kwh, 2) if forecast_error_bias_kwh is not None else None,
              "estimated_total_low_kwh": round(max(float(actual_kwh), total_kwh-forecast_uncertainty_kwh), 2) if forecast_uncertainty_kwh is not None else None,
              "estimated_total_high_kwh": round(total_kwh+forecast_uncertainty_kwh, 2) if forecast_uncertainty_kwh is not None else None,
              "historical_daily_median_kwh": round(history_full_median, 2) if history_full_median is not None else None,
              "historical_daily_to_now_median_kwh": round(history_so_far_median, 2) if history_so_far_median is not None else None,
              "historical_days_used": history_used, "curtailment_days_excluded": len(curtailed_dates),
              "curtailment_hours_excluded": int(solar_model.get("possible_curtailment_hours_30d", 0) or 0),
              "curtailment_adjustment": "Possible-curtailment days are excluded from the daily reference; suspected hours are excluded from learned performance.",
              "performance_ratio": round(performance_ratio, 4),
              "confidence": ("MEDIUM_INDICATIVE" if int(solar_model.get("sample_count", 0) or 0) >= 48 and history_used >= 5
                             else "LOW_INDICATIVE"),
              "performance_samples_30d": int(solar_model.get("performance_samples_30d", 0) or 0),
              "demand_supported_samples": int(solar_model.get("demand_supported_samples", 0) or 0),
              "last_observation_interpretation": (solar_model.get("recent_performance_observations") or [{}])[-1].get("classification"),
              "last_observation_hour": (solar_model.get("recent_performance_observations") or [{}])[-1].get("hour"),
              "measurement_source": "pv_daily_energy", "forecast_hours_used": forecast_hours,
              "calculated_at": calculated_at, "next_update_seconds": 600,
              "method": "measured_today_plus_remaining_weather_and_recent_non_curtailed_daily_history",
              "reason": None}
    conn.execute("INSERT INTO system_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (SOLAR_DAY_FORECAST_KEY, json.dumps(result, separators=(",", ":"))))
    conn.execute("""INSERT INTO energy_solar_day_forecasts
        (local_date, calculated_at, estimated_total_kwh, actual_today_kwh, remaining_estimate_kwh, confidence, potential_max_total_kwh)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(local_date, calculated_at) DO UPDATE SET
        estimated_total_kwh=excluded.estimated_total_kwh, actual_today_kwh=excluded.actual_today_kwh,
        remaining_estimate_kwh=excluded.remaining_estimate_kwh, confidence=excluded.confidence,
        potential_max_total_kwh=excluded.potential_max_total_kwh""",
        (today.isoformat(), calculated_at, result["estimated_total_kwh"], result["actual_today_kwh"],
         result["remaining_estimate_kwh"], result["confidence"], result["potential_max_total_kwh"]))
    conn.execute("DELETE FROM energy_solar_day_forecasts WHERE local_date<?",
                 ((today - timedelta(days=90)).isoformat(),))
    return result


def _estimate_battery_soc(voltage_history: list[dict[str, Any]], power_history: list[dict[str, Any]],
                          capacity_kwh: float | None, minimum_soc: float, maximum_soc: float,
                          as_of: datetime | None = None
                          ) -> tuple[float | None, dict[str, Any]]:
    """Estimate SOC only after a high-voltage charge has settled near zero power.

    Deye convention: positive battery_output_power is discharge; negative is charge.
    A voltage peak alone is not a full-charge event: it must follow active charge
    and remain within 0.15 V of the 90-day ceiling at <=20 W for ten minutes.
    """
    unavailable = {"state": "UNAVAILABLE", "voltage_max_30d_v": None, "anchor_at": None,
                   "integrated_net_discharge_kwh": None, "sample_count": len(power_history)}
    if capacity_kwh is None or capacity_kwh <= 0:
        return None, {**unavailable, "reason": "BATTERY_CAPACITY_NOT_CONFIGURED"}
    voltages: list[tuple[datetime, float]] = []
    for point in voltage_history:
        try:
            stamp = datetime.fromisoformat(str(point["observed_at"]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            value = float(point["value"])
            if math.isfinite(value) and value > 0:
                voltages.append((stamp.astimezone(timezone.utc), value))
        except (KeyError, TypeError, ValueError):
            continue
    if not voltages:
        return None, {**unavailable, "reason": "NO_BATTERY_VOLTAGE_HISTORY"}
    peak_voltage = max(value for _, value in voltages)
    powers: list[tuple[datetime, float]] = []
    for point in power_history:
        try:
            stamp = datetime.fromisoformat(str(point["observed_at"]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            value = float(point["value"])
            if math.isfinite(value):
                powers.append((stamp.astimezone(timezone.utc), value))
        except (KeyError, TypeError, ValueError):
            continue
    powers.sort(key=lambda item: item[0])
    now = as_of.astimezone(timezone.utc) if as_of is not None else datetime.now(timezone.utc)
    voltage_by_time = sorted(voltages)
    stable: list[tuple[datetime, float]] = []
    confirmed_anchor: tuple[datetime, float] | None = None
    for stamp, power in powers:
        nearest = min(voltage_by_time, key=lambda item: abs((item[0] - stamp).total_seconds()), default=None)
        if nearest and abs((nearest[0] - stamp).total_seconds()) <= 120 and nearest[1] >= peak_voltage - 0.15 and abs(power) <= 20:
            if stable and (stamp - stable[-1][0]).total_seconds() > 150:
                stable = []
            stable.append((stamp, nearest[1]))
            if (stable[-1][0] - stable[0][0]).total_seconds() >= 600:
                charge_before = any(t < stable[0][0] and t >= stable[0][0] - timedelta(minutes=30) and p <= -20
                                    for t, p in powers)
                if charge_before:
                    # Ten minutes of stable top conditions confirm the anchor
                    # retrospectively at the start of the stable interval.
                    confirmed_anchor = (stable[0][0], max(v for _, v in stable))
        else:
            stable = []
    if confirmed_anchor is None:
        return None, {**unavailable, "reason": "FULL_CHARGE_STABILIZATION_NOT_CONFIRMED",
                      "voltage_max_90d_v": round(peak_voltage, 3),
                      "charge_power_tolerance_w": 20, "stabilization_minutes": 10}
    peak_at, peak_voltage = confirmed_anchor
    if len(powers) < 2 or powers[-1][0] < peak_at or (now - powers[-1][0]).total_seconds() > 120:
        return None, {**unavailable, "reason": "FRESH_CHARGE_DISCHARGE_HISTORY_REQUIRED",
                      "voltage_max_30d_v": round(peak_voltage, 3), "anchor_at": peak_at.isoformat()}
    after_anchor = [item for item in powers if item[0] >= peak_at]
    if len(after_anchor) < 2 or (after_anchor[0][0] - peak_at).total_seconds() > 180:
        return None, {**unavailable, "reason": "POWER_HISTORY_DOES_NOT_COVER_VOLTAGE_ANCHOR",
                      "voltage_max_30d_v": round(peak_voltage, 3), "anchor_at": peak_at.isoformat()}
    net_discharge_kwh = 0.0
    for (t0, p0), (t1, p1) in zip(after_anchor, after_anchor[1:]):
        seconds = (t1 - t0).total_seconds()
        if seconds <= 0:
            continue
        if seconds > 600:
            return None, {**unavailable, "reason": "GAP_IN_POWER_HISTORY",
                          "voltage_max_30d_v": round(peak_voltage, 3), "anchor_at": peak_at.isoformat()}
        net_discharge_kwh += ((p0 + p1) / 2) * seconds / 3_600_000
    estimated_soc = min(maximum_soc, max(minimum_soc, maximum_soc - (net_discharge_kwh / capacity_kwh * 100)))
    return round(estimated_soc, 2), {
        "state": "ESTIMATED_FROM_30D_VOLTAGE_PEAK_AND_POWER_INTEGRATION",
        "reason": "ROLLING_VOLTAGE_PEAK_IS_AN_ESTIMATED_FULL_CHARGE_ANCHOR",
        "voltage_max_30d_v": round(peak_voltage, 3), "anchor_at": peak_at.isoformat(),
        "integrated_net_discharge_kwh": round(net_discharge_kwh, 4),
        "sample_count": len(after_anchor), "bank_voltage_scope": "SHARED_PARALLEL_BUS",
    }


def _estimate_battery_soc_persistent(conn: sqlite3.Connection,
                                     voltage_history: list[dict[str, Any]],
                                     power_history: list[dict[str, Any]],
                                     capacity_kwh: float | None, minimum_soc: float,
                                     maximum_soc: float, as_of: datetime | None = None
                                     ) -> tuple[float | None, dict[str, Any]]:
    """Continue aggregate parallel-bank coulomb/energy integration across API calls.

    The latest 30-day voltage peak is used only to bootstrap an empty estimator.
    Thereafter its anchor is persisted, so pruning old readings cannot silently
    redefine an older, lower voltage as 100%. Power is integrated once per new
    timestamp; stale samples and gaps fail closed until a fresh voltage-top
    observation re-establishes the anchor.
    """
    now = as_of.astimezone(timezone.utc) if as_of is not None else datetime.now(timezone.utc)
    unavailable = {"state": "UNAVAILABLE", "voltage_max_30d_v": None, "anchor_at": None,
                   "integrated_net_discharge_kwh": None, "sample_count": len(power_history)}
    if capacity_kwh is None or capacity_kwh <= 0:
        return None, {**unavailable, "reason": "BATTERY_CAPACITY_NOT_CONFIGURED"}

    powers = _dedupe_time_series(power_history)
    voltages = _dedupe_time_series(voltage_history)
    if not voltages:
        return None, {**unavailable, "reason": "NO_BATTERY_VOLTAGE_HISTORY"}
    latest_power = None
    if powers:
        try:
            latest_power_at = datetime.fromisoformat(str(powers[-1]["observed_at"]).replace("Z", "+00:00"))
            if latest_power_at.tzinfo is None:
                latest_power_at = latest_power_at.replace(tzinfo=timezone.utc)
            latest_power = (latest_power_at.astimezone(timezone.utc), float(powers[-1]["value"]))
        except (KeyError, TypeError, ValueError):
            latest_power = None
    if latest_power is None or not math.isfinite(latest_power[1]) or (now-latest_power[0]).total_seconds() > 120:
        return None, {**unavailable, "reason": "FRESH_CHARGE_DISCHARGE_HISTORY_REQUIRED"}

    row = conn.execute("SELECT value FROM system_state WHERE key=?", (BATTERY_ESTIMATOR_STATE_KEY,)).fetchone()
    state: dict[str, Any] | None = None
    if row:
        try:
            candidate = json.loads(row[0])
            if (isinstance(candidate, dict) and isinstance(candidate.get("anchor_at"), str)
                    and isinstance(candidate.get("last_power_at"), str)
                    and isinstance(candidate.get("last_power_w"), (int, float))
                    and isinstance(candidate.get("integrated_net_discharge_kwh"), (int, float))
                    and isinstance(candidate.get("voltage_max_v"), (int, float))):
                state = candidate
        except (TypeError, json.JSONDecodeError):
            state = None

    if state is not None and state.get("estimator_version") != 2:
        # Earlier versions anchored at voltage alone, which could pin SOC at 100%
        # through maintenance discharge. Recalibrate from a confirmed event.
        state = None

    if state is None:
        # One-time bootstrap from retained history. The old helper enforces a
        # fresh, gap-free power series following the observed voltage peak.
        initial_soc, details = _estimate_battery_soc(
            voltages, powers, capacity_kwh, minimum_soc, maximum_soc, as_of=now)
        if initial_soc is None:
            return None, details
        try:
            anchor_at = datetime.fromisoformat(str(details["anchor_at"]).replace("Z", "+00:00"))
            anchor_at = anchor_at.replace(tzinfo=anchor_at.tzinfo or timezone.utc).astimezone(timezone.utc)
        except (KeyError, TypeError, ValueError):
            return None, {**unavailable, "reason": "INVALID_VOLTAGE_ANCHOR"}
        integrated = max(0.0, (maximum_soc - initial_soc) * capacity_kwh / 100.0)
        state = {"estimator_version": 2, "anchor_at": anchor_at.isoformat(),
                 "voltage_max_v": float(details["voltage_max_30d_v"]),
                 "integrated_net_discharge_kwh": integrated,
                 "last_power_at": latest_power[0].isoformat(), "last_power_w": latest_power[1],
                 "last_sample_count": len(powers), "needs_reanchor": False}
        conn.execute("INSERT INTO system_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (BATTERY_ESTIMATOR_STATE_KEY, json.dumps(state, separators=(",", ":"))))
        return initial_soc, {**details, "state": "ESTIMATED_FROM_PERSISTED_VOLTAGE_ANCHOR_AND_POWER_INTEGRATION",
                             "reason": "PERSISTED_SHARED_PARALLEL_BUS_ANCHOR",
                             "anchor_at": state["anchor_at"],
                             "voltage_max_30d_v": round(state["voltage_max_v"], 3),
                             "integrated_net_discharge_kwh": round(integrated, 4)}

    try:
        anchor_at = datetime.fromisoformat(state["anchor_at"].replace("Z", "+00:00"))
        anchor_at = anchor_at.replace(tzinfo=anchor_at.tzinfo or timezone.utc).astimezone(timezone.utc)
        last_at = datetime.fromisoformat(state["last_power_at"].replace("Z", "+00:00"))
        last_at = last_at.replace(tzinfo=last_at.tzinfo or timezone.utc).astimezone(timezone.utc)
        last_power = float(state["last_power_w"])
        integrated = float(state["integrated_net_discharge_kwh"])
        voltage_max = float(state["voltage_max_v"])
    except (TypeError, ValueError, KeyError):
        conn.execute("DELETE FROM system_state WHERE key=?", (BATTERY_ESTIMATOR_STATE_KEY,))
        return _estimate_battery_soc_persistent(conn, voltages, powers, capacity_kwh,
                                                minimum_soc, maximum_soc, now)
    original_state = dict(state)

    # A higher voltage alone is not a new full-charge event. Re-anchor only when
    # the full-charge stabilization detector confirms a later event.
    new_anchor: tuple[datetime, float] | None = None
    _, anchor_details = _estimate_battery_soc(voltages, powers, capacity_kwh, minimum_soc, maximum_soc, as_of=now)
    try:
        candidate_at = datetime.fromisoformat(str(anchor_details.get("anchor_at", "")).replace("Z", "+00:00"))
        candidate_at = candidate_at.replace(tzinfo=candidate_at.tzinfo or timezone.utc).astimezone(timezone.utc)
        if candidate_at > anchor_at:
            new_anchor = (candidate_at, float(anchor_details["voltage_max_30d_v"]))
    except (TypeError, ValueError, KeyError):
        pass

    if new_anchor:
        anchor_at, voltage_max = new_anchor
        integrated = 0.0
        state["needs_reanchor"] = False
        # Start integrating from the first power sample at/after the voltage
        # anchor; never charge/discharge-integrate across the anchor itself.
        later_powers = []
        for point in powers:
            try:
                stamp = datetime.fromisoformat(str(point["observed_at"]).replace("Z", "+00:00"))
                stamp = stamp.replace(tzinfo=stamp.tzinfo or timezone.utc).astimezone(timezone.utc)
                value = float(point["value"])
            except (KeyError, TypeError, ValueError):
                continue
            if stamp >= anchor_at and math.isfinite(value):
                later_powers.append((stamp, value))
        if not later_powers or (later_powers[0][0] - anchor_at).total_seconds() > 180:
            state["needs_reanchor"] = True
            return None, {**unavailable, "reason": "POWER_HISTORY_DOES_NOT_COVER_VOLTAGE_ANCHOR",
                          "voltage_max_30d_v": round(voltage_max, 3), "anchor_at": anchor_at.isoformat()}
        last_at, last_power = later_powers[0]
        for sample_at, sample_power in later_powers[1:]:
            seconds = (sample_at-last_at).total_seconds()
            if seconds > 600:
                state["needs_reanchor"] = True
                break
            if seconds > 0:
                integrated += ((last_power + sample_power) / 2) * seconds / 3_600_000
            last_at, last_power = sample_at, sample_power
    elif latest_power[0] > last_at:
        next_points = []
        for point in powers:
            try:
                stamp = datetime.fromisoformat(str(point["observed_at"]).replace("Z", "+00:00"))
                stamp = stamp.replace(tzinfo=stamp.tzinfo or timezone.utc).astimezone(timezone.utc)
                value = float(point["value"])
            except (KeyError, TypeError, ValueError):
                continue
            if stamp > last_at and math.isfinite(value):
                next_points.append((stamp, value))
        previous_at, previous_power = last_at, last_power
        for sample_at, sample_power in next_points:
            seconds = (sample_at-previous_at).total_seconds()
            if seconds > 600:
                state["needs_reanchor"] = True
            elif seconds > 0 and not state.get("needs_reanchor"):
                integrated += ((previous_power + sample_power) / 2) * seconds / 3_600_000
            previous_at, previous_power = sample_at, sample_power
        last_at, last_power = latest_power

    if latest_power[0] > last_at:
        last_at, last_power = latest_power
    state.update({"estimator_version": 2, "anchor_at": anchor_at.isoformat(), "voltage_max_v": voltage_max,
                  "integrated_net_discharge_kwh": integrated,
                  "last_power_at": last_at.isoformat(), "last_power_w": last_power,
                  "last_sample_count": len(powers)})
    if state != original_state:
        conn.execute("INSERT INTO system_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (BATTERY_ESTIMATOR_STATE_KEY, json.dumps(state, separators=(",", ":"))))
    if state.get("needs_reanchor"):
        return None, {**unavailable, "reason": "GAP_IN_POWER_HISTORY_REANCHOR_REQUIRED",
                      "voltage_max_30d_v": round(voltage_max, 3), "anchor_at": anchor_at.isoformat()}
    estimated_soc = min(maximum_soc, max(0.0, maximum_soc - integrated / capacity_kwh * 100))
    return round(estimated_soc, 2), {
        "state": "ESTIMATED_FROM_PERSISTED_VOLTAGE_ANCHOR_AND_POWER_INTEGRATION",
        "reason": "PERSISTED_SHARED_PARALLEL_BUS_ANCHOR",
        "voltage_max_30d_v": round(voltage_max, 3), "anchor_at": anchor_at.isoformat(),
        "integrated_net_discharge_kwh": round(integrated, 4),
        "sample_count": len(powers), "bank_voltage_scope": "SHARED_PARALLEL_BUS",
    }


def _battery_full_voltage_plateau(voltage_history: list[dict[str, Any]],
                                  power_history: list[dict[str, Any]],
                                  current_voltage: float | None,
                                  current_charge_power: float | None,
                                  as_of: datetime | None = None) -> dict[str, Any] | None:
    """Infer a full-charge event only from a sustained local voltage ceiling and taper.

    This is display/diagnostic evidence, not a replacement for SOC integration:
    imported Cloud samples are filtered by the caller, and we require an earlier
    charging interval plus ten minutes at the learned voltage ceiling.
    """
    if (current_voltage is None or current_charge_power is None
            or abs(current_charge_power) > 10):
        return None
    now = as_of.astimezone(timezone.utc) if as_of is not None else datetime.now(timezone.utc)
    parsed_voltage: list[tuple[datetime, float]] = []
    for point in voltage_history:
        try:
            stamp = datetime.fromisoformat(str(point["observed_at"]).replace("Z", "+00:00"))
            stamp = stamp.replace(tzinfo=stamp.tzinfo or timezone.utc).astimezone(timezone.utc)
            value = float(point["value"])
            if math.isfinite(value) and value > 0:
                parsed_voltage.append((stamp, value))
        except (KeyError, TypeError, ValueError):
            continue
    parsed_power: list[tuple[datetime, float]] = []
    for point in power_history:
        try:
            stamp = datetime.fromisoformat(str(point["observed_at"]).replace("Z", "+00:00"))
            stamp = stamp.replace(tzinfo=stamp.tzinfo or timezone.utc).astimezone(timezone.utc)
            value = float(point["value"])
            if math.isfinite(value):
                parsed_power.append((stamp, value))
        except (KeyError, TypeError, ValueError):
            continue
    parsed_voltage.sort()
    parsed_power.sort()
    latest_voltage = parsed_voltage[-1] if parsed_voltage else None
    if (latest_voltage is None or (now-latest_voltage[0]).total_seconds() > 120
            or abs(latest_voltage[1]-current_voltage) > 0.2):
        return None
    local_peak = max(value for _, value in parsed_voltage)
    if current_voltage < local_peak-0.15:
        return None
    recent: list[tuple[datetime, float]] = []
    for stamp, voltage in parsed_voltage:
        if stamp < now-timedelta(minutes=20) or voltage < local_peak-0.15:
            continue
        nearest = min(parsed_power, key=lambda item: abs((item[0]-stamp).total_seconds()), default=None)
        if nearest and abs((nearest[0]-stamp).total_seconds()) <= 120 and abs(nearest[1]) <= 10:
            if recent and (stamp-recent[-1][0]).total_seconds() > 150:
                recent = []
            recent.append((stamp, voltage))
    if (len(recent) < 6 or (recent[-1][0]-recent[0][0]).total_seconds() < 600
            or (now-recent[-1][0]).total_seconds() > 120):
        return None
    charging_before = any(recent[0][0]-timedelta(minutes=30) <= stamp < recent[0][0] and power <= -20
                          for stamp, power in parsed_power)
    if not charging_before:
        return None
    return {"state": "INFERRED_FULL_FROM_VOLTAGE_PLATEAU", "confidence": "MEDIUM",
            "voltage_ceiling_v": round(local_peak, 3), "current_voltage_v": round(current_voltage, 3),
            "charge_power_w": round(current_charge_power, 1),
            "stable_minutes": round((recent[-1][0]-recent[0][0]).total_seconds()/60, 1),
            "sample_count": len(recent), "reason": "LOCAL_CHARGE_TAPER_AND_SUSTAINED_VOLTAGE_CEILING"}


def _linear_forecast(series: list[dict[str, Any]], current: float | None, max_value: float = 15.0) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    points: list[tuple[float, float]] = []
    for item in series:
        if _is_cloud_history(item):
            continue
        try:
            stamp = datetime.fromisoformat(item["observed_at"].replace("Z", "+00:00"))
            value = float(item["value"])
        except (TypeError, ValueError, KeyError):
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age_seconds = (now - stamp).total_seconds()
        if -60 <= age_seconds <= 3 * 3600 and math.isfinite(value):
            points.append((stamp.timestamp() / 3600, value / 1000 if item.get("unit") == "W" else value))
    result: dict[str, Any] = {"method": "linear_regression_last_3h", "confidence": "INSUFFICIENT_HISTORY",
                              "one_hour_value": None, "three_hour_value": None, "six_hour_value": None,
                              "hourly_values": [], "slope_per_hour": None,
                              "unit": series[-1].get("unit") if series else None}
    if len(points) < 3 or points[-1][0] - points[0][0] < (10 / 60):
        return result
    xs = [p[0] for p in points]; ys = [p[1] for p in points]
    mean_x = sum(xs) / len(xs); mean_y = sum(ys) / len(ys)
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom <= 0:
        return result
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / denom
    intercept = mean_y - slope * mean_x
    base = current / 1000 if current is not None and series[-1].get("unit") == "W" else current
    if base is None:
        base = ys[-1]
    hourly_values = [{"hours_ahead": hour,
                      "value": round(max(0.0, min(max_value, intercept + slope * (now.timestamp() / 3600 + hour))), 3),
                      "unit": "kW" if series[-1].get("unit") == "W" else series[-1].get("unit"),
                      "forecast_at": (now + timedelta(hours=hour)).isoformat(timespec="minutes")}
                     for hour in range(1, 7)]
    result.update({"confidence": "LOW_INDICATIVE", "slope_per_hour": round(slope, 3),
                   "one_hour_value": hourly_values[0]["value"],
                   "three_hour_value": hourly_values[2]["value"],
                   "six_hour_value": hourly_values[5]["value"], "hourly_values": hourly_values,
                   "baseline": round(base, 3)})
    return result


def _bounded_load_forecast(series: list[dict[str, Any]], current_w: float | None,
                           as_of: datetime | None = None) -> dict[str, Any]:
    """Forecast household load conservatively; short noisy slopes must not become trends."""
    now = as_of.astimezone(timezone.utc) if as_of else datetime.now(timezone.utc)
    buckets: dict[int, list[float]] = {}
    for item in series:
        if _is_cloud_history(item):
            continue
        try:
            stamp = datetime.fromisoformat(str(item["observed_at"]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            age = (now - stamp.astimezone(timezone.utc)).total_seconds()
            value = float(item["value"])
            if -60 <= age <= 3 * 3600 and math.isfinite(value):
                if item.get("unit") == "W":
                    value /= 1000
                buckets.setdefault(int(stamp.timestamp() // 300), []).append(value)
        except (KeyError, TypeError, ValueError):
            continue

    points = sorted((key * 300 / 3600, sorted(values)[len(values)//2])
                    for key, values in buckets.items() if values)
    unit = "kW" if series and series[-1].get("unit") == "W" else (series[-1].get("unit") if series else "kW")
    result: dict[str, Any] = {"method": "robust_recent_median_with_bounded_slope",
        "confidence": "INSUFFICIENT_HISTORY", "one_hour_value": None, "three_hour_value": None,
        "six_hour_value": None, "hourly_values": [], "slope_per_hour": None, "unit": unit}
    if len(points) < 3 or points[-1][0] - points[0][0] < 10/60:
        return result

    recent = [value for hour, value in points if hour >= points[-1][0] - 15/60]
    base = (current_w / 1000 if unit == "kW" else current_w) if current_w is not None else None
    if base is None or not math.isfinite(float(base)):
        base = sorted(recent)[len(recent)//2] if recent else points[-1][1]
    base = max(0.0, float(base))
    pair_slopes = sorted((b[1]-a[1])/(b[0]-a[0]) for index,a in enumerate(points)
                         for b in points[index+1:] if b[0] > a[0])
    slope = pair_slopes[len(pair_slopes)//2] if pair_slopes else 0.0
    deadband = max(0.05, base * 0.05)
    if abs(slope) <= deadband:
        slope = 0.0
    # Even a persistent trend is allowed to move the six-hour outlook by at
    # most 25% of the baseline (or 0.2 kW for very small loads).
    total_change_limit = max(0.2, base * 0.25)
    slope = max(-total_change_limit/6, min(total_change_limit/6, slope))
    hourly = [{"hours_ahead": hour, "value": round(max(0.0, base+slope*hour), 3), "unit": unit,
               "forecast_at": (now+timedelta(hours=hour)).isoformat(timespec="minutes")}
              for hour in range(1,7)]
    result.update({"confidence":"LOW_INDICATIVE", "slope_per_hour":round(slope,3),
                   "one_hour_value":hourly[0]["value"], "three_hour_value":hourly[2]["value"],
                   "six_hour_value":hourly[5]["value"], "hourly_values":hourly,
                   "baseline":round(base,3)})
    return result


def build_dispatch_plan(current: dict[str, Any], config: dict[str, Any], *, sample_state: str = "UNKNOWN",
                        telemetry_trust: str = "LIVE_UNVERIFIED", forecast_surplus_w: int | None = None,
                        tesla_presence: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compute conservative load allocations; this function never sends commands."""
    automation = config.get("automation", {})
    manager = config.get("surplus_manager", {})
    common = {"decision_interval_seconds": automation.get("decision_interval_seconds", 300), "actions": [],
              "mode": "FORECAST_GUIDED" if manager.get("enabled") else "MEASURED_SURPLUS"}
    if not automation.get("enabled"):
        return {**common, "state": "DISABLED", "reason": "Owner has not enabled automatic dispatch."}
    if manager.get("manual_override"):
        return {**common, "state": "MANUAL_OVERRIDE", "reason": "Ação manual do Owner: o despacho automático está suspenso até retomar Automático."}
    if not automation.get("commissioned") or not automation.get("deye_map_verified"):
        return {**common, "state": "BLOCKED_NOT_COMMISSIONED", "reason": "Owner commissioning and physical Deye map confirmation are required."}
    if sample_state != "LIVE":
        return {**common, "state": "BLOCKED_STALE_TELEMETRY", "reason": "A fresh Deye sample is required."}
    if telemetry_trust not in {"PHYSICALLY_CORROBORATED", "OWNER_COMMISSIONED"}:
        return {**common, "state": "BLOCKED_UNTRUSTED_TELEMETRY", "reason": "Control readings are not physically commissioned."}
    # Automatic dispatch never uses the inverter's reported SOC as a fallback.
    # SOC must come from the Gateway's confirmed full-charge anchor and energy integration.
    allowed_soc_sources = {"gateway_energy_integrated"}
    if manager.get("enabled"):
        allowed_soc_sources.add("gateway_voltage_plateau_inferred")
    if (current.get("battery_soc_percent") is None
            or current.get("battery_soc_source") not in allowed_soc_sources
            or current.get("pv_power_w") is None or current.get("load_power_w") is None):
        return {**common, "state": "BLOCKED_MISSING_TELEMETRY", "reason": "SOC, PV and load power are all required."}
    if current.get("battery_charge_headroom_kwh_to_maximum") is None:
        return {**common, "state": "BLOCKED_BATTERY_CONFIGURATION", "reason": "Configure battery bank capacity and SOC limits first."}
    if manager.get("enabled"):
        reserve = float(manager.get("battery_reserve_soc_percent", 70))
        soc = current.get("battery_soc_percent")
        if isinstance(soc, bool) or not isinstance(soc, (int, float)) or soc < reserve:
            shed = [{"load_id": load["id"], "name": load["name"],
                     "state": "STOP_FOR_BATTERY" if load["control_type"] == "antminer_braiins" else "OFF_FOR_BATTERY",
                     "target_power_w": 0, "control_type": load["control_type"],
                     "requires_load_id": load.get("requires_load_id")}
                    for load in config.get("loads", []) if load.get("enabled") and load.get("automatic")
                    and load.get("control_type") in {"tuya_smart", "tuya_breaker", "antminer_braiins"}]
            return {**common, "state": "WAITING_FOR_BATTERY_RESERVE",
                    "reason": f"A bateria tem de estar acima da reserva configurada ({reserve:g}%).",
                    "actions": shed}
        if forecast_surplus_w is None:
            return {**common, "state": "BLOCKED_FORECAST_UNAVAILABLE",
                    "reason": "O Engine ainda não tem uma previsão fiável de produção e consumo para orientar o plano."}
    if (current["battery_charge_headroom_kwh_to_maximum"] > 0.02
            or (current.get("battery_charge_power_w") or 0) > 100
            or (current.get("battery_discharge_power_w") or 0) > 100):
        shed_actions = []
        for load in config.get("loads", []):
            if load.get("enabled") and load.get("automatic") and load.get("control_type") in {"tuya_smart", "tuya_breaker", "antminer_braiins"}:
                shed_actions.append({"load_id": load["id"], "name": load["name"],
                                     "state": "STOP_FOR_BATTERY" if load["control_type"] == "antminer_braiins" else "OFF_FOR_BATTERY",
                                     "target_power_w": 0, "control_type": load["control_type"],
                                     "requires_load_id": load.get("requires_load_id")})
        return {**common, "state": "WAITING_FOR_BATTERY", "reason": "Battery charging headroom takes priority; flexible loads are being shed.",
                "actions": shed_actions}
    battery_power = current.get("battery_power_w")
    if battery_power is None:
        return {**common, "state": "BLOCKED_MISSING_TELEMETRY", "reason": "Battery charge/discharge power is required to estimate surplus."}
    surplus = max(0, round(current["pv_power_w"] - current["load_power_w"] + battery_power))
    margin = int(automation.get("surplus_margin_w", 250))
    available = max(0, surplus - margin)
    if manager.get("enabled"):
        potential_minimum = int(manager.get("minimum_potential_surplus_w", 800))
        if forecast_surplus_w < potential_minimum:
            available = 0
        else:
            # Forecasts can guide the planned load, but never authorize more
            # demand than the live inverter measurements currently corroborate.
            available = min(available, max(0, forecast_surplus_w - margin))
    actions = []
    actions_by_id: dict[str, dict[str, Any]] = {}
    configured_profile = manager.get("priority_profile", "tesla_home")
    presence_state = tesla_presence.get("state") if isinstance(tesla_presence, dict) else None
    profile = ("tesla_home" if presence_state == "DETECTED" else
               "tesla_away" if presence_state == "NOT_DETECTED" else configured_profile) if manager.get("enabled") else None
    priority_orders = {
        "tesla_home": {"ev_charger": 0, "water_heater": 1, "underfloor_heating": 2, "generic": 3, "miner": 4},
        "tesla_away": {"miner": 0, "water_heater": 1, "underfloor_heating": 2, "generic": 3, "ev_charger": 4},
    }
    profile_order = priority_orders.get(profile, {})
    loads = config.get("loads", [])
    disabled_ids: set[str] = set()
    if profile == "tesla_home":
        disabled_ids.update(item.get("requires_load_id") for item in loads
                            if item.get("kind") == "miner" and item.get("requires_load_id"))
    if profile == "tesla_away":
        disabled_ids.update(item.get("requires_load_id") for item in loads
                            if item.get("kind") == "ev_charger" and item.get("requires_load_id"))
    dependent_ids = {item.get("requires_load_id") for item in loads if item.get("requires_load_id")}
    dependency_rank: dict[str, int] = {}
    for item in loads:
        dependency_id = item.get("requires_load_id")
        if dependency_id:
            dependency_rank[dependency_id] = min(dependency_rank.get(dependency_id, 100),
                                                 profile_order.get(item.get("kind"), 3))
    ordered_loads = sorted(loads, key=lambda item: (
        dependency_rank.get(item.get("id"), profile_order.get(item.get("kind"), 3)),
        0 if item.get("id") in dependent_ids else 1,
        item.get("priority", 100), item.get("id", "")))
    for load in ordered_loads:
        if not load.get("enabled") or not load.get("automatic"):
            continue
        control = load.get("control_type")
        dependency_id = load.get("requires_load_id")
        if manager.get("enabled") and load.get("id") in disabled_ids:
            action = {"load_id": load["id"], "name": load["name"],
                      "state": "OFF_FOR_TESLA_HOME" if profile == "tesla_home" else "OFF_TESLA_AWAY",
                      "target_power_w": 0, "control_type": control}
            actions.append(action); actions_by_id[load["id"]] = action
            continue
        if manager.get("enabled") and profile == "tesla_home" and load.get("kind") == "miner":
            action = {"load_id": load["id"], "name": load["name"], "state": "STOP_FOR_TESLA_HOME",
                      "target_power_w": 0, "control_type": control}
            actions.append(action); actions_by_id[load["id"]] = action
            continue
        if manager.get("enabled") and profile == "tesla_away" and load.get("kind") == "ev_charger":
            action = {"load_id": load["id"], "name": load["name"], "state": "OFF_TESLA_AWAY",
                      "target_power_w": 0, "control_type": control}
            actions.append(action); actions_by_id[load["id"]] = action
            continue
        if control == "manual":
            action = {"load_id": load["id"], "name": load["name"], "state": "SKIPPED_MANUAL", "target_power_w": 0}
            actions.append(action); actions_by_id[load["id"]] = action
            continue
        if control == "tesla_fleet" or load.get("kind") == "ev_charger":
            action = {"load_id": load["id"], "name": load["name"], "state": "BLOCKED_CONTROL_UNAVAILABLE",
                      "reason": "A API Tesla disponível está em modo de leitura; controlo da corrente de carga não está configurado.",
                      "target_power_w": 0}
            actions.append(action); actions_by_id[load["id"]] = action
            continue
        if control == "antminer_braiins":
            minimum = max(1, load.get("minimum_power_w", 1))
            meter = current.get("tuya_load_telemetry", {}).get(load.get("id"), {})
            measured = meter.get("metrics", {}).get("power", {}) if meter.get("fresh") else {}
            baseline = max(0, round(float(measured.get("value", 0)))) if measured.get("unit") == "W" else 0
            target = min(load.get("maximum_power_w", 2900), baseline + available)
            target = target if target >= minimum else 0
            if target and dependency_id and actions_by_id.get(dependency_id, {}).get("state") != "ON":
                action = {"load_id": load["id"], "name": load["name"], "state": "BLOCKED_RELAY_NOT_READY",
                          "target_power_w": target, "control_type": control, "requires_load_id": dependency_id}
                actions.append(action); actions_by_id[load["id"]] = action
                continue
            if target:
                available -= target
            action = {"load_id": load["id"], "name": load["name"], "state": "TARGET" if target else "BELOW_MINIMUM_SURPLUS",
                      "target_power_w": target, "control_type": control,
                      "measured_power_w": baseline if meter.get("fresh") else None,
                      "tuya_telemetry_fresh": bool(meter.get("fresh"))}
            actions.append(action); actions_by_id[load["id"]] = action
            continue
        rated = load.get("rated_power_w", load.get("maximum_power_w", 0))
        meter = current.get("tuya_load_telemetry", {}).get(load.get("id"), {})
        observed_on = meter.get("switch_on") if meter.get("fresh") else None
        measured = meter.get("metrics", {}).get("power", {}) if meter.get("fresh") else {}
        measured_power = measured.get("value") if measured.get("unit") == "W" else None
        turn_on = observed_on is True or available >= rated
        if turn_on and observed_on is not True:
            available -= rated
        action = {"load_id": load["id"], "name": load["name"],
                  "state": "ON" if turn_on else "WAITING_FOR_SURPLUS",
                  "target_power_w": round(measured_power) if turn_on and observed_on is True and measured_power is not None else rated if turn_on else 0,
                  "control_type": control, "observed_switch_on": observed_on,
                  "measured_power_w": measured_power, "tuya_telemetry_fresh": bool(meter.get("fresh"))}
        actions.append(action); actions_by_id[load["id"]] = action
    return {**common, "state": "PLAN_READY", "reason": "A previsão orienta o plano; a telemetria real limita a potência e confirma as condições de segurança.",
            "tesla_presence": presence_state or "UNKNOWN", "effective_priority_profile": profile,
            "estimated_surplus_w": surplus, "potential_surplus_w": forecast_surplus_w if manager.get("enabled") else None,
            "safety_margin_w": margin,
            "unallocated_surplus_w": available, "actions": actions}


def build_summary(conn: sqlite3.Connection, history_hours: int = 24,
                  latest_sample: dict[str, Any] | None = None,
                  history_until: datetime | None = None) -> dict[str, Any]:
    energy_registry.ensure_schema(conn)
    _ensure_solar_forecast_history(conn)
    _merge_single_cloud_device_history(conn)
    equipment = energy_registry.list_equipment(conn)
    inverter_candidates = [e for e in equipment if e["category"] == "inversores" and e["id"].startswith("deye-inverter-")]
    battery_candidates = [e for e in equipment if e["category"] == "baterias" and e["id"].startswith("deye-battery-")]
    inverter = next((e for e in inverter_candidates if e.get("protocol") == "Modbus TCP FC03"),
                    next((e for e in inverter_candidates if e.get("readings")), None))
    battery = next((e for e in battery_candidates if e.get("protocol") == "Modbus TCP FC03"),
                   next((e for e in battery_candidates if e.get("readings")), None))
    inverter_readings = _reading_map(inverter["readings"] if inverter else [])
    battery_readings = _reading_map(battery["readings"] if battery else [])
    # A fresh half-minute sample is held in RAM between durable minute writes.
    # It may update the live card, but never changes historical rows or trust.
    if isinstance(latest_sample, dict) and isinstance(latest_sample.get("metrics"), list):
        sampled_at = latest_sample.get("sampled_at")
        for metric in latest_sample["metrics"]:
            if not isinstance(metric, dict) or not isinstance(metric.get("field"), str):
                continue
            target = inverter_readings if metric.get("category") == "inversores" else battery_readings if metric.get("category") == "baterias" else None
            if target is None or isinstance(metric.get("value"), bool) or not isinstance(metric.get("value"), (int, float)):
                continue
            target[metric["field"]] = {"field": metric["field"], "value": metric["value"],
                                        "unit": metric.get("unit"), "observed_at": sampled_at,
                                        "source": "DEYE_MODBUS_FC03_CANDIDATE_MAP", "trust": "LIVE_UNVERIFIED",
                                        "evidence": {"register": metric.get("register"), "label": metric.get("label")}}
    config = get_config(conn)
    presence_row = conn.execute("SELECT value FROM system_state WHERE key='energy_tesla_presence'").fetchone()
    try:
        tesla_presence = json.loads(presence_row[0]) if presence_row else None
        checked_at = datetime.fromisoformat(str((tesla_presence or {}).get("checked_at", "")).replace("Z", "+00:00"))
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        presence_age = (datetime.now(timezone.utc) - checked_at).total_seconds()
        if not 0 <= presence_age <= 180 or (tesla_presence or {}).get("state") not in {"DETECTED", "NOT_DETECTED"}:
            tesla_presence = {"state": "UNKNOWN", "checked_at": None, "reason": "stale_or_unavailable"}
    except (TypeError, ValueError, json.JSONDecodeError):
        tesla_presence = {"state": "UNKNOWN", "checked_at": None, "reason": "stale_or_unavailable"}
    configured_pv_strings = [item for item in config.get("pv_strings", [])
                             if isinstance(item, dict) and item.get("active", True)]
    mppt_capacity_kw: dict[int, float] = {1: 0.0, 2: 0.0}
    for item in configured_pv_strings:
        try:
            item_capacity = float(item.get("nominal_power_kw") or
                                  (float(item.get("panel_count", 0)) * float(item.get("panel_power_w", 0)) / 1000))
            channel = int(item.get("mppt"))
            if item_capacity > 0 and channel in mppt_capacity_kw:
                mppt_capacity_kw[channel] += item_capacity
        except (TypeError, ValueError):
            continue
    string_capacity_kw = sum(mppt_capacity_kw.values())
    # The string inventory is the source of truth when present. Keep the legacy
    # aggregate as a migration fallback for installations not yet configured by string.
    effective_pv_capacity_kw = string_capacity_kw if string_capacity_kw > 0 else config.get("pv_capacity_kw")
    history_end = history_until.astimezone(timezone.utc) if history_until else None
    history_end_text = history_end.isoformat(timespec="microseconds") if history_end else None
    cutoff_base = history_end or datetime.now(timezone.utc)
    cutoff = (cutoff_base - timedelta(hours=history_hours)).isoformat(timespec="microseconds")
    ids = [e["id"] for e in (inverter, battery) if e]
    series_fields = ("pv_total_power", "pv_daily_energy", "pv1_input_power", "pv1_voltage", "pv1_current",
                     "pv2_input_power", "pv2_voltage", "pv2_current", "load_total_power",
                     "battery_output_power")
    history = {field: _series(conn, ids, field, cutoff, until=history_end_text) for field in series_fields}
    forecast_rows = conn.execute(
        "SELECT estimated_total_kwh,actual_today_kwh,remaining_estimate_kwh,calculated_at,confidence,potential_max_total_kwh "
        "FROM energy_solar_day_forecasts WHERE calculated_at>=?" + (" AND calculated_at<=?" if history_end_text else "") +
        " ORDER BY calculated_at", (cutoff, history_end_text) if history_end_text else (cutoff,)).fetchall()
    history["solar_day_forecast"] = [{"value": row[0], "unit": "kWh", "observed_at": row[3],
                                      "actual_today_kwh": row[1], "remaining_estimate_kwh": row[2],
                                      "confidence": row[4], "potential_max_total_kwh": row[5]} for row in forecast_rows]
    autonomy_cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="microseconds")
    autonomy_load_history = _series(conn, [inverter["id"]] if inverter else [], "load_total_power",
                                    autonomy_cutoff, limit=12000)
    if isinstance(latest_sample, dict) and isinstance(latest_sample.get("metrics"), list):
        sampled_at = latest_sample.get("sampled_at")
        for metric in latest_sample["metrics"]:
            if (isinstance(metric, dict) and metric.get("category") == "inversores"
                    and metric.get("field") == "load_total_power"
                    and isinstance(metric.get("value"), (int, float)) and not isinstance(metric.get("value"), bool)):
                autonomy_load_history.append({"value": float(metric["value"]), "observed_at": sampled_at,
                                              "source": "LIVE_SAMPLE", "trust": "LIVE_UNVERIFIED"})
    autonomy_load_history = _dedupe_time_series(autonomy_load_history)
    # The battery estimator bootstraps from the highest battery voltage observed
    # in the preceding 30 days, then persists that shared-bank anchor and integrates
    # only new signed charge/discharge samples. Keep minute samples for bootstrap.
    battery_cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat(timespec="microseconds")
    battery_voltage_history = _series(conn, [battery["id"]] if battery else [], "battery_voltage", battery_cutoff, limit=150000)
    battery_power_history = _series(conn, [battery["id"]] if battery else [], "battery_output_power", battery_cutoff, limit=150000)
    # Cloud history is valuable for solar/load learning, but it is not a live
    # coulomb-counting stream and must not anchor or advance the current SOC.
    battery_voltage_history = [point for point in battery_voltage_history
                               if point.get("source") != "DEYE_CLOUD_HISTORY"]
    battery_power_history = [point for point in battery_power_history
                             if point.get("source") != "DEYE_CLOUD_HISTORY"]
    if isinstance(latest_sample, dict) and isinstance(latest_sample.get("metrics"), list):
        sample_time = latest_sample.get("sampled_at")
        for metric in latest_sample["metrics"]:
            if (isinstance(metric, dict) and metric.get("category") == "baterias"
                    and metric.get("field") in {"battery_voltage", "battery_output_power"}
                    and isinstance(metric.get("value"), (int, float)) and not isinstance(metric.get("value"), bool)):
                target = battery_voltage_history if metric["field"] == "battery_voltage" else battery_power_history
                target.append({"value": float(metric["value"]), "observed_at": sample_time,
                               "source": "LIVE_SAMPLE", "trust": "LIVE_UNVERIFIED"})
    battery_voltage_history = _dedupe_time_series(battery_voltage_history)
    battery_power_history = _dedupe_time_series(battery_power_history)
    pv = _number(inverter_readings, "pv_total_power")
    load = _number(inverter_readings, "load_total_power")
    all_banks = config.get("battery_banks", [])
    banks = [bank for bank in all_banks if bank.get("active", True)]
    capacity = (sum(float(bank["capacity_kwh"]) for bank in banks) if banks
                else None if all_banks else config["battery_capacity_kwh"])
    min_soc = float(config["minimum_soc_percent"])
    max_soc = float(config["maximum_soc_percent"])
    if banks:
        min_soc = sum(float(bank["capacity_kwh"]) * float(bank["minimum_soc_percent"]) for bank in banks) / capacity
        max_soc = min(float(bank["maximum_soc_percent"]) for bank in banks)
    available = None
    charge_headroom = None
    bank_summary = []
    # SOC is derived only from a Gateway-confirmed full-charge anchor followed by
    # integration of battery power. Deye's percentage register is not a fallback.
    soc, soc_estimate = _estimate_battery_soc_persistent(
        conn, battery_voltage_history, battery_power_history, capacity, 0.0, max_soc)
    battery_voltage = _number(battery_readings, "battery_voltage")
    battery_charge_power = _number(battery_readings, "battery_charge_power")
    voltage_item = battery_readings.get("battery_voltage")
    charge_item = battery_readings.get("battery_charge_power")
    def fresh_local(item: dict[str, Any] | None) -> bool:
        if not isinstance(item, dict) or item.get("source") == "DEYE_CLOUD_HISTORY":
            return False
        stamp = _parse_utc(item.get("observed_at"))
        return stamp is not None and 0 <= (datetime.now(timezone.utc)-stamp).total_seconds() <= 120
    voltage_plateau = (_battery_full_voltage_plateau(
        battery_voltage_history, battery_power_history, battery_voltage, battery_charge_power)
        if fresh_local(voltage_item) and fresh_local(charge_item) else None)
    inferred_voltage_full = soc is None and voltage_plateau is not None
    displayed_soc = soc if soc is not None else max_soc if inferred_voltage_full else None
    displayed_soc_source = ("gateway_energy_integrated" if soc is not None else
                            "gateway_voltage_plateau_inferred" if inferred_voltage_full else
                            "unavailable")
    if inferred_voltage_full:
        soc_estimate = {**soc_estimate, **voltage_plateau,
                        "reason": "VOLTAGE_PLATEAU_CONFIRMED_WITH_LOCAL_CHARGE_TAPER"}
    if displayed_soc is not None and banks:
        capacity = sum(float(bank["capacity_kwh"]) for bank in banks)
        bank_summary = [{**bank, "estimated_soc_percent": displayed_soc if bank.get("active", True) else None,
                         "voltage_max_30d_v": soc_estimate.get("voltage_max_30d_v"),
                         "soc_estimate_state": soc_estimate.get("state"),
                         "energy_above_minimum_kwh": round(bank["capacity_kwh"] * max(0.0, displayed_soc-bank["minimum_soc_percent"]) / 100, 3) if bank.get("active", True) else 0.0,
                         "charge_headroom_kwh": round(bank["capacity_kwh"] * max(0.0, bank["maximum_soc_percent"]-displayed_soc) / 100, 3) if bank.get("active", True) else 0.0}
                        for bank in all_banks]
        available = round(sum(item["energy_above_minimum_kwh"] for item in bank_summary), 3)
        charge_headroom = round(sum(item["charge_headroom_kwh"] for item in bank_summary), 3)
        min_soc = round(sum(b["capacity_kwh"] * b["minimum_soc_percent"] for b in banks) / capacity, 2)
        max_soc = min(float(b["maximum_soc_percent"]) for b in banks)
    elif displayed_soc is not None and capacity is not None:
        available = round(float(capacity) * max(0.0, displayed_soc - min_soc) / 100.0, 3)
        charge_headroom = round(float(capacity) * max(0.0, max_soc - displayed_soc) / 100.0, 3)
    battery_autonomy = _estimate_battery_autonomy(available, load, autonomy_load_history)
    latest_at = max((r.get("observed_at", "") for r in [*inverter_readings.values(), *battery_readings.values()]), default=None)
    forecast = _linear_forecast(history["pv_total_power"], pv, 15.0)
    load_forecast = _bounded_load_forecast(history["load_total_power"], load)
    # Never train or project operational SOC from the Deye-reported SOC.
    soc_forecast = _linear_forecast([], soc, 100.0)
    weather = _solar_weather(config.get("site_latitude"), config.get("site_longitude"))
    weather_current: dict[str, Any] | None = None
    if weather and weather.get("state") == "available":
        now = datetime.now(timezone.utc)
        weather_points = []
        for point in weather.get("hourly", []):
            try:
                stamp = datetime.fromisoformat(str(point.get("observed_at", "")).replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
            if point.get("temperature_c") is not None or point.get("weather_code") is not None:
                weather_points.append((abs((stamp - now).total_seconds()), stamp, point))
        if weather_points:
            _, stamp, point = min(weather_points, key=lambda item: item[0])
            weather_current = {"observed_at": stamp.astimezone(timezone.utc).isoformat(timespec="minutes"),
                               "temperature_c": point.get("temperature_c"),
                               "apparent_temperature_c": point.get("apparent_temperature_c"),
                               "relative_humidity_percent": point.get("relative_humidity_percent"),
                               "cloud_cover_percent": point.get("cloud_cover_percent"),
                               "wind_speed_kmh": point.get("wind_speed_kmh"),
                               "weather_code": point.get("weather_code")}
        if string_capacity_kw > 0:
            modeled_hourly = []
            for point in weather.get("hourly", []):
                by_mppt, effective_irradiance = _point_pv_irradiance(
                    point, configured_pv_strings, config.get("site_latitude"), config.get("site_longitude"))
                modeled_hourly.append({**point, "pv_irradiance_by_mppt_w_m2": by_mppt,
                                       "pv_effective_irradiance_w_m2": effective_irradiance})
            weather = {**weather, "hourly": modeled_hourly}
    potential_points: list[dict[str, Any]] = []
    solar_expected_points: list[dict[str, Any]] = []
    solar_model: dict[str, Any] = {"performance_ratio": None, "sample_count": 0, "new_samples": 0}
    if weather and weather.get("state") == "available" and effective_pv_capacity_kw is not None:
        peak_kw = float(effective_pv_capacity_kw)
        efficiency = float(config.get("pv_system_efficiency", 0.85))
        solar_model = _learn_solar_performance(conn, weather, inverter, battery, peak_kw, efficiency,
                                               max_soc, capacity, mppt_capacity_kw if string_capacity_kw > 0 else None)
        now = datetime.now(timezone.utc)
        for point in weather["hourly"]:
            radiation = point.get("shortwave_radiation_w_m2")
            if not isinstance(radiation, (int, float)) or isinstance(radiation, bool):
                continue
            stamp = datetime.fromisoformat(point["observed_at"].replace("Z", "+00:00"))
            hours = (stamp - now).total_seconds() / 3600
            if hours >= -3.1:
                by_mppt = point.get("pv_irradiance_by_mppt_w_m2")
                if isinstance(by_mppt, dict) and string_capacity_kw > 0:
                    potential_kw = round(sum(mppt_capacity_kw[channel] * float(by_mppt.get(str(channel), radiation))
                                             / 1000 * efficiency for channel in (1, 2)), 3)
                else:
                    potential_kw = round(peak_kw * float(point.get("pv_effective_irradiance_w_m2", radiation)) / 1000 * efficiency, 3)
                potential_points.append({"observed_at": point["observed_at"], "value": potential_kw,
                                         "unit": "kW", "segment": "forecast" if hours > -1 else "historical"})
        for point in potential_points:
            if point["segment"] == "forecast":
                solar_expected_points.append({**point, "value": round(point["value"] * solar_model["performance_ratio"], 3)})
    elif weather:
        weather = {**weather, "state": "needs_pv_capacity"}
    solar_day_forecast = _solar_day_forecast(
        conn, inverter, inverter_readings, weather, effective_pv_capacity_kw,
        float(config.get("pv_system_efficiency", 0.85)), solar_model)
    # Keep the plotted maximum at least as high as verified local production,
    # even when the daily-energy counter is unavailable and the daily estimate
    # cannot be computed. Use the daily adjustment when available, otherwise
    # fall back to the Engine's learned installation performance.
    potential_adjustment = solar_day_forecast.get("potential_adjustment_factor")
    if not isinstance(potential_adjustment, (int, float)) or isinstance(potential_adjustment, bool) or not math.isfinite(potential_adjustment):
        potential_adjustment = solar_model.get("performance_ratio", 1.0)
    if not isinstance(potential_adjustment, (int, float)) or isinstance(potential_adjustment, bool) or not math.isfinite(potential_adjustment):
        potential_adjustment = 1.0
    potential_points = _apply_observed_potential_floor(
        potential_points, history.get("pv_total_power", []), potential_adjustment)
    if solar_day_forecast.get("state") == "ESTIMATED":
        # Apply the same forecast calibration to the plotted likely-production curve.
        expected_scale = solar_day_forecast.get("forecast_calibration_factor", 1.0)
        if isinstance(expected_scale, (int, float)) and not isinstance(expected_scale, bool) and math.isfinite(expected_scale):
            solar_expected_points = [{**point, "value": round(float(point["value"]) * max(0.0, min(1.5, expected_scale)), 3)}
                                     for point in solar_expected_points]
    # Refresh the measured-to-now part from the latest telemetry on every summary
    # request, even when the weather-based remainder is inside its 10-minute cache.
    daily_reading = inverter_readings.get("pv_daily_energy")
    if solar_day_forecast.get("state") == "ESTIMATED" and isinstance(daily_reading, dict):
        measured = daily_reading.get("value")
        measured_at = _parse_utc(daily_reading.get("observed_at"))
        current_utc = datetime.now(timezone.utc)
        if (isinstance(measured, (int, float)) and not isinstance(measured, bool)
                and math.isfinite(measured) and measured >= 0 and measured_at is not None
                and 0 <= (current_utc-measured_at).total_seconds() <= 1200):
            remaining_solar = max(0.0, float(solar_day_forecast.get("remaining_estimate_kwh") or 0.0))
            remaining_potential = max(0.0, float(solar_day_forecast.get("potential_max_remaining_kwh") or 0.0))
            live_estimate_total = float(measured) + remaining_solar
            live_forecast = {**solar_day_forecast, "actual_today_kwh": round(float(measured), 2),
                             "estimated_total_kwh": round(live_estimate_total, 2),
                             "potential_max_total_kwh": round(float(measured) + remaining_potential, 2),
                             "live_measurement_at": daily_reading.get("observed_at"),
                             "calculated_at": current_utc.isoformat(timespec="seconds")}
            live_mae = solar_day_forecast.get("forecast_error_mae_kwh")
            if isinstance(live_mae, (int, float)) and not isinstance(live_mae, bool) and math.isfinite(live_mae):
                live_forecast["estimated_total_low_kwh"] = round(max(float(measured), live_estimate_total-float(live_mae)), 2)
                live_forecast["estimated_total_high_kwh"] = round(live_estimate_total+float(live_mae), 2)
            solar_day_forecast = live_forecast
    current_load_reading = inverter_readings.get("load_total_power")
    current_load_stamp = _parse_utc(current_load_reading.get("observed_at")) if isinstance(current_load_reading, dict) else None
    current_load_for_projection = (load if current_load_stamp is not None
                                   and 0 <= (datetime.now(timezone.utc)-current_load_stamp).total_seconds() <= 120
                                   else None)
    remaining_load_forecast = _estimate_remaining_load_to_day_end(
        autonomy_load_history, current_load_for_projection,
        weather.get("timezone") if isinstance(weather, dict) else None)
    projection_now = datetime.now(timezone.utc)
    try:
        projection_tz = ZoneInfo(weather.get("timezone")) if isinstance(weather, dict) and isinstance(weather.get("timezone"), str) else projection_now.astimezone().tzinfo
    except (ZoneInfoNotFoundError, ValueError):
        projection_tz = projection_now.astimezone().tzinfo or timezone.utc
    projection_day_end = datetime.combine(projection_now.astimezone(projection_tz).date() + timedelta(days=1),
                                          datetime.min.time(), tzinfo=projection_tz).astimezone(timezone.utc)
    current_pv_reading = inverter_readings.get("pv_total_power")
    current_pv_stamp = _parse_utc(current_pv_reading.get("observed_at")) if isinstance(current_pv_reading, dict) else None
    current_pv_for_projection = (pv / 1000.0 if current_pv_stamp is not None
                                 and 0 <= (projection_now-current_pv_stamp).total_seconds() <= 120 else None)
    solar_projection_15m = _engine_quarter_hour_projection(
        projection_now, solar_expected_points, potential_points,
        remaining_load_forecast.get("profile", []), day_end=projection_day_end,
        actual_today_kwh=solar_day_forecast.get("actual_today_kwh"),
        expected_remaining_kwh=solar_day_forecast.get("remaining_estimate_kwh"),
        potential_remaining_kwh=solar_day_forecast.get("potential_max_remaining_kwh"),
        expected_load_remaining_kwh=(remaining_load_forecast.get("remaining_kwh")
                                     if remaining_load_forecast.get("state") == "ESTIMATED" else None),
        current_pv_kw=current_pv_for_projection,
        confidence=solar_day_forecast.get("confidence", "LOW_INDICATIVE"))
    if solar_day_forecast.get("state") == "ESTIMATED" and remaining_load_forecast.get("state") == "ESTIMATED":
        pv_remaining = max(0.0, float(solar_day_forecast.get("remaining_estimate_kwh") or 0.0))
        potential_remaining = max(0.0, float(solar_day_forecast.get("potential_max_remaining_kwh") or 0.0))
        expected_load_remaining = float(remaining_load_forecast["remaining_kwh"])
        expected_balance = pv_remaining - expected_load_remaining
        potential_balance = potential_remaining - expected_load_remaining
        solar_day_forecast = {**solar_day_forecast,
                              "expected_load_remaining_kwh": round(expected_load_remaining, 2),
                              "energy_after_expected_load_kwh": round(max(0.0, expected_balance), 2),
                              "expected_energy_deficit_kwh": round(max(0.0, -expected_balance), 2),
                              "potential_energy_after_expected_load_kwh": round(max(0.0, potential_balance), 2),
                              "net_energy_balance_kwh": round(expected_balance, 2),
                              "load_forecast_confidence": remaining_load_forecast["confidence"],
                              "load_forecast_method": remaining_load_forecast["method"],
                              "load_forecast_profile": remaining_load_forecast["profile"]}
    else:
        solar_day_forecast = {**solar_day_forecast,
                              "expected_load_remaining_kwh": None,
                              "energy_after_expected_load_kwh": None,
                              "expected_energy_deficit_kwh": None,
                              "potential_energy_after_expected_load_kwh": None,
                              "net_energy_balance_kwh": None,
                              "load_forecast_confidence": remaining_load_forecast.get("confidence", "LOW"),
                              "load_forecast_reason": remaining_load_forecast.get("reason", "SOLAR_FORECAST_UNAVAILABLE")}
    max_charge_current = _number(battery_readings, "battery_max_charge_current")
    max_discharge_current = _number(battery_readings, "battery_max_discharge_current")
    battery_at_max = displayed_soc is not None and (all(displayed_soc >= float(b["maximum_soc_percent"]) for b in banks) if banks else displayed_soc >= max_soc)
    projected_potential_kw = None
    if solar_projection_15m.get("state") == "ESTIMATED" and solar_projection_15m.get("values"):
        candidate_potential = solar_projection_15m["values"][0].get("solar_potential_power_kw")
        if isinstance(candidate_potential, (int, float)) and not isinstance(candidate_potential, bool) and math.isfinite(candidate_potential):
            projected_potential_kw = float(candidate_potential)
    charge_stamp = _parse_utc((battery_readings.get("battery_charge_power") or {}).get("observed_at"))
    charge_is_fresh = charge_stamp is not None and 0 <= (datetime.now(timezone.utc) - charge_stamp).total_seconds() <= 120
    curtailment_assessment = {"state": "INSUFFICIENT_DATA", "confidence": "NONE",
                              "reason": "Leituras recentes de FV, carga, bateria ou potencial não disponíveis.",
                              "evidence": {"pv_load_fresh": current_pv_for_projection is not None and current_load_for_projection is not None,
                                           "battery_at_configured_maximum": battery_at_max,
                                           "battery_charge_fresh": charge_is_fresh,
                                           "engine_potential_kw": round(projected_potential_kw, 3) if projected_potential_kw is not None else None}}
    if (current_pv_for_projection is not None and current_load_for_projection is not None
            and projected_potential_kw is not None and projected_potential_kw >= 0.2
            and battery_at_max and charge_is_fresh and battery_charge_power is not None):
        observed_ratio = current_pv_for_projection / projected_potential_kw
        current_load_kw = current_load_for_projection / 1000.0
        demand_can_use_potential = current_load_kw >= projected_potential_kw * 0.90
        if abs(battery_charge_power) <= 20 and observed_ratio < 0.70 and not demand_can_use_potential:
            curtailment_assessment = {"state": "POSSIBLE_CURTAILMENT", "confidence": "MEDIUM",
                "reason": "Bateria no máximo confirmado, carga quase nula e FV medido abaixo do potencial do Engine.",
                "evidence": {"pv_load_fresh": True, "pv_measured_kw": round(current_pv_for_projection, 3),
                             "pv_potential_kw": round(projected_potential_kw, 3),
                             "pv_to_potential_ratio": round(observed_ratio, 3),
                             "house_load_kw": round(current_load_kw, 3),
                             "battery_at_configured_maximum": True,
                             "battery_charge_power_w": round(battery_charge_power, 1),
                             "battery_charge_fresh": True}}
        else:
            reason = ("O consumo pode absorver quase toda a produção potencial; o padrão atual não sustenta curtailment."
                      if demand_can_use_potential else
                      "A produção atual está próxima do potencial ou a bateria ainda está a carregar.")
            curtailment_assessment = {"state": "NO_CURRENT_EVIDENCE", "confidence": "MEDIUM",
                "reason": reason,
                "evidence": {"pv_load_fresh": True, "pv_measured_kw": round(current_pv_for_projection, 3),
                             "pv_potential_kw": round(projected_potential_kw, 3),
                             "pv_to_potential_ratio": round(observed_ratio, 3),
                             "house_load_kw": round(current_load_kw, 3),
                             "battery_at_configured_maximum": True,
                             "battery_charge_power_w": round(battery_charge_power, 1),
                             "battery_charge_fresh": True}}
    current = {"pv_power_w": pv, "load_power_w": load,
                        "battery_soc_percent": displayed_soc,
                        "battery_soc_integrated_percent": soc,
                        "battery_soc_source": displayed_soc_source,
                        "battery_soc_estimate": soc_estimate,
                        "battery_inverter_reported_soc_percent": None,
                        "battery_voltage_max_30d_v": soc_estimate.get("voltage_max_30d_v") if soc_estimate else None,
                        "battery_energy_estimate_state": soc_estimate.get("state", "UNAVAILABLE") if soc_estimate else "UNAVAILABLE",
                        "battery_voltage_v": battery_voltage,
                        "battery_current_a": _number(battery_readings, "battery_output_current"),
                        "battery_power_w": _number(battery_readings, "battery_output_power"),
                        "battery_charge_power_w": battery_charge_power,
                        "battery_discharge_power_w": _number(battery_readings, "battery_discharge_power"),
                        "battery_temperature_c": _number(battery_readings, "battery_temperature"),
                        "battery_energy_available_kwh_above_minimum": available,
                        "battery_autonomy_forecast": battery_autonomy,
                        "battery_charge_headroom_kwh_to_maximum": charge_headroom,
                        "battery_at_configured_maximum": battery_at_max,
                        "battery_configured_max_charge_current_a": max_charge_current,
                        "battery_configured_max_discharge_current_a": max_discharge_current,
                        "battery_configured_max_charge_power_kw": round(battery_voltage * max_charge_current / 1000, 3) if battery_voltage is not None and max_charge_current is not None else None,
                        "battery_configured_max_discharge_power_kw": round(battery_voltage * max_discharge_current / 1000, 3) if battery_voltage is not None and max_discharge_current is not None else None,
                        "battery_capacity_kwh": capacity, "minimum_soc_percent": min_soc,
                        "maximum_soc_percent": max_soc, "battery_banks": bank_summary,
                        "pv_potential_next_15m_kw": round(projected_potential_kw, 3) if projected_potential_kw is not None else None,
                        "curtailment_assessment": curtailment_assessment}
    cached_tuya = read_tuya_telemetry(conn)
    tuya_load_telemetry: dict[str, dict[str, Any]] = {}
    loads_by_id = {item.get("id"): item for item in config.get("loads", []) if isinstance(item, dict)}
    for load_item in config.get("loads", []):
        if not isinstance(load_item, dict):
            continue
        meter_load = load_item
        if load_item.get("control_type") == "antminer_braiins" and load_item.get("requires_load_id"):
            meter_load = loads_by_id.get(load_item.get("requires_load_id"), load_item)
        device_id = meter_load.get("tuya_device_id")
        cached = cached_tuya.get(device_id, {}) if device_id else {}
        selected_codes = meter_load.get("tuya_measurement_codes", {})
        metrics = {field: metric for field, metric in (cached.get("metrics") or {}).items()
                   if selected_codes.get(field) == metric.get("code")}
        switch_code = meter_load.get("tuya_switch_code")
        switch_row = next((item for item in cached.get("status", []) if item.get("code") == switch_code), None)
        tuya_load_telemetry[load_item["id"]] = {"device_id": device_id, "name": cached.get("name"),
            "connection_state": cached.get("connection_state", "unknown"), "verified": bool(cached.get("verified")),
            "fresh": bool(cached.get("fresh")), "observed_at": cached.get("observed_at"), "metrics": metrics,
            "switch_on": switch_row.get("value") if isinstance(switch_row, dict) and isinstance(switch_row.get("value"), bool) else None}
    current["tuya_load_telemetry"] = tuya_load_telemetry
    sample_state = "UNKNOWN"
    if latest_sample is not None:
        try:
            sampled_at = datetime.fromisoformat(str(latest_sample.get("sampled_at", "")).replace("Z", "+00:00"))
            if sampled_at.tzinfo is None:
                sampled_at = sampled_at.replace(tzinfo=timezone.utc)
            sample_age = (datetime.now(timezone.utc) - sampled_at).total_seconds()
            sample_state = "LIVE" if 0 <= sample_age <= 90 else "STALE"
        except (TypeError, ValueError):
            sample_state = "UNKNOWN"
    forecast_load = load_forecast.get("one_hour_value")
    forecast_load_unit = load_forecast.get("unit")
    forecast_load_w = (float(forecast_load) * (1000 if forecast_load_unit == "kW" else 1)
                       if isinstance(forecast_load, (int, float)) and not isinstance(forecast_load, bool)
                       and math.isfinite(forecast_load) else None)
    forecast_surplus_w = (max(0, round(projected_potential_kw * 1000 - forecast_load_w))
                          if projected_potential_kw is not None and forecast_load_w is not None else None)
    dispatch = build_dispatch_plan(current, config, sample_state=sample_state,
                                   telemetry_trust=("OWNER_COMMISSIONED" if config.get("automation", {}).get("deye_map_verified") else "LIVE_UNVERIFIED"),
                                   forecast_surplus_w=forecast_surplus_w, tesla_presence=tesla_presence)
    execution_row = conn.execute("SELECT value FROM system_state WHERE key='energy_dispatch_last'").fetchone()
    try:
        dispatch_execution = json.loads(execution_row[0]) if execution_row else None
    except (TypeError, json.JSONDecodeError):
        dispatch_execution = None
    return {"engine_state": "OWNER_GATED_DISPATCH" if config.get("automation", {}).get("enabled") else "READ_ONLY_ANALYTICS",
            "updated_at": latest_at or None,
            "trust": "LIVE_UNVERIFIED" if inverter or battery else "UNKNOWN",
            "configuration": config,
            "current": current,
            "latest_readings": {**inverter_readings, **battery_readings},
            "forecast": {"weather": {"state": weather.get("state") if weather else "location_not_configured",
                         "provider": weather.get("provider") if weather else None,
                         "fetched_at": weather.get("fetched_at") if weather else None, "current": weather_current},
                         "solar_power": forecast, "solar_projection_15m": solar_projection_15m,
                         "solar_expected": {"hourly_values": solar_expected_points,
                         "confidence": "LOW_INDICATIVE" if solar_expected_points else "UNAVAILABLE"},
                         "solar_potential": {"state": weather.get("state") if weather else "location_not_configured",
                         "provider": weather.get("provider") if weather else None,
                         "hourly_values": potential_points,
                         "capacity_kw": effective_pv_capacity_kw,
                         "mppt_capacity_kw": {str(channel): round(value, 3)
                                              for channel, value in mppt_capacity_kw.items() if value > 0},
                         "capacity_source": "configured_pv_strings" if string_capacity_kw > 0 else "legacy_aggregate_configuration",
                         "efficiency_factor": config.get("pv_system_efficiency", 0.85),
                         "adaptive_model": solar_model},
                         "solar_day": solar_day_forecast,
                         "load_power": load_forecast, "battery_soc": soc_forecast,
                         "weather_adjusted": bool(potential_points),
                         "notice": "O Gateway compara, uma vez por hora, a produção Deye medida com a radiação prevista para essa hora e guarda um fator de desempenho suavizado no SQLite. Esse fator ajusta previsões futuras; a linha de potencial meteorológico permanece separada. Consumo é extrapolação indicativa do histórico. Não controla equipamentos."},
            "history": history,
            "dispatch": dispatch,
            "surplus_manager": {"enabled": bool(config.get("surplus_manager", {}).get("enabled")),
                                "manual_override": bool(config.get("surplus_manager", {}).get("manual_override")),
                                "forecast_surplus_w": forecast_surplus_w,
                                "minimum_potential_surplus_w": config.get("surplus_manager", {}).get("minimum_potential_surplus_w", 800),
                                "priority_profile": config.get("surplus_manager", {}).get("priority_profile", "tesla_home"),
                                "tesla_presence": tesla_presence,
                                "effective_priority_profile": dispatch.get("effective_priority_profile"),
                                "battery_reserve_soc_percent": config.get("surplus_manager", {}).get("battery_reserve_soc_percent", 70),
                                "notice": "A previsão orienta o plano, mas a potência em tempo real limita sempre qualquer aumento."},
            "dispatch_execution": dispatch_execution,
            "limits": {"controls_enabled": bool(config.get("automation", {}).get("enabled") and dispatch["state"] == "PLAN_READY"),
                       "notice": dispatch.get("reason")}}
