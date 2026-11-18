"""Client for the root-owned, systemd socket-activated update broker."""
from __future__ import annotations

import json
import os
import socket
import uuid
from typing import Any

DEFAULT_SOCKET_PATH = "/run/solarminer/update-broker.sock"


def request(action: str, operation_id: str | None = None, enabled: bool | None = None,
            api_key: str | None = None, model: str | None = None,
            suite: str | None = None) -> dict[str, Any]:
    if action not in {"preflight", "enqueue", "tailscale_status", "tailscale_connect", "diagnostics", "watchdog_set",
                      "intelligence_openai_set", "intelligence_openai_status", "intelligence_openai_clear",
                      "intelligence_workspace_tests", "intelligence_bootstrap_start"}:
        raise ValueError("update_broker_action_invalid")
    payload: dict[str, Any] = {"action": action}
    if action == "enqueue":
        try:
            valid_operation_id = isinstance(operation_id, str) and str(uuid.UUID(operation_id)) == operation_id
        except (ValueError, AttributeError):
            valid_operation_id = False
        if not valid_operation_id:
            raise ValueError("update_operation_id_invalid")
        payload["operation_id"] = operation_id
    elif action == "watchdog_set":
        if operation_id is not None or not isinstance(enabled, bool):
            raise ValueError("watchdog_state_invalid")
        payload["enabled"] = enabled
    elif action == "intelligence_openai_set":
        if operation_id is not None or enabled is not None or not isinstance(api_key, str) or not isinstance(model, str):
            raise ValueError("openai_configuration_invalid")
        payload.update({"api_key": api_key, "model": model})
    elif action in {"intelligence_openai_status", "intelligence_openai_clear"}:
        if operation_id is not None or enabled is not None or api_key is not None or model is not None:
            raise ValueError("openai_configuration_unexpected")
    elif action == "intelligence_bootstrap_start":
        if any(value is not None for value in (operation_id, enabled, api_key, model, suite)):
            raise ValueError("intelligence_bootstrap_request_invalid")
    elif action == "intelligence_workspace_tests":
        if operation_id is not None or enabled is not None or api_key is not None or model is not None:
            raise ValueError("intelligence_test_request_invalid")
        if suite not in {"intelligence", "gateway-python"}:
            raise ValueError("intelligence_test_suite_invalid")
        payload["suite"] = suite
    elif operation_id is not None or enabled is not None:
        raise ValueError("update_operation_id_unexpected")
    if action not in {"intelligence_openai_set", "intelligence_openai_status", "intelligence_openai_clear"} and (api_key is not None or model is not None):
        raise ValueError("openai_configuration_unexpected")
    if action != "intelligence_workspace_tests" and suite is not None:
        raise ValueError("intelligence_test_suite_unexpected")
    path = os.environ.get("SOLARMINER_UPDATE_BROKER_SOCKET", DEFAULT_SOCKET_PATH)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(650 if action == "intelligence_workspace_tests" else 35 if action == "tailscale_connect" else 30 if action == "diagnostics" else 15)
        client.connect(path)
        client.sendall(json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n")
        client.shutdown(socket.SHUT_WR)
        response = bytearray()
        response_limit = 40000 if action == "intelligence_workspace_tests" else 65536
        while len(response) <= response_limit:
            chunk = client.recv(4096)
            if not chunk:
                break
            response.extend(chunk)
            if b"\n" in chunk:
                break
    if len(response) > (40000 if action == "intelligence_workspace_tests" else 65536):
        raise RuntimeError("update_broker_response_too_large")
    try:
        result = json.loads(response.decode("utf-8").split("\n", 1)[0])
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("update_broker_response_invalid") from exc
    if not isinstance(result, dict):
        raise RuntimeError("update_broker_response_invalid")
    if result.get("status") == "error":
        reason = result.get("reason")
        if not isinstance(reason, str):
            reason = "update_broker_failed"
        raise RuntimeError(reason[:180])
    return result
