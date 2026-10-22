import hashlib
import os
import time
from pathlib import Path

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
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/info").json()["version"] == "0.6.0"
    token_file = gateway.BOOTSTRAP_PATH
    assert token_file.exists()
    if os.name == "posix":
        assert token_file.stat().st_mode & 0o777 == 0o600
    secret = token_file.read_text().strip()
    assert secret not in client.get("/api/v1/bootstrap/status").text
    assert secret not in caplog.text


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
    assert versions == [1, 2, 3, 4, 5, 6]
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
