import json
import ssl
import subprocess
import urllib.error

from solarminer_gateway import health_watchdog


class Response:
    status = 200

    def __init__(self, body=b'{"status":"ok"}'):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self.body


def command_result(command, stdout="", returncode=0):
    return subprocess.CompletedProcess(command, returncode, stdout, "")


def test_watchdog_restarts_gateway_after_three_consecutive_failed_health_checks(tmp_path, monkeypatch):
    monkeypatch.setattr(health_watchdog, "DATA_DIR", tmp_path)
    calls = []

    def runner(command, **_kwargs):
        calls.append(command)
        if command[1:3] == ["list-units", "--all"]:
            return command_result(command)
        return command_result(command)

    def opener(request, **_kwargs):
        if request.full_url == health_watchdog.GATEWAY_HEALTH_URL:
            raise urllib.error.URLError("offline")
        return Response()

    state_path = tmp_path / "watchdog.json"
    for _ in range(3):
        health_watchdog.check_once(runner=runner, opener=opener,
                                   context_factory=lambda **_kwargs: ssl.create_default_context(),
                                   state_path=state_path, now=lambda: 700,
                                   logger=lambda _message: None)

    assert ["/usr/bin/systemctl", "restart", "solarminer-gateway.service"] in calls
    assert json.loads(state_path.read_text())["gateway_failures"] == 0


def test_watchdog_skips_recovery_during_update_apply(tmp_path):
    calls = []

    def runner(command, **_kwargs):
        calls.append(command)
        if command[1:3] == ["list-units", "--all"]:
            return command_result(command, "solarminer-update-apply@abc.service loaded active running update\n")
        return command_result(command)

    result = health_watchdog.check_once(runner=runner, state_path=tmp_path / "watchdog.json",
                                        logger=lambda _message: None)

    assert result == {"status": "skipped", "reason": "update_or_recovery_active"}
    assert len(calls) == 1


def test_watchdog_skips_recovery_during_offline_recovery(tmp_path):
    calls = []

    def runner(command, **_kwargs):
        calls.append(command)
        if command[1:3] == ["list-units", "--all"]:
            return command_result(command, "solarminer-recovery.service loaded active running recovery\\n")
        return command_result(command)

    result = health_watchdog.check_once(runner=runner, state_path=tmp_path / "watchdog.json",
                                        logger=lambda _message: None)

    assert result == {"status": "skipped", "reason": "update_or_recovery_active"}
    assert len(calls) == 1


def test_watchdog_reloads_nginx_only_after_backend_health_is_good(tmp_path, monkeypatch):
    monkeypatch.setattr(health_watchdog, "DATA_DIR", tmp_path)
    calls = []

    def runner(command, **_kwargs):
        calls.append(command)
        if command[1:3] == ["list-units", "--all"]:
            return command_result(command)
        if command[1:2] == ["is-active"]:
            return command_result(command, "active\n")
        return command_result(command)

    def opener(request, **_kwargs):
        if request.full_url == health_watchdog.PROXY_HEALTH_URL:
            raise urllib.error.HTTPError(request.full_url, 502, "bad gateway", None, None)
        return Response()

    state_path = tmp_path / "watchdog.json"
    for _ in range(3):
        result = health_watchdog.check_once(runner=runner, opener=opener,
                                            context_factory=lambda **_kwargs: ssl.create_default_context(),
                                            state_path=state_path, now=lambda: 700,
                                            logger=lambda _message: None)

    assert result["status"] == "proxy_unhealthy"
    assert ["/usr/sbin/nginx", "-t"] in calls
    assert ["/usr/bin/systemctl", "reload", "nginx.service"] in calls


def test_watchdog_rolls_back_recent_release_after_six_local_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(health_watchdog, "DATA_DIR", tmp_path)
    update_state = tmp_path / "update-state.json"
    update_state.write_text(json.dumps({
        "state": "COMMITTED",
        "previous_target": "releases/0.6.95",
        "new_target": "releases/0.6.96",
        "backup_path": str(tmp_path / "backups/pre-update.sqlite3"),
        "finished_at_utc": "1970-01-01T00:00:00Z",
    }))
    monkeypatch.setattr(health_watchdog, "UPDATE_STATE_PATH", update_state)
    calls = []

    def runner(command, **_kwargs):
        calls.append(command)
        if command[1:3] == ["list-units", "--all"]:
            return command_result(command)
        if command[:3] == ["/usr/bin/tailscale", "status", "--json"]:
            return command_result(command, '{"Self":{"Online":true}}')
        if "--rollback-committed" in command:
            return command_result(command, '{"status":"recovered","state":"ROLLED_BACK"}')
        return command_result(command)

    def opener(request, **_kwargs):
        if request.full_url == health_watchdog.GATEWAY_HEALTH_URL:
            raise urllib.error.URLError("local service unavailable")
        return Response()

    state_path = tmp_path / "watchdog.json"
    for _ in range(health_watchdog.ROLLBACK_FAILURE_THRESHOLD):
        health_watchdog.check_once(runner=runner, opener=opener,
                                   context_factory=lambda **_kwargs: ssl.create_default_context(),
                                   state_path=state_path, now=lambda: 1000,
                                   logger=lambda _message: None)

    assert ["/usr/bin/python3", "-m", "solarminer_gateway.system_update_pipeline",
            "--rollback-committed"] in calls
    assert json.loads(state_path.read_text())["automatic_rollback_completed"] == 1000


def test_watchdog_never_uses_stale_update_for_automatic_rollback(tmp_path):
    update_state = tmp_path / "update-state.json"
    update_state.write_text(json.dumps({
        "state": "COMMITTED", "previous_target": "releases/old", "new_target": "releases/new",
        "backup_path": str(tmp_path / "backup"), "finished_at_utc": "1970-01-01T00:00:00Z",
    }))
    assert not health_watchdog._recent_committed_update(update_state, timestamp=1000 + 25 * 60 * 60)


def test_watchdog_defers_rollback_when_both_external_signals_are_down(tmp_path, monkeypatch):
    update_state = tmp_path / "update-state.json"
    update_state.write_text(json.dumps({
        "state": "COMMITTED", "previous_target": "releases/old", "new_target": "releases/new",
        "backup_path": str(tmp_path / "backup"), "finished_at_utc": "1970-01-01T00:00:00Z",
    }))
    monkeypatch.setattr(health_watchdog, "UPDATE_STATE_PATH", update_state)
    calls = []

    def runner(command, **_kwargs):
        calls.append(command)
        return command_result(command)

    state = {"failures_since_healthy": health_watchdog.ROLLBACK_FAILURE_THRESHOLD}
    attempted = health_watchdog._rollback_recent_release(
        state, timestamp=1000, runner=runner, network_available=False,
        logger=lambda _message: None,
    )

    assert attempted is False
    assert not any("--rollback-committed" in command for command in calls)
