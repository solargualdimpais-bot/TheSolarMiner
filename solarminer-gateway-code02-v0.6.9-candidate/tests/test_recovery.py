from __future__ import annotations

import hashlib
import os
import secrets
import socket
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from argon2.exceptions import VerifyMismatchError
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from solarminer_gateway import app as gateway
from solarminer_gateway import recovery


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "DB_PATH", tmp_path / "gateway.db")
    monkeypatch.setattr(gateway, "BOOTSTRAP_PATH", tmp_path / "bootstrap.token")
    monkeypatch.setattr(gateway, "INSTANCE_MARKER", tmp_path / "initialized.marker")
    with TestClient(gateway.app) as c:
        yield c


def keypair():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return private, public


def signature(private, message: bytes) -> str:
    return private.sign(message).hex()


def create_owner(client, username="owner-a2"):
    bootstrap_token = gateway.BOOTSTRAP_PATH.read_text().strip()
    private, public = keypair()
    ts = int(time.time())
    nonce = "bootstrap-a2-nonce-0001"
    canonical = f"BOOTSTRAP\n{username}\nAA:BB:CC:DD:EE:11\n{ts}\n{nonce}".encode()
    response = client.post("/api/v1/bootstrap/owner", json={
        "bootstrap_token": bootstrap_token, "username": username, "password": "owner-password-old-01",
        "mac": "AA:BB:CC:DD:EE:11", "public_key_pem": public, "signature": signature(private, canonical),
        "timestamp": ts, "nonce": nonce,
    })
    assert response.status_code == 201, response.text
    return response.json(), private, public


def recovery_proof(owner_id, purpose="recovery", device_id=None):
    private, public = keypair()
    challenge = secrets.token_hex(32)
    message = recovery.device_proof_message(purpose, owner_id, challenge, device_id)
    return private, public, challenge, signature(private, message)


def do_recovery(owner, recovery_key=None, password="owner-password-new-02", mac="AA:BB:CC:DD:EE:22"):
    private, public, challenge, proof = recovery_proof(owner["user_id"])
    result = recovery.recover_owner(owner["user_id"], recovery_key or owner["recovery_key"], password,
                                   public, mac, challenge, proof)
    return result, private, public


def test_recovery_key_is_32_random_bytes_formatted_and_verifier_only(client):
    owner, _, _ = create_owner(client)
    raw = recovery.decode_recovery_key(owner["recovery_key"])
    assert len(raw) == 32
    assert owner["recovery_key"].startswith("SMR1-")
    with gateway.db() as conn:
        row = conn.execute("SELECT verifier_sha256,generation,status FROM owner_recovery_keys WHERE owner_user_id=?", (owner["user_id"],)).fetchone()
        db_bytes = gateway.DB_PATH.read_bytes()
    assert row["verifier_sha256"] == recovery.recovery_verifier(raw)
    assert row["generation"] == 1 and row["status"] == "active"
    assert owner["recovery_key"].encode() not in db_bytes
    assert recovery.decode_recovery_key(" ".join(owner["recovery_key"].split())).hex() == raw.hex()


def test_bootstrap_shows_key_once_and_does_not_log_it(client, caplog):
    owner, _, _ = create_owner(client)
    assert owner["recovery_key_display"] == "one_time_only_store_offline"
    assert owner["recovery_key"] not in caplog.text
    assert not hasattr(gateway, "recovery_endpoint")


