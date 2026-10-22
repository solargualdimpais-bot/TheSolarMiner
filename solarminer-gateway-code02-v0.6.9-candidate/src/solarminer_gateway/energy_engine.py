"""Energy summaries, dispatch planning and conservative control eligibility."""
from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from . import energy_registry

ENGINE_CONFIG_KEY = "energy_engine_config"
DEFAULT_CONFIG: dict[str, Any] = {
    "battery_capacity_kwh": None, "minimum_soc_percent": 20.0, "maximum_soc_percent": 100.0,
    "battery_banks": [], "loads": [],
    "automation": {"enabled": False, "commissioned": False, "surplus_margin_w": 250,
                   "decision_interval_seconds": 300, "deye_map_verified": False},
}


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
    allowed = {"battery_capacity_kwh", "minimum_soc_percent", "maximum_soc_percent", "battery_banks", "loads", "automation"}
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise ValueError("unknown_energy_engine_setting")
    existing = get_config(conn)
    merged = {**existing, **payload}
    capacity = merged.get("battery_capacity_kwh")
    minimum = merged.get("minimum_soc_percent", 20)
    maximum = merged.get("maximum_soc_percent", 100)
    banks = merged.get("battery_banks", [])
    if not isinstance(banks, list) or len(banks) > 8:
        raise ValueError("invalid_battery_banks")
    normalized_banks = []
    bank_ids: set[str] = set()
    for bank in banks:
        if not isinstance(bank, dict) or set(bank) - {"id", "name", "capacity_kwh", "minimum_soc_percent", "maximum_soc_percent", "soc_source"}:
            raise ValueError("invalid_battery_bank")
        identifier, name = bank.get("id"), bank.get("name")
        bank_capacity = bank.get("capacity_kwh")
        bank_min = bank.get("minimum_soc_percent", minimum)
        bank_max = bank.get("maximum_soc_percent", maximum)
        source = bank.get("soc_source", "deye_aggregate")
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", identifier) or identifier in bank_ids:
            raise ValueError("invalid_or_duplicate_battery_bank_id")
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError("invalid_battery_bank_name")
        if isinstance(bank_capacity, bool) or not isinstance(bank_capacity, (int, float)) or not math.isfinite(bank_capacity) or not 0.1 <= bank_capacity <= 10000:
            raise ValueError("invalid_battery_bank_capacity_kwh")
        if source != "deye_aggregate":
            raise ValueError("unsupported_battery_soc_source")
        if isinstance(bank_min, bool) or not isinstance(bank_min, (int, float)) or not math.isfinite(bank_min) or not 0 <= bank_min < 100:
            raise ValueError("invalid_battery_bank_minimum_soc")
        if isinstance(bank_max, bool) or not isinstance(bank_max, (int, float)) or not math.isfinite(bank_max) or not 0 < bank_max <= 100 or bank_min >= bank_max:
            raise ValueError("invalid_battery_bank_maximum_soc")
        bank_ids.add(identifier)
        normalized_banks.append({"id": identifier, "name": name.strip(), "capacity_kwh": float(bank_capacity),
                                 "minimum_soc_percent": float(bank_min), "maximum_soc_percent": float(bank_max),
                                 "soc_source": source})
    if normalized_banks:
        capacity = round(sum(item["capacity_kwh"] for item in normalized_banks), 3)
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
    result = {"battery_capacity_kwh": float(capacity) if capacity is not None else None,
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


def _series(conn: sqlite3.Connection, equipment_ids: list[str], field: str, since: str, limit: int = 3000) -> list[dict[str, Any]]:
    if not equipment_ids:
        return []
    marks = ",".join("?" for _ in equipment_ids)
    rows = conn.execute(f"SELECT value_json,unit,observed_at,source,trust FROM energy_readings WHERE equipment_id IN ({marks}) AND field=? AND observed_at>=? ORDER BY observed_at DESC LIMIT ?",
                        (*equipment_ids, field, since, limit)).fetchall()
    return [{"value": json.loads(r[0]), "unit": r[1], "observed_at": r[2], "source": r[3], "trust": r[4]}
            for r in reversed(rows)]


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
                              "one_hour_value": None, "three_hour_value": None, "slope_per_hour": None,
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
    result.update({"confidence": "LOW_INDICATIVE", "slope_per_hour": round(slope, 3),
                   "one_hour_value": round(max(0.0, min(max_value, intercept + slope * (now.timestamp() / 3600 + 1))), 3),
                   "three_hour_value": round(max(0.0, min(max_value, intercept + slope * (now.timestamp() / 3600 + 3))), 3),
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
    series_fields = ("pv_total_power", "load_total_power", "battery_output_power", "battery_soc")
    history = {field: _series(conn, ids, field, cutoff) for field in series_fields}
    pv = _number(inverter_readings, "pv_total_power")
    load = _number(inverter_readings, "load_total_power")
    soc = _number(battery_readings, "battery_soc")
    if soc is not None and not 0 <= soc <= 100:
        soc = None
    banks = config.get("battery_banks", [])
    capacity = config["battery_capacity_kwh"]
    min_soc = float(config["minimum_soc_percent"])
    max_soc = float(config["maximum_soc_percent"])
    available = None
    charge_headroom = None
    bank_summary = []
    if soc is not None and banks:
        capacity = sum(float(bank["capacity_kwh"]) for bank in banks)
        bank_summary = [{**bank, "measured_soc_percent": soc,
                         "energy_above_minimum_kwh": round(bank["capacity_kwh"] * max(0.0, soc-bank["minimum_soc_percent"]) / 100, 3),
                         "charge_headroom_kwh": round(bank["capacity_kwh"] * max(0.0, bank["maximum_soc_percent"]-soc) / 100, 3)}
                        for bank in banks]
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
    soc_forecast = _linear_forecast(history["battery_soc"], soc, 100.0)
    battery_voltage = _number(battery_readings, "battery_voltage")
    max_charge_current = _number(battery_readings, "battery_max_charge_current")
    max_discharge_current = _number(battery_readings, "battery_max_discharge_current")
    battery_at_max = soc is not None and (all(soc >= float(b["maximum_soc_percent"]) for b in banks) if banks else soc >= max_soc)
    current = {"pv_power_w": pv, "load_power_w": load,
                        "battery_soc_percent": soc,
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
            "forecast": {"solar_power": forecast, "load_power": load_forecast,
                         "battery_soc": soc_forecast, "weather_adjusted": False,
                         "notice": "Estimativa indicativa baseada apenas em leituras históricas de FV; não inclui meteorologia nem comanda equipamentos."},
            "history": history,
            "dispatch": dispatch,
            "dispatch_execution": dispatch_execution,
            "limits": {"controls_enabled": bool(config.get("automation", {}).get("enabled") and dispatch["state"] == "PLAN_READY"),
                       "notice": dispatch.get("reason")}}
