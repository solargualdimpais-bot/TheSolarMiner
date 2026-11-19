"""Systemd socket broker exposing only the fixed Intelligence bootstrap action."""
from __future__ import annotations

import json
import subprocess
import sys
import re

from .system_components import installed_component_status

MAX_REQUEST = 1024


def handle_request(raw: bytes, runner=subprocess.run, component_status=installed_component_status) -> dict[str, object]:
    if len(raw) > MAX_REQUEST or not raw.endswith(b"\n"):
        return {"status": "error", "reason": "request_invalid"}
    try:
        request = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return {"status": "error", "reason": "request_invalid"}
    if not isinstance(request, dict) or set(request) != {"action"} or request.get("action") not in {"start", "system_components_status"}:
        return {"status": "error", "reason": "request_invalid"}
    if request["action"] == "system_components_status":
        try:
            components = component_status()
        except Exception:
            return {"status": "error", "reason": "system_component_verifier_failed"}
        if not isinstance(components, dict):
            return {"status": "error", "reason": "system_component_verifier_response_invalid"}
        state = components.get("status")
        version = components.get("version")
        protocol = components.get("protocol")
        reason = components.get("reason")
        if (not isinstance(state, str) or state not in {"OK", "FAILED", "INCOMPATIBLE", "UNAVAILABLE"}
                or (version is not None and (not isinstance(version, str) or len(version) > 64))
                or (protocol is not None and (not isinstance(protocol, int) or isinstance(protocol, bool)))
                or (reason is not None and (not isinstance(reason, str)
                    or not re.fullmatch(r"[a-z0-9_:,-]{1,180}", reason)))):
            return {"status": "error", "reason": "system_component_verifier_response_invalid"}
        return {"status": "ok", "components": {"status": state, "version": version,
                "protocol": protocol, "reason": reason}}
    try:
        result = runner(["/usr/bin/systemctl", "start", "--no-block",
                         "solarminer-intelligence-bootstrap.service"],
                        capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "error", "reason": "intelligence_bootstrap_start_failed"}
    if result.returncode != 0:
        return {"status": "error", "reason": "intelligence_bootstrap_start_failed"}
    return {"status": "ok", "queued": True}


def run() -> int:
    raw = sys.stdin.buffer.readline(MAX_REQUEST + 1)
    response = handle_request(raw)
    sys.stdout.buffer.write(json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()
    return 0 if response.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(run())
