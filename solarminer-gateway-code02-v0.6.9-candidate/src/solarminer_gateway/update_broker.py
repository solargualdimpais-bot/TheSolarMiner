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
DIAGNOSTIC_UNITS = (
    "solarminer-gateway.service", "solarminer-update-check-daily.service",
    "solarminer-update-apply@*.service", "solarminer-tailscale-cert.service", "nginx.service",
)
DIAGNOSTIC_SECRET_PATTERNS = (
    (re.compile(r"(?i)(\b(?:password|passwd|token|secret|authorization|access[_-]?token|api[_-]?key)\b\s*[:=]\s*)([^\s,;]+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.DOTALL), "[REDACTED PRIVATE KEY]"),
    (re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]"), ""),
)


def _redact_diagnostics(value: str) -> str:
    for pattern, replacement in DIAGNOSTIC_SECRET_PATTERNS:
        value = pattern.sub(replacement, value)
    return value[-24000:]


def handle_request(raw: bytes, runner=subprocess.run) -> dict[str, object]:
    if len(raw) > 4096 or not raw.endswith(b"\n"):
        return {"status": "error", "reason": "request_invalid"}
    try:
        request = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return {"status": "error", "reason": "request_invalid"}
    if not isinstance(request, dict) or request.get("action") not in {
        "preflight", "enqueue", "tailscale_status", "tailscale_connect", "diagnostics"
    }:
        return {"status": "error", "reason": "request_invalid"}
    action = request["action"]
    if action in {"preflight", "tailscale_status", "diagnostics"}:
        if set(request) != {"action"}:
            return {"status": "error", "reason": "request_invalid"}
        if action == "preflight":
            args = [HELPER, "--preflight"]
        elif action == "tailscale_status":
            args = [TAILSCALE_INFO_HELPER]
        else:
            args = ["/usr/bin/journalctl", "--since=-2 hours", "--lines=160", "--no-pager", "--output=short-iso"]
            for unit in DIAGNOSTIC_UNITS:
                args.extend(("--unit", unit))
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
    if action == "diagnostics":
        if result.returncode != 0 or not isinstance(result.stdout, str):
            return {"status": "error", "reason": "gateway_journal_unavailable"}
        return {"status": "ok", "logs": _redact_diagnostics(result.stdout),
                "truncated": len(result.stdout) > 24000, "scope": "allowlisted_services_last_2_hours"}
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
        checks = {key: payload.get(key) is True for key in
                  ("certificate_valid", "nginx_config_valid", "nginx_active", "gateway_active")}
        if not installed:
            return {"installed": False, "connected": False, "dns_name": None, "https_url": None,
                    **checks}
        https_url = "https://" + dns_name if connected else None
        return {"installed": True, "connected": connected, "dns_name": dns_name if connected else None,
                "https_url": https_url, **checks}
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