def test_successful_recovery_changes_password_invalidates_sessions_and_replaces_device(client):
    owner, old_private, _ = create_owner(client)
    login_ts = int(time.time())
    login_nonce = "old-owner-login-nonce-01"
    login = client.post("/api/v1/auth/login", json={
        "username": "owner-a2", "password": "owner-password-old-01", "device_id": owner["device_id"],
        "timestamp": login_ts, "nonce": login_nonce,
        "signature": signature(old_private, f"LOGIN\nowner-a2\n{owner['device_id']}\n{login_ts}\n{login_nonce}".encode()),
    })
    assert login.status_code == 200, login.text
    old_token = login.json()["access_token"]
    with gateway.db() as conn:
        old_version = conn.execute("SELECT credential_version FROM users WHERE id=?", (owner["user_id"],)).fetchone()[0]
    result, new_private, new_public = do_recovery(owner)
    assert result["recovery_key_display"] == "one_time_only_store_offline"
    with gateway.db() as conn:
        user = conn.execute("SELECT password_hash,credential_version,role,status FROM users WHERE id=?", (owner["user_id"],)).fetchone()
        old_device = conn.execute("SELECT status FROM user_devices WHERE user_id=? AND device_id=?", (owner["user_id"], owner["device_id"])).fetchone()
        old_session = conn.execute("SELECT revoked_at FROM sessions WHERE token_sha256=?", (gateway.token_hash(old_token),)).fetchone()
    assert user["credential_version"] == old_version + 1
    assert gateway.PASSWORDS.verify(user["password_hash"], "owner-password-new-02")
    with pytest.raises(VerifyMismatchError):
        gateway.PASSWORDS.verify(user["password_hash"], "owner-password-old-01")
    assert user["role"] == "owner" and user["status"] == "active"
    assert old_device["status"] == "revoked" and old_session["revoked_at"] is not None
    assert client.get("/api/v1/status", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
    old_login_ts = int(time.time())
    old_login_nonce = "old-device-after-recovery-01"
    old_login = client.post("/api/v1/auth/login", json={
        "username": "owner-a2", "password": "owner-password-old-01", "device_id": owner["device_id"],
        "timestamp": old_login_ts, "nonce": old_login_nonce,
        "signature": signature(old_private, f"LOGIN\nowner-a2\n{owner['device_id']}\n{old_login_ts}\n{old_login_nonce}".encode()),
    })
    assert old_login.status_code == 401
    ts = int(time.time())
    nonce = "new-device-after-recovery-01"
    new_login = client.post("/api/v1/auth/login", json={
        "username": "owner-a2", "password": "owner-password-new-02", "device_id": result["device_id"],
        "timestamp": ts, "nonce": nonce,
        "signature": signature(new_private, f"LOGIN\nowner-a2\n{result['device_id']}\n{ts}\n{nonce}".encode()),
    })
    assert new_login.status_code == 200, new_login.text
    assert new_public


def test_wrong_malformed_and_consumed_keys_are_rejected_without_partial_mutation(client):
    owner, _, _ = create_owner(client)
    with gateway.db() as conn:
        before = conn.execute("SELECT password_hash,credential_version FROM users WHERE id=?", (owner["user_id"],)).fetchone()
    for bad_key in ("not-a-key", "SMR1-AAAA"):
        private, public, challenge, proof = recovery_proof(owner["user_id"])
        with pytest.raises(recovery.RecoveryError):
            recovery.recover_owner(owner["user_id"], bad_key, "owner-password-new-03", public,
                                   "AA:BB:CC:DD:EE:23", challenge, proof)
    with gateway.db() as conn:
        after = conn.execute("SELECT password_hash,credential_version FROM users WHERE id=?", (owner["user_id"],)).fetchone()
        active_keys = conn.execute("SELECT COUNT(*) FROM owner_recovery_keys WHERE owner_user_id=? AND status='active'", (owner["user_id"],)).fetchone()[0]
    assert tuple(before) == tuple(after)
    assert active_keys == 1
    result, _, _ = do_recovery(owner)
    private, public, challenge, proof = recovery_proof(owner["user_id"])
    with pytest.raises(recovery.RecoveryError, match="invalid_or_consumed_recovery_key"):
        recovery.recover_owner(owner["user_id"], owner["recovery_key"], "owner-password-new-04", public,
                               "AA:BB:CC:DD:EE:24", challenge, proof)
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM owner_recovery_keys WHERE owner_user_id=? AND status='active'", (owner["user_id"],)).fetchone()[0] == 1
    assert result["recovery_key"]


def test_recovery_key_rotates_and_new_key_can_be_used_once_again(client):
    owner, _, _ = create_owner(client)
    first, _, _ = do_recovery(owner)
    with gateway.db() as conn:
        rows = conn.execute("SELECT generation,status FROM owner_recovery_keys WHERE owner_user_id=? ORDER BY generation", (owner["user_id"],)).fetchall()
    assert [(r["generation"], r["status"]) for r in rows] == [(1, "consumed"), (2, "active")]
    second, _, _ = do_recovery({**owner, "recovery_key": first["recovery_key"]}, password="owner-password-new-05", mac="AA:BB:CC:DD:EE:25")
    assert second["recovery_key"] != first["recovery_key"]


def test_recovery_api_endpoint_does_not_exist(client):
    create_owner(client)
    response = client.post("/api/v1/recovery", json={"recovery_key": "dummy-test-value"})
    assert response.status_code == 404
    assert all("recovery" not in route.path.lower() for route in gateway.app.routes if getattr(route, "methods", None))


def test_new_device_requires_valid_ed25519_proof(client):
    owner, _, _ = create_owner(client)
    _, public = keypair()
    challenge = secrets.token_hex(32)
    invalid_signature = "00" * 64
    with pytest.raises(recovery.RecoveryError, match="invalid_device_proof"):
        recovery.recover_owner(owner["user_id"], owner["recovery_key"], "owner-password-new-06", public,
                               "AA:BB:CC:DD:EE:26", challenge, invalid_signature)
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM owner_recovery_keys WHERE status='active'").fetchone()[0] == 1


def test_two_concurrent_recoveries_with_same_key_have_at_most_one_success(client):
    owner, _, _ = create_owner(client)
    barrier = threading.Barrier(2)
    candidates = [recovery_proof(owner["user_id"]), recovery_proof(owner["user_id"])]
    def submit(i):
        private, public, challenge, proof = candidates[i]
        barrier.wait(timeout=5)
        try:
            return recovery.recover_owner(owner["user_id"], owner["recovery_key"], f"owner-password-concurrent-{i}",
                                          public, f"AA:BB:CC:DD:EE:{30+i:02X}", challenge, proof)
        except recovery.RecoveryError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, (0, 1)))
    assert sum(r is not None for r in results) == 1
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM owner_recovery_keys WHERE owner_user_id=? AND status='active'", (owner["user_id"],)).fetchone()[0] == 1
        assert conn.execute("SELECT credential_version FROM users WHERE id=?", (owner["user_id"],)).fetchone()[0] == 2


