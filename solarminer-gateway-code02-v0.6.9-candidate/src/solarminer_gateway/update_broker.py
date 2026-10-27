"""Root-owned, socket-activated broker for fixed, narrowly scoped helpers."""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid

HELPER = "/usr/sbin/solarminer-update-apply"
TAILSCALE_INFO_HELPER = "/usr/sbin/solarminer-tailscale-info"
TAILSCALE_CONNECT_HELPER = "/usr/sbin/solarminer-tailscale-connect"
UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
TAILSCALE_DNS_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.ts\.net$")
TAILSCALE_AUTH_PATTERN = re.compile(r"^https://login\.tailscale\.com/a/[A-Za-z0-9_-]{6,128}$")
DIAGNOSTIC_UNITS = (
    "solarminer-gateway.service", "solarminer-update-check-daily.service",
    "solarminer-gateway-watchdog.service", "solarminer-gateway-watchdog.timer",
    "solarminer-update-apply@*.service", "solarminer-recovery.service",
    "solarminer-recovery.timer", "solarminer-tailscale-cert.service", "nginx.service",
)
DIAGNOSTIC_SECRET_PATTERNS = (
    (re.compile(r"(?i)(\b(?:password|passwd|token|secret|authorization|access[_-]?token|api[_-]?key)\b\s*[:=]\s*)([^\s,;]+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.DOTALL), "[REDACTED PRIVATE KEY]"),
    (re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]"), ""),
)
TAILSCALE_CERT_LOG = "/var/log/solarminer-tailscale-cert.log"
TAILSCALE_CERT_LOG_MAX_BYTES = 12_000
NGINX_ERROR_LOG = "/var/log/nginx/error.log"
NGINX_ERROR_LOG_MAX_BYTES = 8_000
CONSOLE_SERVICES = {
    "solarminer-gateway.service": "gateway",
    "solarminer-gateway-watchdog.timer": "gateway_watchdog",
    "solarminer-recovery.service": "offline_recovery",
    "solarminer-recovery.timer": "offline_recovery_timer",
    "nginx.service": "nginx",
    "tailscaled.service": "tailscale",
    "solarminer-update-check-daily.timer": "daily_update_check",
    "solarminer-update-broker.socket": "privileged_update_broker",
    "solarminer-tailscale-cert.timer": "tailscale_certificate_renewal",
}
def _cpu_sample() -> tuple[int, int] | None:
    try:
        with open("/proc/stat", "r", encoding="ascii") as stream:
            fields = stream.readline().split()
        values = [int(value) for value in fields[1:]]
        if len(values) < 4:
            return None
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return sum(values), idle
    except (OSError, ValueError):
        return None


def _system_resources() -> dict[str, object]:
    first = _cpu_sample()
    if first:
        time.sleep(0.12)
    second = _cpu_sample() if first else None
    cpu_percent = None
    if first and second:
        total_delta, idle_delta = second[0] - first[0], second[1] - first[1]
        if total_delta > 0 and idle_delta >= 0:
            cpu_percent = round(max(0.0, min(100.0, 100 * (1 - idle_delta / total_delta))), 1)
    memory = {}
    try:
        with open("/proc/meminfo", "r", encoding="ascii") as stream:
            for line in stream:
                key, _, value = line.partition(":")
                if key in {"MemTotal", "MemAvailable"}:
                    memory[key] = int(value.strip().split()[0]) * 1024
        total, available = memory["MemTotal"], memory["MemAvailable"]
        memory_data = {"total_bytes": total, "used_bytes": max(0, total - available),
                       "available_bytes": available,
                       "used_percent": round(100 * (total - available) / total, 1) if total else None}
    except (OSError, ValueError, KeyError, IndexError):
        memory_data = {"total_bytes": None, "used_bytes": None, "available_bytes": None, "used_percent": None}
    try:
        disk = shutil.disk_usage("/var/lib/solarminer")
        disk_data = {"path": "/var/lib/solarminer", "total_bytes": disk.total,
                     "used_bytes": disk.used, "free_bytes": disk.free,
                     "used_percent": round(100 * disk.used / disk.total, 1) if disk.total else None}
    except OSError:
        disk_data = {"path": "/var/lib/solarminer", "total_bytes": None,
                     "used_bytes": None, "free_bytes": None, "used_percent": None}
    return {"cpu_percent": cpu_percent, "cpu_count": os.cpu_count(), "memory": memory_data, "disk": disk_data}


def _service_statuses(runner=subprocess.run) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for unit, name in CONSOLE_SERVICES.items():
        try:
            result = runner(["/usr/bin/systemctl", "is-active", unit],
                            capture_output=True, text=True, timeout=2, check=False)
            state = result.stdout.strip() if isinstance(result.stdout, str) else ""
            statuses[name] = state if state in {"active", "inactive", "failed"} else "unknown"
        except (OSError, subprocess.TimeoutExpired):
            statuses[name] = "unknown"
    return statuses


def _redact_diagnostics(value: str) -> str:
    for pattern, replacement in DIAGNOSTIC_SECRET_PATTERNS:
        value = pattern.sub(replacement, value)
    return value[-24000:]


def _read_fixed_root_log(path: str, max_bytes: int) -> str:
    """Read a bounded tail from one fixed, root-owned regular log file."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_size <= 0:
                return ""
            stream.seek(max(0, metadata.st_size - max_bytes))
            data = stream.read(max_bytes)
        text = data.decode("utf-8", errors="replace")
        if metadata.st_size > max_bytes:
            text = text.partition("\n")[2]
        return text.strip()
    except (OSError, ValueError):
        return ""


def _read_tailscale_cert_log() -> str:
    """Read only the fixed, root-owned Tailscale certificate service log."""
    return _read_fixed_root_log(TAILSCALE_CERT_LOG, TAILSCALE_CERT_LOG_MAX_BYTES)


def _read_nginx_error_log() -> str:
    """Read the bounded Nginx error tail to diagnose API and WebSocket proxy failures."""
    return _read_fixed_root_log(NGINX_ERROR_LOG, NGINX_ERROR_LOG_MAX_BYTES)


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
            # Keep a week of fixed, allowlisted service journals so an Owner can
            # inspect an update failure after a reboot or after returning remotely.
            args = ["/usr/bin/journalctl", "--since=-7 days", "--lines=400", "--no-pager", "--output=short-iso"]
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
        logs = result.stdout.rstrip()
        # Capture the current Nginx parser output directly. The Tailscale
        # status helper intentionally returns booleans, which hid the useful
        # `nginx -t` error from the Owner console.
        try:
            # The broker's strict filesystem sandbox explicitly permits the
            # Nginx log and runtime paths; otherwise this check reports EROFS
            # from the sandbox instead of validating the host configuration.
            nginx_check = runner(["/usr/sbin/nginx", "-t"], capture_output=True,
                                 text=True, timeout=8, check=False)
            nginx_output = "\n".join(part.strip() for part in
                                      (nginx_check.stdout or "", nginx_check.stderr or "") if part.strip())
        except (OSError, subprocess.TimeoutExpired):
            nginx_output = "Nginx configuration check could not run."
        if nginx_output:
            logs += "\n\n--- Current Nginx configuration validation ---\n" + nginx_output
        nginx_errors = _read_nginx_error_log()
        if nginx_errors:
            logs += "\n\n--- Recent Nginx proxy errors ---\n" + nginx_errors
        cert_log = _read_tailscale_cert_log()
        if cert_log:
            logs += "\n\n--- SolarMiner Tailscale certificate and Nginx setup log ---\n" + cert_log
        truncated = len(logs) > 24000
        return {"status": "ok", "logs": _redact_diagnostics(logs),
                "services": _service_statuses(runner), "resources": _system_resources(),
                "truncated": truncated,
                "scope": "allowlisted_services_last_7_days_including_update_recovery_plus_tailscale_setup_log_tail"}
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
        nginx_error = payload.get("nginx_config_error")
        if not isinstance(nginx_error, str):
            nginx_error = ""
        nginx_error = _redact_diagnostics(nginx_error)[:1200]
        if not installed:
            return {"installed": False, "connected": False, "dns_name": None, "https_url": None,
                    **checks, "nginx_config_error": nginx_error}
        https_url = "https://" + dns_name if connected else None
        return {"installed": True, "connected": connected, "dns_name": dns_name if connected else None,
                "https_url": https_url, **checks, "nginx_config_error": nginx_error}
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
