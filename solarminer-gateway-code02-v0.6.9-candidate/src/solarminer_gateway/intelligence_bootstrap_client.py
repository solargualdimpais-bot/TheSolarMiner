"""Client for the narrowly scoped Intelligence bootstrap broker."""
from __future__ import annotations

import json
import os
import re
import socket
from typing import Any

DEFAULT_SOCKET_PATH = "/run/solarminer/intelligence-bootstrap.sock"


def _request(action: str, *, timeout: float = 8) -> dict[str, Any]:
    path = os.environ.get("SOLARMINER_INTELLIGENCE_BOOTSTRAP_SOCKET", DEFAULT_SOCKET_PATH)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(path)
        client.sendall(json.dumps({"action": action}, separators=(",", ":")).encode("ascii") + b"\n")
        client.shutdown(socket.SHUT_WR)
        response = bytearray()
        while len(response) <= 1024:
            chunk = client.recv(1024)
            if not chunk:
                break
            response.extend(chunk)
            if b"\n" in chunk:
                break
    if len(response) > 1024:
        raise RuntimeError("intelligence_bootstrap_response_too_large")
    try:
        result = json.loads(response.decode("utf-8").split("\n", 1)[0])
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("intelligence_bootstrap_response_invalid") from exc
    if not isinstance(result, dict):
        raise RuntimeError("intelligence_bootstrap_response_invalid")
    if result.get("status") != "ok":
        reason = result.get("reason")
        if not isinstance(reason, str) or len(reason) > 100:
            reason = "intelligence_bootstrap_broker_failed"
        raise RuntimeError(reason)
    if action == "start" and result.get("queued") is not True:
        raise RuntimeError("intelligence_bootstrap_start_failed")
    return result


def request_start() -> dict[str, Any]:
    result = _request("start", timeout=15)
    if result.get("status") != "ok" or result.get("queued") is not True:
        raise RuntimeError("intelligence_bootstrap_start_failed")
    return result


def request_system_components_status() -> dict[str, Any]:
    result = _request("system_components_status")
    components = result.get("components")
    if result.get("status") != "ok" or not isinstance(components, dict):
        raise RuntimeError("system_component_verifier_unavailable")
    state, version, protocol, reason = (components.get("status"), components.get("version"),
                                        components.get("protocol"), components.get("reason"))
    if (not isinstance(state, str) or state not in {"OK", "FAILED", "INCOMPATIBLE", "UNAVAILABLE"}
            or (version is not None and (not isinstance(version, str) or len(version) > 64))
            or (protocol is not None and (not isinstance(protocol, int) or isinstance(protocol, bool)))
            or (reason is not None and (not isinstance(reason, str)
                or not re.fullmatch(r"[a-z0-9_:,-]{1,180}", reason)))):
        raise RuntimeError("system_component_verifier_response_invalid")
    return {"status": state, "version": version, "protocol": protocol, "reason": reason}