def test_transaction_and_audit_failure_roll_back_recovery(client, monkeypatch):
    owner, old_private, _ = create_owner(client)
    original_audit = gateway.audit
    def failing_audit(conn, actor, action, target, outcome, details=None):
        if action == "owner.recovery" and outcome == "success":
            raise sqlite3.IntegrityError("injected audit failure")
        return original_audit(conn, actor, action, target, outcome, details)
    monkeypatch.setattr(gateway, "audit", failing_audit)
    private, public, challenge, proof = recovery_proof(owner["user_id"])
    with pytest.raises(recovery.RecoveryError, match="recovery_transaction_failed"):
        recovery.recover_owner(owner["user_id"], owner["recovery_key"], "owner-password-new-07", public,
                               "AA:BB:CC:DD:EE:27", challenge, proof)
    with gateway.db() as conn:
        user = conn.execute("SELECT password_hash,credential_version FROM users WHERE id=?", (owner["user_id"],)).fetchone()
        key = conn.execute("SELECT status FROM owner_recovery_keys WHERE owner_user_id=? AND generation=1", (owner["user_id"],)).fetchone()
        assert conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 1
    assert gateway.PASSWORDS.verify(user["password_hash"], "owner-password-old-01")
    assert user["credential_version"] == 1
    assert key["status"] == "active"


def test_last_owner_remains_active_and_recovery_does_not_bypass_invariant(client):
    owner, _, _ = create_owner(client)
    result, _, _ = do_recovery(owner)
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users WHERE role='owner' AND status='active'").fetchone()[0] == 1
        assert conn.execute("SELECT role,status FROM users WHERE id=?", (owner["user_id"],)).fetchone()[:] == ("owner", "active")
    assert result["owner_id"] == owner["user_id"]


def test_recovery_flow_has_no_network_dependency(client, monkeypatch):
    owner, _, _ = create_owner(client)
    def no_network(*args, **kwargs):
        raise AssertionError("network access is forbidden in offline recovery")
    monkeypatch.setattr(socket, "create_connection", no_network)
    result, _, _ = do_recovery(owner)
    assert result["device_id"]


