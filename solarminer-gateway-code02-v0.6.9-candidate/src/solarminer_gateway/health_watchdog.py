"""Independent local recovery for a hung Gateway or Nginx proxy."""
from __future__ import annotations

import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

DATA_DIR = Path(os.environ.get("SOLARMINER_DATA_DIR", "/var/lib/solarminer"))
STATE_FILE = DATA_DIR / "gateway-watchdog.json"
GATEWAY_HEALTH_URL = "https://127.0.0.1:8443/api/v1/health"
PROXY_HEALTH_URL = "https://127.0.0.1/api/v1/health"
FAILURE_THRESHOLD = 3
RESTART_COOLDOWN_SECONDS = 600


def _request_health(url: str, context: ssl.SSLContext, *, timeout: float = 4.0,
                    opener: Callable[..., Any] = urllib.request.urlopen) -> tuple[str, str | None]:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "Connection": "close"})
    try:
        with opener(request, timeout=timeout, context=context) as response:
            if response.status != 200:
                return "unhealthy", f"http_{response.status}"
            payload = json.loads(response.read(65536))
            if isinstance(payload, dict) and payload.get("status") == "ok":
                return "healthy", None
            return "unhealthy", "health_payload_not_ok"
    except urllib.error.HTTPError as exc:
        return "unhealthy", f"http_{exc.code}"
    except (OSError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        return "unreachable", type(exc).__name__


def _run(command: list[str], *, runner: Callable[..., Any] = subprocess.run,
         timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return runner(command, capture_output=True, text=True, timeout=timeout, check=False)


def _update_is_running(*, runner: Callable[..., Any] = subprocess.run) -> bool:
    result = _run(["/usr/bin/systemctl", "list-units", "--all", "--type=service", "--no-legend",
                   "solarminer-update-apply@*.service", "solarminer-recovery.service"], runner=runner)
    if result.returncode != 0:
        # When systemd cannot answer, recovery must not race an installer.
        return True
    return any(len(parts := line.split()) > 2 and parts[2] in {"active", "activating", "deactivating"}
               for line in result.stdout.splitlines())


def _load_state(path: Path = STATE_FILE) -> dict[str, Any]:
    try:
        if path.is_symlink():
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(state: dict[str, Any], path: Path = STATE_FILE) -> None:
    if path.is_symlink():
        raise OSError("watchdog_state_must_not_be_symlink")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.is_symlink():
        raise OSError("watchdog_state_temp_must_not_be_symlink")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(state, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def check_once(*, runner: Callable[..., Any] = subprocess.run,
               opener: Callable[..., Any] = urllib.request.urlopen,
               context_factory: Callable[..., ssl.SSLContext] | None = None,
               state_path: Path = STATE_FILE,
               now: Callable[[], float] = time.time,
               logger: Callable[[str], None] = print) -> dict[str, Any]:
    if _update_is_running(runner=runner):
        logger("watchdog: update/recovery operation active or status unavailable; skipped")
        return {"status": "skipped", "reason": "update_or_recovery_active"}

    cert = DATA_DIR / "server.crt"
    try:
        make_context = context_factory or ssl.create_default_context
        gateway_context = make_context(cafile=str(cert))
    except (OSError, ssl.SSLError, ValueError):
        logger("watchdog: Gateway TLS trust file unavailable; no restart attempted")
        return {"status": "blocked", "reason": "gateway_tls_trust_unavailable"}
    proxy_context = ssl._create_unverified_context()  # loopback-only probe of the local TLS proxy
    gateway_state, gateway_reason = _request_health(GATEWAY_HEALTH_URL, gateway_context, opener=opener)
    proxy_state, proxy_reason = _request_health(PROXY_HEALTH_URL, proxy_context, opener=opener)
    state = _load_state(state_path)
    timestamp = now()

    if gateway_state == "healthy":
        state["gateway_failures"] = 0
    else:
        state["gateway_failures"] = int(state.get("gateway_failures", 0)) + 1
        logger(f"watchdog: Gateway health {gateway_state} ({gateway_reason or 'unknown'})")

    if gateway_state != "healthy":
        last_restart = float(state.get("gateway_last_restart", 0) or 0)
        if state["gateway_failures"] >= FAILURE_THRESHOLD and timestamp - last_restart >= RESTART_COOLDOWN_SECONDS:
            if _update_is_running(runner=runner):
                logger("watchdog: update/recovery operation became active; restart skipped")
                return {"status": "skipped", "reason": "update_or_recovery_active"}
            result = _run(["/usr/bin/systemctl", "restart", "solarminer-gateway.service"], runner=runner, timeout=20)
            if result.returncode == 0:
                state["gateway_last_restart"] = timestamp
                state["gateway_failures"] = 0
                logger("watchdog: restarted Gateway after three failed health checks")
            else:
                logger("watchdog: Gateway restart failed")
        state["proxy_failures"] = 0
        _save_state(state, state_path)
        return {"status": "gateway_unhealthy", "gateway": gateway_state, "proxy": proxy_state}

    if proxy_state == "healthy":
        state["proxy_failures"] = 0
        _save_state(state, state_path)
        return {"status": "healthy", "gateway": gateway_state, "proxy": proxy_state}

    state["proxy_failures"] = int(state.get("proxy_failures", 0)) + 1
    logger(f"watchdog: Nginx proxy health {proxy_state} ({proxy_reason or 'unknown'})")
    if state["proxy_failures"] >= FAILURE_THRESHOLD:
        if _update_is_running(runner=runner):
            logger("watchdog: update/recovery operation became active; Nginx reload skipped")
            return {"status": "skipped", "reason": "update_or_recovery_active"}
        config = _run(["/usr/sbin/nginx", "-t"], runner=runner)
        if config.returncode != 0:
            logger("watchdog: Nginx configuration test failed; no reload attempted")
            state["proxy_last_failure"] = timestamp
            _save_state(state, state_path)
            return {"status": "nginx_config_invalid", "gateway": "healthy"}
        service_state = _run(["/usr/bin/systemctl", "is-active", "nginx.service"], runner=runner)
        action = "reload" if service_state.returncode == 0 and service_state.stdout.strip() == "active" else "start"
        result = _run(["/usr/bin/systemctl", action, "nginx.service"], runner=runner, timeout=20)
        if result.returncode == 0:
            state["proxy_failures"] = 0
            state["proxy_last_restart"] = timestamp
            logger(f"watchdog: Nginx {action} requested after three failed proxy checks")
        else:
            logger(f"watchdog: Nginx {action} failed")
    _save_state(state, state_path)
    return {"status": "proxy_unhealthy", "gateway": "healthy", "proxy": proxy_state}


def main() -> int:
    result = check_once()
    return 1 if result.get("status") in {"blocked", "nginx_config_invalid"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
