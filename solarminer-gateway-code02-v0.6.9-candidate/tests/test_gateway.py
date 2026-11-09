import asyncio
import hashlib
import io
import json
import os
import time
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from solarminer_gateway import app as gateway
from solarminer_gateway import cli as gateway_cli


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "DB_PATH", tmp_path / "gateway.db")
    monkeypatch.setattr(gateway, "BOOTSTRAP_PATH", tmp_path / "bootstrap.token")
    monkeypatch.setattr(gateway, "INSTANCE_MARKER", tmp_path / "initialized.marker")
    with TestClient(gateway.app) as c:
        yield c


def keypair():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, public


def sig(private, text):
    return private.sign(text.encode()).hex()


def create_owner(client):
    token = gateway.BOOTSTRAP_PATH.read_text().strip()
    private, public = keypair()
    ts, nonce = int(time.time()), "bootstrap-nonce-00000001"
    canonical = f"BOOTSTRAP\nowner1\nAA:BB:CC:DD:EE:01\n{ts}\n{nonce}"
    response = client.post("/api/v1/bootstrap/owner", json={
        "bootstrap_token": token, "username": "owner1", "password": "a-long-passphrase-01",
        "mac": "aa:bb:cc:dd:ee:01", "public_key_pem": public, "signature": sig(private, canonical),
        "timestamp": ts, "nonce": nonce,
    })
    assert response.status_code == 201, response.text
    return response.json(), private, public


def login(client, owner, private, password="a-long-passphrase-01", nonce="login-nonce-00000001", username="owner1"):
    ts = int(time.time())
    canonical = f"LOGIN\n{username}\n{owner['device_id']}\n{ts}\n{nonce}"
    return client.post("/api/v1/auth/login", json={
        "username": username, "password": password, "device_id": owner["device_id"],
        "timestamp": ts, "nonce": nonce, "signature": sig(private, canonical),
    })