def test_recovery_setup_rotates_key_with_password_and_existing_device_proof(client):
    owner, device_private, _ = create_owner(client)
    challenge = secrets.token_hex(32)
    proof = signature(device_private, recovery.device_proof_message("setup", owner["user_id"], challenge, owner["device_id"]))
    new_key = recovery.setup_recovery_key(owner["user_id"], "owner-password-old-01", owner["device_id"], challenge, proof)
    assert new_key != owner["recovery_key"]
    with gateway.db() as conn:
        rows = conn.execute("SELECT generation,status FROM owner_recovery_keys WHERE owner_user_id=? ORDER BY generation", (owner["user_id"],)).fetchall()
    assert [(r["generation"], r["status"]) for r in rows] == [(1, "consumed"), (2, "active")]


def test_recovery_setup_rejects_wrong_password_and_invalidates_nothing(client):
    owner, device_private, _ = create_owner(client)
    challenge = secrets.token_hex(32)
    proof = signature(device_private, recovery.device_proof_message("setup", owner["user_id"], challenge, owner["device_id"]))
    with pytest.raises(recovery.RecoveryError, match="reauthentication_failed"):
        recovery.setup_recovery_key(owner["user_id"], "wrong-owner-password", owner["device_id"], challenge, proof)
    with gateway.db() as conn:
        rows = conn.execute("SELECT generation,status FROM owner_recovery_keys WHERE owner_user_id=?", (owner["user_id"],)).fetchall()
    assert [(r["generation"], r["status"]) for r in rows] == [(1, "active")]


def test_emergency_backup_is_consistent_private_and_contains_no_plaintext_secrets(client):
    owner, _, _ = create_owner(client)
    backup = recovery.create_consistent_backup()
    assert backup.exists()
    assert backup.stat().st_mode & 0o777 == 0o600
    assert backup.parent.stat().st_mode & 0o777 == 0o700
    with sqlite3.connect(backup) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT username FROM users WHERE id=?", (owner["user_id"],)).fetchone()[0] == "owner-a2"
    raw = backup.read_bytes()
    assert owner["recovery_key"].encode() not in raw
    assert b"owner-password-old-01" not in raw


def test_emergency_reset_preserves_users_data_and_rotates_credentials(client):
    owner, old_private, _ = create_owner(client)
    login_ts = int(time.time())
    login_nonce = "emergency-old-session-01"
    old_login = client.post("/api/v1/auth/login", json={
        "username": "owner-a2", "password": "owner-password-old-01", "device_id": owner["device_id"],
        "timestamp": login_ts, "nonce": login_nonce,
        "signature": signature(old_private, f"LOGIN\nowner-a2\n{owner['device_id']}\n{login_ts}\n{login_nonce}".encode()),
    })
    assert old_login.status_code == 200
    token = old_login.json()["access_token"]
    private, public = keypair()
    challenge = secrets.token_hex(32)
    proof = signature(private, recovery.device_proof_message("emergency", owner["user_id"], challenge))
    result = recovery.emergency_reset(owner["user_id"], "owner-password-emergency-08", public,
                                      "AA:BB:CC:DD:EE:28", challenge, proof)
    assert Path(result["backup_path"]).exists()
    assert result["recovery_key"]
    with gateway.db() as conn:
        user = conn.execute("SELECT credential_version,password_hash,role,status FROM users WHERE id=?", (owner["user_id"],)).fetchone()
        session = conn.execute("SELECT revoked_at FROM sessions WHERE token_sha256=?", (gateway.token_hash(token),)).fetchone()
        events = {r[0] for r in conn.execute("SELECT action FROM audit WHERE target=?", (owner["user_id"],)).fetchall()}
    assert user["credential_version"] == 2 and user["role"] == "owner" and user["status"] == "active"
    assert session["revoked_at"] is not None
    assert "owner.emergency_recovery" in events
    assert client.get("/api/v1/status", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_emergency_audit_failure_rolls_back_and_preserves_backup(client, monkeypatch):
    owner, _, _ = create_owner(client)
    original_audit = gateway.audit
    def failing_audit(conn, actor, action, target, outcome, details=None):
        if action == "owner.emergency_recovery" and outcome == "success":
            raise sqlite3.IntegrityError("injected emergency audit failure")
        return original_audit(conn, actor, action, target, outcome, details)
    monkeypatch.setattr(gateway, "audit", failing_audit)
    private, public = keypair()
    challenge = secrets.token_hex(32)
    proof = signature(private, recovery.device_proof_message("emergency", owner["user_id"], challenge))
    with pytest.raises(recovery.RecoveryError, match="emergency_recovery_transaction_failed_backup_preserved"):
        recovery.emergency_reset(owner["user_id"], "owner-password-emergency-09", public,
                                 "AA:BB:CC:DD:EE:29", challenge, proof)
    with gateway.db() as conn:
        user = conn.execute("SELECT password_hash,credential_version FROM users WHERE id=?", (owner["user_id"],)).fetchone()
        assert conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM owner_recovery_keys WHERE owner_user_id=? AND status='active'", (owner["user_id"],)).fetchone()[0] == 1
    assert user["credential_version"] == 1
    assert gateway.PASSWORDS.verify(user["password_hash"], "owner-password-old-01")
    assert list((Path(gateway.DB_PATH).parent / "backup").rglob("gateway-pre-emergency.db"))


def test_emergency_reset_requires_root_privileges(monkeypatch):
    from solarminer_gateway import cli
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1001)
    with pytest.raises(PermissionError, match="root"):
        cli._require_root()


