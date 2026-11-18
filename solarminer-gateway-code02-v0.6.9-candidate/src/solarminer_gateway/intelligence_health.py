"""Readiness checks shared by the Intelligence bootstrap and tests."""
from __future__ import annotations

import json
import time
from typing import Any, Callable
from urllib.request import urlopen


OLLAMA_REQUIRED_ENV = {
    "OLLAMA_HOST": "127.0.0.1:11434",
    "OLLAMA_NO_CLOUD": "1",
    "OLLAMA_NUM_PARALLEL": "1",
    "OLLAMA_MAX_LOADED_MODELS": "1",
    "OLLAMA_KEEP_ALIVE": "5m",
    "OLLAMA_CONTEXT_LENGTH": "8192",
}


def validate_ollama_environment(raw_environment: bytes) -> None:
    """Fail unless the running Ollama process received the local-only limits."""
    entries: dict[str, str] = {}
    for item in raw_environment.split(b"\0"):
        if b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        try:
            entries[key.decode("ascii")] = value.decode("utf-8")
        except UnicodeDecodeError:
            continue
    missing = [name for name, value in OLLAMA_REQUIRED_ENV.items() if entries.get(name) != value]
    if missing:
        raise RuntimeError("ollama_effective_configuration_mismatch:" + ",".join(missing))


def validate_agent_health(payload: Any, expected_model: str) -> None:
    """Validate the agent, its SDK-backed HTTP server, Ollama, and model."""
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise RuntimeError("agent_health_status_invalid")
    if payload.get("agent") != "OpenClaude":
        raise RuntimeError("agent_health_identity_invalid")
    ollama = payload.get("ollama")
    if not isinstance(ollama, dict) or ollama.get("runtime") != "available":
        raise RuntimeError("agent_health_ollama_unavailable")
    if ollama.get("installed") is not True:
        raise RuntimeError("agent_health_model_not_installed")
    if ollama.get("model") != expected_model:
        raise RuntimeError("agent_health_model_mismatch")
    if payload.get("configured") is not True:
        raise RuntimeError("agent_health_not_configured")


def wait_for_agent_health(
    expected_model: str,
    *,
    timeout_seconds: float = 120,
    poll_interval: float = 2,
    opener: Callable[..., Any] = urlopen,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Poll loopback health until the actual agent reports ready or deadline."""
    deadline = clock() + max(0, timeout_seconds)
    last_reason = "agent_health_no_response"
    while True:
        try:
            with opener("http://127.0.0.1:8765/health", timeout=3) as response:
                if getattr(response, "status", 200) != 200:
                    last_reason = "agent_health_http_status_invalid"
                else:
                    payload = json.loads(response.read().decode("utf-8"))
                    try:
                        validate_agent_health(payload, expected_model)
                        return payload
                    except RuntimeError as exc:
                        last_reason = str(exc)
        except Exception as exc:  # avoid exposing URL, environment, or secrets in status
            last_reason = "agent_health_transport_" + type(exc).__name__
        remaining = deadline - clock()
        if remaining <= 0:
            raise RuntimeError(last_reason)
        sleep(min(max(poll_interval, 0.1), remaining))
