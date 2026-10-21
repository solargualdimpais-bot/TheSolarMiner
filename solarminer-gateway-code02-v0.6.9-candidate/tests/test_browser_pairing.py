import hashlib
import os
import json
import shutil
import subprocess
import socket
import urllib.request
import time
from pathlib import Path

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


def keypair():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, public


def sign(private, message):
    return private.sign(message.encode()).hex()


def bootstrap_owner(client):
    token = gateway.BOOTSTRAP_PATH.read_text().strip()
    private, public = keypair()
    ts, nonce = int(time.time()), "bootstrap-browser-test-nonce-01"
    canonical = f"BOOTSTRAP\nowner-browser\nAA:BB:CC:DD:EE:01\n{ts}\n{nonce}"
    response = client.post("/api/v1/bootstrap/owner", json={
        "bootstrap_token": token, "username": "owner-browser", "password": "browser-test-password-01",
        "mac": "AA:BB:CC:DD:EE:01", "public_key_pem": public, "signature": sign(private, canonical),
        "timestamp": ts, "nonce": nonce,
    })
    assert response.status_code == 201, response.text
    return response.json(), private


def signed_login(client, user, private, username="owner-browser", password="browser-test-password-01", nonce="browser-login-nonce-0001"):
    ts = int(time.time())
    canonical = f"LOGIN\n{username}\n{user['device_id']}\n{ts}\n{nonce}"
    return client.post("/api/v1/auth/login", json={"username": username, "password": password,
        "device_id": user["device_id"], "timestamp": ts, "nonce": nonce, "signature": sign(private, canonical)})


def issue_code(client, token, username="owner-browser", expires_in=300):
    return client.post("/api/v1/devices/pairing-codes", headers={"Authorization": f"Bearer {token}"},
                       json={"username": username, "expires_in": expires_in})


def pair_payload(private, public, code, mac="AA:BB:CC:DD:EE:99", nonce="browser-pair-nonce-0001", timestamp=None):
    timestamp = timestamp if timestamp is not None else int(time.time())
    normalized_mac = mac.upper()
    der = serialization.load_pem_public_key(public.encode()).public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    digest = hashlib.sha256(der).hexdigest()
    canonical = f"PAIR\n{code}\n{digest}\n{normalized_mac}\n{timestamp}\n{nonce}"
    return {"pairing_code": code, "mac": mac, "public_key_pem": public, "timestamp": timestamp,
            "nonce": nonce, "signature": sign(private, canonical)}


def test_pairing_requires_authenticated_admin_and_target_user(client):
    assert client.post("/api/v1/devices/pairing-codes", json={"username": "owner-browser"}).status_code == 401
    owner, private = bootstrap_owner(client)
    session = signed_login(client, owner, private).json()["access_token"]
    response = issue_code(client, session, username="missing-user")
    assert response.status_code == 404
    assert client.get("/api/v1/energy/equipment").status_code == 401


