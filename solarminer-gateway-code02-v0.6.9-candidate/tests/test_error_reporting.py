import json
import logging

from solarminer_gateway import error_reporting


class _Response:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit):
        return json.dumps({
            "html_url": "https://github.com/solargualdimpais-bot/TheSolarMiner/issues/123"
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
    result = error_reporting.flush_reports(queue, token)

    assert result["status"] == "sent"
    assert result["sent"] == 100
    remaining = [json.loads(line) for line in queue.read_text().splitlines()]
    assert [item["id"] for item in remaining] == ["id-100"]
    request = captured["request"]
    assert request.full_url == error_reporting.ISSUES_URL
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