def test_owner_terminal_diagnostics_reports_runtime_capabilities(client):
    owner, private, _ = create_owner(client)
    session = login(client, owner, private)
    assert session.status_code == 200, session.text
    response = client.get("/api/v1/system/terminal/diagnostics", headers={
        "Authorization": f"Bearer {session.json()['access_token']}"
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert isinstance(result["available"], bool)
    assert isinstance(result["pty_available"], bool)
    assert isinstance(result["shell_available"], bool)
    assert result["available"] is (result["pty_available"] and result["shell_available"])


def test_shelly_blu_scan_observation_is_bound_to_bridge_and_expires(client):
    device = {"mac": "AA:BB:CC:DD:EE:01", "bridge_mac": "AA:BB:CC:DD:EE:40",
              "name": "SBHT-003C", "rssi": -55, "values": []}
    with gateway.db() as conn:
        gateway._remember_shelly_blu_scan(conn, [device])
        row = conn.execute("SELECT details_json FROM shelly_blu_scan_observations WHERE bridge_mac=? AND mac=?",
                           (device["bridge_mac"], device["mac"])).fetchone()
        assert row is not None
        assert json.loads(row["details_json"])["name"] == "SBHT-003C"
        assert conn.execute("SELECT COUNT(*) FROM shelly_blu_scan_observations WHERE bridge_mac=?",
                            ("AA:BB:CC:DD:EE:41",)).fetchone()[0] == 0


def test_shelly_blu_discovery_returns_and_persists_successful_scan(client, monkeypatch):
    owner, private, _ = create_owner(client)
    bearer = login(client, owner, private).json()["access_token"]
    bridge_mac = "AA:BB:CC:DD:EE:40"
    sensor = {"mac": "AA:BB:CC:DD:EE:01", "bridge_mac": bridge_mac, "bridge_host": "192.168.1.40",
              "name": "SBHT-003C", "model": "SBHT-003C", "rssi": -55, "values": []}
    with gateway.db() as conn:
        conn.execute("""INSERT INTO shelly_devices(device_id,mac,name,host,model,generation,device_type,protocol,
            auth_ciphertext,created_at,updated_at) VALUES(?,?,?,?,?,2,'smart_blugw','shelly_rpc',X'',?,?)""",
            ("shelly:" + bridge_mac, bridge_mac, "Shelly BLU", "192.168.1.40", "SN-GW-BT01",
             gateway.utcnow(), gateway.utcnow()))

    durations = []
    def scan(conn, *, duration_seconds, bridge_macs):
        durations.append(duration_seconds)
        return [sensor], [{"mac": bridge_mac, "name": "Shelly BLU", "model": "SN-GW-BT01", "state": "scanned"}]
    monkeypatch.setattr(gateway, "_scan_registered_shelly_blu_bridges", scan)
    response = client.post(f"/api/v1/integrations/shelly/shelly:{bridge_mac}/blu/discover",
                           headers={"Authorization": f"Bearer {bearer}"}, json={})
    assert response.status_code == 200, response.text
    assert response.json()["device_count"] == 1
    assert durations == [30.0]
    with gateway.db() as conn:
        row = conn.execute("SELECT details_json FROM shelly_blu_scan_observations WHERE bridge_mac=? AND mac=?",
                           (bridge_mac, sensor["mac"])).fetchone()
    assert row is not None
    assert json.loads(row["details_json"])["name"] == sensor["name"]


def test_shelly_blu_registration_uses_recent_gateway_scan_instead_of_missing_second_beacon(client, monkeypatch):
    owner, private, _ = create_owner(client)
    bearer = login(client, owner, private).json()["access_token"]
    bridge_mac = "AA:BB:CC:DD:EE:40"
    sensor = {"mac": "AA:BB:CC:DD:EE:01", "bridge_mac": bridge_mac, "bridge_host": "192.168.1.40",
              "name": "SBHT-003C", "model": "SBHT-003C", "rssi": -55, "values": []}
    with gateway.db() as conn:
        conn.execute("""INSERT INTO shelly_devices(device_id,mac,name,host,model,generation,device_type,protocol,
            auth_ciphertext,created_at,updated_at) VALUES(?,?,?,?,?,2,'smart_blugw','shelly_rpc',X'',?,?)""",
            ("blu-bridge", bridge_mac, "Shelly BLU", "192.168.1.40", "SN-GW-BT01", gateway.utcnow(), gateway.utcnow()))
        gateway._remember_shelly_blu_scan(conn, [sensor])
    monkeypatch.setattr(gateway.hardware_integrations.shelly_integration, "discover_bluetooth_devices",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected second scan")))
    response = client.post("/api/v1/integrations/shelly/blu/register", headers={"Authorization": f"Bearer {bearer}"},
                           json={"mac": sensor["mac"], "bridge_mac": bridge_mac, "name": "Sensor Cozinha"})
    assert response.status_code == 200, response.text
    assert response.json()["device"]["mac"] == sensor["mac"]


def test_retired_huawei_search_routes_are_not_registered():
    paths = {route.path for route in gateway.app.routes if hasattr(route, "path")}
    assert not any(path.startswith("/api/v1/integrations/huawei/") for path in paths)


def test_owner_can_check_tesla_presence_from_local_neighbour_cache(client, monkeypatch):
    owner, private, _ = create_owner(client)
    token = login(client, owner, private).json()["access_token"]
    monkeypatch.setattr(gateway.hardware_integrations, "load_config", lambda: {
        "tesla": {"local_mac": "4C:FC:AA:D5:86:68"},
    })
    monkeypatch.setattr(gateway, "local_arp_entries", lambda: {"4C:FC:AA:D5:86:68": "192.168.8.100"})
    response = client.post("/api/v1/energy/ev/tesla/presence",
                           headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "DETECTED"
    assert response.json()["ip"] == "192.168.8.100"
    assert client.post("/api/v1/energy/ev/tesla/presence").status_code == 401


def test_tesla_oauth_start_uses_current_https_origin_and_minimal_read_scopes(client):
    owner, private, _ = create_owner(client)
    token = login(client, owner, private).json()["access_token"]
    gateway._tesla_oauth_pending.clear()
    response = client.post("https://gateway.example/api/v1/energy/ev/tesla/oauth/start", headers={
        "Authorization": f"Bearer {token}", "Origin": "https://solarminer.example",
    }, json={"region": "europe", "client_id": "client-123", "client_secret": "secret-value",
             "local_mac": "AA:BB:CC:DD:EE:01"})
    assert response.status_code == 200, response.text
    result = response.json()
    query = parse_qs(urlsplit(result["authorize_url"]).query)
    assert query["redirect_uri"] == ["https://gateway.example/api/integration/tesla/callback"]
    assert query["scope"] == ["openid offline_access vehicle_device_data"]
    assert result["allowed_origin"] == "https://solarminer.example"
    assert "secret-value" not in response.text
    assert gateway._tesla_oauth_pending[result["state"]]["client_secret"] == "secret-value"
    assert client.post("https://gateway.example/api/v1/energy/ev/tesla/oauth/start", headers={
        "Authorization": f"Bearer {token}", "Origin": "http://solarminer.example",
    }, json={"region": "europe", "client_id": "client-123", "client_secret": "secret-value"}).status_code == 400


def test_tesla_oauth_callback_exchanges_code_persists_rotating_token_and_posts_safe_vehicles(client, monkeypatch):
    owner, private, _ = create_owner(client)
    token = login(client, owner, private).json()["access_token"]
    gateway._tesla_oauth_pending.clear()
    start = client.post("https://gateway.example/api/v1/energy/ev/tesla/oauth/start", headers={
        "Authorization": f"Bearer {token}", "Origin": "https://solarminer.example",
    }, json={"region": "europe", "client_id": "client-123", "client_secret": "secret-value"}).json()
    config = {}
    calls = []

    def fake_http(url, *, token=None, form=None):
        calls.append((url, token, form))
        if form:
            assert form["grant_type"] == "authorization_code"
            assert form["client_secret"] == "secret-value"
            assert form["redirect_uri"] == start["redirect_uri"]
            return {"access_token": "access-token", "refresh_token": "refresh-token-rotated"}
        assert token == "access-token"
        return {"response": [{"id_s": "987654321", "display_name": "My Tesla", "vin": "VIN000000000000000ABCD"}]}

    monkeypatch.setattr(gateway.hardware_integrations, "_tesla_http", fake_http)
    monkeypatch.setattr(gateway.hardware_integrations, "load_config", lambda: config)
    monkeypatch.setattr(gateway.hardware_integrations, "save_config", lambda value: config.update(value))
    callback = client.get("/api/integration/tesla/callback", params={"code": "oauth-code", "state": start["state"]})
    assert callback.status_code == 200
    assert "solarminer-tesla-oauth-result" in callback.text
    assert "refresh-token-rotated" not in callback.text
    assert config["tesla"]["refresh_token"] == "refresh-token-rotated"
    assert config["tesla"]["vehicle_ids"] == []
    assert config["tesla"]["client_id"] == "client-123"
    assert config["tesla"]["local_mac"] == ""
    assert "987654321" in callback.text and "My Tesla" in callback.text
    replay = client.get("/api/integration/tesla/callback", params={"code": "oauth-code", "state": start["state"]})
    assert replay.status_code == 400


def test_tesla_oauth_uses_public_relay_and_gateway_exchanges_code_outbound(client, monkeypatch):
    owner, private, _ = create_owner(client)
    token = login(client, owner, private).json()["access_token"]
    monkeypatch.setenv("SOLARMINER_TESLA_RELAY_URL", "https://relay.example")
    monkeypatch.setenv("SOLARMINER_TESLA_RELAY_API_KEY", "relay-api-key-value-with-at-least-32-characters")
    gateway._tesla_oauth_pending.clear()
    relay_calls = []

    class Response:
        def __init__(self, payload): self.payload = json.dumps(payload).encode()
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self, _limit=-1): return self.payload

    def fake_urlopen(request, timeout=0):
        relay_calls.append(request)
        if request.method == "POST": return Response({"expires_in": 600})
        if request.method == "GET": return Response({"ready": True, "code": "one-time-code"})
        if request.method == "DELETE": return Response({})
        raise AssertionError(request.method)

    monkeypatch.setattr(gateway, "urlopen", fake_urlopen)
    config, calls = {}, []

    def fake_http(url, *, token=None, form=None):
        calls.append((url, token, form))
        if form:
            assert form["code"] == "one-time-code"
            assert form["redirect_uri"] == "https://relay.example/oauth/callback"
            return {"access_token": "access-token", "refresh_token": "rotated-refresh-token"}
        return {"response": [{"id_s": "987654321", "display_name": "My Tesla", "vin": "VIN000000000000000ABCD"}]}

    monkeypatch.setattr(gateway.hardware_integrations, "_tesla_http", fake_http)
    monkeypatch.setattr(gateway.hardware_integrations, "load_config", lambda: config)
    monkeypatch.setattr(gateway.hardware_integrations, "save_config", lambda value: config.update(value))
    start = client.post("https://gateway.example/api/v1/energy/ev/tesla/oauth/start", headers={
        "Authorization": f"Bearer {token}", "Origin": "https://solarminer.example",
    }, json={"region": "europe", "client_id": "client-123", "client_secret": "secret-value"})
    assert start.status_code == 200, start.text
    flow = start.json()
    query = parse_qs(urlsplit(flow["authorize_url"]).query)
    assert query["redirect_uri"] == ["https://relay.example/oauth/callback"]
    assert flow["relay_mode"] is True
    assert "secret-value" not in start.text
    assert relay_calls[0].full_url == "https://relay.example/v1/sessions"

    complete = client.post("/api/v1/energy/ev/tesla/oauth/complete", headers={
        "Authorization": f"Bearer {token}",
    }, json={"state": flow["state"]})
    assert complete.status_code == 200, complete.text
    assert complete.json()["ok"] is True
    assert complete.json()["vehicles"][0]["id"] == "987654321"
    assert config["tesla"]["refresh_token"] == "rotated-refresh-token"
    assert len(calls) == 2
    assert relay_calls[-1].method == "DELETE"
    assert "one-time-code" not in complete.text and "rotated-refresh-token" not in complete.text


def test_owner_can_save_and_test_tesla_relay_without_receiving_its_key(client, monkeypatch):
    owner, private, _ = create_owner(client)
    token = login(client, owner, private).json()["access_token"]
    monkeypatch.delenv("SOLARMINER_TESLA_RELAY_URL", raising=False)
    monkeypatch.delenv("SOLARMINER_TESLA_RELAY_API_KEY", raising=False)
    saved = {}
    monkeypatch.setattr(gateway.hardware_integrations, "load_config", lambda: saved)
    monkeypatch.setattr(gateway.hardware_integrations, "save_config", lambda value: saved.update(value) or {})
    calls = []

    def relay_request(relay, method, path, payload=None, bearer=None):
        calls.append((relay, method, path, payload, bearer))
        return {"status": "ok"}

    monkeypatch.setattr(gateway, "_tesla_oauth_relay_request", relay_request)
    key = "r" * 64
    response = client.put("/api/v1/energy/ev/tesla/relay", headers={"Authorization": f"Bearer {token}"},
                          json={"relay_url": "https://relay.example", "api_key": key})
    assert response.status_code == 200, response.text
    assert response.json() == {"configured": True, "relay_url": "https://relay.example",
                               "oauth_redirect_uri": "https://relay.example/oauth/callback", "secrets_returned": False}
    assert key not in response.text
    assert saved["tesla_oauth_relay"]["api_key"] == key
    assert calls[0][1:3] == ("GET", "/v1/health")
    public = client.get("/api/v1/energy/ev/tesla", headers={"Authorization": f"Bearer {token}"})
    assert public.status_code == 200
    assert public.json()["relay_configured"] is True
    assert public.json()["relay_url"] == "https://relay.example"
    assert key not in public.text


@pytest.mark.parametrize("relay_url", ["http://relay.example", "https://127.0.0.1", "https://localhost", "https://relay.example/path"])
def test_tesla_relay_rejects_nonpublic_or_nonhttps_origins(relay_url):
    with pytest.raises(gateway.HTTPException):
        gateway._normalize_tesla_oauth_relay_config(relay_url, "r" * 64)


def test_deye_ip_recovery_selects_only_the_ambiguous_mac_candidate_that_answers_modbus(client, monkeypatch):
    mac = "AA:BB:CC:DD:EE:84"
    config = {"deye": {"host": "192.168.8.84", "port": 502, "unit_id": 1,
                       "model": "SUN-15K-SG05LP3-EU-SM2", "local_mac": mac}}
    monkeypatch.setattr(gateway.hardware_integrations, "load_config", lambda: config)
    monkeypatch.setattr(gateway.hardware_integrations, "save_config", lambda value: config.update(value))
    monkeypatch.setattr(gateway.network_scanner, "scan_attached_networks", lambda: {
        "hosts": [{"ip": "192.168.8.84", "mac": mac, "mac_ip_conflict": True,
                    "ip_candidates": ["192.168.8.84", "192.168.8.200"]}],
        "mac_ip_conflicts": [{"mac": mac, "ip_candidates": ["192.168.8.84", "192.168.8.200"]}],
    })
    probes = []

    def read_deye(candidate):
        host = candidate["host"]
        probes.append(host)
        if host.endswith(".200"):
            return {"host": host, "connection_state": "mapped_registers_response",
                    "metrics_decoded": True, "metrics": [{"field": "pv_power", "value": 321}]}
        return {"host": host, "connection_state": "tcp_unreachable", "metrics_decoded": False}

    monkeypatch.setattr(gateway.hardware_integrations, "read_deye", read_deye)
    key = gateway._deye_recovery_key(config["deye"])
    monkeypatch.setitem(gateway._deye_unreachable_since, key, time.monotonic() - 61)
    result = gateway._read_deye_with_inventory_recovery(dict(config["deye"]))
    assert result["host"] == "192.168.8.200"
    assert result["connection_state"] == "mapped_registers_response"
    assert result["ip_refreshed_by_mac"] is True
    assert result["mac_verified_on_lan"] is True
    assert config["deye"]["host"] == "192.168.8.200"
    assert probes.count("192.168.8.84") == 2  # initial read, then candidate validation
    assert probes.count("192.168.8.200") == 1


def test_deye_ip_recovery_does_not_change_config_when_multiple_ambiguous_ips_answer(client, monkeypatch):
    mac = "AA:BB:CC:DD:EE:85"
    config = {"deye": {"host": "192.168.8.84", "port": 502, "unit_id": 1,
                       "model": "SUN-15K-SG05LP3-EU-SM2", "local_mac": mac}}
    monkeypatch.setattr(gateway.hardware_integrations, "load_config", lambda: config)
    monkeypatch.setattr(gateway.hardware_integrations, "save_config", lambda value: config.update(value))
    monkeypatch.setattr(gateway.network_scanner, "scan_attached_networks", lambda: {
        "hosts": [{"ip": "192.168.8.84", "mac": mac, "ip_candidates": ["192.168.8.84", "192.168.8.200"]}],
        "mac_ip_conflicts": [{"mac": mac, "ip_candidates": ["192.168.8.84", "192.168.8.200"]}],
    })
    monkeypatch.setattr(gateway.hardware_integrations, "read_deye", lambda candidate: {
        "host": candidate["host"], "connection_state": "mapped_registers_response", "metrics_decoded": True})
    result = gateway._refresh_deye_host_by_inventory_mac(dict(config["deye"]))
    assert result is None
    assert config["deye"]["host"] == "192.168.8.84"


def test_shelly_registration_uses_authenticated_owner_and_sqlite_mac_identity(client, monkeypatch):
    owner, private, _ = create_owner(client)
    token = login(client, owner, private).json()["access_token"]
    monkeypatch.setattr(gateway.hardware_integrations.shelly_integration, "identify_and_read", lambda host, **auth: {
        "host": host, "manufacturer": "Shelly", "model": "Plus 1PM", "mac": "AA:BB:CC:DD:EE:30",
        "generation": 2, "protocol": "shelly_rpc", "firmware": "1.4", "capabilities": ["relay", "power"],
        "components": [], "status": {}, "observed_at": time.time(), "command_sent": False})
    headers = {"Authorization": f"Bearer {token}"}
    first = client.post("/api/v1/integrations/shelly/register", headers=headers,
                        json={"name": "Shelly hall", "host": "192.168.1.30"})
    assert first.status_code == 200, first.text
    assert first.json()["device"]["mac"] == "AA:BB:CC:DD:EE:30"
    second = client.post("/api/v1/integrations/shelly/register", headers=headers,
                         json={"name": "Shelly hall", "host": "192.168.1.31"})
    assert second.status_code == 200, second.text
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM shelly_devices WHERE mac='AA:BB:CC:DD:EE:30'").fetchone()[0] == 1
        device = conn.execute("SELECT host FROM shelly_devices WHERE mac='AA:BB:CC:DD:EE:30'").fetchone()
        assert device["host"] == "192.168.1.31"
        inventory = conn.execute("SELECT last_ip FROM gateway_device_inventory WHERE mac='AA:BB:CC:DD:EE:30'").fetchone()
        assert inventory["last_ip"] == "192.168.1.31"
    monkeypatch.setattr(gateway.hardware_integrations, "load_config", lambda: {})
    monkeypatch.setattr(gateway.network_scanner, "scan_attached_networks", lambda: {
        "networks": ["192.168.1.0/24"], "skipped_networks": [], "scanned_count": 254,
        "responsive_count": 1, "hosts": [{"ip": "192.168.1.31", "mac": "AA:BB:CC:DD:EE:30",
                    "hostname": "shelly-hall", "manufacturer": "Shelly", "model": "Plus 1PM"}],
        "mac_ip_conflicts": [],
    })
    monkeypatch.setattr(gateway, "_enrich_shelly_scan", lambda report: None)
    scanned = client.post("/api/v1/network/scan", headers=headers)
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["responsive_count"] == 1
    assert scanned.json()["hosts"][0]["matched_devices"][0]["provider"] == "shelly"
    # The next inventory/read synchronization must project Shelly rows without
    # calling a misspelled helper (the production NameError seen in Gateway logs).
    monkeypatch.setattr(gateway.hardware_integrations.shelly_integration, "read_devices", lambda config: [])
    synced = client.post("/api/v1/integrations/shelly/read", headers=headers)
    assert synced.status_code == 200, synced.text
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM gateway_device_inventory WHERE mac='AA:BB:CC:DD:EE:30'").fetchone()[0] == 1
    assert client.post("/api/v1/integrations/shelly/register",
                       json={"name": "No auth", "host": "192.168.1.32"}).status_code == 401


def test_owner_can_read_shelly_product_profiles_from_gateway_catalog(client):
    owner, private, _ = create_owner(client)
    token = login(client, owner, private).json()["access_token"]
    response = client.get("/api/v1/smart-products/shelly-profiles",
                          headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"] == "gateway_sqlite"
    assert {item["product_code"] for item in payload["profiles"]} >= {
        "shelly_vintage_gen1", "shelly_blu_gateway_gwf_kz01"
    }
    assert client.get("/api/v1/smart-products/shelly-profiles").status_code == 401


@pytest.mark.skipif(os.name != "posix", reason="O terminal PTY do Gateway corre em Linux/POSIX")
def test_owner_terminal_executes_and_streams_real_gateway_shell(client, tmp_path, monkeypatch):
    owner, private, _ = create_owner(client)
    token = login(client, owner, private).json()["access_token"]
    monkeypatch.setattr(gateway, "DATA_DIR", tmp_path)
    with client.websocket_connect(
        "/api/v1/system/terminal/ws",
        headers={"origin": "https://solargualdimpais-bot.github.io"},
    ) as socket:
        socket.send_json({"type": "authenticate", "token": token})
        ready = socket.receive_json()
        assert ready["type"] == "ready"
        socket.send_json({"type": "input", "data": "printf 'solarminer-terminal-ok\\n'\n"})
        output = ""
        for _ in range(10):
            message = socket.receive_json()
            if message["type"] == "output":
                output += message["data"]
                if "solarminer-terminal-ok" in output:
                    break
        assert "solarminer-terminal-ok" in output
        socket.send_json({"type": "close"})


def password_device_payload(private, public, username, password, nonce_value="new-device-password-login-01"):
    ts = int(time.time())
    public_der = serialization.load_pem_public_key(public.encode()).public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    password_digest = hashlib.sha256(password.encode()).hexdigest()
    public_digest = hashlib.sha256(public_der).hexdigest()
    canonical = f"PASSWORD-DEVICE-LOGIN\n{username}\n{ts}\n{nonce_value}\n{password_digest}\n{public_digest}"
    return {"username": username, "password": password, "public_key_pem": public,
            "timestamp": ts, "nonce": nonce_value, "signature": sig(private, canonical)}


def test_password_login_registers_new_device_and_issues_owner_session(client):
    create_owner(client)
    private, public = keypair()
    payload = password_device_payload(private, public, "owner1", "a-long-passphrase-01")
    response = client.post("/api/v1/auth/password-device-login", json=payload)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["user"]["role"] == "owner"
    assert result["device_id"]
    assert client.get("/api/v1/system/update/status", headers={"Authorization": f"Bearer {result['access_token']}"}).status_code == 200


def test_tuya_lan_event_history_records_switch_and_availability_transitions(client):
    with gateway.db() as conn:
        gateway._persist_tuya_device_events(conn, [{
            "device_id": "tuya_switch_1", "name": "Garden relay", "connection_state": "local_responded",
            "status": [{"code": "switch_1", "value": True}],
        }])
        gateway._persist_tuya_device_events(conn, [{
            "device_id": "tuya_switch_1", "name": "Garden relay", "connection_state": "local_responded",
            "status": [{"code": "switch_1", "value": False}],
        }])
        gateway._persist_tuya_device_events(conn, [{
            "device_id": "tuya_switch_1", "name": "Garden relay", "connection_state": "failed",
            "reason": "tuya_lan_unavailable",
        }])
        rows = conn.execute("SELECT event_type,channel_code,old_value_json,new_value_json FROM device_events ORDER BY id").fetchall()
    assert [(row["event_type"], row["channel_code"]) for row in rows] == [
        ("availability", ""), ("switch_state", "switch_1"), ("switch_state", "switch_1"), ("availability", "")]
    assert rows[1]["new_value_json"] == "true"
    assert rows[2]["old_value_json"] == "true" and rows[2]["new_value_json"] == "false"
    assert rows[3]["new_value_json"] == "false"


def test_tuya_event_collector_polls_devices_even_without_a_pwa_request(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(gateway, "_tuya_last_diagnostic_log_at", 0.0)
    monkeypatch.setattr(gateway.time, "monotonic", lambda: 61.0)
    caplog.set_level("INFO")
    monkeypatch.setenv("SOLARMINER_DATA_DIR", str(tmp_path / "solarminer-data"))
    monkeypatch.setattr(gateway, "DB_PATH", tmp_path / "gateway.db")
    monkeypatch.setattr(gateway, "BOOTSTRAP_PATH", tmp_path / "bootstrap.token")
    monkeypatch.setattr(gateway, "INSTANCE_MARKER", tmp_path / "initialized.marker")
    gateway.initialize()
    config = {"devices": [
        {"device_id": "lan-ready", "name": "Relay", "local_key": "local-key-valid", "local_ip": "192.168.1.20"},
        {"device_id": "not-configured", "name": "No key", "local_ip": "192.168.1.21"},
    ]}
    monkeypatch.setattr(gateway.hardware_integrations, "load_config", lambda: {"tuya": config})
    monkeypatch.setattr(gateway.hardware_integrations, "save_config", lambda _config: None)
    observed = []
    def read_tuya(selected, *, on_reading=None, background_poll=False):
        assert background_poll is True
        observed.extend(item["device_id"] for item in selected["devices"])
        readings = [{"device_id": "lan-ready", "name": "Relay", "connection_state": "local_responded",
                     "status": [{"code": "switch_1", "value": True}]}]
        if on_reading:
            for reading in readings:
                on_reading(reading)
        return readings
    monkeypatch.setattr(gateway.hardware_integrations, "read_tuya", read_tuya)

    assert gateway._collect_tuya_device_events_once() == 2
    assert observed == ["lan-ready"]
    with gateway.db() as conn:
        rows = conn.execute("SELECT event_type, new_value_json FROM device_events ORDER BY id").fetchall()
    assert [(row["event_type"], row["new_value_json"]) for row in rows] == [
        ("availability", "true"), ("switch_state", "true")]
    assert config["devices"][0]["local_control_state"] == "ready"
    assert "Periodic Tuya poll diagnostic outcome=success configured=1 successful=1 failed=0" in caplog.text
    assert "lan-ready" not in caplog.text


def test_tuya_event_collector_marks_a_failed_device_offline_without_rewriting_status(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(gateway, "_tuya_last_diagnostic_log_at", 0.0)
    monkeypatch.setenv("SOLARMINER_DATA_DIR", str(tmp_path / "solarminer-data"))
    monkeypatch.setattr(gateway, "DB_PATH", tmp_path / "gateway.db")
    monkeypatch.setattr(gateway, "BOOTSTRAP_PATH", tmp_path / "bootstrap.token")
    monkeypatch.setattr(gateway, "INSTANCE_MARKER", tmp_path / "initialized.marker")
    gateway.initialize()
    config = {"devices": [{"device_id": "lan-offline", "name": "Breaker", "local_key": "local-key-valid",
                          "local_ip": "192.168.1.20", "local_control_state": "ready",
                          "current_status": [{"code": "power", "value": 500}], "last_status_at": 123}]}
    saved = []
    monkeypatch.setattr(gateway.hardware_integrations, "load_config", lambda: {"tuya": config})
    monkeypatch.setattr(gateway.hardware_integrations, "save_config", lambda value: saved.append(value))
    def read_tuya(_selected, *, on_reading=None, background_poll=False):
        assert background_poll is True
        readings = [{"device_id": "lan-offline", "name": "Breaker", "connection_state": "failed",
                     "reason": "tuya_local_ip_not_found_for_mac", "status": []}]
        if on_reading:
            for reading in readings:
                on_reading(reading)
        return readings
    monkeypatch.setattr(gateway.hardware_integrations, "read_tuya", read_tuya)

    gateway._collect_tuya_device_events_once()

    assert config["devices"][0]["local_control_state"] == "unavailable"
    assert config["devices"][0]["current_status"] == [{"code": "power", "value": 500}]
    assert config["devices"][0]["last_status_at"] == 123
    assert len(saved) == 1
    assert "Periodic Tuya poll diagnostic outcome=partial configured=1 successful=0 failed=1" in caplog.text
    assert "lan-offline" not in caplog.text


def test_tuya_event_poll_interval_defaults_to_five_seconds_and_enforces_safe_minimum(monkeypatch):
    monkeypatch.delenv("SOLARMINER_TUYA_EVENT_POLL_SECONDS", raising=False)
    assert gateway._tuya_event_poll_interval_seconds() == 5.0
    monkeypatch.setenv("SOLARMINER_TUYA_EVENT_POLL_SECONDS", "5")
    assert gateway._tuya_event_poll_interval_seconds() == 5.0
    monkeypatch.setenv("SOLARMINER_TUYA_EVENT_POLL_SECONDS", "1.5")
    assert gateway._tuya_event_poll_interval_seconds() == 5.0
    monkeypatch.setenv("SOLARMINER_TUYA_EVENT_POLL_SECONDS", "invalid")
    assert gateway._tuya_event_poll_interval_seconds() == 5.0


def test_password_login_rejects_wrong_password_without_registering_device(client):
    create_owner(client)
    private, public = keypair()
    payload = password_device_payload(private, public, "owner1", "wrong-password")
    response = client.post("/api/v1/auth/password-device-login", json=payload)
    assert response.status_code == 401
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 1


def test_password_login_rejects_invalid_signature_without_registering_device(client):
    create_owner(client)
    private, public = keypair()
    payload = password_device_payload(private, public, "owner1", "a-long-passphrase-01")
    payload["signature"] = "00" * 64
    response = client.post("/api/v1/auth/password-device-login", json=payload)
    assert response.status_code == 401
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 1


def test_password_login_preserves_non_owner_role_and_owner_management_stays_forbidden(client):
    create_owner(client)
    with gateway.db() as conn:
        conn.execute("INSERT INTO users(id,account_id,username,password_hash,role,status,created_at) VALUES(?,?,?,?, 'viewer','active',?)",
                     ("00000000-0000-4000-8000-000000000002", "00000000-0000-4000-8000-000000000003",
                      "viewer1", gateway.PASSWORDS.hash("viewer-password-01"), gateway.utcnow()))
    private, public = keypair()
    payload = password_device_payload(private, public, "viewer1", "viewer-password-01")
    response = client.post("/api/v1/auth/password-device-login", json=payload)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["user"]["role"] == "viewer"
    denied = client.get("/api/v1/system/update/source", headers={"Authorization": f"Bearer {result['access_token']}"})
    assert denied.status_code == 403


def test_password_login_rate_limit_is_shared_across_source_ips(client):
    create_owner(client)
    account_hash = gateway.token_hash("owner1".casefold())
    with gateway.db() as conn:
        conn.executemany("INSERT INTO password_device_attempts(ip_hash,account_hash,attempted_at) VALUES(?,?,?)",
                         [(gateway.token_hash(f"other-source-{index}"), account_hash, int(time.time())) for index in range(10)])
    private, public = keypair()
    payload = password_device_payload(private, public, "owner1", "a-long-passphrase-01")
    response = client.post("/api/v1/auth/password-device-login", json=payload, headers={"X-Real-IP": "198.51.100.28"})
    assert response.status_code == 429
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 1


def test_health_info_and_bootstrap_token_permissions(client, caplog):
    import inspect

    assert inspect.iscoroutinefunction(gateway.health)
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/info").json()["version"] == "0.6.0"
    token_file = gateway.BOOTSTRAP_PATH
    assert token_file.exists()
    if os.name == "posix":
        assert token_file.stat().st_mode & 0o777 == 0o600
    secret = token_file.read_text().strip()
    assert secret not in client.get("/api/v1/bootstrap/status").text
    assert secret not in caplog.text


def test_health_endpoint_is_independent_of_database(monkeypatch):
    def unexpected_database_access():
        raise AssertionError("liveness health must not wait on SQLite")

    monkeypatch.setattr(gateway, "db", unexpected_database_access)
    response = asyncio.run(gateway.health())

    assert response["status"] == "ok"
    assert "bootstrap_state" not in response
    assert response["package_version"] == gateway.PACKAGE_VERSION


def test_open_database_connection_does_not_reissue_wal_mode_pragma(tmp_path, monkeypatch):
    statements = []

    class Connection:
        row_factory = None

        def execute(self, statement):
            statements.append(statement)
            return self

        def close(self):
            pass

    monkeypatch.setattr(gateway, "DB_PATH", tmp_path / "gateway.db")
    monkeypatch.setattr(gateway, "INSTANCE_MARKER", tmp_path / "not-initialized")
    monkeypatch.setattr(gateway.sqlite3, "connect", lambda *_args, **_kwargs: Connection())

    with gateway.db():
        pass

    assert "PRAGMA foreign_keys=ON" in statements
    assert "PRAGMA recursive_triggers=ON" in statements
    assert "PRAGMA busy_timeout=10000" in statements
    assert not any("journal_mode" in statement.casefold() for statement in statements)


def test_bootstrap_login_persistence_and_session(client):
    owner, private, _ = create_owner(client)
    assert not gateway.BOOTSTRAP_PATH.exists()
    assert client.get("/api/v1/bootstrap/status").json()["state"] == "OWNER_ACTIVE"
    response = login(client, owner, private)
    assert response.status_code == 200, response.text
    bearer = response.json()["access_token"]
    assert client.get("/api/v1/status", headers={"Authorization": f"Bearer {bearer}"}).status_code == 200
    assert client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {bearer}"}).status_code == 200
    assert client.get("/api/v1/status", headers={"Authorization": f"Bearer {bearer}"}).status_code == 401


def test_bad_password_and_unauthenticated_rejected(client):
    owner, private, _ = create_owner(client)
    assert login(client, owner, private, password="wrong-password-long", nonce="login-nonce-00000002").status_code == 401
    assert client.get("/api/v1/status").status_code == 401


def test_bootstrap_single_use(client):
    owner, private, public = create_owner(client)
    ts, nonce = int(time.time()), "bootstrap-nonce-00000002"
    canonical = f"BOOTSTRAP\nowner2\nAA:BB:CC:DD:EE:02\n{ts}\n{nonce}"
    response = client.post("/api/v1/bootstrap/owner", json={
        "bootstrap_token": "wrong-token-that-is-long-enough-12345", "username": "owner2", "password": "a-long-passphrase-02",
        "mac": "AA:BB:CC:DD:EE:02", "public_key_pem": public, "signature": sig(private, canonical),
        "timestamp": ts, "nonce": nonce,
    })
    assert response.status_code == 409


def test_console_password_first_owner_and_passwordless_device_relogin(client):
    chosen_password = "OwnerPass-8"
    with gateway.db() as conn:
        conn.execute("UPDATE bootstrap SET setup_password_hash=? WHERE id=1", (gateway.PASSWORDS.hash(chosen_password),))
    private, public = keypair()
    username = "Owner Name"
    ts, nonce = int(time.time()), "console-bootstrap-nonce-01"
    canonical = f"BOOTSTRAP\n{username}\n{ts}\n{nonce}"
    payload = {"username": username, "password": chosen_password, "public_key_pem": public,
               "signature": sig(private, canonical), "timestamp": ts, "nonce": nonce}
    wrong = {**payload, "password": "WrongPass-8"}
    assert client.post("/api/v1/bootstrap/owner", json=wrong).status_code == 401
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users WHERE role='owner'").fetchone()[0] == 0
        assert conn.execute("SELECT setup_password_hash FROM bootstrap WHERE id=1").fetchone()[0]
    created = client.post("/api/v1/bootstrap/owner", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["mac_status"] == "unknown"
    with gateway.db() as conn:
        assert conn.execute("SELECT setup_password_hash FROM bootstrap WHERE id=1").fetchone()[0] is None
    assert client.post("/api/v1/bootstrap/owner", json=payload).status_code == 409

    device_id = created.json()["device_id"]
    user_id = created.json()["user_id"]
    ts2, nonce2 = int(time.time()), "device-login-nonce-0001"
    proof = f"DEVICE-LOGIN\n{user_id}\n{device_id}\n{ts2}\n{nonce2}"
    response = client.post("/api/v1/auth/device-login", json={
        "user_id": user_id, "device_id": device_id, "timestamp": ts2, "nonce": nonce2, "signature": sig(private, proof)
    })
    assert response.status_code == 200, response.text
    assert response.json()["user"]["username"] == username
    bearer = response.json()["access_token"]
    assert client.get("/api/v1/status", headers={"Authorization": f"Bearer {bearer}"}).status_code == 200
    ts3, nonce3 = int(time.time()), "device-login-legacy-nonce"
    legacy_proof = f"DEVICE-LOGIN\n{device_id}\n{ts3}\n{nonce3}"
    legacy = client.post("/api/v1/auth/device-login", json={
        "device_id": device_id, "timestamp": ts3, "nonce": nonce3, "signature": sig(private, legacy_proof)
    })
    assert legacy.status_code == 200, legacy.text


def test_local_owner_password_command_stores_only_argon2_hash(client, monkeypatch, capsys):
    monkeypatch.setattr(gateway_cli, "_require_root", lambda: None)
    monkeypatch.setattr(gateway_cli, "_require_tty", lambda: None)
    answers = iter(["VisiblePass-8", "VisiblePass-8"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    gateway_cli.run_owner_password()
    output = capsys.readouterr().out
    assert "VisiblePass-8" not in output
    with gateway.db() as conn:
        row = conn.execute("SELECT setup_password_hash FROM bootstrap WHERE id=1").fetchone()
        assert gateway.PASSWORDS.verify(row[0], "VisiblePass-8")
        assert "VisiblePass-8" not in row[0]


def test_remote_bootstrap_requires_allowlisted_origin_and_device_signature(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "_CORS_ORIGINS", ["https://solargualdimpais-bot.github.io"])
    monkeypatch.setattr(gateway, "DB_PATH", tmp_path / "gateway.db")
    monkeypatch.setattr(gateway, "BOOTSTRAP_PATH", tmp_path / "bootstrap.token")
    monkeypatch.setattr(gateway, "INSTANCE_MARKER", tmp_path / "initialized.marker")
    with TestClient(gateway.app, client=("203.0.113.23", 54321)) as remote_client:
        token = gateway.BOOTSTRAP_PATH.read_text().strip()
        private, public = keypair()
        ts, nonce = int(time.time()), "remote-bootstrap-nonce-01"
        canonical = f"BOOTSTRAP\nowner-pages\nAA:BB:CC:DD:EE:23\n{ts}\n{nonce}"
        payload = {
            "bootstrap_token": token, "username": "owner-pages", "password": "a-long-pages-passphrase-01",
            "mac": "AA:BB:CC:DD:EE:23", "public_key_pem": public, "signature": sig(private, canonical),
            "timestamp": ts, "nonce": nonce,
        }

        rejected = remote_client.post("/api/v1/bootstrap/owner", json=payload, headers={"Origin": "https://evil.example"})
        assert rejected.status_code == 403
        assert rejected.json()["detail"] == "bootstrap_origin_not_allowed"

        accepted = remote_client.post("/api/v1/bootstrap/owner", json=payload, headers={"Origin": "https://solargualdimpais-bot.github.io"})
        assert accepted.status_code == 201, accepted.text
        assert accepted.json()["role"] == "owner"


def test_same_origin_bootstrap_is_allowed_for_gateway_hosted_pwa(client):
    client = TestClient(gateway.app, client=("192.0.2.20", 54321))
    token = gateway.BOOTSTRAP_PATH.read_text().strip()
    private, public = keypair()
    ts, nonce = int(time.time()), "same-origin-bootstrap-nonce"
    canonical = f"BOOTSTRAP\nowner-same-origin\nAA:BB:CC:DD:EE:24\n{ts}\n{nonce}"
    payload = {
        "bootstrap_token": token, "username": "owner-same-origin", "password": "a-long-sameorigin-pass-01",
        "mac": "AA:BB:CC:DD:EE:24", "public_key_pem": public, "signature": sig(private, canonical),
        "timestamp": ts, "nonce": nonce,
    }
    response = client.post("/api/v1/bootstrap/owner", json=payload,
        headers={"Origin": "http://testserver"})
    assert response.status_code == 201, response.text


def test_role_permissions_and_required_device_association(client):
    owner, private, _ = create_owner(client)
    bearer = login(client, owner, private).json()["access_token"]
    headers = {"Authorization": f"Bearer {bearer}"}
    # Invalid MAC is rejected; valid MAC metadata is never treated as cryptographic identity.
    device_private, device_public = keypair()
    bad = client.post("/api/v1/devices", headers=headers, json={"mac": "not-a-mac", "public_key_pem": device_public})
    assert bad.status_code == 422
    good = client.post("/api/v1/devices", headers=headers, json={"mac": "11:22:33:44:55:66", "public_key_pem": device_public})
    assert good.status_code == 201 and good.json()["mac_status"] == "declared"
    missing = client.post("/api/v1/users", headers=headers, json={"username": "operator1", "password": "a-long-passphrase-03", "role": "operator", "device_id": "missing"})
    assert missing.status_code == 422
    created = client.post("/api/v1/users", headers=headers, json={"username": "viewer1", "password": "a-long-passphrase-04", "role": "viewer", "device_id": good.json()["id"]})
    assert created.status_code == 201
    ts, nonce = int(time.time()), "viewer-login-nonce-0001"
    canonical = f"LOGIN\nviewer1\n{good.json()['id']}\n{ts}\n{nonce}"
    viewer_login = client.post("/api/v1/auth/login", json={"username":"viewer1", "password":"a-long-passphrase-04", "device_id":good.json()["id"], "timestamp":ts, "nonce":nonce, "signature":sig(device_private, canonical)})
    assert viewer_login.status_code == 200
    viewer_headers = {"Authorization": f"Bearer {viewer_login.json()['access_token']}"}
    assert client.get("/api/v1/status", headers=viewer_headers).status_code == 200
    assert client.get("/api/v1/users", headers=viewer_headers).status_code == 403
    assert client.post(f"/api/v1/devices/{good.json()['id']}/revoke", headers=headers).status_code == 200
    assert client.get("/api/v1/status", headers=viewer_headers).status_code == 401


def test_nonce_replay_and_timestamp_rejected(client):
    owner, private, _ = create_owner(client)
    first = login(client, owner, private, nonce="login-nonce-00000003")
    assert first.status_code == 200
    replay = login(client, owner, private, nonce="login-nonce-00000003")
    assert replay.status_code == 401
    ts = int(time.time()) - 1000
    nonce = "login-nonce-00000004"
    canonical = f"LOGIN\nowner1\n{owner['device_id']}\n{ts}\n{nonce}"
    stale = client.post("/api/v1/auth/login", json={"username":"owner1", "password":"a-long-passphrase-01", "device_id":owner['device_id'], "timestamp":ts, "nonce":nonce, "signature":sig(private, canonical)})
    assert stale.status_code == 401


def test_real_tls_certificate_validation_and_untrusted_rejection(tmp_path):
    import socket
    import ssl
    import subprocess
    import sys
    import urllib.error
    import urllib.request

    cert = tmp_path / "server.crt"
    key = tmp_path / "server.key"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-keyout", str(key), "-out", str(cert), "-subj", "/CN=localhost",
        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(Path(gateway.__file__).parents[1]),
        "SOLARMINER_DB_PATH": str(tmp_path / "tls.db"),
        "SOLARMINER_BOOTSTRAP_PATH": str(tmp_path / "tls-bootstrap.token"),
        "SOLARMINER_INSTANCE_MARKER": str(tmp_path / "tls-initialized.marker"),
        "SOLARMINER_DATA_DIR": str(tmp_path),
        "SOLARMINER_TLS_CERT": str(cert),
        "SOLARMINER_TLS_KEY": str(key),
    })
    code = ("import uvicorn; from solarminer_gateway.app import app; "
            f"uvicorn.run(app,host='127.0.0.1',port={port},ssl_certfile={str(cert)!r},ssl_keyfile={str(key)!r},log_level='error',access_log=False)")
    process = subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"https://localhost:{port}/api/v1/health"
    try:
        context = ssl.create_default_context(cafile=str(cert))
        deadline = time.time() + 10
        last_error = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, context=context, timeout=1) as response:
                    assert response.status == 200
                    assert b'"version":"0.6.0"' in response.read()
                break
            except Exception as exc:
                last_error = exc
                time.sleep(0.1)
        else:
            pytest.fail(f"TLS endpoint did not become ready: {last_error}")
        with pytest.raises((urllib.error.URLError, ssl.SSLCertVerificationError)):
            urllib.request.urlopen(url, context=ssl.create_default_context(), timeout=2)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_expired_bootstrap_is_not_reissued_after_reinitialization(client):
    old_token = gateway.BOOTSTRAP_PATH.read_text().strip()
    with gateway.db() as conn:
        conn.execute("UPDATE bootstrap SET expires_at=? WHERE id=1", (int(time.time()) - 1,))
    gateway.initialize()
    assert client.get("/api/v1/bootstrap/status").json()["state"] == "RECOVERY_REQUIRED"
    assert not gateway.BOOTSTRAP_PATH.exists()
    with gateway.db() as conn:
        row = conn.execute("SELECT token_sha256,expires_at,state FROM bootstrap WHERE id=1").fetchone()
    assert row["token_sha256"] == gateway.token_hash(old_token)
    assert row["state"] == "expired"


def test_deye_cloud_history_import_runs_as_owner_scoped_progress_job(client, monkeypatch):
    owner, private, _ = create_owner(client)
    token = login(client, owner, private).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    def fake_history(config, station_id, *, days, progress_callback):
        assert station_id == "12345" and days == 90
        progress_callback(34, "A descarregar amostras: 200 recebidas…")
        progress_callback(78, "A descarregar amostras: 400 recebidas…")
        return []

    monkeypatch.setattr(gateway, "_require_deye_cloud_config", lambda: {"app_id": "configured"})
    monkeypatch.setattr(gateway.hardware_integrations, "deye_cloud_history", fake_history)
    monkeypatch.setattr(gateway.hardware_integrations, "load_config", lambda: {})
    started = client.post("/api/v1/integrations/deye-cloud/history/import", json={"station_id": "12345"}, headers=headers)
    assert started.status_code == 200, started.text
    job_id = started.json()["job_id"]
    deadline = time.time() + 5
    while time.time() < deadline:
        status = client.get(f"/api/v1/integrations/deye-cloud/history/import/{job_id}", headers=headers)
        assert status.status_code == 200, status.text
        if status.json()["status"] == "completed":
            break
        time.sleep(0.01)
    assert status.json()["status"] == "completed"
    assert status.json()["progress"] == 100
    assert status.json()["result"]["source_rows"] == 0
    assert client.get(f"/api/v1/integrations/deye-cloud/history/import/{job_id}").status_code == 401


def test_concurrent_bootstrap_creates_only_one_owner(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr(gateway, "DB_PATH", tmp_path / "concurrent.db")
    monkeypatch.setattr(gateway, "BOOTSTRAP_PATH", tmp_path / "concurrent-bootstrap.token")
    monkeypatch.setattr(gateway, "INSTANCE_MARKER", tmp_path / "concurrent-initialized.marker")
    with TestClient(gateway.app, client=("127.0.0.1", 12345)) as c:
        token = gateway.BOOTSTRAP_PATH.read_text().strip()
        private, public = keypair()
        ts, nonce = int(time.time()), "bootstrap-concurrent-0001"
        canonical = f"BOOTSTRAP\nowner-concurrent\nAA:BB:CC:DD:EE:77\n{ts}\n{nonce}"
        payload = {"bootstrap_token": token, "username": "owner-concurrent", "password": "a-long-passphrase-77",
                   "mac": "AA:BB:CC:DD:EE:77", "public_key_pem": public, "signature": sig(private, canonical),
                   "timestamp": ts, "nonce": nonce}
        def submit():
            return c.post("/api/v1/bootstrap/owner", json=payload).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda _: submit(), range(2)))
        assert sorted(statuses) == [201, 409]
        with gateway.db() as conn:
            assert conn.execute("SELECT COUNT(*) FROM users WHERE role='owner' AND status='active'").fetchone()[0] == 1


def test_missing_database_after_initialization_fails_closed(client):
    marker = gateway.INSTANCE_MARKER
    assert marker.exists()
    assert gateway.DB_PATH.exists()
    gateway.DB_PATH.unlink()
    gateway.initialize()
    assert marker.exists()
    assert not gateway.DB_PATH.exists()
    assert not gateway.BOOTSTRAP_PATH.exists()


def test_owner_creation_attempt_is_denied_and_audited(client):
    owner, private, _ = create_owner(client)
    bearer = login(client, owner, private).json()["access_token"]
    headers = {"Authorization": f"Bearer {bearer}"}
    device_private, device_public = keypair()
    device = client.post("/api/v1/devices", headers=headers,
                         json={"mac": "21:22:23:24:25:26", "public_key_pem": device_public})
    assert device.status_code == 201
    response = client.post("/api/v1/users", headers=headers, json={
        "username": "owner-attempt", "password": "a-long-passphrase-owner", "role": "owner",
        "device_id": device.json()["id"]})
    assert response.status_code == 403
    events = client.get("/api/v1/audit", headers=headers).json()["events"]
    assert any(e["action"] == "user.owner_creation_attempt" and e["outcome"] == "denied"
               and e["target"] == "owner-attempt" for e in events)
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users WHERE role='owner' AND username='owner-attempt'").fetchone()[0] == 0


def test_last_active_owner_is_protected_by_api_and_sqlite_triggers(client):
    owner, private, _ = create_owner(client)
    bearer = login(client, owner, private).json()["access_token"]
    headers = {"Authorization": f"Bearer {bearer}"}
    uid = owner["user_id"]

    response = client.post(f"/api/v1/users/{uid}/revoke", headers=headers,
                            json={"current_password": "a-long-passphrase-01"})
    assert response.status_code == 403
    assert response.json()["detail"] == "self_deactivation_forbidden"
    with gateway.db() as conn:
        row = conn.execute("SELECT role,status FROM users WHERE id=?", (uid,)).fetchone()
        assert tuple(row) == ("owner", "active")
        denied = conn.execute("SELECT action,outcome,details_json FROM audit WHERE action='user.revoke' AND target=? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
        assert denied and denied["outcome"] == "denied" and "self_deactivation_forbidden" in denied["details_json"]
        for statement in (
            ("UPDATE users SET status='revoked' WHERE id=?", (uid,)),
            ("UPDATE users SET role='admin' WHERE id=?", (uid,)),
            ("DELETE FROM users WHERE id=?", (uid,)),
        ):
            with pytest.raises(Exception) as exc:
                conn.execute(statement[0], statement[1])
            assert "last_active_owner_protected" in str(exc.value)
        with pytest.raises(Exception) as replace_exc:
            conn.execute("INSERT OR REPLACE INTO users(id,account_id,username,password_hash,role,status,created_at,credential_version) VALUES(?,?,?,?,?,?,?,1)",
                         (uid, "replacement-account", "owner1", "replacement-hash", "viewer", "active", gateway.utcnow()))
        assert "last_active_owner_protected" in str(replace_exc.value)
        row = conn.execute("SELECT role,status FROM users WHERE id=?", (uid,)).fetchone()
        assert tuple(row) == ("owner", "active")
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_admin_cannot_bypass_owner_only_status_management_through_legacy_revoke(client):
    import uuid
    owner, private, _ = create_owner(client)
    owner_headers, _ = _owner_headers(client, owner, private, nonce="legacy-revoke-owner-login")
    member, _ = _create_member(client, owner, private, role="admin", username="legacy-revoke-admin",
                               password="legacy-admin-password-0001")
    admin_login = login(client, owner, private, username=member["username"],
                        password="legacy-admin-password-0001", nonce="legacy-revoke-admin-login")
    assert admin_login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    response = client.post(f"/api/v1/users/{owner['user_id']}/revoke", headers=admin_headers,
                           json={"current_password": "legacy-admin-password-0001"})
    assert response.status_code == 403
    with gateway.db() as conn:
        row = conn.execute("SELECT role,status FROM users WHERE id=?", (owner["user_id"],)).fetchone()
        event = conn.execute("SELECT outcome,details_json FROM audit WHERE action='user.revoke' ORDER BY id DESC LIMIT 1").fetchone()
    assert tuple(row) == ("owner", "active")
    assert event and event["outcome"] == "denied" and "actor_not_active_owner" in event["details_json"]
    assert client.get("/api/v1/users", headers=owner_headers).status_code == 200


def test_role_change_trigger_invalidates_existing_sessions(client):
    import uuid
    owner, private, _ = create_owner(client)
    bearer = login(client, owner, private).json()["access_token"]
    headers = {"Authorization": f"Bearer {bearer}"}
    other_owner = str(uuid.uuid4())
    with gateway.db() as conn:
        conn.execute("INSERT INTO users(id,account_id,username,password_hash,role,status,created_at) VALUES(?,?,?,?, 'owner','active',?)",
                     (other_owner, str(uuid.uuid4()), "owner-extra", "unused-hash", gateway.utcnow()))
        conn.execute("UPDATE users SET role='admin' WHERE id=?", (owner["user_id"],))
        version = conn.execute("SELECT credential_version FROM users WHERE id=?", (owner["user_id"],)).fetchone()[0]
        assert version == 2
    assert client.get("/api/v1/status", headers=headers).status_code == 401


def test_operator_cannot_manage_users_devices_or_audit(client):
    owner, private, _ = create_owner(client)
    owner_token = login(client, owner, private).json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    created_device = client.post("/api/v1/devices", headers=owner_headers, json={
        "mac": "31:32:33:34:35:36", "public_key_pem": owner["public_key_pem"] if "public_key_pem" in owner else keypair()[1]})
    assert created_device.status_code == 201
    response = client.post("/api/v1/users", headers=owner_headers, json={
        "username": "operator-a1", "password": "a-long-passphrase-operator", "role": "operator",
        "device_id": owner["device_id"]})
    assert response.status_code == 201
    operator_login = login(client, owner, private, password="a-long-passphrase-operator",
                           nonce="operator-login-nonce-0001", username="operator-a1")
    assert operator_login.status_code == 200
    headers = {"Authorization": f"Bearer {operator_login.json()['access_token']}"}
    assert client.get("/api/v1/status", headers=headers).status_code == 200
    assert client.get("/api/v1/users", headers=headers).status_code == 403
    assert client.post("/api/v1/users", headers=headers, json={
        "username": "operator-b", "password": "a-long-passphrase-operator-b", "role": "viewer",
        "device_id": owner["device_id"]}).status_code == 403
    assert client.post("/api/v1/devices", headers=headers, json={
        "mac": "41:42:43:44:45:46", "public_key_pem": keypair()[1]}).status_code == 403
    assert client.post(f"/api/v1/devices/{created_device.json()['id']}/revoke", headers=headers).status_code == 403
    assert client.get("/api/v1/audit", headers=headers).status_code == 403
    assert client.post("/api/v1/users/not-a-user/revoke", headers=headers).status_code == 403


def test_role_change_api_is_absent_and_explicitly_not_claimed_as_implemented(client):
    owner, private, _ = create_owner(client)
    bearer = login(client, owner, private).json()["access_token"]
    response = client.put(f"/api/v1/users/{owner['user_id']}",
                          headers={"Authorization": f"Bearer {bearer}"}, json={"role": "owner"})
    # The existing project has no role-change endpoint. This must not be mistaken
    # for a fully audited anti-escalation workflow; the gap is reported BLOCKED.
    assert response.status_code == 404


def test_admin_permission_matrix_preserves_existing_role_capabilities(client):
    owner, private, _ = create_owner(client)
    owner_headers = {"Authorization": f"Bearer {login(client, owner, private).json()['access_token']}"}
    response = client.post("/api/v1/users", headers=owner_headers, json={
        "username": "admin-a1", "password": "a-long-passphrase-admin", "role": "admin",
        "device_id": owner["device_id"]})
    assert response.status_code == 201
    admin_login = login(client, owner, private, password="a-long-passphrase-admin",
                        nonce="admin-login-nonce-0001", username="admin-a1")
    assert admin_login.status_code == 200
    headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    assert client.get("/api/v1/status", headers=headers).status_code == 200
    assert client.get("/api/v1/users", headers=headers).status_code == 200
    assert client.get("/api/v1/audit", headers=headers).status_code == 403
    # Admin may create users under the pre-existing manage_users permission.
    created = client.post("/api/v1/users", headers=headers, json={
        "username": "viewer-by-admin", "password": "a-long-passphrase-viewer", "role": "viewer",
        "device_id": owner["device_id"]})
    assert created.status_code == 201
    managed_device = client.post("/api/v1/devices", headers=headers,
                                 json=_make_device_payload("AA:BB:CC:DD:EE:27"))
    assert managed_device.status_code == 201, managed_device.text
    managed_revoke = client.post(f"/api/v1/devices/{managed_device.json()['id']}/revoke", headers=headers)
    assert managed_revoke.status_code == 200, managed_revoke.text


def test_create_user_failure_rolls_back_user_and_association(client):
    owner, private, _ = create_owner(client)
    headers = {"Authorization": f"Bearer {login(client, owner, private).json()['access_token']}"}
    payload = {"username": "rollback-user", "password": "a-long-passphrase-rollback", "role": "viewer",
               "device_id": owner["device_id"]}
    assert client.post("/api/v1/users", headers=headers, json=payload).status_code == 201
    # A duplicate username causes the insert transaction to roll back; no second
    # user/device-association row may be left behind.
    duplicate = client.post("/api/v1/users", headers=headers, json=payload)
    assert duplicate.status_code == 409
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users WHERE username='rollback-user'").fetchone()[0] == 1
        uid = conn.execute("SELECT id FROM users WHERE username='rollback-user'").fetchone()[0]
        assert conn.execute("SELECT COUNT(*) FROM user_devices WHERE user_id=?", (uid,)).fetchone()[0] == 1
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_owner_can_read_and_configure_valid_tailscale_endpoint(client, monkeypatch):
    owner, private, _ = create_owner(client)
    headers, _ = _owner_headers(client, owner, private, nonce="owner-tailscale-endpoint-01")
    monkeypatch.setattr(gateway, "_read_tailscale_status", lambda: {
        "installed": True, "connected": True, "dns_name": "solarminer-gateway.tail1234.ts.net",
        "https_url": "https://solarminer-gateway.tail1234.ts.net"})
    status = client.get("/api/v1/system/tailscale", headers=headers)
    assert status.status_code == 200
    assert status.json()["detected_endpoint"] == "https://solarminer-gateway.tail1234.ts.net"
    assert status.json()["https_ready"] is False
    saved = client.put("/api/v1/system/tailscale", headers=headers,
                       json={"endpoint": "https://solarminer-gateway.tail1234.ts.net/"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["configured_endpoint"] == "https://solarminer-gateway.tail1234.ts.net"
    assert saved.json()["endpoint"] == "https://solarminer-gateway.tail1234.ts.net"
    cleared = client.put("/api/v1/system/tailscale", headers=headers, json={"endpoint": None})
    assert cleared.status_code == 200
    assert cleared.json()["configured_endpoint"] is None


def test_owner_can_read_redacted_gateway_console_logs(client, monkeypatch):
    owner, private, _ = create_owner(client)
    headers, _ = _owner_headers(client, owner, private, nonce="owner-console-logs-01")
    monkeypatch.setattr(gateway.update_helper_client, "request", lambda action: {
        "status": "ok", "logs": "2026-10-22 INFO service started", "truncated": False,
        "services": {"gateway": "active", "nginx": "active"},
        "resources": {"cpu_percent": 4.2, "cpu_count": 6,
                       "memory": {"total_bytes": 100, "used_bytes": 40, "available_bytes": 60, "used_percent": 40.0},
                       "disk": {"path": "/var/lib/solarminer", "total_bytes": 1000, "used_bytes": 250,
                                "free_bytes": 750, "used_percent": 25.0}},
        "scope": "allowlisted_services_last_7_days_including_update_recovery_plus_tailscale_setup_log_tail"} if action == "diagnostics" else {})
    response = client.get("/api/v1/system/console", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "available"
    assert response.json()["logs"] == "2026-10-22 INFO service started"
    assert response.json()["truncated"] is False
    assert response.json()["services"]["gateway"] == "active"
    assert response.json()["resources"]["memory"]["used_percent"] == 40.0


def test_owner_can_configure_private_diagnostics_token_without_readback(client, tmp_path, monkeypatch):
    owner, private, _ = create_owner(client)
    headers, _ = _owner_headers(client, owner, private, nonce="owner-diagnostics-token-01")
    token_path = tmp_path / "github-diagnostics-token"
    monkeypatch.setattr(gateway.error_reporting, "TOKEN_PATH", token_path)
    token = "github_pat_" + "x" * 40
    status = client.get("/api/v1/system/diagnostics-upload", headers=headers)
    assert status.status_code == 200
    assert status.json() == {"configured": False, "destination": "solargualdimpais-bot/TheSolarMiner-Diagnostics"}
    saved = client.put("/api/v1/system/diagnostics-upload", headers=headers, json={"token": token})
    assert saved.status_code == 200, saved.text
    assert saved.json()["configured"] is True
    assert token not in saved.text
    assert token_path.read_text() == token
    assert "github-diagnostics-token" not in saved.text
    removed = client.delete("/api/v1/system/diagnostics-upload", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["configured"] is False
    assert not token_path.exists()


def test_owner_can_submit_privacy_filtered_endpoint_probe_diagnostics(client, monkeypatch):
    owner, private, _ = create_owner(client)
    headers, _ = _owner_headers(client, owner, private, nonce="owner-client-diagnostic-01")
    captured = []
    monkeypatch.setattr(gateway.LOG, "error", lambda message, *args: captured.append(message % args))
    payload = {"events": [{"occurred_at": "2026-11-08T12:00:00Z", "browser": "Safari",
        "endpoint_kind": "Tailscale", "route": "/api/v1/health", "outcome": "timeout",
        "latency_ms": 3500, "http_status": None, "error_name": "AbortError"}]}
    response = client.post("/api/v1/system/client-diagnostics", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "recorded", "events": 1, "failures": 1}
    assert captured and '"browser":"Safari"' in captured[0]
    assert client.post("/api/v1/system/client-diagnostics", headers=headers,
        json={"events": [{**payload["events"][0], "endpoint_url": "https://private.example"}]}).status_code == 422


def test_owner_can_toggle_watchdog_manually(client, monkeypatch):
    owner, private, _ = create_owner(client)
    headers, _ = _owner_headers(client, owner, private, nonce="owner-watchdog-toggle-01")
    calls = []
    monkeypatch.setattr(gateway.update_helper_client, "request", lambda action, **kwargs: calls.append((action, kwargs)) or {
        "status": "ok", "enabled": kwargs["enabled"], "timer": "active" if kwargs["enabled"] else "inactive"})
    response = client.put("/api/v1/system/watchdog", headers=headers, json={"enabled": True})
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok", "enabled": True, "timer": "active"}
    assert calls == [("watchdog_set", {"enabled": True})]


def test_owner_can_send_manual_diagnostics_to_automatic_destination(client, monkeypatch):
    owner, private, _ = create_owner(client)
    headers, _ = _owner_headers(client, owner, private, nonce="owner-manual-report-01")
    monkeypatch.setattr(gateway.error_reporting, "diagnostics_upload_status", lambda: {"configured": True})
    captured = []
    monkeypatch.setattr(gateway.error_reporting, "flush_reports", lambda **kwargs: captured.append(kwargs) or {
        "status": "sent", "issue_url": "https://github.com/solargualdimpais-bot/TheSolarMiner-Diagnostics/issues/1"})
    response = client.post("/api/v1/system/diagnostics-upload/send", headers=headers, json={})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "sent"
    assert captured == [{"force_system_report": True, "report_source": "owner_manual"}]


def test_non_owner_cannot_read_gateway_console(client, monkeypatch):
    owner, private, _ = create_owner(client)
    member, _ = _create_member(client, owner, private, role="viewer", username="console-viewer",
                               password="console-viewer-password")
    viewer_login = login(client, owner, private, username=member["username"],
                         password="console-viewer-password", nonce="console-viewer-login-01")
    assert viewer_login.status_code == 200, viewer_login.text
    headers = {"Authorization": f"Bearer {viewer_login.json()['access_token']}"}
    monkeypatch.setattr(gateway.update_helper_client, "request", lambda *_args: pytest.fail("viewer triggered privileged diagnostics"))
    response = client.get("/api/v1/system/console", headers=headers)
    assert response.status_code == 403


@pytest.mark.parametrize("endpoint", [
    "http://solarminer-gateway.tail1234.ts.net",
    "https://evil.example",
    "https://user@solarminer-gateway.tail1234.ts.net",
    "https://solarminer-gateway.tail1234.ts.net/path",
    "https://solarminer-gateway.tail1234.ts.net?x=1",
    "https://solarminer-gateway.tail1234.ts.net:8443",
])
def test_tailscale_endpoint_rejects_noncanonical_or_untrusted_urls(client, endpoint):
    owner, private, _ = create_owner(client)
    headers, _ = _owner_headers(client, owner, private, nonce="owner-tailscale-invalid-01")
    response = client.put("/api/v1/system/tailscale", headers=headers, json={"endpoint": endpoint})
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_tailscale_endpoint"


def test_non_owner_cannot_read_or_configure_tailscale(client):
    owner, private, _ = create_owner(client)
    member, _ = _create_member(client, owner, private, role="viewer", username="tailscale-viewer",
                               password="tailscale-viewer-password")
    viewer_login = login(client, owner, private, username=member["username"],
                         password="tailscale-viewer-password", nonce="viewer-tailscale-01")
    assert viewer_login.status_code == 200, viewer_login.text
    headers = {"Authorization": f"Bearer {viewer_login.json()['access_token']}"}
    assert client.get("/api/v1/system/tailscale", headers=headers).status_code == 403
    assert client.put("/api/v1/system/tailscale", headers=headers,
                      json={"endpoint": "https://solarminer-gateway.tail1234.ts.net"}).status_code == 403
    assert client.post("/api/v1/system/tailscale/connect", headers=headers, json={}).status_code == 403


def test_owner_can_start_tailscale_auth_without_exposing_raw_command_output(client, monkeypatch):
    owner, private, _ = create_owner(client)
    headers, _ = _owner_headers(client, owner, private, nonce="owner-tailscale-start-01")
    monkeypatch.setattr(gateway, "_start_tailscale_auth", lambda: {
        "started": True, "connected": False,
        "auth_url": "https://login.tailscale.com/a/AbCdEf123456"})
    response = client.post("/api/v1/system/tailscale/connect", headers=headers, json={})
    assert response.status_code == 200, response.text
    assert response.json() == {"started": True, "connected": False,
                               "auth_url": "https://login.tailscale.com/a/AbCdEf123456"}


def test_tailscale_auth_url_is_strictly_validated(monkeypatch):
    monkeypatch.setattr(gateway.update_helper_client, "request", lambda *_args, **_kwargs: {
        "auth_url": "https://evil.example/a/token", "connected": False})
    with pytest.raises(gateway.HTTPException) as exc:
        gateway._start_tailscale_auth()
    assert exc.value.status_code == 503


def test_migration_v2_upgrades_existing_v1_database_without_losing_users(tmp_path, monkeypatch):
    import sqlite3
    db_path = tmp_path / "existing-v1.db"
    marker = tmp_path / "existing.marker"
    bootstrap = tmp_path / "existing-bootstrap.token"
    monkeypatch.setattr(gateway, "DB_PATH", db_path)
    monkeypatch.setattr(gateway, "INSTANCE_MARKER", marker)
    monkeypatch.setattr(gateway, "BOOTSTRAP_PATH", bootstrap)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(gateway.SCHEMA)
        conn.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(1,?)", (gateway.utcnow(),))
        conn.execute("INSERT INTO system_state(key,value) VALUES('bootstrap_state','OWNER_ACTIVE')")
        conn.execute("INSERT INTO users(id,account_id,username,password_hash,role,status,created_at) VALUES('legacy-owner','acct-1','legacy-owner','unused-hash','owner','active',?)", (gateway.utcnow(),))
    marker.write_text("existing-v1\n")
    gateway.initialize()
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT username FROM users WHERE id='legacy-owner'").fetchone()[0] == "legacy-owner"
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=2").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=3").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=4").fetchone()[0] == 1
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='owner_recovery_keys'").fetchone()[0] == "owner_recovery_keys"
        triggers = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        assert {"protect_last_active_owner_update", "protect_last_active_owner_delete", "protect_last_active_owner_replace", "invalidate_sessions_on_role_change"}.issubset(triggers)
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_owner_dps_semantics_are_persisted_in_product_scoped_sqlite_map():
    import sqlite3
    with sqlite3.connect(":memory:") as conn:
        conn.executescript(gateway.SCHEMA)
        saved = gateway._persist_tuya_product_dps_map(conn, {"breaker-product": {
            "product_name": "Energy breaker", "category": "switch", "device_kind": "breaker",
            "dps_profile": {"dps": [{"dps_id": 18, "function_code": "cur_current",
                "semantic_code": "current", "display_name": "Corrente", "unit": "mA",
                "scale": 1, "confidence": "OWNER_CUSTOM"}]},
            "custom_dps_overrides": {"18": {"label": "Corrente da carga", "semantic_code": "current",
                "unit": "A", "data_type": "number", "scale": 1000}},
        }})
        row = conn.execute("SELECT protocol,product_id,dps_id,semantic_code,description,unit,scale,confidence FROM tuya_product_dps_map").fetchone()
    assert saved == 1
    assert row == ("tuya", "breaker-product", 18, "current", "Corrente da carga", "A", 1000.0, "OWNER_CUSTOM")


def test_every_existing_protected_route_rejects_direct_unauthenticated_access(client):
    create_owner(client)
    _, public2 = keypair()
    requests = [
        ("GET", "/api/v1/status", None),
        ("POST", "/api/v1/auth/logout", {}),
        ("GET", "/api/v1/users", None),
        ("POST", "/api/v1/users", {"username": "direct-user", "password": "a-long-passphrase-direct", "role": "viewer", "device_id": "missing"}),
        ("POST", "/api/v1/devices", {"mac": "51:52:53:54:55:56", "public_key_pem": public2}),
        ("POST", "/api/v1/devices/not-a-device/revoke", {}),
        ("POST", "/api/v1/users/not-a-user/revoke", {}),
        ("GET", "/api/v1/audit", None),
    ]
    for method, path, payload in requests:
        response = client.request(method, path, json=payload)
        assert response.status_code == 401, (method, path, response.status_code, response.text)


def _owner_headers(client, owner, private, nonce="owner-login-for-a1b-0001"):
    response = login(client, owner, private, nonce=nonce)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, response.json()["access_token"]


def _create_member(client, owner, private, role="operator", username="member1", password="member-password-0001"):
    headers, _ = _owner_headers(client, owner, private, nonce=f"create-member-{username}-nonce")
    response = client.post("/api/v1/users", headers=headers, json={
        "username": username, "password": password, "role": role, "device_id": owner["device_id"]
    })
    assert response.status_code == 201, response.text
    return response.json(), headers


def test_owner_can_change_other_user_role_with_reauth_and_invalidates_old_session(client):
    owner, private, _ = create_owner(client)
    member, owner_headers = _create_member(client, owner, private)
    old_login = login(client, owner, private, username=member["username"],
                      password="member-password-0001", nonce="member-old-session-role-01")
    assert old_login.status_code == 200, old_login.text
    old_token = old_login.json()["access_token"]
    response = client.patch(f"/api/v1/users/{member['id']}/role", headers=owner_headers,
                            json={"role": "admin", "current_password": "a-long-passphrase-01"})
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "admin"
    assert client.get("/api/v1/status", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
    with gateway.db() as conn:
        event = conn.execute("SELECT outcome,details_json FROM audit WHERE action='user.role_changed' ORDER BY id DESC LIMIT 1").fetchone()
    assert event["outcome"] == "success"
    assert '"previous_role":"operator"' in event["details_json"]
    assert '"new_role":"admin"' in event["details_json"]
    assert owner_headers["Authorization"].startswith("Bearer ")
    assert client.get("/api/v1/users", headers=owner_headers).status_code == 200


def test_owner_can_deactivate_and_reactivate_other_user_without_restoring_old_session(client):
    owner, private, _ = create_owner(client)
    member, owner_headers = _create_member(client, owner, private)
    logged = login(client, owner, private, username=member["username"], password="member-password-0001",
                   nonce="member-status-session-01")
    assert logged.status_code == 200
    old_token = logged.json()["access_token"]
    deactivated = client.patch(f"/api/v1/users/{member['id']}/status", headers=owner_headers,
                               json={"status": "revoked", "current_password": "a-long-passphrase-01"})
    assert deactivated.status_code == 200, deactivated.text
    assert client.get("/api/v1/status", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
    denied_login = login(client, owner, private, username=member["username"], password="member-password-0001",
                         nonce="member-status-login-denied-01")
    assert denied_login.status_code == 401
    reactivated = client.patch(f"/api/v1/users/{member['id']}/status", headers=owner_headers,
                               json={"status": "active", "current_password": "a-long-passphrase-01"})
    assert reactivated.status_code == 200, reactivated.text
    assert client.get("/api/v1/status", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
    new_login = login(client, owner, private, username=member["username"], password="member-password-0001",
                      nonce="member-status-login-after-reactivation")
    assert new_login.status_code == 200, new_login.text


def test_non_owner_roles_cannot_change_roles_or_status_even_with_correct_password(client):
    owner, private, _ = create_owner(client)
    for role, username, password, nonce in [
        ("admin", "admin-a1b", "admin-password-0001", "admin-a1b-login-01"),
        ("operator", "operator-a1b", "operator-password-0001", "operator-a1b-login-01"),
        ("viewer", "viewer-a1b", "viewer-password-0001", "viewer-a1b-login-01"),
    ]:
        member, _ = _create_member(client, owner, private, role=role, username=username, password=password)
        login_response = login(client, owner, private, username=username, password=password, nonce=nonce)
        assert login_response.status_code == 200
        headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}
        role_response = client.patch(f"/api/v1/users/{owner['user_id']}/role", headers=headers,
                                     json={"role": "admin", "current_password": password})
        status_response = client.patch(f"/api/v1/users/{owner['user_id']}/status", headers=headers,
                                       json={"status": "revoked", "current_password": password})
        assert role_response.status_code == 403
        assert status_response.status_code == 403
    with gateway.db() as conn:
        denied = conn.execute("SELECT COUNT(*) FROM audit WHERE action IN ('user.role_changed','user.status_changed') AND outcome='denied'").fetchone()[0]
    assert denied >= 6


def test_self_changes_bad_password_and_invalid_values_are_denied_and_audited(client, caplog):
    owner, private, _ = create_owner(client)
    headers, _ = _owner_headers(client, owner, private, nonce="owner-self-check-login-01")
    self_role = client.patch(f"/api/v1/users/{owner['user_id']}/role", headers=headers,
                             json={"role": "viewer", "current_password": "a-long-passphrase-01"})
    self_status = client.patch(f"/api/v1/users/{owner['user_id']}/status", headers=headers,
                               json={"status": "revoked", "current_password": "a-long-passphrase-01"})
    bad_password = client.patch(f"/api/v1/users/{owner['user_id']}/role", headers=headers,
                                json={"role": "admin", "current_password": "not-the-password-secret"})
    bad_role = client.patch(f"/api/v1/users/{owner['user_id']}/role", headers=headers,
                            json={"role": "superuser", "current_password": "a-long-passphrase-01"})
    bad_status = client.patch(f"/api/v1/users/{owner['user_id']}/status", headers=headers,
                              json={"status": "disabled-ish", "current_password": "a-long-passphrase-01"})
    wrong_role_type = client.patch(f"/api/v1/users/{owner['user_id']}/role", headers=headers,
                                   json={"role": 123, "current_password": "a-long-passphrase-01"})
    wrong_status_type = client.patch(f"/api/v1/users/{owner['user_id']}/status", headers=headers,
                                     json={"status": False, "current_password": "a-long-passphrase-01"})
    extra_field = client.patch(f"/api/v1/users/{owner['user_id']}/role", headers=headers,
                               json={"role": "admin", "current_password": "a-long-passphrase-01", "actor_role": "owner"})
    assert self_role.status_code == 403
    assert self_status.status_code == 403
    assert bad_password.status_code == 401
    assert bad_role.status_code == 400
    assert bad_status.status_code == 400
    assert wrong_role_type.status_code == 422
    assert wrong_status_type.status_code == 422
    assert extra_field.status_code == 422
    audit_response = client.get("/api/v1/audit", headers=headers)
    assert audit_response.status_code == 200
    body = audit_response.text + caplog.text
    assert "not-the-password-secret" not in body
    with gateway.db() as conn:
        events = conn.execute("SELECT action,outcome,details_json FROM audit WHERE action IN ('user.role_changed','user.status_changed')").fetchall()
    reasons = [r["details_json"] for r in events]
    assert any("self_role_change_forbidden" in x and "last_active_owner_protected" in x for x in reasons)
    assert any("self_deactivation_forbidden" in x and "last_active_owner_protected" in x for x in reasons)
    assert any("reauthentication_failed" in x for x in reasons)
    assert any("invalid_role" in x for x in reasons)
    assert any("invalid_status" in x for x in reasons)


def test_last_active_owner_cannot_be_demoted_or_deactivated_through_a1b(client):
    owner, private, _ = create_owner(client)
    headers, _ = _owner_headers(client, owner, private, nonce="owner-last-check-login-01")
    demote = client.patch(f"/api/v1/users/{owner['user_id']}/role", headers=headers,
                          json={"role": "admin", "current_password": "a-long-passphrase-01"})
    deactivate = client.patch(f"/api/v1/users/{owner['user_id']}/status", headers=headers,
                              json={"status": "revoked", "current_password": "a-long-passphrase-01"})
    assert demote.status_code == 403  # Self-change policy is stricter than the last-owner guard.
    assert deactivate.status_code == 403
    with gateway.db() as conn:
        owner_count = conn.execute("SELECT COUNT(*) FROM users WHERE role='owner' AND status='active'").fetchone()[0]
        trigger_names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert owner_count == 1
    assert {"protect_last_active_owner_update", "protect_last_active_owner_delete", "protect_last_active_owner_replace"}.issubset(trigger_names)


def test_sqlite_replace_trigger_and_migration_v2_remain_intact_after_a1b(client):
    owner, private, _ = create_owner(client)
    with gateway.db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM users WHERE id=?", (owner["user_id"],)).fetchone()
        with pytest.raises(Exception, match="last_active_owner_protected"):
            conn.execute("INSERT OR REPLACE INTO users(id,account_id,username,password_hash,role,status,created_at,credential_version) VALUES(?,?,?,?,?,?,?,?)",
                         (row["id"], row["account_id"], row["username"], row["password_hash"], "admin", "active", row["created_at"], row["credential_version"]))
        conn.rollback()
        versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
        triggers = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert versions == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    assert "protect_last_active_owner_replace" in triggers


def test_audit_failure_rolls_back_privilege_change_and_fails_closed(client):
    owner, private, _ = create_owner(client)
    member, headers = _create_member(client, owner, private, username="auditfailuremember")
    with gateway.db() as conn:
        conn.execute("""CREATE TRIGGER force_role_audit_failure BEFORE INSERT ON audit
                       WHEN NEW.action='user.role_changed' AND NEW.outcome='success'
                       BEGIN SELECT RAISE(ABORT, 'audit_unavailable'); END""")
    response = client.patch(f"/api/v1/users/{member['id']}/role", headers=headers,
                            json={"role": "admin", "current_password": "a-long-passphrase-01"})
    assert response.status_code == 503
    with gateway.db() as conn:
        target = conn.execute("SELECT role FROM users WHERE id=?", (member["id"],)).fetchone()
        failure = conn.execute("SELECT outcome,details_json FROM audit WHERE action='user.role_change_failed' ORDER BY id DESC LIMIT 1").fetchone()
        success = conn.execute("SELECT COUNT(*) FROM audit WHERE action='user.role_changed' AND outcome='success'").fetchone()[0]
    assert target["role"] == "operator"
    assert success == 0
    assert failure and failure["outcome"] == "failed"


@pytest.mark.parametrize("trial", range(5))
def test_concurrent_two_owner_role_demotions_never_remove_all_owners(client, trial):
    from concurrent.futures import ThreadPoolExecutor
    import uuid

    owner, private, _ = create_owner(client)
    owner_headers, _ = _owner_headers(client, owner, private, nonce=f"concurrent-owner-one-login-{trial}")
    owner2_password = "second-owner-password-01"
    owner2_id = str(uuid.uuid4())
    with gateway.db() as conn:
        conn.execute("INSERT INTO users(id,account_id,username,password_hash,role,status,created_at) VALUES(?,?,?,?, 'owner','active',?)",
                     (owner2_id, str(uuid.uuid4()), f"owner2concurrent{trial}", gateway.PASSWORDS.hash(owner2_password), gateway.utcnow()))
        conn.execute("INSERT INTO user_devices(user_id,device_id,status,created_at) VALUES(?,?,'active',?)",
                     (owner2_id, owner["device_id"], gateway.utcnow()))
    owner2 = {"device_id": owner["device_id"]}
    owner2_login = login(client, owner2, private, username=f"owner2concurrent{trial}", password=owner2_password,
                         nonce="concurrent-owner-two-login")
    assert owner2_login.status_code == 200, owner2_login.text
    owner2_headers = {"Authorization": f"Bearer {owner2_login.json()['access_token']}"}
    barrier = __import__("threading").Barrier(2)

    def demote(headers, target_id, nonce_unused=None):
        barrier.wait(timeout=5)
        return client.patch(f"/api/v1/users/{target_id}/role", headers=headers,
                            json={"role": "admin", "current_password": "a-long-passphrase-01" if headers is owner_headers else owner2_password})

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(demote, owner_headers, owner2_id)
        second = pool.submit(demote, owner2_headers, owner["user_id"])
        responses = [first.result(timeout=15), second.result(timeout=15)]
    assert sorted(r.status_code for r in responses) == [200, 403]
    with gateway.db() as conn:
        owners = conn.execute("SELECT COUNT(*) FROM users WHERE role='owner' AND status='active'").fetchone()[0]
        successful = conn.execute("SELECT COUNT(*) FROM audit WHERE action='user.role_changed' AND outcome='success'").fetchone()[0]
        denied = conn.execute("SELECT COUNT(*) FROM audit WHERE action='user.role_changed' AND outcome='denied'").fetchone()[0]
    assert owners >= 1
    assert successful == 1
    assert denied == 1


def _pause_after_initial_permission_check(monkeypatch, route_path, method):
    """Test-only dependency override: pause after auth/RBAC but before handler code."""
    import threading
    route = next(r for r in gateway.app.routes
                 if getattr(r, "path", None) == route_path and method in getattr(r, "methods", set()))
    permission_dependency = next(d.call for d in route.dependant.dependencies
                                 if getattr(d.call, "__name__", "") == "dependency")
    reached = threading.Event()
    release = threading.Event()

    def paused_dependency(session=__import__("fastapi").Depends(gateway.current_session)):
        result = permission_dependency(session)
        reached.set()
        if not release.wait(timeout=10):
            raise RuntimeError("test synchronization timed out")
        return result

    gateway.app.dependency_overrides[permission_dependency] = paused_dependency
    return reached, release, permission_dependency


def _make_device_payload(mac="AA:BB:CC:DD:EE:22"):
    _, public = keypair()
    return {"mac": mac, "public_key_pem": public, "mac_status": "declared"}


def test_aud_a1b01_create_user_rejected_if_admin_demoted_after_initial_authorization(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    owner, private, _ = create_owner(client)
    admin, _ = _create_member(client, owner, private, role="admin", username="raceadmin1",
                              password="race-admin-password-01")
    admin_login = login(client, owner, private, username=admin["username"],
                        password="race-admin-password-01", nonce="race-admin-login-01")
    assert admin_login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    owner_headers, _ = _owner_headers(client, owner, private, nonce="race-owner-login-01")
    reached, release, dependency = _pause_after_initial_permission_check(monkeypatch, "/api/v1/users", "POST")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(client.post, "/api/v1/users", headers=admin_headers, json={
                "username": "mustnotexist1", "password": "new-user-password-01", "role": "operator",
                "device_id": owner["device_id"]})
            assert reached.wait(timeout=5), "request did not reach the post-authorization pause"
            demote = client.patch(f"/api/v1/users/{admin['id']}/role", headers=owner_headers,
                                  json={"role": "viewer", "current_password": "a-long-passphrase-01"})
            assert demote.status_code == 200, demote.text
            release.set()
            response = pending.result(timeout=10)
        assert response.status_code == 401, response.text
        with gateway.db() as conn:
            assert conn.execute("SELECT 1 FROM users WHERE username='mustnotexist1'").fetchone() is None
            assert conn.execute("SELECT COUNT(*) FROM audit WHERE action='user.created' AND outcome='success' AND target=(SELECT id FROM users WHERE username='mustnotexist1')").fetchone()[0] == 0
            role = conn.execute("SELECT role FROM users WHERE id=?", (admin["id"],)).fetchone()[0]
        assert role == "viewer"
    finally:
        release.set()
        gateway.app.dependency_overrides.pop(dependency, None)


def test_aud_a1b01_create_user_wins_write_lock_before_demotion(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    owner, private, _ = create_owner(client)
    admin, _ = _create_member(client, owner, private, role="admin", username="raceadmin2",
                              password="race-admin-password-02")
    admin_login = login(client, owner, private, username=admin["username"],
                        password="race-admin-password-02", nonce="race-admin-login-02")
    assert admin_login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    owner_headers, _ = _owner_headers(client, owner, private, nonce="race-owner-login-02")
    lock_acquired = threading.Event()
    release = threading.Event()
    demotion_started = threading.Event()
    demotion_lock_attempt = threading.Event()
    original_revalidate = gateway._revalidate_actor
    original_db = gateway.db

    def paused_revalidate(conn, session, permission):
        actor = original_revalidate(conn, session, permission)
        lock_acquired.set()
        if not release.wait(timeout=10):
            raise RuntimeError("test synchronization timed out")
        return actor

    class ConnectionProxy:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, *args):
            if sql.strip().upper() == "BEGIN IMMEDIATE" and lock_acquired.is_set() and not release.is_set():
                demotion_lock_attempt.set()
            return self._conn.execute(sql, *args)

        def __getattr__(self, name):
            return getattr(self._conn, name)

    from contextlib import contextmanager
    @contextmanager
    def observed_db():
        with original_db() as conn:
            yield ConnectionProxy(conn)

    monkeypatch.setattr(gateway, "db", observed_db)
    monkeypatch.setattr(gateway, "_revalidate_actor", paused_revalidate)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            create = pool.submit(client.post, "/api/v1/users", headers=admin_headers, json={
                "username": "createdbeforedemotion", "password": "new-user-password-02", "role": "operator",
                "device_id": owner["device_id"]})
            assert lock_acquired.wait(timeout=5), "create request did not acquire/revalidate under write lock"

            def demote_actor():
                demotion_started.set()
                return client.patch(f"/api/v1/users/{admin['id']}/role", headers=owner_headers,
                                    json={"role": "viewer", "current_password": "a-long-passphrase-01"})

            demotion = pool.submit(demote_actor)
            assert demotion_started.wait(timeout=5)
            assert demotion_lock_attempt.wait(timeout=5), "demotion did not attempt its SQLite write lock"
            release.set()
            created = create.result(timeout=10)
            demoted = demotion.result(timeout=10)
        assert created.status_code == 201, created.text
        assert demoted.status_code == 200, demoted.text
        with gateway.db() as conn:
            user = conn.execute("SELECT id FROM users WHERE username='createdbeforedemotion'").fetchone()
            event = conn.execute("SELECT outcome,target FROM audit WHERE action='user.created' AND target=?", (user["id"],)).fetchone()
        assert user is not None
        assert event and event["outcome"] == "success" and event["target"] == user["id"]
    finally:
        release.set()
        monkeypatch.setattr(gateway, "_revalidate_actor", original_revalidate)
        monkeypatch.setattr(gateway, "db", original_db)


@pytest.mark.parametrize("endpoint_kind", ["create", "revoke"])
def test_aud_a1b01_device_write_rejected_after_admin_demoted(client, monkeypatch, endpoint_kind):
    from concurrent.futures import ThreadPoolExecutor

    owner, private, _ = create_owner(client)
    admin, _ = _create_member(client, owner, private, role="admin", username=f"deviceadmin{endpoint_kind}",
                              password="device-admin-password-01")
    logged = login(client, owner, private, username=admin["username"], password="device-admin-password-01",
                   nonce=f"device-admin-login-{endpoint_kind}-01")
    assert logged.status_code == 200
    admin_headers = {"Authorization": f"Bearer {logged.json()['access_token']}"}
    owner_headers, _ = _owner_headers(client, owner, private, nonce=f"device-owner-login-{endpoint_kind}-01")
    target_device = client.post("/api/v1/devices", headers=owner_headers, json=_make_device_payload()).json()
    if endpoint_kind == "create":
        path, route_path, method, payload = "/api/v1/devices", "/api/v1/devices", "POST", _make_device_payload("AA:BB:CC:DD:EE:23")
    else:
        path, route_path, method, payload = f"/api/v1/devices/{target_device['id']}/revoke", "/api/v1/devices/{device_id}/revoke", "POST", None
    reached, release, dependency = _pause_after_initial_permission_check(monkeypatch, route_path, method)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            if payload is None:
                pending = pool.submit(client.post, path, headers=admin_headers)
            else:
                pending = pool.submit(client.post, path, headers=admin_headers, json=payload)
            assert reached.wait(timeout=5), "device request did not reach post-authorization pause"
            demote = client.patch(f"/api/v1/users/{admin['id']}/role", headers=owner_headers,
                                  json={"role": "viewer", "current_password": "a-long-passphrase-01"})
            assert demote.status_code == 200, demote.text
            release.set()
            response = pending.result(timeout=10)
        assert response.status_code == 401, response.text
        with gateway.db() as conn:
            if endpoint_kind == "create":
                assert conn.execute("SELECT 1 FROM devices WHERE mac_declared='AA:BB:CC:DD:EE:23'").fetchone() is None
                assert conn.execute("SELECT COUNT(*) FROM audit WHERE action='device.created' AND outcome='success' AND details_json LIKE '%AA:BB:CC:DD:EE:23%'").fetchone()[0] == 0
            else:
                status = conn.execute("SELECT status FROM devices WHERE id=?", (target_device["id"],)).fetchone()[0]
                assert status == "active"
                assert conn.execute("SELECT COUNT(*) FROM audit WHERE action='device.revoked' AND outcome='success' AND target=?", (target_device["id"],)).fetchone()[0] == 0
    finally:
        release.set()
        gateway.app.dependency_overrides.pop(dependency, None)


def test_aud_a1b01_device_create_and_revoke_remain_available_to_owner(client):
    owner, private, _ = create_owner(client)
    headers, _ = _owner_headers(client, owner, private, nonce="device-owner-normal-login-01")
    payload = _make_device_payload("AA:BB:CC:DD:EE:24")
    created = client.post("/api/v1/devices", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    revoked = client.post(f"/api/v1/devices/{created.json()['id']}/revoke", headers=headers)
    assert revoked.status_code == 200, revoked.text
    with gateway.db() as conn:
        device = conn.execute("SELECT status FROM devices WHERE id=?", (created.json()["id"],)).fetchone()
        events = conn.execute("SELECT action,outcome FROM audit WHERE target=? AND action IN ('device.created','device.revoked') ORDER BY id",
                              (created.json()["id"],)).fetchall()
    assert device["status"] == "revoked"
    assert [(r["action"], r["outcome"]) for r in events] == [("device.created", "success"), ("device.revoked", "success")]


def test_aud_a1b01_login_rechecks_after_completed_deactivation(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    owner, private, _ = create_owner(client)
    member, owner_headers = _create_member(client, owner, private, username="loginraceinactive",
                                           password="login-race-password-01")
    reached = threading.Event()
    release = threading.Event()
    original_verify = gateway.verify_signature

    def paused_verify(pem, message, signature):
        original_verify(pem, message, signature)
        if message.startswith(b"LOGIN\nloginraceinactive\n"):
            reached.set()
            if not release.wait(timeout=10):
                raise RuntimeError("test synchronization timed out")

    monkeypatch.setattr(gateway, "verify_signature", paused_verify)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(login, client, owner, private, "login-race-password-01",
                                  "login-race-member-nonce-01", "loginraceinactive")
            assert reached.wait(timeout=5), "login did not pass initial password/signature checks"
            response = client.patch(f"/api/v1/users/{member['id']}/status", headers=owner_headers,
                                    json={"status": "revoked", "current_password": "a-long-passphrase-01"})
            assert response.status_code == 200, response.text
            release.set()
            login_response = pending.result(timeout=10)
        assert login_response.status_code == 401, login_response.text
        with gateway.db() as conn:
            user = conn.execute("SELECT status,credential_version FROM users WHERE id=?", (member["id"],)).fetchone()
            sessions = conn.execute("SELECT COUNT(*) FROM sessions WHERE user_id=?", (member["id"],)).fetchone()[0]
            successes = conn.execute("SELECT COUNT(*) FROM audit WHERE action='auth.login' AND target=? AND outcome='success'", (member["id"],)).fetchone()[0]
        assert user["status"] == "revoked"
        assert user["credential_version"] == 2
        assert sessions == 0
        assert successes == 0
    finally:
        release.set()
        monkeypatch.setattr(gateway, "verify_signature", original_verify)


def test_aud_a1b01_login_cannot_cross_deactivation_reactivation(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    owner, private, _ = create_owner(client)
    member, owner_headers = _create_member(client, owner, private, username="loginracereactivate",
                                           password="login-race-password-02")
    old_login = login(client, owner, private, username=member["username"], password="login-race-password-02",
                      nonce="login-race-old-session-01")
    assert old_login.status_code == 200
    old_token = old_login.json()["access_token"]
    reached = threading.Event()
    release = threading.Event()
    original_verify = gateway.verify_signature

    def paused_verify(pem, message, signature):
        original_verify(pem, message, signature)
        if message.startswith(b"LOGIN\nloginracereactivate\n"):
            reached.set()
            if not release.wait(timeout=10):
                raise RuntimeError("test synchronization timed out")

    monkeypatch.setattr(gateway, "verify_signature", paused_verify)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(login, client, owner, private, "login-race-password-02",
                                  "login-race-member-nonce-02", "loginracereactivate")
            assert reached.wait(timeout=5), "login did not pass initial password/signature checks"
            deactivated = client.patch(f"/api/v1/users/{member['id']}/status", headers=owner_headers,
                                       json={"status": "revoked", "current_password": "a-long-passphrase-01"})
            assert deactivated.status_code == 200, deactivated.text
            reactivated = client.patch(f"/api/v1/users/{member['id']}/status", headers=owner_headers,
                                       json={"status": "active", "current_password": "a-long-passphrase-01"})
            assert reactivated.status_code == 200, reactivated.text
            release.set()
            login_response = pending.result(timeout=10)
        assert login_response.status_code == 401, login_response.text
        assert client.get("/api/v1/status", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
        with gateway.db() as conn:
            user = conn.execute("SELECT status,credential_version FROM users WHERE id=?", (member["id"],)).fetchone()
            old_session = conn.execute("SELECT revoked_at,credential_version FROM sessions WHERE token_sha256=?",
                                       (gateway.token_hash(old_token),)).fetchone()
            sessions = conn.execute("SELECT COUNT(*) FROM sessions WHERE user_id=?", (member["id"],)).fetchone()[0]
            successes = conn.execute("SELECT COUNT(*) FROM audit WHERE action='auth.login' AND target=? AND outcome='success'", (member["id"],)).fetchone()[0]
        assert user["status"] == "active"
        assert user["credential_version"] == 3
        assert old_session["revoked_at"] is not None
        assert old_session["credential_version"] == 1
        assert sessions == 1
        assert successes == 1  # only the pre-deactivation login succeeded
    finally:
        release.set()
        monkeypatch.setattr(gateway, "verify_signature", original_verify)


def test_aud_a1b01_user_and_device_audit_failure_rolls_back_mutation(client):
    owner, private, _ = create_owner(client)
    headers, _ = _owner_headers(client, owner, private, nonce="audit-atomic-owner-login-01")
    with gateway.db() as conn:
        conn.execute("""CREATE TRIGGER fail_user_create_audit BEFORE INSERT ON audit
                       WHEN NEW.action='user.created' AND NEW.outcome='success'
                       BEGIN SELECT RAISE(ABORT, 'audit_unavailable'); END""")
    user_response = client.post("/api/v1/users", headers=headers, json={
        "username": "auditrollbackuser", "password": "audit-user-password-01", "role": "operator",
        "device_id": owner["device_id"]})
    assert user_response.status_code == 503
    with gateway.db() as conn:
        assert conn.execute("SELECT 1 FROM users WHERE username='auditrollbackuser'").fetchone() is None
        assert conn.execute("SELECT COUNT(*) FROM audit WHERE action='user.created' AND outcome='success'").fetchone()[0] == 0
        conn.execute("DROP TRIGGER fail_user_create_audit")
        conn.execute("""CREATE TRIGGER fail_device_create_audit BEFORE INSERT ON audit
                       WHEN NEW.action='device.created' AND NEW.outcome='success'
                       BEGIN SELECT RAISE(ABORT, 'audit_unavailable'); END""")
    device_response = client.post("/api/v1/devices", headers=headers, json=_make_device_payload("AA:BB:CC:DD:EE:25"))
    assert device_response.status_code == 503
    with gateway.db() as conn:
        assert conn.execute("SELECT 1 FROM devices WHERE mac_declared='AA:BB:CC:DD:EE:25'").fetchone() is None
        assert conn.execute("SELECT COUNT(*) FROM audit WHERE action='device.created' AND outcome='success'").fetchone()[0] == 0



def test_aud_a1b01_status_generation_changes_only_on_real_transitions(client):
    owner, private, _ = create_owner(client)
    member, owner_headers = _create_member(client, owner, private, username="statusgenerationmember",
                                           password="status-generation-password-01")
    with gateway.db() as conn:
        initial = conn.execute("SELECT credential_version FROM users WHERE id=?", (member["id"],)).fetchone()[0]
    assert initial == 1
    first_deactivation = client.patch(f"/api/v1/users/{member['id']}/status", headers=owner_headers,
                                      json={"status": "revoked", "current_password": "a-long-passphrase-01"})
    assert first_deactivation.status_code == 200, first_deactivation.text
    with gateway.db() as conn:
        after_deactivation = conn.execute("SELECT credential_version FROM users WHERE id=?", (member["id"],)).fetchone()[0]
    assert after_deactivation == 2
    no_op = client.patch(f"/api/v1/users/{member['id']}/status", headers=owner_headers,
                         json={"status": "revoked", "current_password": "a-long-passphrase-01"})
    assert no_op.status_code == 200, no_op.text
    with gateway.db() as conn:
        after_no_op = conn.execute("SELECT credential_version FROM users WHERE id=?", (member["id"],)).fetchone()[0]
    assert after_no_op == 2
    reactivation = client.patch(f"/api/v1/users/{member['id']}/status", headers=owner_headers,
                                json={"status": "active", "current_password": "a-long-passphrase-01"})
    assert reactivation.status_code == 200, reactivation.text
    with gateway.db() as conn:
        after_reactivation = conn.execute("SELECT credential_version FROM users WHERE id=?", (member["id"],)).fetchone()[0]
    assert after_reactivation == 3
    no_op_active = client.patch(f"/api/v1/users/{member['id']}/status", headers=owner_headers,
                                json={"status": "active", "current_password": "a-long-passphrase-01"})
    assert no_op_active.status_code == 200, no_op_active.text
    with gateway.db() as conn:
        after_second_no_op = conn.execute("SELECT credential_version FROM users WHERE id=?", (member["id"],)).fetchone()[0]
    assert after_second_no_op == 3


def test_aud_a1b01_device_revoke_audit_failure_rolls_back(client):
    owner, private, _ = create_owner(client)
    headers, _ = _owner_headers(client, owner, private, nonce="device-revoke-audit-owner-login-01")
    created = client.post("/api/v1/devices", headers=headers,
                          json=_make_device_payload("AA:BB:CC:DD:EE:26"))
    assert created.status_code == 201, created.text
    device_id = created.json()["id"]
    with gateway.db() as conn:
        conn.execute("""CREATE TRIGGER fail_device_revoke_audit BEFORE INSERT ON audit
                       WHEN NEW.action='device.revoked' AND NEW.outcome='success'
                       BEGIN SELECT RAISE(ABORT, 'audit_unavailable'); END""")
    response = client.post(f"/api/v1/devices/{device_id}/revoke", headers=headers)
    assert response.status_code == 503
    with gateway.db() as conn:
        device = conn.execute("SELECT status FROM devices WHERE id=?", (device_id,)).fetchone()
        success_events = conn.execute("SELECT COUNT(*) FROM audit WHERE action='device.revoked' AND outcome='success' AND target=?", (device_id,)).fetchone()[0]
    assert device["status"] == "active"
    assert success_events == 0


def test_site_profile_is_shared_and_owner_only_for_writes(client):
    owner, owner_private, owner_public = create_owner(client)
    owner_login = client.post("/api/v1/auth/password-device-login", json=password_device_payload(
        owner_private, owner_public, "owner1", "a-long-passphrase-01", "site-profile-owner-login-01"))
    assert owner_login.status_code == 201, owner_login.text
    owner_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}
    import base64
    image = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xffimage\xff\xd9").decode("ascii")
    profile = {"name": "Casa Solar", "photo_data_url": image, "photo_opacity": 0.38, "photo_position_x": 50, "photo_position_y": 50, "photo_zoom": 1.0, "photo_vignette": 0.35, "floors": [
        {"id": "floor-ground", "name": "Rés do chão", "rooms": [{"id": "room-living", "name": "Sala"}]}
    ]}
    saved = client.put("/api/v1/site/profile", headers=owner_headers, json=profile)
    assert saved.status_code == 200, saved.text
    assert client.get("/api/v1/site/profile", headers=owner_headers).json() == profile
    replacement = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xffnew-house-photo\xff\xd9").decode("ascii")
    photo_saved = client.put("/api/v1/site/profile/photo", headers=owner_headers,
                             json={"kind": "house", "floor_id": "", "room_id": "", "photo_data_url": replacement})
    assert photo_saved.status_code == 200, photo_saved.text
    assert photo_saved.json()["photo_data_url"] == replacement
    assert photo_saved.json()["floors"] == profile["floors"]

    with gateway.db() as conn:
        conn.execute("INSERT INTO users(id,account_id,username,password_hash,role,status,created_at) VALUES(?,?,?,?, 'viewer','active',?)",
                     ("00000000-0000-4000-8000-000000000082", "00000000-0000-4000-8000-000000000083",
                      "siteviewer", gateway.PASSWORDS.hash("viewer-password-01"), gateway.utcnow()))
    viewer_private, viewer_public = keypair()
    viewer_login = client.post("/api/v1/auth/password-device-login", json=password_device_payload(
        viewer_private, viewer_public, "siteviewer", "viewer-password-01", "site-profile-viewer-login-01"))
    assert viewer_login.status_code == 201, viewer_login.text
    viewer_headers = {"Authorization": f"Bearer {viewer_login.json()['access_token']}"}
    assert client.get("/api/v1/site/profile", headers=viewer_headers).status_code == 200
    denied = client.put("/api/v1/site/profile", headers=viewer_headers, json={**profile, "name": "Alteração não autorizada"})
    assert denied.status_code == 403
    assert client.get("/api/v1/site/profile", headers=owner_headers).json()["name"] == "Casa Solar"


def test_tuya_product_import_accepts_explicit_json_schema_without_enabling_writes():
    payload = '{"products":[{"product_id":"kg_ev","product_name":"EV Charger","functions":[{"code":"charge_switch","dp_id":1,"type":"Boolean"}],"dps":[{"dps_id":2,"display_name":"Power","semantic_code":"power","data_type":"Integer","unit":"W","scale":1}]}]}'
    profiles = gateway._parse_tuya_product_import(payload, "catalog.json")
    assert list(profiles) == ["kg_ev"]
    assert profiles["kg_ev"]["functions"][0]["dp_id"] == 1
    assert profiles["kg_ev"]["dps_profile"]["dps"][0]["semantic_code"] == "power"
    assert profiles["kg_ev"]["schema_source"] == "EXTERNAL_REFERENCE"


def test_tuya_product_import_accepts_csv_product_and_dps_rows_as_reference_only():
    payload = "product_id,product_name,category,dps_id,dps_name\nkg_ev,EV Charger,charger,7,Charging state\nkg_ev,EV Charger,charger,8,Current"
    profiles = gateway._parse_tuya_product_import(payload, "catalog.csv")
    dps = profiles["kg_ev"]["dps_profile"]["dps"]
    assert [row["dps_id"] for row in dps] == [7, 8]
    assert all(row["write_supported"] is False and row["semantic_code"] == "unknown" for row in dps)


def test_tuya_product_import_accepts_one_dps_per_csv_column():
    payload = "Product ID,Product Name,DPS 1,DPS 2\nkg_columns,EV Charger,Switch state,Power (W)"
    profiles = gateway._parse_tuya_product_import(payload, "column-map.csv")
    dps = profiles["kg_columns"]["dps_profile"]["dps"]
    assert [(item["dps_id"], item["display_name"]) for item in dps] == [(1, "Switch state"), (2, "Power (W)")]
    assert all(item["write_supported"] is False for item in dps)


def test_tuya_product_import_extracts_html_tables_and_rejects_unstructured_text():
    html = "<table><tr><th>Product ID</th><th>Name</th><th>DPS ID</th><th>DPS Name</th></tr><tr><td>kg_ev</td><td>EV Charger</td><td>3</td><td>Voltage</td></tr></table>"
    profiles = gateway._parse_tuya_product_import(html, "reference.html")
    assert profiles["kg_ev"]["dps_profile"]["dps"][0]["dps_id"] == 3
    with pytest.raises(ValueError, match="product_import_product_id_column_required"):
        gateway._parse_tuya_product_import("a paragraph with no structured product information", "notes.txt")


def test_tuya_product_import_reads_first_sheet_of_xlsx():
    workbook = io.BytesIO()
    with zipfile.ZipFile(workbook, "w") as archive:
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Products" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="worksheet"/></Relationships>')
        archive.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Product ID</t></si><si><t>Name</t></si><si><t>DPS ID</t></si><si><t>Power</t></si><si><t>kg_xlsx</t></si><si><t>Charger</t></si></sst>')
        archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c><c r="D1" t="inlineStr"><is><t>DPS Name</t></is></c></row><row r="2"><c r="A2" t="s"><v>4</v></c><c r="B2" t="s"><v>5</v></c><c r="C2"><v>9</v></c><c r="D2" t="s"><v>3</v></c></row></sheetData></worksheet>')
    profiles = gateway._parse_tuya_product_import(workbook.getvalue(), "catalog.xlsx")
    assert profiles["kg_xlsx"]["product_name"] == "Charger"
    assert profiles["kg_xlsx"]["dps_profile"]["dps"][0]["dps_id"] == 9


def test_tuya_product_import_preview_is_read_only_and_apply_skips_owner_selected_rows(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SOLARMINER_DATA_DIR", str(tmp_path / "data"))
    owner, private, _ = create_owner(client)
    login_result = login(client, owner, private)
    headers = {"Authorization": f"Bearer {login_result.json()['access_token']}"}
    content = json.dumps({"products": [
        {"product_id": "kg_one", "product_name": "Charger One", "dps": [{"dps_id": 2, "display_name": "Power"}]},
        {"product_id": "kg_two", "product_name": "Charger Two", "dps": [{"dps_id": 4, "display_name": "Current"}]},
    ]})
    preview = client.post("/api/v1/integrations/tuya/product-catalog/preview", headers=headers,
                          json={"content": content, "filename": "products.json"})
    assert preview.status_code == 200, preview.text
    assert preview.json()["persisted"] is False
    assert preview.json()["source_count"] == 2
    before = client.get("/api/v1/integrations/hardware", headers=headers).json()["tuya"]["product_catalog"]
    assert "kg_one" not in before and "kg_two" not in before
    applied = client.post("/api/v1/integrations/tuya/product-catalog/apply", headers=headers,
                          json={"profiles": preview.json()["profiles"], "excluded_product_ids": ["kg_two"]})
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied_count"] == 1
    after = client.get("/api/v1/integrations/hardware", headers=headers).json()["tuya"]["product_catalog"]
    assert "kg_one" in after and "kg_two" not in after
    with gateway.db() as conn:
        assert conn.execute("SELECT 1 FROM tuya_product_dps_map WHERE product_id='kg_one' AND dps_id=2").fetchone()


def test_zigbee2mqtt_profiles_share_catalog_without_crossing_tuya_dps(client):
    owner, private, _ = create_owner(client)
    auth = login(client, owner, private)
    assert auth.status_code == 200, auth.text
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
    with gateway.db() as conn:
        assert conn.execute("SELECT 1 FROM smart_product_catalog_sources WHERE source_key='zigbee2mqtt-device-catalog'").fetchone() is None
    response = client.get("/api/v1/smart-products/zigbee2mqtt-catalog?limit=2", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["protocol"] == "zigbee2mqtt"
    assert payload["tuya_dps_merged"] is False
    assert payload["total"] > 5000
    assert len(payload["profiles"]) == 2
    profile = payload["profiles"][0]
    assert profile["profile"]["protocol"] == "zigbee2mqtt"
    assert profile["source_url"].startswith("https://www.zigbee2mqtt.io/devices/")

    product_code = profile["product_code"]
    assert profile["product_id"] == product_code
    with gateway.db() as conn:
        conn.execute("INSERT INTO smart_product_catalog(manufacturer,protocol,product_code,product_name,updated_at) VALUES(?,?,?,?,?)",
                     (profile["manufacturer"], "tuya", product_code, "Tuya de teste", gateway.utcnow()))
        rows = conn.execute("SELECT protocol,product_name FROM smart_product_catalog WHERE manufacturer=? AND product_code=? ORDER BY protocol",
                            (profile["manufacturer"], product_code)).fetchall()
    assert [(row["protocol"], row["product_name"]) for row in rows] == [("tuya", "Tuya de teste"), ("zigbee2mqtt", profile["product_name"])]