def test_browser_ed25519_pair_login_read_logout_end_to_end(client):
    owner, owner_private = bootstrap_owner(client)
    owner_token = signed_login(client, owner, owner_private).json()["access_token"]
    issued = issue_code(client, owner_token)
    assert issued.status_code == 201, issued.text
    body = issued.json()
    assert body["single_use"] is True and body["expires_in"] == 300
    # New browser/device creates its own Ed25519 key; private key is never submitted.
    new_private, new_public = keypair()
    paired = client.post("/api/v1/devices/pair", json=pair_payload(new_private, new_public, body["pairing_code"]))
    assert paired.status_code == 201, paired.text
    identity = paired.json()
    assert identity["association_status"] == "active" and identity["mac_status"] == "declared"
    assert identity["device_id"] != owner["device_id"]
    login_ts = int(time.time())
    login_nonce = "browser-new-login-nonce-01"
    login_canonical = f"LOGIN\nowner-browser\n{identity['device_id']}\n{login_ts}\n{login_nonce}"
    logged_in = client.post("/api/v1/auth/login", json={"username": "owner-browser", "password": "browser-test-password-01",
        "device_id": identity["device_id"], "timestamp": login_ts, "nonce": login_nonce,
        "signature": sign(new_private, login_canonical)})
    assert logged_in.status_code == 200, logged_in.text
    token = logged_in.json()["access_token"]
    assert logged_in.json()["device_id"] == identity["device_id"]
    response = client.get("/api/v1/energy/equipment", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    assert "equipment" in response.json()
    assert client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"}, json={}).status_code == 200
    assert client.get("/api/v1/energy/equipment", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_pairing_signature_tamper_does_not_consume_code(client):
    owner, private = bootstrap_owner(client)
    token = signed_login(client, owner, private).json()["access_token"]
    code = issue_code(client, token).json()["pairing_code"]
    device_private, public = keypair()
    payload = pair_payload(device_private, public, code)
    payload["mac"] = "AA:BB:CC:DD:EE:88"  # signed MAC was changed after signing
    denied = client.post("/api/v1/devices/pair", json=payload)
    assert denied.status_code == 401
    assert denied.json()["detail"] == "device_signature_invalid"
    valid = client.post("/api/v1/devices/pair", json=pair_payload(device_private, public, code, nonce="browser-pair-nonce-0002"))
    assert valid.status_code == 201, valid.text


def test_pairing_code_is_single_use_and_expiry_is_server_enforced(client):
    owner, private = bootstrap_owner(client)
    token = signed_login(client, owner, private).json()["access_token"]
    code = issue_code(client, token).json()["pairing_code"]
    device_private, public = keypair()
    payload = pair_payload(device_private, public, code)
    assert client.post("/api/v1/devices/pair", json=payload).status_code == 201
    replay = pair_payload(device_private, public, code, nonce="browser-pair-nonce-0002")
    response = client.post("/api/v1/devices/pair", json=replay)
    assert response.status_code == 401 and response.json()["detail"] == "pairing_code_invalid_expired_or_used"

    expiring = issue_code(client, token).json()["pairing_code"]
    with gateway.db() as conn:
        conn.execute("UPDATE device_pairing_codes SET expires_at=? WHERE token_sha256=?", (int(time.time()) - 1, gateway.token_hash(expiring)))
    expired_payload = pair_payload(*keypair(), expiring, nonce="browser-pair-nonce-0003")
    expired = client.post("/api/v1/devices/pair", json=expired_payload)
    assert expired.status_code == 401 and expired.json()["detail"] == "pairing_code_invalid_expired_or_used"


def test_pairing_rejects_stale_timestamp_and_invalid_key(client):
    owner, private = bootstrap_owner(client)
    token = signed_login(client, owner, private).json()["access_token"]
    code = issue_code(client, token).json()["pairing_code"]
    device_private, public = keypair()
    stale = pair_payload(device_private, public, code, timestamp=int(time.time()) - gateway.NONCE_WINDOW - 2)
    response = client.post("/api/v1/devices/pair", json=stale)
    assert response.status_code == 401 and response.json()["detail"] == "timestamp_out_of_window"
    bad_key = pair_payload(device_private, public, code, nonce="browser-pair-nonce-0002")
    bad_key["public_key_pem"] = "not-a-public-key" + "x" * 100
    invalid = client.post("/api/v1/devices/pair", json=bad_key)
    assert invalid.status_code == 422


def test_pairing_code_issue_rejects_extra_fields_and_bad_expiry(client):
    owner, private = bootstrap_owner(client)
    token = signed_login(client, owner, private).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/devices/pairing-codes", headers=headers,
                       json={"username": "owner-browser", "expires_in": 30}).status_code == 422
    assert client.post("/api/v1/devices/pairing-codes", headers=headers,
                       json={"username": "owner-browser", "expires_in": 300, "role": "owner"}).status_code == 422


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for browser WebCrypto interoperability test")
def test_webcrypto_generated_ed25519_pair_signature_is_accepted_by_gateway(client):
    owner, owner_private = bootstrap_owner(client)
    owner_token = signed_login(client, owner, owner_private).json()["access_token"]
    code = issue_code(client, owner_token).json()["pairing_code"]
    timestamp = int(time.time())
    nonce = "webcrypto-pair-interop-nonce-01"
    mac = "AA:BB:CC:DD:EE:77"
    fixture = Path(__file__).with_name("browser_crypto_fixture.mjs")
    generated = subprocess.run(["node", str(fixture)], input=json.dumps({"mode": "pair", "code": code, "mac": mac,
        "timestamp": timestamp, "nonce": nonce}), text=True, capture_output=True, check=True, timeout=10)
    browser_payload = json.loads(generated.stdout)
    response = client.post("/api/v1/devices/pair", json={"pairing_code": code, "mac": mac,
        "public_key_pem": browser_payload["public_key_pem"], "timestamp": timestamp, "nonce": nonce,
        "signature": browser_payload["signature"]})
    assert response.status_code == 201, response.text
    assert response.json()["public_key_sha256"] == browser_payload["public_key_sha256"]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for browser WebCrypto interoperability test")
def test_webcrypto_login_signature_matches_existing_gateway_canonical_format(client):
    owner, private = bootstrap_owner(client)
    ts = int(time.time())
    nonce = "webcrypto-login-interop-nonce-01"
    canonical = f"LOGIN\nowner-browser\n{owner['device_id']}\n{ts}\n{nonce}"
    pkcs8 = private.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    fixture = Path(__file__).with_name("browser_crypto_fixture.mjs")
    signed = subprocess.run(["node", str(fixture)], input=json.dumps({"mode": "sign-login",
        "private_key_pkcs8_b64": __import__("base64").b64encode(pkcs8).decode(), "canonical": canonical}),
        text=True, capture_output=True, check=True, timeout=10)
    signature = json.loads(signed.stdout)["signature"]
    response = client.post("/api/v1/auth/login", json={"username": "owner-browser", "password": "browser-test-password-01",
        "device_id": owner["device_id"], "timestamp": ts, "nonce": nonce, "signature": signature})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    assert client.get("/api/v1/energy/equipment", headers={"Authorization": f"Bearer {token}"}).status_code == 200


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for browser-to-Gateway integration test")
def test_complete_browser_pair_login_read_logout_over_local_http(client):
    # The real JavaScript/Web Crypto client calls a separate loopback Uvicorn process.
    # Keeping the server in a child process prevents pytest's executor/thread shutdown
    # from depending on an in-process Uvicorn event loop.
    owner, owner_private = bootstrap_owner(client)
    owner_token = signed_login(client, owner, owner_private).json()["access_token"]
    issued = issue_code(client, owner_token)
    assert issued.status_code == 201

    root = Path(__file__).resolve().parents[1]
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    env["SOLARMINER_DATA_DIR"] = str(gateway.DB_PATH.parent)
    env["SOLARMINER_DB_PATH"] = str(gateway.DB_PATH)
    env["SOLARMINER_BOOTSTRAP_PATH"] = str(gateway.BOOTSTRAP_PATH)
    env["SOLARMINER_INSTANCE_MARKER"] = str(gateway.INSTANCE_MARKER)
    process = subprocess.Popen([__import__("sys").executable, "-m", "uvicorn", "solarminer_gateway.app:app",
        "--host", "127.0.0.1", "--port", str(port), "--log-level", "error", "--no-access-log", "--lifespan", "off"],
        cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.time() + 8
        while time.time() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate(timeout=1)
                raise AssertionError(f"loopback Gateway exited before readiness: {stdout} {stderr}")
            try:
                with urllib.request.urlopen(base_url + "/api/v1/health", timeout=0.3) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(0.05)
        else:
            raise AssertionError("loopback Gateway did not become ready")

        fixture = Path(__file__).with_name("browser_crypto_fixture.mjs")
        run = subprocess.run(["node", str(fixture)], input=json.dumps({"mode": "flow", "base_url": base_url,
            "code": issued.json()["pairing_code"], "mac": "AA:BB:CC:DD:EE:88", "username": "owner-browser",
            "password": "browser-test-password-01"}), text=True, capture_output=True, check=True, timeout=20)
        result = json.loads(run.stdout)
        assert result == {"pair_status": "paired", "login_username": "owner-browser", "read_status": 200,
                          "equipment_count": 0, "logout_status": "revoked"}
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)



def test_viewer_cannot_issue_pairing_code_and_raw_code_is_not_persisted(client):
    owner, owner_private = bootstrap_owner(client)
    owner_token = signed_login(client, owner, owner_private).json()["access_token"]
    created = client.post("/api/v1/users", headers={"Authorization": f"Bearer {owner_token}"}, json={
        "username": "viewer-browser", "password": "viewer-browser-password-01", "role": "viewer", "device_id": owner["device_id"]})
    assert created.status_code == 201, created.text
    ts = int(time.time())
    nonce = "viewer-login-nonce-browser-01"
    canonical = f"LOGIN\nviewer-browser\n{owner['device_id']}\n{ts}\n{nonce}"
    viewer_login = client.post("/api/v1/auth/login", json={"username": "viewer-browser", "password": "viewer-browser-password-01",
        "device_id": owner["device_id"], "timestamp": ts, "nonce": nonce, "signature": sign(owner_private, canonical)})
    assert viewer_login.status_code == 200, viewer_login.text
    viewer_token = viewer_login.json()["access_token"]
    denied = issue_code(client, viewer_token, username="viewer-browser")
    assert denied.status_code == 403

    issued = issue_code(client, owner_token)
    assert issued.status_code == 201
    raw_code = issued.json()["pairing_code"]
    with gateway.db() as conn:
        row = conn.execute("SELECT token_sha256 FROM device_pairing_codes WHERE token_sha256=?", (gateway.token_hash(raw_code),)).fetchone()
        raw_match = conn.execute("SELECT 1 FROM device_pairing_codes WHERE token_sha256=?", (raw_code,)).fetchone()
    assert row is not None
    assert raw_match is None
