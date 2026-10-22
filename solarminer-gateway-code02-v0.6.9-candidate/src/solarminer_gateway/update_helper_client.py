"""Client for the root-owned, systemd socket-activated update broker."""
from __future__ import annotations

import json
import os
import socket
import uuid
from typing import Any

DEFAULT_SOCKET_PATH = "/run/solarminer/update-broker.sock"


def request(action: str, operation_id: str | None = None) -> dict[str, Any]:
    if action not in {"preflight", "enqueue", "tailscale_status", "tailscale_connect"}:
        raise ValueError("update_broker_action_invalid")
    payload: dict[str, str] = {"action": action}
    if action == "enqueue":
        try:
            valid_operation_id = isinstance(operation_id, str) and str(uuid.UUID(operation_id)) == operation_id
        except (ValueError, AttributeError):
            valid_operation_id = False
        if not valid_operation_id:
            raise ValueError("update_operation_id_invalid")
        payload["operation_id"] = operation_id
    elif operation_id is not None:
        raise ValueError("update_operation_id_unexpected")
    path = os.environ.get("SOLARMINER_UPDATE_BROKER_SOCKET", DEFAULT_SOCKET_PATH)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(35 if action == "tailscale_connect" else 15)
        client.connect(path)
        client.sendall(json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n")
        client.shutdown(socket.SHUT_WR)
        response = bytearray()
        while len(response) <= 65536:
            chunk = client.recv(4096)
            if not chunk:
                break
            response.extend(chunk)
            if b"\n" in chunk:
                break
    if len(response) > 65536:
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