def test_cli_does_not_accept_recovery_key_as_argument(monkeypatch, capsys):
    from solarminer_gateway import cli
    monkeypatch.setattr("sys.argv", ["solarminer-gateway", "recovery", "--recovery-key", "TEST_ONLY_DUMMY_KEY"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_recovery_success_audit_and_session_invalidation_are_atomic(client):
    owner, old_private, _ = create_owner(client)
    result, _, _ = do_recovery(owner)
    with gateway.db() as conn:
        success = conn.execute("SELECT COUNT(*) FROM audit WHERE action='owner.recovery' AND outcome='success' AND target=?", (owner["user_id"],)).fetchone()[0]
        started = conn.execute("SELECT COUNT(*) FROM audit WHERE action='owner.recovery_started' AND outcome='attempted' AND target=?", (owner["user_id"],)).fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM owner_recovery_keys WHERE owner_user_id=? AND status='active'", (owner["user_id"],)).fetchone()[0]
    assert success == 1 and started == 1 and active == 1
    assert result["device_id"]


def test_role_removal_or_deactivation_consumes_owner_recovery_key(client):
    owner, owner_private, _ = create_owner(client)
    # A second owner is inserted directly for this focused invariant test; production APIs remain unchanged.
    second_private, second_public = keypair()
    second_device_id = "a2-second-owner-device"
    second_owner_id = "a2-second-owner-user"
    der = serialization.load_pem_public_key(second_public.encode()).public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    with gateway.db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT INTO devices(id,public_key_pem,public_key_sha256,mac_declared,mac_status,status,created_at) VALUES(?,?,?,'AA:BB:CC:DD:EE:31','declared','active',?)",
                     (second_device_id, second_public, hashlib.sha256(der).hexdigest(), gateway.utcnow()))
        conn.execute("INSERT INTO users(id,account_id,username,password_hash,role,status,created_at) VALUES(?,?,?,?, 'owner','active',?)",
                     (second_owner_id, "a2-second-acct", "owner-second", gateway.PASSWORDS.hash("owner-password-second-31"), gateway.utcnow()))
        conn.execute("INSERT INTO user_devices(user_id,device_id,status,created_at) VALUES(?,?,'active',?)",
                     (second_owner_id, second_device_id, gateway.utcnow()))
        conn.execute("INSERT INTO owner_recovery_keys(id,owner_user_id,verifier_sha256,generation,status,created_at) VALUES(?,?,?,?, 'active',?)",
                     ("second-recovery-key", second_owner_id, recovery.recovery_verifier(os.urandom(32)), 1, gateway.utcnow()))
        conn.commit()
    ts = int(time.time())
    nonce = "owner-a2-role-change-login"
    login = client.post("/api/v1/auth/login", json={
        "username": "owner-a2", "password": "owner-password-old-01", "device_id": owner["device_id"],
        "timestamp": ts, "nonce": nonce,
        "signature": signature(owner_private, f"LOGIN\nowner-a2\n{owner['device_id']}\n{ts}\n{nonce}".encode()),
    })
    assert login.status_code == 200
    response = client.patch(f"/api/v1/users/{second_owner_id}/role",
                            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
                            json={"role": "admin", "current_password": "owner-password-old-01"})
    assert response.status_code == 200, response.text
    with gateway.db() as conn:
        key = conn.execute("SELECT status FROM owner_recovery_keys WHERE owner_user_id=?", (second_owner_id,)).fetchone()[0]
    assert key == "consumed"
    promoted = client.patch(f"/api/v1/users/{second_owner_id}/role",
                            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
                            json={"role": "owner", "current_password": "owner-password-old-01"})
    assert promoted.status_code == 200, promoted.text
    with gateway.db() as conn:
        conn.execute("INSERT INTO owner_recovery_keys(id,owner_user_id,verifier_sha256,generation,status,created_at) VALUES(?,?,?,?, 'active',?)",
                     ("second-recovery-key-v2", second_owner_id, recovery.recovery_verifier(os.urandom(32)), 2, gateway.utcnow()))
    deactivated = client.patch(f"/api/v1/users/{second_owner_id}/status",
                               headers={"Authorization": f"Bearer {login.json()['access_token']}"},
                               json={"status": "revoked", "current_password": "owner-password-old-01"})
    assert deactivated.status_code == 200, deactivated.text
    with gateway.db() as conn:
        statuses = [r[0] for r in conn.execute("SELECT status FROM owner_recovery_keys WHERE owner_user_id=? ORDER BY generation", (second_owner_id,))]
    assert statuses == ["consumed", "consumed"]


def test_recovery_consumption_and_session_invalidation_persist_after_reinitialization(client):
    owner, old_private, _ = create_owner(client)
    ts = int(time.time())
    nonce = "persist-before-recovery-01"
    login = client.post("/api/v1/auth/login", json={
        "username": "owner-a2", "password": "owner-password-old-01", "device_id": owner["device_id"],
        "timestamp": ts, "nonce": nonce,
        "signature": signature(old_private, f"LOGIN\nowner-a2\n{owner['device_id']}\n{ts}\n{nonce}".encode()),
    })
    assert login.status_code == 200
    old_token = login.json()["access_token"]
    result, _, _ = do_recovery(owner)
    gateway.initialize()
    with gateway.db() as conn:
        key_states = [(r[0], r[1]) for r in conn.execute("SELECT generation,status FROM owner_recovery_keys WHERE owner_user_id=? ORDER BY generation", (owner["user_id"],))]
        session = conn.execute("SELECT revoked_at FROM sessions WHERE token_sha256=?", (gateway.token_hash(old_token),)).fetchone()
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert key_states == [(1, "consumed"), (2, "active")]
    assert session["revoked_at"] is not None
    assert result["recovery_key"]
    assert client.get("/api/v1/status", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401


def test_emergency_interruption_before_commit_rolls_back_and_keeps_backup(client, monkeypatch):
    owner, _, _ = create_owner(client)
    original_insert = recovery._insert_new_device
    def interrupted(*args, **kwargs):
        raise RuntimeError("simulated interruption before commit")
    monkeypatch.setattr(recovery, "_insert_new_device", interrupted)
    private, public = keypair()
    challenge = secrets.token_hex(32)
    proof = signature(private, recovery.device_proof_message("emergency", owner["user_id"], challenge))
    with pytest.raises(recovery.RecoveryError, match="emergency_recovery_transaction_failed_backup_preserved"):
        recovery.emergency_reset(owner["user_id"], "owner-password-emergency-10", public,
                                 "AA:BB:CC:DD:EE:32", challenge, proof)
    monkeypatch.setattr(recovery, "_insert_new_device", original_insert)
    with gateway.db() as conn:
        user = conn.execute("SELECT password_hash,credential_version FROM users WHERE id=?", (owner["user_id"],)).fetchone()
        assert conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM owner_recovery_keys WHERE owner_user_id=? AND status='active'", (owner["user_id"],)).fetchone()[0] == 1
    assert user["credential_version"] == 1
    assert gateway.PASSWORDS.verify(user["password_hash"], "owner-password-old-01")
    assert list((Path(gateway.DB_PATH).parent / "backup").rglob("gateway-pre-emergency.db"))


def test_service_must_be_stopped_before_cli_recovery(monkeypatch):
    from types import SimpleNamespace
    from solarminer_gateway import cli
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/systemctl")
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="active\n", stderr=""))
    with pytest.raises(recovery.RecoveryError, match="stop_solarminer_gateway_service"):
        cli._require_service_stopped()


