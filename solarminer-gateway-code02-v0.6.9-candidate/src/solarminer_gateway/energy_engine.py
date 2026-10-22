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
from typing import Any

from . import energy_registry

ENGINE_CONFIG_KEY = "energy_engine_config"
BATTERY_ESTIMATOR_STATE_KEY = "energy_engine_battery_estimator"
DEFAULT_CONFIG: dict[str, Any] = {
    "site_location_name": None, "site_latitude": None, "site_longitude": None,
    "pv_capacity_kw": None, "pv_system_efficiency": 0.85,
    "battery_capacity_kwh": None, "minimum_soc_percent": 20.0, "maximum_soc_percent": 100.0,
    "battery_banks": [], "loads": [],
    "automation": {"enabled": False, "commissioned": False, "surplus_margin_w": 250,
                   "decision_interval_seconds": 300, "deye_map_verified": False},
}
_WEATHER_CACHE: dict[str, Any] = {"key": None, "expires_at": 0.0, "value": None}
_WEATHER_LOCK = threading.Lock()


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
    return result


def save_config(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {"site_location_name", "site_latitude", "site_longitude", "pv_capacity_kw", "pv_system_efficiency",
               "battery_capacity_kwh", "minimum_soc_percent", "maximum_soc_percent", "battery_banks", "loads", "automation"}
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
        allowed_load = {"id", "name", "kind", "control_type", "rated_power_w", "minimum_power_w", "maximum_power_w",
                        "priority", "enabled", "automatic", "tuya_device_id", "tuya_switch_code",
                        "minimum_on_seconds", "minimum_off_seconds", "requires_load_id"}
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
                                 "rated_power_w": rated, "minimum_power_w": minimum_power,
                                 "maximum_power_w": maximum_power, "priority": priority, "enabled": enabled,
                                 "automatic": automatic, "tuya_device_id": device_id, "tuya_switch_code": switch_code,
                                 "minimum_on_seconds": min_on, "minimum_off_seconds": min_off,
                                 "requires_load_id": requires_load_id})
    for load in normalized_loads:
        if load["requires_load_id"] is not None:
            dependency = next((item for item in normalized_loads if item["id"] == load["requires_load_id"]), None)
            if (dependency is None or dependency["id"] == load["id"]
                    or dependency["control_type"] not in {"tuya_smart", "tuya_breaker"}
                    or not dependency["enabled"] or not dependency["automatic"]):
                raise ValueError("invalid_flexible_load_dependency")
        if load["control_type"] == "antminer_braiins" and load["automatic"] and load["enabled"] and load["requires_load_id"] is None:
            raise ValueError("automatic_antminer_requires_tuya_relay_load")
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
    result = {"site_location_name": location_name.strip() if isinstance(location_name, str) else None,
              "site_latitude": float(latitude) if latitude is not None else None,
              "site_longitude": float(longitude) if longitude is not None else None,
              "pv_capacity_kw": float(pv_capacity) if pv_capacity is not None else None,
              "pv_system_efficiency": float(pv_efficiency),
              "battery_capacity_kwh": float(capacity) if capacity is not None else None,
              "minimum_soc_percent": float(minimum), "maximum_soc_percent": float(maximum),
              "battery_banks": normalized_banks, "loads": normalized_loads, "automation": normalized_automation}
    conn.execute("INSERT INTO system_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (ENGINE_CONFIG_KEY, json.dumps(result, separators=(",", ":"))))
    return result


def _reading_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["field"]: item for item in rows}


