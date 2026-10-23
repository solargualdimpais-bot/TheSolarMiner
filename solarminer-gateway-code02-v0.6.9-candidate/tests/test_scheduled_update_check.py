from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from pathlib import Path
import socket

import pytest

from solarminer_gateway import scheduled_update_check as daily
from solarminer_gateway import update_broker, update_helper_client


def test_api_and_daily_units_keep_privilege_escalation_disabled():
    packaging = Path(__file__).parents[1] / "packaging"
    for name in ("solarminer-gateway.service", "solarminer-update-check-daily.service"):
        content = (packaging / name).read_text(encoding="utf-8")
        assert "NoNewPrivileges=true" in content
        assert "ReadWritePaths=/var/lib/solarminer" in content
        assert "RestrictSUIDSGID=true" in content
        assert "ProtectSystem=strict" in content


def test_update_broker_is_root_owned_and_socket_is_private_to_service_account():
    packaging = Path(__file__).parents[1] / "packaging"
    socket_unit = (packaging / "solarminer-update-broker.socket").read_text(encoding="utf-8")
    service_unit = (packaging / "solarminer-update-broker@.service").read_text(encoding="utf-8")
    assert "SocketUser=solarminer" in socket_unit
    assert "SocketMode=0600" in socket_unit
    assert "Accept=yes" in socket_unit
    assert "Service=" not in socket_unit
    assert "User=root" in service_unit
    assert "NoNewPrivileges=true" in service_unit
    assert "RestrictSUIDSGID=true" in service_unit
    assert "ReadWritePaths=/opt/solarminer /var/lib/solarminer" in service_unit


def test_root_broker_accepts_only_allowlisted_actions_and_validated_enqueue(monkeypatch):
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "status": "APPLY_QUEUED", "operation_id": "12345678-1234-1234-1234-123456789abc",
            "extra_secret": "must-not-be-returned",
        }), stderr="")

    op = "12345678-1234-1234-1234-123456789abc"
    response = update_broker.handle_request(
        json.dumps({"action": "enqueue", "operation_id": op}).encode() + b"\n", runner)
    assert response == {"status": "APPLY_QUEUED", "operation_id": op}
    assert calls[0][0] == ["/usr/sbin/solarminer-update-apply", "--enqueue", op]
    assert calls[0][1]["timeout"] == 12
    assert update_broker.handle_request(b'{"action":"enqueue","operation_id":"../../etc/passwd"}\n', runner)["status"] == "error"
    assert update_broker.handle_request(b'{"action":"recover"}\n', runner)["status"] == "error"
    assert update_broker.handle_request(b'{"action":"system_action","operation":"anything"}\n', runner)["status"] == "error"
    assert len(calls) == 1


def test_root_broker_console_reads_fixed_service_logs_and_tailscale_setup_log_and_redacts_secrets(monkeypatch):
    calls = []
    raw_logs = ("2026-10-22T10:00:00+00:00 gateway INFO password=visible-secret Bearer abc.def.ghi\n"
                "-----BEGIN ED25519 PRIVATE KEY-----\nsecret-key-material\n-----END ED25519 PRIVATE KEY-----\n")

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=raw_logs, stderr="must-not-leak")

    monkeypatch.setattr(update_broker, "_read_tailscale_cert_log", lambda: "nginx: [emerg] certificate file missing\n")
    response = update_broker.handle_request(b'{"action":"diagnostics"}\n', runner)
    assert calls[0][0][0] == "/usr/bin/journalctl"
    assert "--no-pager" in calls[0][0]
    assert "--lines=160" in calls[0][0]
    assert calls[0][1]["timeout"] == 12
    assert response["status"] == "ok"
    assert "visible-secret" not in response["logs"]
    assert "abc.def.ghi" not in response["logs"]
    assert "secret-key-material" not in response["logs"]
    assert "must-not-leak" not in response["logs"]
    assert "Tailscale certificate and Nginx setup log" in response["logs"]
    assert "nginx: [emerg] certificate file missing" in response["logs"]
    assert response["scope"] == "allowlisted_services_last_2_hours_plus_tailscale_setup_log_tail"
    assert set(response["services"]) == set(update_broker.CONSOLE_SERVICES.values())
    assert set(response["resources"]) == {"cpu_percent", "cpu_count", "memory", "disk"}


def test_service_status_reader_uses_only_fixed_units_and_distinguishes_failure():
    requested = []

    def runner(args, **_kwargs):
        requested.append(args)
        state = "failed" if args[-1] == "nginx.service" else "active"
        return SimpleNamespace(returncode=0 if state == "active" else 3, stdout=state, stderr="")

    statuses = update_broker._service_statuses(runner)
    assert statuses["nginx"] == "failed"
    assert statuses["gateway"] == "active"
    assert {call[-1] for call in requested} == set(update_broker.CONSOLE_SERVICES)
    assert all(call[:2] == ["/usr/bin/systemctl", "is-active"] for call in requested)


@pytest.mark.parametrize(("action", "helper", "payload"), [
    ("tailscale_status", "/usr/sbin/solarminer-tailscale-info",
     {"installed": True, "connected": True, "dns_name": "solarminer.tailnet.ts.net"}),
    ("tailscale_connect", "/usr/sbin/solarminer-tailscale-connect",
     {"started": True, "connected": False, "auth_url": "https://login.tailscale.com/a/AbCdEf123456"}),
])
def test_root_broker_runs_fixed_tailscale_helpers_and_returns_only_sanitized_data(action, helper, payload):
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps({**payload, "secret": "never-return"}), stderr="")

    response = update_broker.handle_request(json.dumps({"action": action}).encode() + b"\n", runner)
    assert calls[0][0] == [helper]
    assert calls[0][1]["timeout"] == (28 if action == "tailscale_connect" else 12)
    assert "secret" not in response
    if action == "tailscale_status":
        assert response == {
            "installed": True, "connected": True,
            "dns_name": "solarminer.tailnet.ts.net",
            "https_url": "https://solarminer.tailnet.ts.net",
            "certificate_valid": False, "nginx_config_valid": False,
            "nginx_active": False, "gateway_active": False,
        }
    else:
        assert response == payload


