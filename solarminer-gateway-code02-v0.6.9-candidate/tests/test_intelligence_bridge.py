import json
import time
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from solarminer_gateway import app as gateway


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "DB_PATH", tmp_path / "gateway.db")
    monkeypatch.setattr(gateway, "BOOTSTRAP_PATH", tmp_path / "bootstrap.token")
    monkeypatch.setattr(gateway, "INSTANCE_MARKER", tmp_path / "initialized.marker")
    with TestClient(gateway.app) as test_client:
        yield test_client


def _owner(client):
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    timestamp = int(time.time())
    nonce = "intelligence-bootstrap-nonce"
    bootstrap_token = gateway.BOOTSTRAP_PATH.read_text().strip()
    canonical = f"BOOTSTRAP\nowner-intelligence\nAA:BB:CC:DD:EE:71\n{timestamp}\n{nonce}"
    created = client.post("/api/v1/bootstrap/owner", json={
        "bootstrap_token": bootstrap_token, "username": "owner-intelligence",
        "password": "owner-intelligence-password-long", "mac": "AA:BB:CC:DD:EE:71",
        "public_key_pem": public, "signature": private.sign(canonical.encode()).hex(),
        "timestamp": timestamp, "nonce": nonce,
    })
    assert created.status_code == 201, created.text
    timestamp = int(time.time())
    nonce = "intelligence-login-nonce"
    canonical = f"LOGIN\nowner-intelligence\n{created.json()['device_id']}\n{timestamp}\n{nonce}"
    signed_in = client.post("/api/v1/auth/login", json={
        "username": "owner-intelligence", "password": "owner-intelligence-password-long",
        "device_id": created.json()["device_id"], "timestamp": timestamp, "nonce": nonce,
        "signature": private.sign(canonical.encode()).hex(),
    })
    assert signed_in.status_code == 200, signed_in.text
    return {"Authorization": f"Bearer {signed_in.json()['access_token']}"}


def test_intelligence_service_identity_is_read_only_and_revocable(client):
    owner = _owner(client)
    created = client.post("/api/v1/intelligence/service-tokens", headers=owner,
                          json={"label": "SolarMiner Intelligence"})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["scope"] == ["read"]
    assert body["token_display"] == "shown_once"
    service = {"Authorization": f"Bearer {body['token']}"}
    assert client.get("/api/v1/intelligence/snapshot", headers=service).status_code == 200
    assert client.put("/api/v1/energy/engine/config", headers=service, json={}).status_code == 401
    assert client.delete(f"/api/v1/intelligence/service-tokens/{body['service_id']}", headers=owner).status_code == 200
    assert client.get("/api/v1/intelligence/snapshot", headers=service).status_code == 401
    with gateway.db() as conn:
        stored = conn.execute("SELECT token_sha256 FROM intelligence_service_tokens WHERE id=?",
                              (body["service_id"],)).fetchone()[0]
        audit_actions = [row[0] for row in conn.execute(
            "SELECT action FROM audit WHERE action LIKE 'intelligence.%'").fetchall()]
    assert stored != body["token"]
    assert "intelligence.service_token.create" in audit_actions
    assert "intelligence.service_token.revoke" in audit_actions


@pytest.mark.parametrize(("method", "path", "payload"), [
    ("post", "/api/v1/integrations/tuya/switch", {"device_id": "breaker-1", "on": True}),
    ("post", "/api/v1/integrations/shelly/relay-1/switch", {"on": True}),
    ("post", "/api/v1/automations", {}),
    ("put", "/api/v1/energy/engine/config", {}),
    ("put", "/api/v1/integrations/hardware", {}),
    ("post", "/api/v1/devices/discover", {}),
])
def test_intelligence_service_identity_cannot_write_or_operate(client, method, path, payload):
    owner = _owner(client)
    created = client.post("/api/v1/intelligence/service-tokens", headers=owner, json={})
    assert created.status_code == 201, created.text
    service = {"Authorization": f"Bearer {created.json()['token']}"}

    response = getattr(client, method)(path, headers=service, json=payload)

    assert response.status_code == 401, f"{method.upper()} {path}: {response.status_code} {response.text}"