def _number(readings: dict[str, dict[str, Any]], field: str) -> float | None:
    value = readings.get(field, {}).get("value")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _solar_weather(latitude: float | None, longitude: float | None) -> dict[str, Any] | None:
    """Fetch hourly solar radiation from the fixed Open-Meteo forecast API, cached for 15 minutes."""
    if latitude is None or longitude is None:
        return None
    cache_key = f"{latitude:.5f},{longitude:.5f}"
    with _WEATHER_LOCK:
        if _WEATHER_CACHE["key"] == cache_key and _WEATHER_CACHE["expires_at"] > time.monotonic():
            return _WEATHER_CACHE["value"]
        query = urllib.parse.urlencode({
            "latitude": f"{latitude:.5f}", "longitude": f"{longitude:.5f}",
            "hourly": "shortwave_radiation,temperature_2m,apparent_temperature,relative_humidity_2m,cloud_cover,wind_speed_10m,weather_code", "past_hours": 4,
            "forecast_hours": 7, "timezone": "UTC", "temperature_unit": "celsius", "wind_speed_unit": "kmh",
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
            temperature = hourly.get("temperature_2m") if isinstance(hourly, dict) else None
            apparent_temperature = hourly.get("apparent_temperature") if isinstance(hourly, dict) else None
            humidity = hourly.get("relative_humidity_2m") if isinstance(hourly, dict) else None
            cloud_cover = hourly.get("cloud_cover") if isinstance(hourly, dict) else None
            wind_speed = hourly.get("wind_speed_10m") if isinstance(hourly, dict) else None
            weather_codes = hourly.get("weather_code") if isinstance(hourly, dict) else None
            if not isinstance(times, list) or not isinstance(radiation, list) or len(times) != len(radiation) or len(times) > 16:
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
            optional_arrays = (temperature, apparent_temperature, humidity, cloud_cover, wind_speed, weather_codes)
            if any(not isinstance(values, list) or len(values) != len(times) for values in optional_arrays):
                raise ValueError("weather_response_invalid")
            points = []
            for stamp, value, temp, feels, humidity_value, cloud_value, wind, code in zip(
                    times, radiation, temperature, apparent_temperature, humidity, cloud_cover, wind_speed, weather_codes):
                if not isinstance(stamp, str):
                    continue
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 2000):
                    continue
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
                        parsed = parsed.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                points.append({"observed_at": parsed.astimezone(timezone.utc).isoformat(timespec="minutes"),
                               "shortwave_radiation_w_m2": float(value) if value is not None else None,
                               "temperature_c": float(temp) if temp is not None else None,
                               "apparent_temperature_c": float(feels) if feels is not None else None,
                               "relative_humidity_percent": humidity_value,
                               "cloud_cover_percent": cloud_value,
                               "wind_speed_kmh": float(wind) if wind is not None else None,
                               "weather_code": code})
            if not points:
                raise ValueError("weather_data_empty")
            result = {"provider": "Open-Meteo", "state": "available", "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "hourly": points}
        except (OSError, TimeoutError, urllib.error.URLError, ValueError, UnicodeError, json.JSONDecodeError):
            result = {"provider": "Open-Meteo", "state": "unavailable", "hourly": []}
        _WEATHER_CACHE.update({"key": cache_key, "expires_at": time.monotonic() + 900, "value": result})
        return result


def _learn_solar_performance(conn: sqlite3.Connection, weather: dict[str, Any], inverter: dict[str, Any] | None,
                             battery: dict[str, Any] | None, capacity_kw: float,
                             baseline_efficiency: float, maximum_soc_percent: float,
                             battery_capacity_kwh: float | None = None) -> dict[str, Any]:
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
            if min(len(channel_values.get(field, [])) for field in fields) < 10:
                continue
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
            potential_kw = capacity_kw * float(radiation) / 1000 * baseline_efficiency
            if potential_kw < 0.2:
                processed.add(hour_key)
                continue
            observed_ratio = max(0.1, min(1.2, actual_kw / potential_kw))
            def hourly_average(equipment: dict[str, Any] | None, field: str) -> float | None:
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
                return sum(context_values) / len(context_values) if len(context_values) >= 10 else None
            historical_soc = None
            if battery and battery_capacity_kwh:
                battery_since = (stamp - timedelta(days=30)).isoformat(timespec="microseconds")
                historical_voltage = _series(conn, [battery["id"]], "battery_voltage", battery_since, limit=50000, until=finish)
                historical_power = _series(conn, [battery["id"]], "battery_output_power", battery_since, limit=50000, until=finish)
                historical_soc, _ = _estimate_battery_soc(historical_voltage, historical_power,
                                                          battery_capacity_kwh, 0.0, maximum_soc_percent,
                                                          as_of=stamp)
            historical_charge_w = hourly_average(battery, "battery_charge_power")
            historical_load_w = hourly_average(inverter, "load_total_power")
            irradiance_bin = str(min(10, max(0, int(float(radiation) // 100))))
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
            curtailed = (observed_ratio < 0.70 and historical_soc is not None
                         and historical_soc >= maximum_soc_percent - 2
                         and historical_charge_w is not None and historical_charge_w <= 150
                         and historical_load_w is not None and historical_load_w < max(500, (potential_kw - actual_kw) * 1000))
            if curtailed:
                event = {
                    "hour": hour_key, "observed_performance_ratio": round(observed_ratio, 4),
                    "weather_potential_kw": round(potential_kw, 3), "measured_mppt_power_kw": round(actual_kw, 3),
                    "battery_soc_percent": round(historical_soc, 2), "battery_charge_power_w": round(historical_charge_w, 1),
                    "house_load_power_w": round(historical_load_w, 1), **mppt_sample,
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
            count = int(model.get("sample_count", 0)) if isinstance(model.get("sample_count", 0), int) else 0
            ratio = observed_ratio if count == 0 else max(0.1, min(1.2, ratio * 0.8 + observed_ratio * 0.2))
            model["sample_count"] = count + 1
            model["last_sample_at"] = hour_key
            model["last_mppt_sample"] = {
                **mppt_sample,
                "measured_total_kw": round(actual_kw, 3), "weather_potential_kw": round(potential_kw, 3),
                "observed_performance_ratio": round(observed_ratio, 4),
                "interpretation": "observed_output_may_include_curtailment",
            }
            if observed_ratio >= 0.70:
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
    conn.execute("INSERT INTO system_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, json.dumps(model, separators=(",", ":"))))
    return {"performance_ratio": ratio, "sample_count": int(model.get("sample_count", 0)),
            "last_sample_at": model.get("last_sample_at"), "new_samples": accepted,
            "possible_curtailment_hours": int(model.get("possible_curtailment_hours", 0)),
            "new_curtailment_candidates": possible_curtailment,
            "last_curtailment_candidate": model.get("last_curtailment_candidate"),
            "mppt_voltage_profiles": profiles,
            "mppt_empirical_curtailment_voltage_v": model.get("mppt_empirical_curtailment_voltage_v", {}),
            "mppt_lowest_observed_operating_voltage_v": model.get("mppt_lowest_observed_operating_voltage_v", {}),
            "recent_curtailment_candidates": candidate_events[-24:]}


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


def _dedupe_time_series(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_stamp: dict[str, dict[str, Any]] = {}
    for point in points:
        stamp = point.get("observed_at")
        value = point.get("value")
        if (isinstance(stamp, str) and isinstance(value, (int, float))
                and not isinstance(value, bool) and math.isfinite(value)):
            by_stamp[stamp] = point
    return [by_stamp[key] for key in sorted(by_stamp)]


def _estimate_battery_soc(voltage_history: list[dict[str, Any]], power_history: list[dict[str, Any]],
                          capacity_kwh: float | None, minimum_soc: float, maximum_soc: float,
                          as_of: datetime | None = None
                          ) -> tuple[float | None, dict[str, Any]]:
    """Estimate aggregate parallel-bank SOC from the 30-day voltage ceiling and signed power.

    Deye convention: positive battery_output_power is discharge; negative is charge.
    The rolling voltage maximum is an estimated full-charge anchor, not verified SOC.
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
    # Earliest occurrence of the highest voltage is the anchor. Equal later
    # samples must not repeatedly reset estimated SOC to full.
    peak_at, peak_voltage = voltages[0]
    for stamp, value in voltages[1:]:
        if value > peak_voltage:
            peak_at, peak_voltage = stamp, value
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
        state = {"anchor_at": anchor_at.isoformat(),
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

    # A new voltage ceiling, beyond measurement noise, is a new full-charge
    # anchor. An invalidated state can only recover at the previous ceiling.
    new_anchor: tuple[datetime, float] | None = None
    for point in voltages:
        try:
            stamp = datetime.fromisoformat(str(point["observed_at"]).replace("Z", "+00:00"))
            stamp = stamp.replace(tzinfo=stamp.tzinfo or timezone.utc).astimezone(timezone.utc)
            value = float(point["value"])
        except (KeyError, TypeError, ValueError):
            continue
        if stamp > last_at and math.isfinite(value) and value > 0:
            if value >= voltage_max + 0.1 or (state.get("needs_reanchor") and value >= voltage_max - 0.1):
                if new_anchor is None or stamp > new_anchor[0]:
                    new_anchor = (stamp, value)

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
    state.update({"anchor_at": anchor_at.isoformat(), "voltage_max_v": voltage_max,
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


def _linear_forecast(series: list[dict[str, Any]], current: float | None, max_value: float = 15.0) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    points: list[tuple[float, float]] = []
    for item in series:
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


def build_dispatch_plan(current: dict[str, Any], config: dict[str, Any], *, sample_state: str = "UNKNOWN",
                        telemetry_trust: str = "LIVE_UNVERIFIED") -> dict[str, Any]:
    """Compute conservative load allocations; this function never sends commands."""
    automation = config.get("automation", {})
    common = {"decision_interval_seconds": automation.get("decision_interval_seconds", 300), "actions": []}
    if not automation.get("enabled"):
        return {**common, "state": "DISABLED", "reason": "Owner has not enabled automatic dispatch."}
    if not automation.get("commissioned") or not automation.get("deye_map_verified"):
        return {**common, "state": "BLOCKED_NOT_COMMISSIONED", "reason": "Owner commissioning and physical Deye map confirmation are required."}
    if sample_state != "LIVE":
        return {**common, "state": "BLOCKED_STALE_TELEMETRY", "reason": "A fresh Deye sample is required."}
    if telemetry_trust not in {"PHYSICALLY_CORROBORATED", "OWNER_COMMISSIONED"}:
        return {**common, "state": "BLOCKED_UNTRUSTED_TELEMETRY", "reason": "Control readings are not physically commissioned."}
    if current.get("battery_soc_percent") is None or current.get("pv_power_w") is None or current.get("load_power_w") is None:
        return {**common, "state": "BLOCKED_MISSING_TELEMETRY", "reason": "SOC, PV and load power are all required."}
    if current.get("battery_charge_headroom_kwh_to_maximum") is None:
        return {**common, "state": "BLOCKED_BATTERY_CONFIGURATION", "reason": "Configure battery bank capacity and SOC limits first."}
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
    actions = []
    actions_by_id: dict[str, dict[str, Any]] = {}
    for load in sorted(config.get("loads", []), key=lambda item: (item.get("priority", 100), item.get("id", ""))):
        if not load.get("enabled") or not load.get("automatic"):
            continue
        control = load.get("control_type")
        dependency_id = load.get("requires_load_id")
        if control == "manual":
            action = {"load_id": load["id"], "name": load["name"], "state": "SKIPPED_MANUAL", "target_power_w": 0}
            actions.append(action); actions_by_id[load["id"]] = action
            continue
        if control == "tesla_fleet":
            action = {"load_id": load["id"], "name": load["name"], "state": "BLOCKED_CONTROL_UNAVAILABLE", "target_power_w": 0}
            actions.append(action); actions_by_id[load["id"]] = action
            continue
        if control == "antminer_braiins":
            minimum = max(1, load.get("minimum_power_w", 1))
            target = min(load.get("maximum_power_w", 2900), available)
            target = target if target >= minimum else 0
            if target and dependency_id and actions_by_id.get(dependency_id, {}).get("state") != "ON":
                action = {"load_id": load["id"], "name": load["name"], "state": "BLOCKED_RELAY_NOT_READY",
                          "target_power_w": target, "control_type": control, "requires_load_id": dependency_id}
                actions.append(action); actions_by_id[load["id"]] = action
                continue
            if target:
                available -= target
            action = {"load_id": load["id"], "name": load["name"], "state": "TARGET" if target else "BELOW_MINIMUM_SURPLUS",
                      "target_power_w": target, "control_type": control}
            actions.append(action); actions_by_id[load["id"]] = action
            continue
        rated = load.get("rated_power_w", load.get("maximum_power_w", 0))
        turn_on = available >= rated
        if turn_on:
            available -= rated
        action = {"load_id": load["id"], "name": load["name"],
                  "state": "ON" if turn_on else "WAITING_FOR_SURPLUS",
                  "target_power_w": rated if turn_on else 0, "control_type": control}
        actions.append(action); actions_by_id[load["id"]] = action
    return {**common, "state": "PLAN_READY", "reason": "Plan only; device commands are managed by the dispatcher.",
            "estimated_surplus_w": surplus, "safety_margin_w": margin,
            "unallocated_surplus_w": available, "actions": actions}


def build_summary(conn: sqlite3.Connection, history_hours: int = 24,
                  latest_sample: dict[str, Any] | None = None) -> dict[str, Any]:
    energy_registry.ensure_schema(conn)
    equipment = energy_registry.list_equipment(conn)
    inverter = next((e for e in equipment if e["category"] == "inversores" and e["id"].startswith("deye-inverter-")), None)
    battery = next((e for e in equipment if e["category"] == "baterias" and e["id"].startswith("deye-battery-")), None)
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
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=history_hours)).isoformat(timespec="microseconds")
    ids = [e["id"] for e in (inverter, battery) if e]
    series_fields = ("pv_total_power", "pv1_input_power", "pv1_voltage", "pv1_current",
                     "pv2_input_power", "pv2_voltage", "pv2_current", "load_total_power",
                     "battery_output_power")
    history = {field: _series(conn, ids, field, cutoff) for field in series_fields}
    # The battery estimator bootstraps from the highest battery voltage observed
    # in the preceding 30 days, then persists that shared-bank anchor and integrates
    # only new signed charge/discharge samples. Keep minute samples for bootstrap.
    battery_cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="microseconds")
    battery_voltage_history = _series(conn, [battery["id"]] if battery else [], "battery_voltage", battery_cutoff, limit=50000)
    battery_power_history = _series(conn, [battery["id"]] if battery else [], "battery_output_power", battery_cutoff, limit=50000)
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
    deye_soc = _number(battery_readings, "battery_soc")
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
    # The inverter's SOC is deliberately not used as the operating SOC. The
    # Gateway estimates SOC from a recent voltage ceiling and integrated power.
    soc, soc_estimate = _estimate_battery_soc_persistent(
        conn, battery_voltage_history, battery_power_history, capacity, 0.0, max_soc)
    if soc is not None and banks:
        capacity = sum(float(bank["capacity_kwh"]) for bank in banks)
        bank_summary = [{**bank, "estimated_soc_percent": soc if bank.get("active", True) else None,
                         "voltage_max_30d_v": soc_estimate.get("voltage_max_30d_v"),
                         "soc_estimate_state": soc_estimate.get("state"),
                         "energy_above_minimum_kwh": round(bank["capacity_kwh"] * max(0.0, soc-bank["minimum_soc_percent"]) / 100, 3) if bank.get("active", True) else 0.0,
                         "charge_headroom_kwh": round(bank["capacity_kwh"] * max(0.0, bank["maximum_soc_percent"]-soc) / 100, 3) if bank.get("active", True) else 0.0}
                        for bank in all_banks]
        available = round(sum(item["energy_above_minimum_kwh"] for item in bank_summary), 3)
        charge_headroom = round(sum(item["charge_headroom_kwh"] for item in bank_summary), 3)
        min_soc = round(sum(b["capacity_kwh"] * b["minimum_soc_percent"] for b in banks) / capacity, 2)
        max_soc = min(float(b["maximum_soc_percent"]) for b in banks)
    elif soc is not None and capacity is not None:
        available = round(float(capacity) * max(0.0, soc - min_soc) / 100.0, 3)
        charge_headroom = round(float(capacity) * max(0.0, max_soc - soc) / 100.0, 3)
    latest_at = max((r.get("observed_at", "") for r in [*inverter_readings.values(), *battery_readings.values()]), default=None)
    forecast = _linear_forecast(history["pv_total_power"], pv, 15.0)
    load_forecast = _linear_forecast(history["load_total_power"], load, 100.0)
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
    potential_points: list[dict[str, Any]] = []
    solar_expected_points: list[dict[str, Any]] = []
    solar_model: dict[str, Any] = {"performance_ratio": None, "sample_count": 0, "new_samples": 0}
    if weather and weather.get("state") == "available" and config.get("pv_capacity_kw") is not None:
        peak_kw = float(config["pv_capacity_kw"])
        efficiency = float(config.get("pv_system_efficiency", 0.85))
        solar_model = _learn_solar_performance(conn, weather, inverter, battery, peak_kw, efficiency, max_soc, capacity)
        now = datetime.now(timezone.utc)
        for point in weather["hourly"]:
            radiation = point.get("shortwave_radiation_w_m2")
            if not isinstance(radiation, (int, float)) or isinstance(radiation, bool):
                continue
            stamp = datetime.fromisoformat(point["observed_at"].replace("Z", "+00:00"))
            hours = (stamp - now).total_seconds() / 3600
            if -3.1 <= hours <= 6.1:
                potential_kw = round(peak_kw * radiation / 1000 * efficiency, 3)
                potential_points.append({"observed_at": point["observed_at"], "value": potential_kw,
                                         "unit": "kW", "segment": "historical" if hours <= 0 else "forecast"})
        for point in potential_points:
            if point["segment"] == "forecast":
                solar_expected_points.append({**point, "value": round(point["value"] * solar_model["performance_ratio"], 3)})
    elif weather:
        weather = {**weather, "state": "needs_pv_capacity"}
    battery_voltage = _number(battery_readings, "battery_voltage")
    max_charge_current = _number(battery_readings, "battery_max_charge_current")
    max_discharge_current = _number(battery_readings, "battery_max_discharge_current")
    battery_at_max = soc is not None and (all(soc >= float(b["maximum_soc_percent"]) for b in banks) if banks else soc >= max_soc)
    current = {"pv_power_w": pv, "load_power_w": load,
                        "battery_soc_percent": soc,
                        "battery_soc_source": "gateway_energy_integrated" if soc is not None else "unavailable",
                        "battery_soc_estimate": soc_estimate,
                        "battery_inverter_reported_soc_percent": deye_soc,
                        "battery_voltage_max_30d_v": soc_estimate.get("voltage_max_30d_v") if soc_estimate else None,
                        "battery_energy_estimate_state": soc_estimate.get("state", "UNAVAILABLE") if soc_estimate else "UNAVAILABLE",
                        "battery_voltage_v": battery_voltage,
                        "battery_current_a": _number(battery_readings, "battery_output_current"),
                        "battery_power_w": _number(battery_readings, "battery_output_power"),
                        "battery_charge_power_w": _number(battery_readings, "battery_charge_power"),
                        "battery_discharge_power_w": _number(battery_readings, "battery_discharge_power"),
                        "battery_temperature_c": _number(battery_readings, "battery_temperature"),
                        "battery_energy_available_kwh_above_minimum": available,
                        "battery_charge_headroom_kwh_to_maximum": charge_headroom,
                        "battery_at_configured_maximum": battery_at_max,
                        "battery_configured_max_charge_current_a": max_charge_current,
                        "battery_configured_max_discharge_current_a": max_discharge_current,
                        "battery_configured_max_charge_power_kw": round(battery_voltage * max_charge_current / 1000, 3) if battery_voltage is not None and max_charge_current is not None else None,
                        "battery_configured_max_discharge_power_kw": round(battery_voltage * max_discharge_current / 1000, 3) if battery_voltage is not None and max_discharge_current is not None else None,
                        "battery_capacity_kwh": capacity, "minimum_soc_percent": min_soc,
                        "maximum_soc_percent": max_soc, "battery_banks": bank_summary}
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
    dispatch = build_dispatch_plan(current, config, sample_state=sample_state,
                                   telemetry_trust=("OWNER_COMMISSIONED" if config.get("automation", {}).get("deye_map_verified") else "LIVE_UNVERIFIED"))
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
                         "solar_power": forecast, "solar_expected": {"hourly_values": solar_expected_points,
                         "confidence": "LOW_INDICATIVE" if solar_expected_points else "UNAVAILABLE"},
                         "solar_potential": {"state": weather.get("state") if weather else "location_not_configured",
                         "provider": weather.get("provider") if weather else None,
                         "hourly_values": potential_points,
                         "capacity_kw": config.get("pv_capacity_kw"),
                         "efficiency_factor": config.get("pv_system_efficiency", 0.85),
                         "adaptive_model": solar_model},
                         "load_power": load_forecast, "battery_soc": soc_forecast,
                         "weather_adjusted": bool(potential_points),
                         "notice": "O Gateway compara, uma vez por hora, a produção Deye medida com a radiação prevista para essa hora e guarda um fator de desempenho suavizado no SQLite. Esse fator ajusta previsões futuras; a linha de potencial meteorológico permanece separada. Consumo é extrapolação indicativa do histórico. Não controla equipamentos."},
            "history": history,
            "dispatch": dispatch,
            "dispatch_execution": dispatch_execution,
            "limits": {"controls_enabled": bool(config.get("automation", {}).get("enabled") and dispatch["state"] == "PLAN_READY"),
                       "notice": dispatch.get("reason")}}