def test_recovery_secrets_do_not_appear_in_audit_or_application_logs(client, caplog):
    owner, _, _ = create_owner(client)
    new_password = "owner-password-secret-check-11"
    result, _, _ = do_recovery(owner, password=new_password, mac="AA:BB:CC:DD:EE:33")
    assert owner["recovery_key"] not in caplog.text
    assert new_password not in caplog.text
    assert result["recovery_key"] not in caplog.text
    with gateway.db() as conn:
        audit_text = " ".join(row[0] for row in conn.execute("SELECT details_json FROM audit").fetchall())
        verifier_rows = conn.execute("SELECT verifier_sha256 FROM owner_recovery_keys WHERE owner_user_id=?", (owner["user_id"],)).fetchall()
    assert owner["recovery_key"] not in audit_text
    assert new_password not in audit_text
    assert result["recovery_key"] not in audit_text
    assert all(len(row[0]) == 64 for row in verifier_rows)


def test_recovery_schema_migration_is_additive_and_versioned(client):
    owner, _, _ = create_owner(client)
    with gateway.db() as conn:
        versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert conn.execute("SELECT username FROM users WHERE id=?", (owner["user_id"],)).fetchone()[0] == "owner-a2"
    assert versions == [1, 2, 3, 4, 5, 6]
    assert "owner_recovery_keys" in tables