def test_intelligence_snapshot_reads_only_persisted_device_engine_state(client, monkeypatch):
    owner = _owner(client)
    token = client.post("/api/v1/intelligence/service-tokens", headers=owner, json={}).json()["token"]
    with gateway.db() as conn:
        conn.execute("INSERT INTO system_state(key,value) VALUES(?,?)", (gateway.SMART_DEVICE_ENGINE_STATE_KEY,
            json.dumps({"schema": 1, "devices": {
                "tuya:breaker-1": {"name": "Disjuntor", "status": [
                    {"code": "cur_current", "value": 1.25}, {"code": "wifi_password", "value": "do-not-leak"}],
                    "last_success_at": time.time(), "last_attempt_at": time.time(), "latency_ms": 87.5},
            }})))
    def no_device_io(*args, **kwargs):
        raise AssertionError("Intelligence must not perform device I/O")
    monkeypatch.setattr(gateway, "_smart_device_engine_tasks", set())
    monkeypatch.setattr(gateway, "_smart_device_command_router", type("Router", (), {"execute": no_device_io})())
    monkeypatch.setattr(gateway, "_tuya_devices_sync_work", no_device_io)
    response = client.get("/api/v1/intelligence/snapshot", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    snapshot = response.json()
    device = snapshot["device_engine"]["devices"][0]
    assert device["device_id"] == "breaker-1"
    assert device["measurement_valid"] is True
    assert device["status"] == [{"code": "cur_current", "value": 1.25}]
    assert snapshot["source_semantics"]["device_io_performed"] is False
    assert "do-not-leak" not in response.text
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit WHERE action='intelligence.snapshot.read'").fetchone()[0] == 1


def test_intelligence_snapshot_exposes_redacted_inventory_update_events_and_dps_knowledge(client, monkeypatch):
    token = client.post("/api/v1/intelligence/service-tokens", json={"label": "test"},
                        headers=_owner(client)).json()["token"]
    monkeypatch.setattr(gateway.hardware_integrations, "public_config", lambda: {"tuya": {"devices": [{
        "device_id": "tuya-device-1", "product_id": "product-1", "product_name": "Smart meter",
        "dps_knowledge": {"confidence": "SUGGESTED", "mapping_conflicts": [], "dps": [
            {"dps_id": 7, "semantic_code": "power", "display_name": "Power", "unit": "W",
             "confidence": "COMMUNITY_REFERENCE", "raw_value": "must-not-leak"}]},
    }]}})
    with gateway.db() as conn:
        conn.execute("""INSERT INTO gateway_device_inventory
            (device_key,source_provider,source_device_id,name,device_type,mac,last_ip,manufacturer,model,product_id,
             confirmation_status,created_at,updated_at,last_seen_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("deye:inverter-1", "deye", "inverter-1", "Inverter", "inverter", "AA:BB:CC:DD:EE:71",
             "192.168.1.10", "Deye", "SUN-15K", "pid-deye", "confirmed", "now", "now", "now"))
        conn.execute("""INSERT INTO device_events
            (occurred_at,device_id,device_name,event_type,channel_code,old_value_json,new_value_json,source)
            VALUES(?,?,?,?,?,?,?,?)""",
            ("now", "tuya-device-1", "Meter", "command_confirmed", "switch_1", "false", "true", "TUYA_LAN"))
        conn.execute("""INSERT INTO device_events
            (occurred_at,device_id,device_name,event_type,channel_code,old_value_json,new_value_json,source)
            VALUES(?,?,?,?,?,?,?,?)""",
            ("now", "tuya-device-1", "Meter", "status_change", "wifi_password", None,
             json.dumps("secret-value"), "TUYA_LAN"))
        conn.execute("INSERT INTO update_operations(id,state,installed_version,target_version,created_at,updated_at,details_json) "
                      "VALUES(?,?,?,?,?,?,?)", ("test-update", "FAILED", "0.6.243", "0.6.9", 1, 2,
                      json.dumps({"reason": "command_timeout", "command": "systemctl restart solarminer-gateway",
                                  "timeout_seconds": 20, "api_key": "must-not-leak"})))

    response = client.get("/api/v1/intelligence/snapshot", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200, response.text
    body = response.json()
    inventory = body["device_inventory"]["devices"][0]
    assert inventory["mac"] == "AA:BB:CC:DD:EE:71"
    assert inventory["last_ip"] == "192.168.1.10"
    assert body["tuya_dps_knowledge"]["devices"][0]["dps"][0]["dps_id"] == 7
    assert "raw_value" not in body["tuya_dps_knowledge"]["devices"][0]["dps"][0]
    assert body["recent_device_events"][0]["new_value"] is None
    assert body["recent_device_events"][1]["new_value"] is True
    assert body["update_history"]["records"][0]["diagnostic"]["command"] == "systemctl restart solarminer-gateway"
    assert "api_key" not in response.text and "must-not-leak" not in response.text and "secret-value" not in response.text


def test_intelligence_builds_incremental_latency_baseline_from_distinct_persisted_engine_samples(client, monkeypatch):
    owner = _owner(client)
    token = client.post("/api/v1/intelligence/service-tokens", headers=owner, json={}).json()["token"]
    current = {"last_attempt_at": time.time(), "latency_ms": 100.0, "online": True,
               "lan_online": True, "measurement_valid": True, "availability_source": "TUYA_LAN",
               "last_success_at": time.time(), "status": [{"code": "cur_current", "value": 1.0}]}
    monkeypatch.setattr(gateway, "_smart_engine_snapshot", lambda: {"devices": {"tuya:plug-1": {"name": "Plug"}}})
    monkeypatch.setattr(gateway, "_smart_engine_device_view", lambda *_args, **_kwargs: dict(current))
    monkeypatch.setattr(gateway, "energy_engine_summary", lambda **_kwargs: {"state": "available"})
    headers = {"Authorization": f"Bearer {token}"}
    baseline = None
    start = time.time()

    for index in range(5):
        current.update(last_attempt_at=start + index * 60, latency_ms=100.0)
        response = client.get("/api/v1/intelligence/snapshot", headers=headers)
        assert response.status_code == 200, response.text
        baseline = response.json()["device_engine"]["learning"]["devices"][0]
        assert baseline["sample_is_new"] is True
        assert baseline["latency_anomaly"] is False

    current.update(last_attempt_at=start + 5 * 60, latency_ms=1500.0)
    anomaly_response = client.get("/api/v1/intelligence/snapshot", headers=headers)
    learned = anomaly_response.json()["device_engine"]["learning"]["devices"][0]
    assert learned["state"] == "baseline_ready"
    assert learned["sample_count"] == 6
    assert learned["median_latency_ms"] == 100.0
    assert learned["latency_anomaly"] is True
    with gateway.db() as conn:
        observations = conn.execute("SELECT COUNT(*) FROM intelligence_device_latency_observations").fetchone()[0]
        anomalies = conn.execute("SELECT COUNT(*) FROM audit WHERE action='intelligence.learning.latency_anomaly'").fetchone()[0]
    assert observations == 6
    assert anomalies == 1


def test_intelligence_bridge_rejects_missing_or_revoked_credentials(client):
    assert client.get("/api/v1/intelligence/snapshot").status_code == 401
    assert client.get("/api/v1/intelligence/snapshot", headers={"Authorization": "Bearer invalid-token"}).status_code == 401


def test_intelligence_diagnostics_reads_bounded_errors_and_allowlisted_journal(client, monkeypatch):
    token = client.post("/api/v1/intelligence/service-tokens", json={"label": "test"},
                        headers=_owner(client)).json()["token"]
    monkeypatch.setattr(gateway.error_reporting, "read_recent_gateway_errors", lambda limit: [
        {"level": "ERROR", "component": "solarminer.test", "message": "device timeout", "occurred_at": "2026-11-16T00:00:00Z"}
    ])
    monkeypatch.setattr(gateway.update_helper_client, "request", lambda action: {
        "status": "ok", "logs": "gateway service failed", "truncated": False,
        "scope": "allowlisted test services",
    })

    response = client.get("/api/v1/intelligence/diagnostics?limit=25",
                          headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["application_errors"][0]["message"] == "device timeout"
    assert body["allowlisted_service_journal"] == "gateway service failed"
    assert body["coverage"]["system_journal"].startswith("root_broker_allowlisted_services")
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit WHERE action='intelligence.diagnostics.read' AND outcome='success'").fetchone()[0] == 1


def test_intelligence_github_reports_reuses_private_diagnostics_configuration(client, monkeypatch):
    token = client.post("/api/v1/intelligence/service-tokens", json={"label": "test"},
                        headers=_owner(client)).json()["token"]
    monkeypatch.setattr(gateway.error_reporting, "read_github_diagnostics_reports", lambda limit: {
        "state": "available", "repository": "configured-private-repository",
        "reports": [{"number": 4, "title": "Gateway update rollback", "body": "systemctl timed out"}],
    })

    response = client.get("/api/v1/intelligence/github-reports?limit=5",
                          headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200, response.text
    assert response.json()["reports"][0]["body"] == "systemctl timed out"
    assert "token" not in response.text.lower()
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit WHERE action='intelligence.github_reports.read' AND outcome='success'").fetchone()[0] == 1


def test_intelligence_can_append_only_bounded_tool_and_workspace_audit_events(client):
    token = client.post("/api/v1/intelligence/service-tokens", json={"label": "test"},
                        headers=_owner(client)).json()["token"]
    service = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/intelligence/agent-events", headers=service,
                           json={"event": "tool_denied", "tool": "Bash"})

    assert response.status_code == 201, response.text
    assert response.json() == {"status": "recorded"}
    changed = client.post("/api/v1/intelligence/agent-events", headers=service,
                          json={"event": "workspace_file_edit", "tool": "Edit",
                                "path": "src/solarminer_gateway/energy_engine.py"})
    assert changed.status_code == 201, changed.text
    tested = client.post("/api/v1/intelligence/agent-events", headers=service,
                         json={"event": "workspace_tests_passed", "tool": "solarminer_validate_intelligence_workspace"})
    assert tested.status_code == 201, tested.text
    assert client.post("/api/v1/intelligence/agent-events", headers=service,
                       json={"event": "arbitrary_write", "tool": "Bash"}).status_code == 422
    assert client.post("/api/v1/intelligence/agent-events", headers=service,
                       json={"event": "workspace_file_edit", "tool": "Edit", "path": "../etc/passwd"}).status_code == 422
    with gateway.db() as conn:
        rows = conn.execute("SELECT outcome,details_json FROM audit WHERE action='intelligence.agent.action' ORDER BY id").fetchall()
    assert [row[0] for row in rows] == ["denied", "success", "success"]
    assert json.loads(rows[0][1])["tool"] == "Bash"
    assert json.loads(rows[1][1])["path"] == "src/solarminer_gateway/energy_engine.py"


def test_intelligence_workspace_tests_go_through_the_restricted_root_broker_and_are_audited(client, monkeypatch):
    token = client.post("/api/v1/intelligence/service-tokens", json={"label": "test"},
                        headers=_owner(client)).json()["token"]
    calls = []
    monkeypatch.setattr(gateway.update_helper_client, "request", lambda action, **kwargs:
                        calls.append((action, kwargs)) or {
                            "status": "passed", "suite": "intelligence", "exit_code": 0,
                            "isolation": "separate_uid_private_network_read_only_snapshot",
                            "output": "tests 5\npass 5\nfail 0"})
    headers = {"Authorization": f"Bearer {token}"}

    result = client.post("/api/v1/intelligence/workspace-tests", headers=headers,
                         json={"suite": "intelligence"})

    assert result.status_code == 200, result.text
    assert result.json()["isolation"] == "separate_uid_private_network_read_only_snapshot"
    assert calls == [("intelligence_workspace_tests", {"suite": "intelligence"})]
    with gateway.db() as conn:
        events = [json.loads(row[0])["event"] for row in conn.execute(
            "SELECT details_json FROM audit WHERE action='intelligence.agent.action' ORDER BY id").fetchall()]
    assert events == ["workspace_tests_started", "workspace_tests_passed"]


def test_intelligence_workspace_tests_reject_missing_identity_and_invalid_suite(client, monkeypatch):
    called = []
    monkeypatch.setattr(gateway.update_helper_client, "request", lambda *args, **kwargs: called.append(args))
    assert client.post("/api/v1/intelligence/workspace-tests", json={"suite": "gateway-python"}).status_code == 401
    service = client.post("/api/v1/intelligence/service-tokens", json={"label": "test"},
                          headers=_owner(client)).json()["token"]
    response = client.post("/api/v1/intelligence/workspace-tests",
                           headers={"Authorization": f"Bearer {service}"},
                           json={"suite": "arbitrary", "command": "id"})
    assert response.status_code == 422
    assert called == []


def test_intelligence_workspace_test_runner_has_a_persistent_hourly_limit(client, monkeypatch):
    token = client.post("/api/v1/intelligence/service-tokens", json={"label": "test"},
                        headers=_owner(client)).json()["token"]
    with gateway.db() as conn:
        service_id = conn.execute("SELECT id FROM intelligence_service_tokens").fetchone()[0]
        window = int(time.time()) // 3600 * 3600
        conn.execute("INSERT INTO intelligence_workspace_test_limits(service_id,window_start,request_count) VALUES(?,?,6)",
                     (service_id, window))
    called = []
    monkeypatch.setattr(gateway.update_helper_client, "request", lambda *args, **kwargs: called.append(args))

    response = client.post("/api/v1/intelligence/workspace-tests", headers={"Authorization": f"Bearer {token}"},
                           json={"suite": "intelligence"})

    assert response.status_code == 429
    assert response.json()["detail"] == "intelligence_workspace_test_hourly_limit_reached"
    assert called == []


def test_intelligence_daily_review_is_append_only_rate_limited_redacted_and_owner_visible(client):
    owner = _owner(client)
    token = client.post("/api/v1/intelligence/service-tokens", json={"label": "test"},
                        headers=owner).json()["token"]
    service = {"Authorization": f"Bearer {token}"}
    raw_secret = "sk-abcdefghijklmnopqrstuvwxyz0123456789"
    report = f"Revisão com evidência; api_key={raw_secret}; falha observada no inversor."

    created = client.post("/api/v1/intelligence/reviews", headers=service,
                          json={"review_kind": "daily_engine_review", "report_text": report})

    assert created.status_code == 201, created.text
    duplicate = client.post("/api/v1/intelligence/reviews", headers=service,
                            json={"review_kind": "daily_engine_review", "report_text": "Outra revisão válida com evidência suficiente."})
    assert duplicate.status_code == 429
    owner_view = client.get("/api/v1/intelligence/reviews", headers=owner)
    assert owner_view.status_code == 200, owner_view.text
    saved = owner_view.json()["reviews"][0]["report_text"]
    assert "[REDACTED]" in saved
    assert raw_secret not in owner_view.text
    assert owner_view.json()["status"] == "proposal_only"
    assert client.put(f"/api/v1/intelligence/reviews/{created.json()['review_id']}", headers=owner,
                      json={"report_text": "alterado"}).status_code == 404
    with gateway.db() as conn:
        actions = [tuple(row) for row in conn.execute(
            "SELECT action,outcome FROM audit WHERE action IN ('intelligence.review.create','intelligence.review.read')")]
    assert ("intelligence.review.create", "success") in actions
    assert ("intelligence.review.create", "rate_limited") in actions
    assert ("intelligence.review.read", "success") in actions


def test_intelligence_provider_configuration_is_owner_only_and_never_returns_or_audits_key(client, monkeypatch):
    owner = _owner(client)
    secret = "sk-project-test-credential-12345678901234567890"
    calls = []
    monkeypatch.setattr(gateway.update_helper_client, "request", lambda action, **kwargs:
                        calls.append((action, kwargs)) or {"status": "ok", "configured": True})

    response = client.put("/api/v1/intelligence/provider", headers=owner,
                          json={"api_key": secret, "model": "reasoning-model-latest"})

    assert response.status_code == 200, response.text
    assert response.json()["configured"] is True
    assert secret not in response.text
    assert calls == [("intelligence_openai_set", {"api_key": secret, "model": "reasoning-model-latest"})]
    with gateway.db() as conn:
        audit_rows = conn.execute("SELECT details_json FROM audit WHERE action='intelligence.provider.configure'").fetchall()
    assert len(audit_rows) == 1
    assert secret not in audit_rows[0][0]


def test_intelligence_provider_status_reports_local_runtime_model_and_optional_cloud_state(client, monkeypatch):
    owner = _owner(client)
    monkeypatch.setattr(gateway, "_intelligence_ollama_binary_installed", lambda: True)
    real_is_file = gateway.Path.is_file
    def deny_gateway_access_to_protected_intelligence_tree(path):
        if str(path).startswith("/opt/solarminer/intelligence/"):
            raise PermissionError(13, "Permission denied", str(path))
        return real_is_file(path)
    monkeypatch.setattr(gateway.Path, "is_file", deny_gateway_access_to_protected_intelligence_tree)
    monkeypatch.setattr(gateway, "_read_intelligence_bootstrap_status", lambda: {
        "state": "running", "stage": "downloading_model", "message": "A descarregar o modelo.",
        "percent": 42, "downloaded_bytes": 420, "total_bytes": 1000, "updated_at": 1000,
    })
    monkeypatch.setattr(gateway.update_helper_client, "request", lambda action, **kwargs:
                        {"status": "ok", "configured": False})
    monkeypatch.setattr(gateway.system_components, "installed_component_status", lambda: {
        "status": "OK", "version": "0.6.261", "protocol": 1, "reason": None,
    })
    monkeypatch.setattr(gateway.intelligence_bootstrap_client, "request_system_components_status", lambda: {
        "status": "OK", "version": "0.6.261", "protocol": 1, "reason": None,
    })
    monkeypatch.setattr(gateway.system_components, "integrated_diagnostics", lambda _version, **_kwargs: {
        "status": "OK", "reason": None, "application_version": "0.6.261",
        "debian_package_version": "0.6.261", "active_release": "0.6.261",
        "system_components": {"status": "OK", "version": "0.6.261", "protocol": 1, "reason": None},
        "operating_system": {"id": "debian", "version": "13", "codename": "trixie"},
        "python_version": "3.13.0", "units": {}, "paths": {},
    })

    class FakeConnection:
        def __init__(self, host, port, timeout):
            assert host == "127.0.0.1"
            assert port in {8765, 11434}
            assert timeout in {2, 3}
            self.port = port
            self.path = None
        def close(self): pass
        def request(self, method, path, *, headers):
            assert method == "GET"
            self.path = path
        def getresponse(self):
            if self.port == 11434 and self.path == "/api/version":
                return SimpleNamespace(status=200, read=lambda _limit: b'{"version":"0.40.16"}')
            if self.port == 11434 and self.path == "/api/tags":
                # Ollama-compatible endpoints may identify a model by either
                # `name` or `model`; the Gateway must accept both shapes.
                return SimpleNamespace(status=200, read=lambda _limit: b'{"models":[{"model":"qwen3.5:9b-q4_K_M"}]}')
            health = {"configured": True, "ollama": {
                "runtime": "available", "model": "qwen3.5:9b-q4_K_M",
                "installed": True, "loaded": False, "working": False,
            }}
            return SimpleNamespace(status=200, read=lambda _limit: json.dumps(health).encode())

    monkeypatch.setattr(gateway.http.client, "HTTPConnection", FakeConnection)
    request_id = "a1a1a1a1-a1a1-41a1-81a1-a1a1a1a1a1a1"
    response = client.get("/api/v1/intelligence/provider",
                          headers={**owner, "X-SolarMiner-Diagnostic-ID": request_id})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert {key: payload[key] for key in (
        "default_provider", "agent", "ollama", "installation", "openai", "bootstrap",
    )} == {
        "default_provider": "ollama", "agent": "available",
        "ollama": {"runtime": "available", "installed": True, "loaded": False,
                   "working": False, "model": "qwen3.5:9b-q4_K_M"},
        "installation": {"node": True, "openclaude": True,
                         "ollama": True, "model": True},
        "openai": {"state": "not_configured", "configured": False,
                   "error_type": None, "credential_display": "never_returned"},
        "bootstrap": {"state": "running", "stage": "downloading_model", "message": "A descarregar o modelo.",
                      "percent": 42, "downloaded_bytes": 420, "total_bytes": 1000, "updated_at": 1000},
    }
    assert payload["system_components"] == {
        "status": "OK", "version": "0.6.261", "protocol": 1, "reason": None,
    }
    assert payload["system_diagnostics"]["status"] == "OK"
    assert payload["system_diagnostics"]["active_release"] == "0.6.261"
    assert payload["system_diagnostics"]["debian_package_version"] == "0.6.261"
    assert payload["diagnostic"]["request_id"] == request_id
    assert payload["diagnostic"]["state"] == "completed"
    assert payload["diagnostic"]["stage"] == "complete"
    assert any(step["stage"] == "ollama_runtime" for step in payload["diagnostic"]["steps"])

    trace = client.get(f"/api/v1/intelligence/provider/diagnostics/{request_id}", headers=owner)
    assert trace.status_code == 200, trace.text
    assert trace.json()["state"] == "completed"
    assert trace.json()["request_id"] == request_id
    assert client.get(f"/api/v1/intelligence/provider/diagnostics/{request_id}").status_code == 401


def test_provider_status_diagnostic_endpoint_distinguishes_unknown_and_rejects_invalid_ids(client, monkeypatch):
    owner = _owner(client)
    unknown_id = "b2b2b2b2-b2b2-42b2-82b2-b2b2b2b2b2b2"
    unknown = client.get(f"/api/v1/intelligence/provider/diagnostics/{unknown_id}", headers=owner)
    assert unknown.status_code == 200, unknown.text
    assert unknown.json()["state"] == "not_seen"
    assert unknown.json()["request_id"] == unknown_id
    assert unknown.json()["reason"] == "gateway_route_did_not_record_request"
    assert unknown.json()["agent_trace"]["state"] == "unavailable"
    assert unknown.json()["agent_trace"]["credential_status"] == "unknown"

    class UnauthorizedAgentConnection:
        def __init__(self, *_args, **_kwargs): pass
        def request(self, method, path, *, headers):
            assert method == "GET" and path == f"/v1/diagnostics/{unknown_id}"
            assert headers["Authorization"].startswith("Bearer ")
        def getresponse(self):
            return SimpleNamespace(status=401, read=lambda _limit: b'{"error":"unauthorized"}')
        def close(self): pass

    monkeypatch.setattr(gateway, "_read_intelligence_local_token", lambda: "local-client-token-123456789012345678901234567890")
    monkeypatch.setattr(gateway.http.client, "HTTPConnection", UnauthorizedAgentConnection)
    rejected = client.get(f"/api/v1/intelligence/provider/diagnostics/{unknown_id}", headers=owner)
    assert rejected.status_code == 200
    rejected_trace = rejected.json()["agent_trace"]
    assert rejected_trace["credential_status"] == "rejected"
    assert rejected_trace["reason"] == "agent_credential_rejected"
    assert "Authorization" not in json.dumps(rejected.json())
    invalid = client.get("/api/v1/intelligence/provider/diagnostics/not-a-uuid", headers=owner)
    assert invalid.status_code == 422


def test_provider_status_separates_installed_ollama_from_unreachable_local_services(client, monkeypatch):
    owner = _owner(client)
    monkeypatch.setattr(gateway, "_intelligence_ollama_binary_installed", lambda: True)
    monkeypatch.setattr(gateway.update_helper_client, "request",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError("broker absent")))
    monkeypatch.setattr(gateway.http.client, "HTTPConnection",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionRefusedError("local service absent")))
    monkeypatch.setattr(gateway, "_read_intelligence_bootstrap_status", lambda: {
        "state": "not_started", "stage": "waiting", "message": "A instalação ainda não começou.",
        "percent": None, "downloaded_bytes": None, "total_bytes": None, "updated_at": None,
    })

    response = client.get("/api/v1/intelligence/provider", headers=owner)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["agent"] == "unavailable"
    assert payload["ollama"]["runtime"] == "unavailable"
    assert payload["installation"]["ollama"] is True
    assert payload["openai"]["state"] == "status_unavailable"
    assert payload["bootstrap"]["state"] == "not_started"


def test_provider_status_reports_invalid_ollama_tags_schema_without_failing_the_route(client, monkeypatch):
    owner = _owner(client)
    monkeypatch.setattr(gateway, "_intelligence_ollama_binary_installed", lambda: True)
    monkeypatch.setattr(gateway.update_helper_client, "request", lambda *_args, **_kwargs:
                        {"status": "ok", "configured": False})
    monkeypatch.setattr(gateway, "_read_intelligence_bootstrap_status", lambda: {
        "state": "not_started", "stage": "waiting", "message": "A instalação ainda não começou.",
        "percent": None, "downloaded_bytes": None, "total_bytes": None, "updated_at": time.time(),
    })

    class MalformedOllamaConnection:
        def __init__(self, host, port, timeout):
            self.port = port
            self.path = None
        def close(self): pass
        def request(self, method, path, *, headers): self.path = path
        def getresponse(self):
            if self.path == "/api/version":
                return SimpleNamespace(status=200, read=lambda _limit: b'{"version":"0.40.16"}')
            if self.port == 11434:
                return SimpleNamespace(status=200, read=lambda _limit: b'{"models":null}')
            health = {"configured": False, "ollama": {
                "runtime": "available", "model": "qwen3.5:9b-q4_K_M",
                "installed": True, "loaded": False, "working": False,
            }}
            return SimpleNamespace(status=200, read=lambda _limit: json.dumps(health).encode())

    monkeypatch.setattr(gateway.http.client, "HTTPConnection", MalformedOllamaConnection)
    request_id = "c3c3c3c3-c3c3-43c3-83c3-c3c3c3c3c3c3"
    response = client.get("/api/v1/intelligence/provider",
                          headers={**owner, "X-SolarMiner-Diagnostic-ID": request_id})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["installation"]["ollama"] is True
    assert payload["installation"]["model"] is False
    assert payload["diagnostic"]["state"] == "degraded"
    assert payload["diagnostic"]["error_type"] == "TypeError"
    assert payload["diagnostic"]["error_reason"] == "ollama_tags_response_invalid"


def test_provider_status_continues_after_ollama_binary_check_type_error(client, monkeypatch):
    owner = _owner(client)
    monkeypatch.setattr(gateway, "_intelligence_ollama_binary_installed",
                        lambda: (_ for _ in ()).throw(TypeError("binary probe type mismatch")))
    monkeypatch.setattr(gateway.update_helper_client, "request",
                        lambda *_args, **_kwargs: {"status": "ok", "configured": False})
    monkeypatch.setattr(gateway, "_read_intelligence_bootstrap_status", lambda: {
        "state": "not_started", "stage": "waiting", "message": "A instalação ainda não começou.",
        "percent": None, "downloaded_bytes": None, "total_bytes": None, "updated_at": time.time(),
    })
    ollama_paths = []

    class RuntimeConnection:
        def __init__(self, host, port, timeout):
            self.port = port
            self.path = None
        def close(self): pass
        def request(self, method, path, *, headers): self.path = path
        def getresponse(self):
            ollama_paths.append(self.path) if self.port == 11434 else None
            if self.path == "/api/version":
                return SimpleNamespace(status=200, read=lambda _limit: b'{"version":"0.40.16"}')
            if self.path == "/api/tags":
                return SimpleNamespace(status=200, read=lambda _limit: b'{"models":[{"name":"qwen3.5:9b-q4_K_M"}]}')
            health = {"configured": False, "ollama": {
                "runtime": "available", "model": "qwen3.5:9b-q4_K_M",
                "installed": True, "loaded": False, "working": False,
            }}
            return SimpleNamespace(status=200, read=lambda _limit: json.dumps(health).encode())

    monkeypatch.setattr(gateway.http.client, "HTTPConnection", RuntimeConnection)
    request_id = "d4d4d4d4-d4d4-44d4-84d4-d4d4d4d4d4d4"
    response = client.get("/api/v1/intelligence/provider",
                          headers={**owner, "X-SolarMiner-Diagnostic-ID": request_id})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["installation"]["ollama"] is None
    assert payload["installation"]["model"] is True
    assert payload["ollama"]["runtime"] == "available"
    assert ollama_paths == ["/api/version", "/api/tags"]
    assert payload["diagnostic"]["state"] == "degraded"
    assert payload["diagnostic"]["stage"] == "complete"
    assert payload["diagnostic"]["error_type"] == "TypeError"
    assert payload["diagnostic"]["error_reason"] == "ollama_binary_check_failed"


def test_provider_status_records_type_error_from_openclaude_health(client, monkeypatch):
    owner = _owner(client)
    monkeypatch.setattr(gateway, "_intelligence_ollama_binary_installed", lambda: True)
    monkeypatch.setattr(gateway.update_helper_client, "request",
                        lambda *_args, **_kwargs: {"status": "ok", "configured": False})
    monkeypatch.setattr(gateway, "_read_intelligence_bootstrap_status", lambda: {
        "state": "not_started", "stage": "waiting", "message": "A instalação ainda não começou.",
        "percent": None, "downloaded_bytes": None, "total_bytes": None, "updated_at": time.time(),
    })
    monkeypatch.setattr(gateway.http.client, "HTTPConnection",
                        lambda _host, port, _timeout: (_ for _ in ()).throw(TypeError("health schema mismatch"))
                        if port == 8765 else _fake_ollama_connection(port))

    request_id = "e5e5e5e5-e5e5-45e5-85e5-e5e5e5e5e5e5"
    response = client.get("/api/v1/intelligence/provider",
                          headers={**owner, "X-SolarMiner-Diagnostic-ID": request_id})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["agent"] == "unavailable"
    assert payload["diagnostic"]["state"] == "degraded"
    assert payload["diagnostic"]["stage"] == "complete"
    assert payload["diagnostic"]["error_type"] == "TypeError"
    assert payload["diagnostic"]["error_reason"] == "openclaude_health_type_error"


def _fake_ollama_connection(port):
    class FakeConnection:
        def __init__(self):
            self.port = port
            self.path = None
        def close(self): pass
        def request(self, _method, path, *, headers): self.path = path
        def getresponse(self):
            if self.path == "/api/version":
                return SimpleNamespace(status=200, read=lambda _limit: b'{"version":"0.40.16"}')
            return SimpleNamespace(status=200, read=lambda _limit: b'{"models":[]}')
    return FakeConnection()


def test_ollama_installation_detection_is_independent_of_runtime_health(monkeypatch, tmp_path):
    executable = tmp_path / "ollama"
    executable.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(gateway.shutil, "which", lambda _name: str(executable))
    monkeypatch.setattr(gateway.os, "access", lambda _path, _mode: True)
    assert gateway._intelligence_ollama_binary_installed() is True
    monkeypatch.setattr(gateway.os, "access", lambda _path, _mode: False)
    assert gateway._intelligence_ollama_binary_installed() is False


def test_owner_can_queue_intelligence_repair_and_action_is_audited(client, monkeypatch):
    owner = _owner(client)
    calls = []
    monkeypatch.setattr(gateway, "_read_intelligence_bootstrap_status", lambda: {
        "state": "failed", "stage": "installing_ollama", "message": "A instalação falhou.",
        "percent": None, "downloaded_bytes": None, "total_bytes": None, "updated_at": time.time(),
    })
    monkeypatch.setattr(gateway.intelligence_bootstrap_client, "request_start", lambda:
                        calls.append(("start", {})) or {"status": "ok", "queued": True})

    response = client.post("/api/v1/intelligence/bootstrap", headers=owner, json={})

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "queued", "queued": True}
    assert calls == [("start", {})]
    with gateway.db() as conn:
        audit_row = conn.execute("SELECT outcome FROM audit WHERE action='intelligence.bootstrap.start'").fetchone()
    assert audit_row[0] == "queued"


def test_bootstrap_falls_back_to_preinstalled_broker_when_new_socket_is_missing(client, monkeypatch):
    owner = _owner(client)
    calls = []
    monkeypatch.setattr(gateway, "_read_intelligence_bootstrap_status", lambda: {"state": "failed"})
    monkeypatch.setattr(gateway.intelligence_bootstrap_client, "request_start",
                        lambda: (_ for _ in ()).throw(FileNotFoundError("socket not deployed")))
    monkeypatch.setattr(gateway.update_helper_client, "request", lambda action:
                        calls.append(action) or {"status": "ok", "queued": True})

    response = client.post("/api/v1/intelligence/bootstrap", headers=owner, json={})

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "queued", "queued": True}
    assert calls == ["intelligence_bootstrap_start"]


def test_intelligence_bootstrap_repair_is_not_queued_twice_while_running(client, monkeypatch):
    owner = _owner(client)
    calls = []
    monkeypatch.setattr(gateway, "_read_intelligence_bootstrap_status", lambda: {
        "state": "running", "stage": "downloading_model", "message": "A descarregar.",
        "percent": 21, "downloaded_bytes": 10, "total_bytes": 50, "updated_at": time.time(),
    })
    monkeypatch.setattr(gateway.intelligence_bootstrap_client, "request_start", lambda: calls.append("start"))

    response = client.post("/api/v1/intelligence/bootstrap", headers=owner, json={})

    assert response.status_code == 200
    assert response.json() == {"status": "already_running", "queued": False}
    assert calls == []


def test_intelligence_ask_forwards_only_authenticated_local_request_and_audits_metadata(client, monkeypatch):
    owner = _owner(client)
    monkeypatch.setattr(gateway, "_read_intelligence_local_token",
                        lambda: "local-client-token-123456789012345678901234567890")
    observed = {}

    class FakeConnection:
        def __init__(self, host, port, timeout):
            observed.update(host=host, port=port, timeout=timeout)
        def connect(self): pass
        def close(self): pass
        def request(self, method, path, *, body=None, headers):
            observed.update(method=method, path=path,
                            body=json.loads(body) if body else None, headers=headers)
        def getresponse(self):
            if observed["method"] == "GET":
                return SimpleNamespace(status=200, read=lambda _limit: json.dumps({
                    "state": "completed", "stage": "agent_response_ready", "steps": [],
                    "mcp_tool_calls": 1, "mcp_tool_results": 1,
                }).encode())
            return SimpleNamespace(status=200, read=lambda _limit: b'{"answer":"Leitura local concluida."}')

    monkeypatch.setattr(gateway.http.client, "HTTPConnection", FakeConnection)
    prompt = "Analisa os erros recentes do Device Engine."
    diagnostic_id = str(uuid.uuid4())
    response = client.post("/api/v1/intelligence/ask",
                           params={"diagnostic_id": diagnostic_id}, headers=owner,
                           json={"prompt": prompt})

    assert response.status_code == 200, response.text
    assert response.json()["answer"] == "Leitura local concluida."
    assert response.json()["provider"] == "ollama"
    assert observed["host"] == "127.0.0.1" and observed["port"] == 8765
    assert observed["timeout"] == 305
    assert observed["method"] == "POST" and observed["path"] == "/v1/analyze"
    assert observed["headers"]["Authorization"] == "Bearer local-client-token-123456789012345678901234567890"
    assert observed["headers"]["X-SolarMiner-Diagnostic-ID"] == diagnostic_id
    assert observed["body"] == {"prompt": prompt, "provider": "ollama"}
    with gateway.db() as conn:
        details = conn.execute("SELECT details_json FROM audit WHERE action='intelligence.ask' AND outcome='success'").fetchone()[0]
        count = conn.execute("SELECT request_count FROM intelligence_request_limits ORDER BY window_start DESC LIMIT 1").fetchone()[0]
    assert prompt not in details and "local-client-token" not in details
    assert json.loads(details)["provider"] == "ollama"
    assert count == 1

    diagnostic = client.get(f"/api/v1/intelligence/provider/diagnostics/{diagnostic_id}", headers=owner)
    assert diagnostic.status_code == 200
    assert diagnostic.json()["state"] == "completed"
    assert diagnostic.json()["agent_trace"]["stage"] == "agent_response_ready"
    assert diagnostic.json()["agent_trace"]["mcp_tool_calls"] == 1
    assert observed["method"] == "GET"
    assert observed["headers"]["Authorization"] == "Bearer local-client-token-123456789012345678901234567890"
    assert diagnostic.json()["agent_trace"]["credential_status"] == "accepted"

    cloud = client.post("/api/v1/intelligence/ask", headers=owner,
                        json={"prompt": "Usa OpenAI apenas nesta pergunta.", "provider": "openai"})
    assert cloud.status_code == 200, cloud.text
    assert cloud.json()["provider"] == "openai"
    assert observed["body"]["provider"] == "openai"


def test_intelligence_ask_reports_type_error_at_local_agent_boundary(client, monkeypatch):
    owner = _owner(client)
    monkeypatch.setattr(gateway, "_read_intelligence_local_token",
                        lambda: "local-client-token-123456789012345678901234567890")
    monkeypatch.setattr(gateway.http.client, "HTTPConnection",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(TypeError("response schema mismatch")))

    response = client.post("/api/v1/intelligence/ask", headers=owner,
                           json={"prompt": "Estado do inversor?"})

    assert response.status_code == 503
    assert response.json()["detail"] == "intelligence_agent_type_error"
    with gateway.db() as conn:
        details = conn.execute("SELECT details_json FROM audit WHERE action='intelligence.ask' "
                               "AND outcome='failed' ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert json.loads(details)["error_type"] == "TypeError"
    assert json.loads(details)["error_reason"] == "intelligence_agent_type_error"


def test_intelligence_ask_exposes_safe_permission_failure_trace(client, monkeypatch):
    owner = _owner(client)
    monkeypatch.setattr(gateway, "_read_intelligence_local_token",
                        lambda: "local-client-token-123456789012345678901234567890")
    diagnostic_id = str(uuid.uuid4())

    class PermissionResponse:
        status = 503
        def read(self, _limit):
            return b'{"error":"intelligence_permission_denied","error_type":"Error","error_code":"EACCES"}'

    class FakeConnection:
        def __init__(self, *_args, **_kwargs): pass
        def connect(self): pass
        def close(self): pass
        def request(self, *_args, **_kwargs): pass
        def getresponse(self): return PermissionResponse()

    monkeypatch.setattr(gateway.http.client, "HTTPConnection", FakeConnection)
    response = client.post("/api/v1/intelligence/ask",
                           headers={**owner, "X-SolarMiner-Diagnostic-ID": diagnostic_id},
                           json={"prompt": "Test permissions"})
    assert response.status_code == 503
    assert response.json()["detail"] == "intelligence_permission_denied"
    trace = client.get(f"/api/v1/intelligence/provider/diagnostics/{diagnostic_id}", headers=owner)
    assert trace.status_code == 200
    assert trace.json()["state"] == "failed"
    assert trace.json()["stage"] == "openclaude_agent"
    assert trace.json()["error_type"] == "Error"
    assert trace.json()["error_reason"] == "intelligence_permission_denied"
    assert "private" not in json.dumps(trace.json()).lower()


def test_intelligence_ask_reports_agent_analysis_timeout_as_gateway_504(client, monkeypatch):
    owner = _owner(client)
    monkeypatch.setattr(gateway, "_read_intelligence_local_token",
                        lambda: "local-client-token-123456789012345678901234567890")

    class TimeoutResponse:
        status = 504
        def read(self, _limit): return b'{"error":"analysis_timeout"}'

    class FakeConnection:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("127.0.0.1", 8765, 305)
        def connect(self): pass
        def close(self): pass
        def request(self, method, path, *, body, headers):
            assert (method, path) == ("POST", "/v1/analyze")
        def getresponse(self): return TimeoutResponse()

    monkeypatch.setattr(gateway.http.client, "HTTPConnection", FakeConnection)
    response = client.post("/api/v1/intelligence/ask", headers=owner,
                           json={"prompt": "Hello World"})
    assert response.status_code == 504
    assert response.json()["detail"] == "intelligence_analysis_timeout"


def test_intelligence_ask_enforces_persistent_hourly_cost_limit(client):
    owner = _owner(client)
    with gateway.db() as conn:
        user_id = conn.execute("SELECT id FROM users WHERE username='owner-intelligence'").fetchone()[0]
        current_window = int(time.time()) // 3600 * 3600
        conn.execute("INSERT INTO intelligence_request_limits(user_id,window_start,request_count) VALUES(?,?,30)",
                     (user_id, current_window))

    response = client.post("/api/v1/intelligence/ask", headers=owner, json={"prompt": "Teste quota."})

    assert response.status_code == 429
    assert response.json()["detail"] == "intelligence_hourly_limit_reached"
    with gateway.db() as conn:
        audit = conn.execute("SELECT outcome,details_json FROM audit WHERE action='intelligence.ask' ORDER BY id DESC LIMIT 1").fetchone()
    assert audit[0] == "rate_limited"
    assert json.loads(audit[1])["limit"] == 30
