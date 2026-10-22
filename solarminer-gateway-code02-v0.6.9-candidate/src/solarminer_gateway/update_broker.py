"""Root-owned, socket-activated broker for fixed, narrowly scoped helpers."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import uuid

HELPER = "/usr/sbin/solarminer-update-apply"
TAILSCALE_INFO_HELPER = "/usr/sbin/solarminer-tailscale-info"
TAILSCALE_CONNECT_HELPER = "/usr/sbin/solarminer-tailscale-connect"
UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
TAILSCALE_DNS_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.ts\.net$")
TAILSCALE_AUTH_PATTERN = re.compile(r"^https://login\.tailscale\.com/a/[A-Za-z0-9_-]{6,128}$")


def handle_request(raw: bytes, runner=subprocess.run) -> dict[str, object]:
    if len(raw) > 4096 or not raw.endswith(b"\n"):
        return {"status": "error", "reason": "request_invalid"}
    try:
        request = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return {"status": "error", "reason": "request_invalid"}
    if not isinstance(request, dict) or request.get("action") not in {
        "preflight", "enqueue", "tailscale_status", "tailscale_connect"
    }:
        return {"status": "error", "reason": "request_invalid"}
    action = request["action"]
    if action in {"preflight", "tailscale_status"}:
        if set(request) != {"action"}:
            return {"status": "error", "reason": "request_invalid"}
        args = [HELPER, "--preflight"] if action == "preflight" else [TAILSCALE_INFO_HELPER]
    elif action == "tailscale_connect":
        if set(request) != {"action"}:
            return {"status": "error", "reason": "request_invalid"}
        args = [TAILSCALE_CONNECT_HELPER]
    else:
        if set(request) != {"action", "operation_id"} or not isinstance(request.get("operation_id"), str):
            return {"status": "error", "reason": "request_invalid"}
        operation_id = request["operation_id"]
        if not UUID_PATTERN.fullmatch(operation_id):
            return {"status": "error", "reason": "operation_id_invalid"}
        try:
            if str(uuid.UUID(operation_id)) != operation_id:
                return {"status": "error", "reason": "operation_id_invalid"}
        except ValueError:
            return {"status": "error", "reason": "operation_id_invalid"}
        args = [HELPER, "--enqueue", operation_id]
    try:
        timeout = 28 if action == "tailscale_connect" else 12
        result = runner(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "error", "reason": "update_helper_unavailable_or_timed_out"}
    if action == "tailscale_connect" and result.returncode != 0:
        return {"status": "error", "reason": "tailscale_connect_failed"}
    if action == "tailscale_status" and result.returncode != 0:
        return {"status": "error", "reason": "tailscale_status_unavailable"}
    raw_result = result.stdout if result.returncode == 0 else result.stderr
    try:
        payload = json.loads(raw_result or "")
    except (ValueError, TypeError):
        return {"status": "error", "reason": "update_helper_response_invalid"}
    if not isinstance(payload, dict):
        return {"status": "error", "reason": "update_helper_response_invalid"}
    if action == "tailscale_status":
        if not isinstance(payload.get("installed"), bool) or not isinstance(payload.get("connected"), bool):
            return {"status": "error", "reason": "tailscale_status_invalid"}
        installed = payload.get("installed") is True
        connected = payload.get("connected") is True
        dns_name = payload.get("dns_name")
        if connected and (not installed or not isinstance(dns_name, str) or not TAILSCALE_DNS_PATTERN.fullmatch(dns_name)):
            return {"status": "error", "reason": "tailscale_status_invalid"}
        if not installed:
            return {"installed": False, "connected": False, "dns_name": None, "https_url": None}
        https_url = "https://" + dns_name if connected else None
        return {"installed": True, "connected": connected, "dns_name": dns_name if connected else None,
                "https_url": https_url}
    if action == "tailscale_connect":
        if payload.get("started") is not True or not isinstance(payload.get("connected"), bool):
            return {"status": "error", "reason": "tailscale_connect_failed"}
        connected = payload.get("connected") is True
        auth_url = payload.get("auth_url")
        if auth_url is not None and (not isinstance(auth_url, str) or not TAILSCALE_AUTH_PATTERN.fullmatch(auth_url)):
            return {"status": "error", "reason": "tailscale_connect_response_invalid"}
        if not connected and auth_url is None:
            return {"status": "error", "reason": "tailscale_auth_url_missing"}
        return {"started": True, "connected": connected, "auth_url": auth_url}
    if result.returncode != 0 or payload.get("status") == "error":
        reason = payload.get("reason")
        if not isinstance(reason, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,180}", reason):
            reason = "update_pipeline_failed"
        return {"status": "error", "reason": reason}
    allowed = {"status", "operation_id", "target_version", "health_check_seconds", "current_target", "recovery_timer"}
    return {key: value for key, value in payload.items() if key in allowed}


def main() -> int:
    request = sys.stdin.buffer.readline(4097)
    response = handle_request(request)
    sys.stdout.write(json.dumps(response, sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0 if response.get("status") != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
