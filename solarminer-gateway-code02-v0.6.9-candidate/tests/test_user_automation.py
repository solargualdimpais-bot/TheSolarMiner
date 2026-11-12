import json
import sqlite3
from datetime import datetime, timezone

import pytest

from solarminer_gateway import user_automation


def valid_rule(**overrides):
    payload = {
        "name": "Luz de presença",
        "trigger": {
            "type": "tuya_state",
            "device_id": "device-1",
            "code": "switch",
            "operator": "eq",
            "value": True,
            "for_seconds": 15,
        },
        "actions": [
            {"target_type": "tuya", "operation": "switch", "device_id": "device-2", "code": "switch", "on": True},
            {"target_type": "shelly", "operation": "switch", "device_id": "shelly:AA:BB:CC:DD:EE:FF", "channel": 0, "on": False},
        ],
        "enabled": True,
    }
    payload.update(overrides)
    return payload


def fresh_telemetry(value=True, *, code="switch", observed_at=None, verified=True, connection_state="local_responded"):
    return {
        "device-1": {
            "connection_state": connection_state,
            "verified": verified,
            "observed_at": observed_at or datetime.now(timezone.utc).isoformat(),
            "status": [{"code": code, "value": value}],
        }
    }


def test_validate_rule_normalizes_multiple_ordered_actions():
    normalized = user_automation.validate_rule(valid_rule())
    assert normalized["enabled"] is True
    assert normalized["actions"] == valid_rule()["actions"]
    assert normalized["action"] == valid_rule()["actions"][0]


def test_validate_rule_accepts_legacy_single_action():
    payload = valid_rule()
    payload["action"] = payload["actions"][0]
    del payload["actions"]
    assert user_automation.validate_rule(payload)["actions"] == [payload["action"]]


@pytest.mark.parametrize("duration", [-1, 86401, True, 1.5])
def test_validate_rule_rejects_invalid_stability_duration(duration):
    payload = valid_rule()
    payload["trigger"]["for_seconds"] = duration
    with pytest.raises(ValueError, match="automation_trigger_duration_invalid"):
        user_automation.validate_rule(payload)


def test_validate_rule_rejects_unbounded_or_unsupported_actions():
    payload = valid_rule()
    payload["actions"] *= 5
    with pytest.raises(ValueError, match="automation_trigger_or_action_invalid"):
        user_automation.validate_rule(payload)

    payload = valid_rule()
    payload["actions"][0]["operation"] = "toggle"
    with pytest.raises(ValueError, match="automation_action_unsupported"):
        user_automation.validate_rule(payload)


def test_validate_rule_rejects_non_finite_thresholds():
    payload = valid_rule()
    payload["trigger"].update(operator="gt", value=float("inf"))
    with pytest.raises(ValueError, match="automation_trigger_value_invalid"):
        user_automation.validate_rule(payload)


def test_evaluate_trigger_accepts_only_recent_verified_lan_state():
    trigger = user_automation.validate_rule(valid_rule())["trigger"]
    assert user_automation.evaluate_trigger(trigger, fresh_telemetry(), datetime.now().astimezone()) == (True, "Condição verdadeira")

    assert user_automation.evaluate_trigger(trigger, fresh_telemetry(verified=False), datetime.now().astimezone())[0] is False
    assert user_automation.evaluate_trigger(trigger, fresh_telemetry(connection_state="failed"), datetime.now().astimezone())[0] is False


def test_evaluate_trigger_rejects_stale_missing_and_mismatched_values():
    trigger = user_automation.validate_rule(valid_rule())["trigger"]
    old = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - 120, timezone.utc).isoformat()
    assert user_automation.evaluate_trigger(trigger, fresh_telemetry(observed_at=old), datetime.now().astimezone()) == (False, "Leitura Tuya desatualizada")
    assert user_automation.evaluate_trigger(trigger, {}, datetime.now().astimezone()) == (False, "Equipamento Tuya sem leitura LAN confirmada")
    assert user_automation.evaluate_trigger(trigger, fresh_telemetry(False), datetime.now().astimezone()) == (False, "Condição falsa")


def test_evaluate_trigger_numeric_comparison_requires_numbers():
    trigger = {"type": "tuya_state", "device_id": "device-1", "code": "power", "operator": "gt", "value": 10, "for_seconds": 0}
    assert user_automation.evaluate_trigger(trigger, fresh_telemetry(11, code="power"), datetime.now().astimezone())[0] is True
    assert user_automation.evaluate_trigger(trigger, fresh_telemetry("eleven", code="power"), datetime.now().astimezone())[0] is False


def test_evaluate_schedule_uses_gateway_local_weekday_and_time():
    trigger = {"type": "schedule", "at": "20:15", "weekdays": [0, 2]}
    monday = datetime(2026, 11, 9, 20, 15, tzinfo=timezone.utc)
    assert user_automation.evaluate_trigger(trigger, {}, monday) == (True, "Agendado")
    assert user_automation.evaluate_trigger(trigger, {}, monday.replace(hour=20, minute=16)) == (False, "Fora do horário configurado")
    assert user_automation.evaluate_trigger(trigger, {}, monday.replace(day=10)) == (False, "Fora do horário configurado")


def test_schema_persists_rules_and_execution_history():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    user_automation.ensure_schema(conn)
    payload = user_automation.validate_rule(valid_rule())
    conn.execute(
        "INSERT INTO user_automation_rules(id,name,enabled,trigger_json,action_json,runtime_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
        ("rule-1", payload["name"], 1, json.dumps(payload["trigger"]), json.dumps(payload["actions"]), "{}", "2026-11-12", "2026-11-12"),
    )
    conn.execute(
        "INSERT INTO user_automation_runs(rule_id,rule_name,outcome,reason,details_json,occurred_at) VALUES(?,?,?,?,?,?)",
        ("rule-1", payload["name"], "confirmed", "Todas as ações foram confirmadas", json.dumps({"action_count": 2}), "2026-11-12"),
    )
    rules = user_automation.list_rules(conn)
    events = user_automation.history(conn)
    assert rules[0]["actions"] == payload["actions"]
    assert events[0]["details"]["action_count"] == 2
    conn.close()
