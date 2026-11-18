import json

import pytest

from solarminer_gateway.intelligence_health import (
    OLLAMA_REQUIRED_ENV,
    validate_agent_health,
    validate_ollama_environment,
    wait_for_agent_health,
)


def _health(*, model="qwen3.5:9b-q4_K_M", installed=True, configured=True):
    return {
        "status": "ok", "agent": "OpenClaude", "configured": configured,
        "ollama": {"runtime": "available", "model": model, "installed": installed},
    }


def test_agent_health_requires_real_sdk_server_and_expected_model():
    validate_agent_health(_health(), "qwen3.5:9b-q4_K_M")
    for payload, reason in [
        (_health(configured=False), "agent_health_not_configured"),
        (_health(installed=False), "agent_health_model_not_installed"),
        (_health(model="other"), "agent_health_model_mismatch"),
        ({"status": "ok", "agent": "other"}, "agent_health_identity_invalid"),
    ]:
        with pytest.raises(RuntimeError, match=reason):
            validate_agent_health(payload, "qwen3.5:9b-q4_K_M")


def test_ollama_process_must_have_all_local_only_limits():
    raw = b"\0".join(f"{name}={value}".encode() for name, value in OLLAMA_REQUIRED_ENV.items()) + b"\0"
    validate_ollama_environment(raw)
    with pytest.raises(RuntimeError, match="OLLAMA_NO_CLOUD"):
        validate_ollama_environment(raw.replace(b"OLLAMA_NO_CLOUD=1", b"OLLAMA_NO_CLOUD=0"))


def test_agent_health_waits_for_readiness_then_reports_success():
    responses = iter([_health(configured=False), _health()])
    now = [0.0]

    class Response:
        status = 200
        def __init__(self, payload): self.payload = payload
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read(self): return json.dumps(self.payload).encode()

    def opener(_url, timeout):
        assert timeout == 3
        return Response(next(responses))

    def sleep(seconds): now[0] += seconds
    payload = wait_for_agent_health("qwen3.5:9b-q4_K_M", timeout_seconds=3,
                                    poll_interval=1, opener=opener,
                                    clock=lambda: now[0], sleep=sleep)
    assert payload["configured"] is True
    assert now[0] == 1


def test_agent_health_timeout_preserves_safe_failure_reason():
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read(self): return json.dumps(_health(configured=False)).encode()

    with pytest.raises(RuntimeError, match="agent_health_not_configured"):
        wait_for_agent_health("qwen3.5:9b-q4_K_M", timeout_seconds=0,
                              opener=lambda *_args, **_kwargs: Response())