def test_precheck_recovery_key_fails_fast_but_transaction_still_rechecks(client):
    owner, _, _ = create_owner(client)
    with pytest.raises(recovery.RecoveryError, match="invalid_or_consumed_recovery_key"):
        recovery.precheck_recovery_key(owner["user_id"], "SMR1-INVALID-TEST-KEY")
    assert recovery.precheck_recovery_key(owner["user_id"], owner["recovery_key"]) is None


def test_database_enforces_at_most_one_active_recovery_key_per_owner(client):
    owner, _, _ = create_owner(client)
    with gateway.db() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO owner_recovery_keys(id,owner_user_id,verifier_sha256,generation,status,created_at) VALUES(?,?,?,?, 'active',?)",
                         ("duplicate-active-key", owner["user_id"], recovery.recovery_verifier(os.urandom(32)), 2, gateway.utcnow()))


def test_recovery_globally_revokes_lost_device_shared_with_another_account(client):
    owner, old_private, _ = create_owner(client)
    ts = int(time.time())
    nonce = "owner-create-shared-viewer"
    owner_login = client.post("/api/v1/auth/login", json={
        "username": "owner-a2", "password": "owner-password-old-01", "device_id": owner["device_id"],
        "timestamp": ts, "nonce": nonce,
        "signature": signature(old_private, f"LOGIN\nowner-a2\n{owner['device_id']}\n{ts}\n{nonce}".encode()),
    })
    assert owner_login.status_code == 200
    create_viewer = client.post("/api/v1/users", headers={"Authorization": f"Bearer {owner_login.json()['access_token']}"},
                                json={"username": "shared-viewer", "password": "viewer-password-shared-01",
                                      "role": "viewer", "device_id": owner["device_id"]})
    assert create_viewer.status_code == 201, create_viewer.text
    viewer_ts = int(time.time())
    viewer_nonce = "shared-viewer-login-before-recovery"
    viewer_login = client.post("/api/v1/auth/login", json={
        "username": "shared-viewer", "password": "viewer-password-shared-01", "device_id": owner["device_id"],
        "timestamp": viewer_ts, "nonce": viewer_nonce,
        "signature": signature(old_private, f"LOGIN\nshared-viewer\n{owner['device_id']}\n{viewer_ts}\n{viewer_nonce}".encode()),
    })
    assert viewer_login.status_code == 200
    viewer_token = viewer_login.json()["access_token"]
    do_recovery(owner)
    with gateway.db() as conn:
        device = conn.execute("SELECT status FROM devices WHERE id=?", (owner["device_id"],)).fetchone()[0]
        association = conn.execute("SELECT status FROM user_devices WHERE user_id=? AND device_id=?",
                                   (create_viewer.json()["id"], owner["device_id"])).fetchone()[0]
        session = conn.execute("SELECT revoked_at FROM sessions WHERE token_sha256=?", (gateway.token_hash(viewer_token),)).fetchone()[0]
    assert device == "revoked" and association == "revoked" and session is not None
    assert client.get("/api/v1/status", headers={"Authorization": f"Bearer {viewer_token}"}).status_code == 401
