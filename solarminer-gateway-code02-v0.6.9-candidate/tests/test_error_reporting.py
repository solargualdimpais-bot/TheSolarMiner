import json
import logging
import os

from solarminer_gateway import error_reporting


class _Response:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit):
        return json.dumps({
            "html_url": f"https://github.com/{error_reporting.REPOSITORY}/issues/123"
        }).encode()


def test_sanitize_message_removes_credentials_and_identifiers():
    value = error_reporting.sanitize_message(
        "password=hunter2 token=ghp_123 https://example.test/path?token=x "
        "192.168.8.168 fd12:3456::168 AA:BB:CC:DD:EE:FF username=Hugo /var/lib/solarminer/key"
    )
    for secret in ("hunter2", "ghp_123", "example.test", "192.168.8.168", "fd12:3456::168", "AA:BB:CC:DD:EE:FF", "Hugo", "/var/lib"):
        assert secret not in value


def test_error_handler_queues_error_but_not_warning(tmp_path):
    path = tmp_path / "queue.ndjson"
    handler = error_reporting.ErrorQueueHandler(level=logging.ERROR)
    handler.emit(logging.LogRecord("solarminer.gateway", logging.WARNING, "", 0, "warning", (), None))
    assert not path.exists()

    error_reporting.enqueue_record(
        logging.LogRecord("solarminer.gateway", logging.ERROR, "", 1, "connection failed", (), None), path
    )
    item = json.loads(path.read_text().strip())
    assert item["level"] == "ERROR"
    assert item["message"] == "connection failed"


def test_flush_posts_sanitized_batch_and_retains_newer_records(tmp_path, monkeypatch):
    queue = tmp_path / "queue.ndjson"
    token = tmp_path / "token"
    token.write_text("secret-token-value")
    records = [
        {"id": f"id-{i}", "occurred_at": "2026-10-22T00:00:00+00:00", "level": "ERROR",
         "component": "solarminer.gateway", "message": f"failure {i}", "exception_type": None}
        for i in range(101)
    ]
    queue.write_text("".join(json.dumps(item) + "\n" for item in records))
    captured = {}

    class _Opener:
        def open(self, request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return _Response()

    monkeypatch.setattr(error_reporting.urllib.request, "build_opener", lambda *_: _Opener())
    result = error_reporting.flush_reports(queue, token, tmp_path / "system-fingerprint")

    assert result["status"] == "sent"
    assert result["sent"] == 50
    remaining = [json.loads(line) for line in queue.read_text().splitlines()]
    assert [item["id"] for item in remaining] == [f"id-{i}" for i in range(50, 101)]
    request = captured["request"]
    assert request.full_url == error_reporting.ISSUES_URL
    assert "TheSolarMiner-Diagnostics" in request.full_url
    assert request.get_header("Authorization") == "Bearer secret-token-value"
    body = request.data.decode()
    assert "failure 0" in body
    assert "secret-token-value" not in body


def test_failed_github_request_keeps_queue(tmp_path, monkeypatch):
    queue = tmp_path / "queue.ndjson"
    token = tmp_path / "token"
    token.write_text("secret-token-value")
    record = {"id": "one", "occurred_at": "now", "level": "ERROR", "component": "gateway",
              "message": "failure", "exception_type": None}
    original = json.dumps(record) + "\n"
    queue.write_text(original)

    class _Opener:
        def open(self, *_args, **_kwargs):
            raise OSError("network offline")

    monkeypatch.setattr(error_reporting.urllib.request, "build_opener", lambda *_: _Opener())
    try:
        error_reporting.flush_reports(queue, token)
    except OSError:
        pass
    else:
        raise AssertionError("network failure should be propagated to the sender")
    assert queue.read_text() == original


def test_missing_token_keeps_reports_queued(tmp_path):
    queue = tmp_path / "queue.ndjson"
    queue.write_text("{}\n")
    result = error_reporting.flush_reports(queue, tmp_path / "missing-token")
    assert result == {"status": "not_configured", "sent": 0}
    assert queue.read_text() == "{}\n"


def test_private_diagnostics_token_storage_is_atomic_and_never_returned(tmp_path):
    token_path = tmp_path / "private" / "github-diagnostics-token"
    token = "github_pat_" + "x" * 40
    error_reporting.configure_diagnostics_upload(token, token_path)
    assert token_path.read_text() == token
    assert error_reporting.diagnostics_upload_status(token_path) == {
        "configured": True, "destination": "solargualdimpais-bot/TheSolarMiner-Diagnostics"
    }
    if os.name == "posix":
        assert token_path.stat().st_mode & 0o777 == 0o600
    error_reporting.remove_diagnostics_upload(token_path)
    assert error_reporting.diagnostics_upload_status(token_path)["configured"] is False


def test_private_diagnostics_token_rejects_non_fine_grained_and_symlink_paths(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="github_fine_grained_token_required"):
        error_reporting.configure_diagnostics_upload("not-a-token", tmp_path / "token")
    target = tmp_path / "target"
    target.write_text("untouched")
    link = tmp_path / "private-token"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="github_token_path_unsafe"):
        error_reporting.configure_diagnostics_upload("github_pat_" + "x" * 40, link)
    assert target.read_text() == "untouched"


def test_system_snapshot_uses_broker_and_redacts_secrets_and_private_addresses(monkeypatch):
    from solarminer_gateway import update_helper_client
    monkeypatch.setattr(update_helper_client, "request", lambda action: {
        "status": "ok", "services": {"gateway": "active"},
        "resources": {"cpu_percent": 4.5, "disk": {"path": "/private/location", "used_percent": 10}},
        "logs": "failed password=hunter2 at https://private.example/x from 192.168.1.20",
    })
    snapshot = error_reporting._collect_system_diagnostics()
    assert "service gateway: active" in snapshot
    assert "cpu_percent: 4.5" in snapshot
    assert "used_percent: 10" in snapshot
    assert "hunter2" not in snapshot
    assert "private.example" not in snapshot
    assert "192.168.1.20" not in snapshot
    assert "/private/location" not in snapshot


def test_system_failure_is_reported_without_app_queue_and_is_deduplicated(tmp_path, monkeypatch):
    from solarminer_gateway import update_helper_client
    queue = tmp_path / "queue.ndjson"
    token_path = tmp_path / "token"
    fingerprint_path = tmp_path / "fingerprint"
    token_path.write_text("github_pat_" + "x" * 40)
    monkeypatch.setattr(update_helper_client, "request", lambda action: {
        "status": "ok", "services": {"gateway": "failed"},
        "logs": "2026-10-26 ERROR update recovery preflight failed password=private",
        "resources": {},
    })
    captured = []

    class _Opener:
        def open(self, request, timeout):
            captured.append(request)
            return _Response()

    monkeypatch.setattr(error_reporting.urllib.request, "build_opener", lambda *_: _Opener())
    first = error_reporting.flush_reports(queue, token_path, fingerprint_path)
    assert first["status"] == "sent"
    assert first["system_diagnostics"] is True
    assert not queue.exists()
    body = json.loads(captured[0].data.decode())["body"]
    assert "update recovery preflight failed" in body
    assert "private" not in body
    assert fingerprint_path.exists()
    second = error_reporting.flush_reports(queue, token_path, fingerprint_path)
    assert second == {"status": "empty", "sent": 0}
    assert len(captured) == 1
