import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from solarminer_gateway import app as gateway


@pytest.fixture
def presence_client(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "DB_PATH", tmp_path / "gateway.db")
    monkeypatch.setattr(gateway, "BOOTSTRAP_PATH", tmp_path / "bootstrap.token")
    monkeypatch.setattr(gateway, "INSTANCE_MARKER", tmp_path / "initialized.marker")
    with TestClient(gateway.app) as client:
        yield client


def _keypair():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, public


def _sig(private, text):
    return private.sign(text.encode()).hex()


def _login_owner(client):
    bootstrap = gateway.BOOTSTRAP_PATH.read_text().strip()
    private, public = _keypair()
    ts, nonce = int(time.time()), "presence-bootstrap-nonce-00001"
    canonical = f"BOOTSTRAP\nownerpresence\nAA:BB:CC:DD:EE:31\n{ts}\n{nonce}"
    response = client.post("/api/v1/bootstrap/owner", json={
        "bootstrap_token": bootstrap, "username": "ownerpresence", "password": "a-long-presence-passphrase-01",
        "mac": "AA:BB:CC:DD:EE:31", "public_key_pem": public, "signature": _sig(private, canonical),
        "timestamp": ts, "nonce": nonce,
    })
    assert response.status_code == 201, response.text
    device = response.json()
    ts, nonce = int(time.time()), "presence-login-nonce-00001"
    canonical = f"LOGIN\nownerpresence\n{device['device_id']}\n{ts}\n{nonce}"
    login = client.post("/api/v1/auth/login", json={
        "username": "ownerpresence", "password": "a-long-presence-passphrase-01", "device_id": device["device_id"],
        "timestamp": ts, "nonce": nonce, "signature": _sig(private, canonical),
    })
    assert login.status_code == 200, login.text
    return login.json()["access_token"], device["device_id"]


def test_presence_requires_valid_session(presence_client):
    assert presence_client.post("/api/v1/presence/heartbeat").status_code == 401
    assert presence_client.get("/api/v1/presence/me").status_code == 401


def test_heartbeat_uses_session_identity_and_returns_gateway_ttl(presence_client):
    token, device_id = _login_owner(presence_client)
    headers = {"Authorization": f"Bearer {token}"}
    result = presence_client.post("/api/v1/presence/heartbeat", headers=headers)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["state"] == "online"
    assert body["ttl_seconds"] == gateway.PRESENCE_TTL_SECONDS
    assert body["connection_method"] == "unknown"
    assert body["throttled"] is False
    assert "user_id" not in body and "device_id" not in body
    own = presence_client.get("/api/v1/presence/me", headers=headers)
    assert own.status_code == 200
    assert own.json()["state"] == "online"
    with gateway.db() as conn:
        row = conn.execute("SELECT device_id FROM user_presence").fetchone()
    assert row["device_id"] == device_id


def test_heartbeat_throttles_excessive_updates(presence_client):
    token, _ = _login_owner(presence_client)
    headers = {"Authorization": f"Bearer {token}"}
    assert presence_client.post("/api/v1/presence/heartbeat", headers=headers).json()["throttled"] is False
    second = presence_client.post("/api/v1/presence/heartbeat", headers=headers)
    assert second.status_code == 200
    assert second.json()["throttled"] is True


def test_presence_expires_to_offline_and_no_record_is_unknown(presence_client):
    token, _ = _login_owner(presence_client)
    headers = {"Authorization": f"Bearer {token}"}
    assert presence_client.get("/api/v1/presence/me", headers=headers).json()["state"] == "unknown"
    presence_client.post("/api/v1/presence/heartbeat", headers=headers)
    with gateway.db() as conn:
        conn.execute("UPDATE user_presence SET expires_at=?", (int(time.time()) - 1,))
    body = presence_client.get("/api/v1/presence/me", headers=headers).json()
    assert body["state"] == "offline"
    assert body["connection_method"] == "unknown"


def test_logout_invalidates_presence_for_session_device(presence_client):
    token, _ = _login_owner(presence_client)
    headers = {"Authorization": f"Bearer {token}"}
    assert presence_client.post("/api/v1/presence/heartbeat", headers=headers).status_code == 200
    logout = presence_client.post("/api/v1/auth/logout", headers=headers)
    assert logout.status_code == 200
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM user_presence").fetchone()[0] == 0
    assert presence_client.get("/api/v1/presence/me", headers=headers).status_code == 401


def test_presence_does_not_accept_client_claimed_lan_remote_or_other_user(presence_client):
    token, _ = _login_owner(presence_client)
    headers = {"Authorization": f"Bearer {token}"}
    result = presence_client.post("/api/v1/presence/heartbeat", headers=headers, json={"user_id": "victim", "device_id": "victim-device", "connection_method": "LAN"})
    assert result.status_code == 200
    body = result.json()
    assert body["connection_method"] == "unknown"
    assert "user_id" not in body and "device_id" not in body
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM user_presence WHERE user_id='victim'").fetchone()[0] == 0


def test_presence_audit_records_new_online_transition(presence_client):
    token, _ = _login_owner(presence_client)
    headers = {"Authorization": f"Bearer {token}"}
    response = presence_client.post("/api/v1/presence/heartbeat", headers=headers)
    assert response.status_code == 200
    with gateway.db() as conn:
        actions = [row[0] for row in conn.execute("SELECT action FROM audit WHERE action LIKE 'presence.%'").fetchall()]
    assert "presence.online" in actions