@pytest.mark.parametrize(("payload", "reason"), [
    ({"installed": True, "connected": True, "dns_name": "attacker.example"}, "tailscale_status_invalid"),
    ({"installed": True, "connected": True, "dns_name": "solarminer.tailnet.ts.net", "https_url": "https://attacker.example"}, None),
])
def test_root_broker_rejects_invalid_tailscale_identity_or_ignores_helper_supplied_urls(payload, reason):
    def runner(_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    response = update_broker.handle_request(b'{"action":"tailscale_status"}\n', runner)
    if reason:
        assert response == {"status": "error", "reason": reason}
    else:
        assert response["https_url"] == "https://solarminer.tailnet.ts.net"


def test_root_broker_does_not_report_pending_tailscale_login_as_success_without_auth_url():
    def runner(_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout='{"started":true,"connected":false,"auth_url":null}', stderr="")

    assert update_broker.handle_request(b'{"action":"tailscale_connect"}\n', runner) == {
        "status": "error", "reason": "tailscale_auth_url_missing"
    }


def test_helper_client_uses_private_unix_socket_and_rejects_bad_operation_ids(monkeypatch, tmp_path):
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("Unix domain sockets are not available on this Windows test host")
    import threading

    path = tmp_path / "broker.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen(1)
    monkeypatch.setenv("SOLARMINER_UPDATE_BROKER_SOCKET", str(path))
    received = {}

    def serve():
        connection, _ = listener.accept()
        with connection:
            data = b""
            while not data.endswith(b"\n"):
                chunk = connection.recv(4096)
                if not chunk:
                    break
                data += chunk
            received.update(json.loads(data))
            connection.sendall(b'{"status":"ready"}\n')

    worker = threading.Thread(target=serve)
    worker.start()
    assert update_helper_client.request("preflight") == {"status": "ready"}
    worker.join(timeout=2)
    listener.close()
    assert received == {"action": "preflight"}
    try:
        update_helper_client.request("enqueue", "not-a-uuid")
    except ValueError as exc:
        assert str(exc) == "update_operation_id_invalid"
    else:
        raise AssertionError("invalid operation ID was accepted")


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, *_args):
        query = _args[0]
        if "system_state" in query:
            return SimpleNamespace(fetchone=lambda: {"value": "https://github.com/owner/repo"})
        return SimpleNamespace(fetchone=lambda: None)


def _prepare(monkeypatch, result):
    operation_id = str(uuid.uuid4())
    source = {
        "repository_url": "https://github.com/owner/repo",
        "manifest_url": "https://github.com/owner/repo/releases/latest/download/solarminer-release.json",
        "manifest_origins": {"https://github.com", "https://release-assets.githubusercontent.com"},
        "package_origins": {"https://github.com", "https://release-assets.githubusercontent.com"},
    }
    monkeypatch.setattr(daily.gateway, "db", lambda: _Connection())
    monkeypatch.setattr(daily.updates, "load_update_source", lambda _url: source)
    monkeypatch.setattr(daily.gateway, "_check_system_update_manifest", lambda *_args, **_kwargs: result(operation_id))
    return operation_id


def test_daily_check_queues_only_a_verified_update_after_preflight(monkeypatch, capsys):
    operation_id = _prepare(monkeypatch, lambda op: {
        "status": "verified_staged", "operation_id": op,
        "available_version": "0.6.27", "activation_available": True,
    })
    calls = []

    def request(action, op_id=None):
        calls.append((action, op_id))
        return {"status": "APPLY_QUEUED", "operation_id": operation_id}

    monkeypatch.setattr(daily.update_helper_client, "request", request)
    assert daily.main() == 0
    assert calls == [("enqueue", operation_id)]
    assert json.loads(capsys.readouterr().out) == {
        "status": "apply_queued", "operation_id": operation_id, "target_version": "0.6.27"
    }


def test_daily_check_does_not_apply_when_preflight_fails(monkeypatch, capsys):
    _prepare(monkeypatch, lambda op: {
        "status": "verified_staged", "operation_id": op,
        "available_version": "0.6.27", "activation_available": False,
    })
    monkeypatch.setattr(daily.update_helper_client, "request", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not enqueue")))
    assert daily.main() == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "update_pipeline_preflight_failed"


def test_daily_check_requires_helper_queue_confirmation(monkeypatch, capsys):
    _prepare(monkeypatch, lambda op: {
        "status": "verified_staged", "operation_id": op,
        "available_version": "0.6.27", "activation_available": True,
    })
    monkeypatch.setattr(daily.update_helper_client, "request", lambda *_args, **_kwargs: {})
    assert daily.main() == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "update_helper_did_not_confirm_queue"


def test_daily_check_does_not_retry_a_release_with_failed_history(monkeypatch, capsys):
    _prepare(monkeypatch, lambda op: {
        "status": "verified_staged", "operation_id": op,
        "available_version": "0.6.27", "activation_available": True,
    })
    monkeypatch.setattr(daily, "_previous_apply_failed", lambda *_args: True)
    monkeypatch.setattr(daily.update_helper_client, "request", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not enqueue")))
    assert daily.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "auto_apply_blocked_after_previous_failure"
    assert result["reason"] == "owner_review_required"
