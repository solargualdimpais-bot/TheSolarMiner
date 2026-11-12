"""Persistent, local-first user automations, separate from the energy engine."""
from __future__ import annotations

import json
import math
import re
import sqlite3
import time
import uuid
from datetime import datetime
from typing import Any

MAX_RULES = 100
MAX_HISTORY = 1000
MAX_NAME = 100
MAX_FOR_SECONDS = 86400
MAX_STALENESS_SECONDS = 60
OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_automation_rules(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0,
 trigger_json TEXT NOT NULL, action_json TEXT NOT NULL, runtime_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_automation_runs(
 id INTEGER PRIMARY KEY AUTOINCREMENT, rule_id TEXT NOT NULL, rule_name TEXT NOT NULL,
 outcome TEXT NOT NULL, reason TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}',
 occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_user_automation_runs_time ON user_automation_runs(occurred_at DESC);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def validate_rule(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) - {"name", "trigger", "action", "actions", "enabled"}:
        raise ValueError("automation_payload_invalid")
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > MAX_NAME:
        raise ValueError("automation_name_invalid")
    trigger, action = payload.get("trigger"), payload.get("action")
    actions = payload.get("actions")
    if actions is None and isinstance(payload.get("action"), dict):
        actions = [payload["action"]]
    if not isinstance(trigger, dict) or not isinstance(actions, list) or not 1 <= len(actions) <= 8:
        raise ValueError("automation_trigger_or_action_invalid")
    kind = trigger.get("type")
    if kind == "tuya_state":
        if set(trigger) - {"type", "device_id", "code", "operator", "value", "for_seconds"}:
            raise ValueError("automation_trigger_fields_invalid")
        if not isinstance(trigger.get("device_id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", trigger["device_id"]):
            raise ValueError("automation_trigger_device_invalid")
        if not isinstance(trigger.get("code"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", trigger["code"]):
            raise ValueError("automation_trigger_code_invalid")
        if trigger.get("operator") not in OPERATORS:
            raise ValueError("automation_trigger_operator_invalid")
        value = trigger.get("value")
        if isinstance(value, (dict, list)) or value is None or (isinstance(value, str) and len(value) > 128) or (isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isfinite(float(value))):
            raise ValueError("automation_trigger_value_invalid")
        if trigger["operator"] not in {"eq", "ne"} and not _finite_number(value):
            raise ValueError("automation_trigger_number_required")
        duration = trigger.get("for_seconds", 0)
        if isinstance(duration, bool) or not isinstance(duration, int) or not 0 <= duration <= MAX_FOR_SECONDS:
            raise ValueError("automation_trigger_duration_invalid")
        trigger = {"type": kind, "device_id": trigger["device_id"], "code": trigger["code"],
                   "operator": trigger["operator"], "value": value, "for_seconds": duration}
    elif kind == "schedule":
        if set(trigger) - {"type", "at", "weekdays"} or not isinstance(trigger.get("at"), str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", trigger["at"]):
            raise ValueError("automation_schedule_invalid")
        days = trigger.get("weekdays", list(range(7)))
        if not isinstance(days, list) or not days or len(days) > 7 or any(isinstance(day, bool) or not isinstance(day, int) or day not in range(7) for day in days):
            raise ValueError("automation_schedule_weekdays_invalid")
        trigger = {"type": kind, "at": trigger["at"], "weekdays": sorted(set(days))}
    else:
        raise ValueError("automation_trigger_type_unsupported")

    normalized_actions = []
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("automation_action_invalid")
        target_kind = action.get("target_type")
        operation = action.get("operation")
        if target_kind == "tuya" and operation == "switch":
            allowed = {"target_type", "operation", "device_id", "code", "on"}
            if set(action) != allowed or not isinstance(action.get("device_id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", action["device_id"]):
                raise ValueError("automation_tuya_action_invalid")
            if not isinstance(action.get("code"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", action["code"]) or not isinstance(action.get("on"), bool):
                raise ValueError("automation_tuya_action_invalid")
        elif target_kind == "shelly" and operation == "switch":
            allowed = {"target_type", "operation", "device_id", "channel", "on"}
            if set(action) != allowed or not isinstance(action.get("device_id"), str) or not re.fullmatch(r"shelly:[A-Za-z0-9:_-]{1,128}", action["device_id"]):
                raise ValueError("automation_shelly_action_invalid")
            if isinstance(action.get("channel"), bool) or not isinstance(action.get("channel"), int) or not 0 <= action["channel"] <= 31 or not isinstance(action.get("on"), bool):
                raise ValueError("automation_shelly_action_invalid")
        elif target_kind == "shelly" and operation == "brightness":
            allowed = {"target_type", "operation", "device_id", "component", "channel", "percent"}
            if set(action) != allowed or not isinstance(action.get("device_id"), str) or not re.fullmatch(r"shelly:[A-Za-z0-9:_-]{1,128}", action["device_id"]):
                raise ValueError("automation_shelly_action_invalid")
            if action.get("component") not in {"light", "rgb", "rgbw", "cct", "color"} or isinstance(action.get("channel"), bool) or not isinstance(action.get("channel"), int) or not 0 <= action["channel"] <= 31 or isinstance(action.get("percent"), bool) or not isinstance(action.get("percent"), int) or not 0 <= action["percent"] <= 100:
                raise ValueError("automation_shelly_action_invalid")
        else:
            raise ValueError("automation_action_unsupported")
        normalized_actions.append(dict(action))
    if not isinstance(payload.get("enabled", False), bool):
        raise ValueError("automation_enabled_invalid")
    return {"name": name.strip(), "trigger": trigger, "actions": normalized_actions, "action": normalized_actions[0], "enabled": bool(payload.get("enabled", False))}


def _operator(actual: Any, operator: str, expected: Any) -> bool:
    if operator in {"eq", "ne"}:
        if isinstance(actual, bool) or isinstance(expected, bool):
            equal = type(actual) is type(expected) and actual == expected
        else:
            equal = actual == expected or (isinstance(actual, (int, float)) and
                                            isinstance(expected, (int, float)) and
                                            float(actual) == float(expected))
        return equal if operator == "eq" else not equal
    if not _finite_number(actual) or not _finite_number(expected):
        return False
    return {"gt": actual > expected, "gte": actual >= expected,
            "lt": actual < expected, "lte": actual <= expected}[operator]


def evaluate_trigger(trigger: dict[str, Any], telemetry: dict[str, Any], now: datetime) -> tuple[bool, str]:
    if trigger["type"] == "schedule":
        ready = now.strftime("%H:%M") == trigger["at"] and now.weekday() in trigger["weekdays"]
        return ready, "Agendado" if ready else "Fora do horário configurado"
    item = telemetry.get(trigger["device_id"])
    if not isinstance(item, dict) or item.get("connection_state") != "local_responded" or item.get("verified") is not True:
        return False, "Equipamento Tuya sem leitura LAN confirmada"
    stamp = item.get("observed_at") or item.get("last_attempt_at")
    try:
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        age = time.time() - parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return False, "Leitura sem data válida"
    if age < -5 or age > MAX_STALENESS_SECONDS:
        return False, "Leitura Tuya desatualizada"
    status = item.get("status") if isinstance(item.get("status"), list) else []
    row = next((entry for entry in status if isinstance(entry, dict) and entry.get("code") == trigger["code"]), None)
    if row is None:
        return False, "Código Tuya ainda não foi observado"
    matched = _operator(row.get("value"), trigger["operator"], trigger["value"])
    return matched, "Condição verdadeira" if matched else "Condição falsa"


def _json(value: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}


def list_rules(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    result = []
    for row in conn.execute("SELECT * FROM user_automation_rules ORDER BY created_at DESC"):
        runtime = _json(row["runtime_json"])
        result.append({"id": row["id"], "name": row["name"], "enabled": bool(row["enabled"]),
                       "trigger": _json(row["trigger_json"]), "actions": _json(row["action_json"]),
                       "last_outcome": runtime.get("last_outcome"), "last_reason": runtime.get("last_reason"),
                       "last_run_at": runtime.get("last_run_at"), "updated_at": row["updated_at"]})
    return result


def history(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM user_automation_runs ORDER BY id DESC LIMIT ?", (max(1, min(200, limit)),)).fetchall()
    return [{"id": row["id"], "rule_id": row["rule_id"], "rule_name": row["rule_name"],
             "outcome": row["outcome"], "reason": row["reason"], "details": _json(row["details_json"]),
             "occurred_at": row["occurred_at"]} for row in rows]

