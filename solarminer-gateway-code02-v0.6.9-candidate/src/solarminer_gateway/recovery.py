"""Local owner-recovery primitives for SolarMiner Gateway A2.

Recovery is deliberately not exposed through HTTP. Commands are expected to be
run locally while the service is stopped; the CLI enforces OS-root privileges
and checks systemd state before calling these functions.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from argon2.exceptions import InvalidHashError, VerifyMismatchError, VerificationError
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import app as gateway

RECOVERY_DOMAIN = b"SolarMiner Gateway owner recovery key v1\x00"
DEVICE_PROOF_PREFIX = "SOLARMINER-GATEWAY-DEVICE-PROOF-V1"
MIN_PASSWORD_LENGTH = 12


class RecoveryError(ValueError):
    """Safe, user-facing recovery failure without secret material."""


def generate_recovery_key() -> tuple[str, bytes]:
    raw = os.urandom(32)
    encoded = base64.b32encode(raw).decode("ascii").rstrip("=")
    grouped = "-".join(encoded[i:i + 4] for i in range(0, len(encoded), 4))
    return f"SMR1-{grouped}", raw


def decode_recovery_key(value: str) -> bytes:
    if not isinstance(value, str):
        raise RecoveryError("invalid_recovery_key")
    normalized = "".join(ch for ch in value.upper() if ch not in "- \t\r\n")
    if not normalized.startswith("SMR1"):
        raise RecoveryError("invalid_recovery_key")
    normalized = normalized[4:]
    if not normalized or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for ch in normalized):
        raise RecoveryError("invalid_recovery_key")
    try:
        raw = base64.b32decode(normalized + "=" * ((8 - len(normalized) % 8) % 8), casefold=False)
    except (ValueError, base64.binascii.Error) as exc:
        raise RecoveryError("invalid_recovery_key") from exc
    if len(raw) != 32:
        raise RecoveryError("invalid_recovery_key")
    return raw


def recovery_verifier(raw: bytes) -> str:
    if not isinstance(raw, bytes) or len(raw) != 32:
        raise ValueError("recovery key must be exactly 32 random bytes")
    # The key has 256 bits of cryptographic entropy, so a domain-separated
    # SHA-256 verifier is appropriate; a slow password KDF is not needed.
    return hashlib.sha256(RECOVERY_DOMAIN + raw).hexdigest()


def _key_verifies(value: str, verifier: str) -> bool:
    try:
        raw = decode_recovery_key(value)
    except RecoveryError:
        return False
    return hmac.compare_digest(recovery_verifier(raw), verifier)


def lookup_active_owner(username: str) -> dict[str, str]:
    with gateway.db() as conn:
        row = conn.execute("SELECT id,username,role,status FROM users WHERE username=?", (username,)).fetchone()
        if not row or row["role"] != "owner" or row["status"] != "active":
            raise RecoveryError("active_owner_not_found")
        return {"id": row["id"], "username": row["username"]}


def precheck_recovery_key(owner_id: str, recovery_key: str) -> None:
    """Interactive preflight only; recover_owner revalidates under BEGIN IMMEDIATE."""
    with gateway.db() as conn:
        owner = conn.execute("SELECT role,status FROM users WHERE id=?", (owner_id,)).fetchone()
        row = conn.execute("SELECT verifier_sha256 FROM owner_recovery_keys WHERE owner_user_id=? AND status='active'",
                           (owner_id,)).fetchone()
    if not owner or owner["role"] != "owner" or owner["status"] != "active":
        _record_failed_attempt("owner.recovery", owner_id, "active_owner_required")
        raise RecoveryError("active_owner_required")
    if not row or not _key_verifies(recovery_key, row["verifier_sha256"]):
        _record_failed_attempt("owner.recovery", owner_id, "invalid_or_consumed_recovery_key")
        raise RecoveryError("invalid_or_consumed_recovery_key")


def lookup_active_device(owner_id: str, device_id: str) -> dict[str, str]:
    with gateway.db() as conn:
        row = conn.execute(
            "SELECT d.id,d.public_key_pem FROM devices d JOIN user_devices ud ON ud.device_id=d.id "
            "WHERE ud.user_id=? AND ud.device_id=? AND ud.status='active' AND d.status='active'",
            (owner_id, device_id),
        ).fetchone()
        if not row:
            raise RecoveryError("active_device_not_found")
        return {"id": row["id"], "public_key_pem": row["public_key_pem"]}


def device_proof_message(purpose: str, owner_id: str, challenge: str, device_id: str | None = None) -> bytes:
    if purpose not in {"recovery", "setup", "emergency"}:
        raise ValueError("unsupported proof purpose")
    fields = [DEVICE_PROOF_PREFIX, purpose, owner_id]
    if device_id is not None:
        fields.append(device_id)
    fields.append(challenge)
    return "\n".join(fields).encode("utf-8")


def verify_device_proof(public_key_pem: str, message: bytes, signature_hex: str) -> None:
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
        if not isinstance(key, Ed25519PublicKey):
            raise RecoveryError("device_key_must_be_ed25519")
        signature = bytes.fromhex(signature_hex)
        if len(signature) != 64:
            raise RecoveryError("invalid_device_proof")
        key.verify(signature, message)
    except RecoveryError:
        raise
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise RecoveryError("invalid_device_proof") from exc


def _record_audit(action: str, target: str | None, outcome: str, details: dict[str, Any] | None = None,
                  actor_user_id: str | None = None) -> None:
    with gateway.db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        gateway.audit(conn, actor_user_id, action, target, outcome, details or {})
        conn.commit()


def _record_failed_attempt(action: str, owner_id: str | None, reason: str) -> None:
    try:
        _record_audit(action, owner_id, "failed", {"reason": reason})
    except sqlite3.Error:
        gateway.LOG.warning("%s failed; database audit record unavailable", action)


def _normalized_device(public_key_pem: str, mac: str) -> tuple[str, str, str]:
    try:
        normalized_mac = gateway.normalize_mac(mac)
    except Exception as exc:
        raise RecoveryError("invalid_device_mac_metadata") from exc
    try:
        key = gateway.load_public_key(public_key_pem)
    except Exception as exc:
        raise RecoveryError("invalid_ed25519_public_key") from exc
    der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return public_key_pem, hashlib.sha256(der).hexdigest(), normalized_mac


def _insert_new_device(conn: sqlite3.Connection, owner_id: str, public_key_pem: str, public_key_hash: str,
                       mac: str) -> str:
    if conn.execute("SELECT 1 FROM devices WHERE public_key_sha256=?", (public_key_hash,)).fetchone():
        raise RecoveryError("device_key_already_registered_use_a_new_key")
    device_id = str(uuid.uuid4())
    now = gateway.utcnow()
    old_device_ids = [row[0] for row in conn.execute(
        "SELECT device_id FROM user_devices WHERE user_id=? AND status='active'", (owner_id,)
    ).fetchall()]
    if old_device_ids:
        placeholders = ",".join("?" for _ in old_device_ids)
        # These devices are treated as lost/compromised during full owner recovery.
        # Revoke them globally, including any other account associations and sessions,
        # so a shared lost device cannot continue authenticating as another user.
        conn.execute(
            f"UPDATE sessions SET revoked_at=? WHERE device_id IN ({placeholders}) AND revoked_at IS NULL",
            (int(time.time()), *old_device_ids),
        )
        conn.execute(f"UPDATE devices SET status='revoked' WHERE id IN ({placeholders})", tuple(old_device_ids))
        conn.execute(f"UPDATE user_devices SET status='revoked' WHERE device_id IN ({placeholders})", tuple(old_device_ids))
    conn.execute(
        "INSERT INTO devices(id,public_key_pem,public_key_sha256,mac_declared,mac_status,status,created_at) "
        "VALUES(?,?,?,?, 'declared','active',?)",
        (device_id, public_key_pem, public_key_hash, mac, now),
    )
    conn.execute("INSERT INTO user_devices(user_id,device_id,status,created_at) VALUES(?,?,'active',?)",
                 (owner_id, device_id, now))
    return device_id


def _rotate_recovery_key(conn: sqlite3.Connection, owner_id: str, raw: bytes, reason: str) -> int:
    now = gateway.utcnow()
    conn.execute("UPDATE owner_recovery_keys SET status='consumed',consumed_at=? WHERE owner_user_id=? AND status='active'",
                 (now, owner_id))
    generation = conn.execute("SELECT COALESCE(MAX(generation),0)+1 FROM owner_recovery_keys WHERE owner_user_id=?",
                              (owner_id,)).fetchone()[0]
    conn.execute(
        "INSERT INTO owner_recovery_keys(id,owner_user_id,verifier_sha256,generation,status,created_at,consumed_at) "
        "VALUES(?,?,?,?,'active',?,NULL)",
        (str(uuid.uuid4()), owner_id, recovery_verifier(raw), generation, now),
    )
    gateway.audit(conn, owner_id, "owner.recovery_key_issued", owner_id, "success",
                  {"generation": generation, "source": reason})
    return int(generation)


def setup_recovery_key(owner_id: str, current_password: str, device_id: str,
                       challenge: str, signature_hex: str) -> str:
    """Provision/rotate a recovery key for an owner who can still authenticate."""
    _record_audit("owner.recovery_setup_started", owner_id, "attempted")
    replacement, raw = generate_recovery_key()
    try:
        with gateway.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            owner = conn.execute("SELECT * FROM users WHERE id=?", (owner_id,)).fetchone()
            if not owner or owner["role"] != "owner" or owner["status"] != "active":
                gateway.audit(conn, owner_id, "owner.recovery_setup", owner_id, "denied", {"reason": "active_owner_required"})
                conn.commit()
                raise RecoveryError("active_owner_required")
            try:
                gateway.PASSWORDS.verify(owner["password_hash"], current_password)
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                gateway.audit(conn, owner_id, "owner.recovery_setup", owner_id, "denied", {"reason": "reauthentication_failed"})
                conn.commit()
                raise RecoveryError("reauthentication_failed")
            device = conn.execute(
                "SELECT d.public_key_pem FROM devices d JOIN user_devices ud ON ud.device_id=d.id "
                "WHERE ud.user_id=? AND ud.device_id=? AND ud.status='active' AND d.status='active'",
                (owner_id, device_id),
            ).fetchone()
            if not device:
                gateway.audit(conn, owner_id, "owner.recovery_setup", owner_id, "denied", {"reason": "active_device_required"})
                conn.commit()
                raise RecoveryError("active_device_required")
            try:
                verify_device_proof(device["public_key_pem"],
                                    device_proof_message("setup", owner_id, challenge, device_id), signature_hex)
            except RecoveryError:
                gateway.audit(conn, owner_id, "owner.recovery_setup", owner_id, "denied", {"reason": "invalid_device_proof"})
                conn.commit()
                raise
            generation = _rotate_recovery_key(conn, owner_id, raw, "local_setup_or_rotation")
            gateway.audit(conn, owner_id, "owner.recovery_setup", owner_id, "success", {"generation": generation})
            conn.commit()
    except Exception:
        # gateway.db() closes the connection on context exit; SQLite rolls back
        # any still-open transaction when the connection is closed.
        _restore_db_sidecar_ownership()
        raise
    _restore_db_sidecar_ownership()
    return replacement


def recover_owner(owner_id: str, recovery_key: str, new_password: str, new_device_public_key_pem: str,
                  mac: str, challenge: str, signature_hex: str) -> dict[str, str]:
    """Consume one recovery key, rotate it, replace owner device and invalidate sessions atomically."""
    if not isinstance(new_password, str) or not MIN_PASSWORD_LENGTH <= len(new_password) <= 1024:
        raise RecoveryError("new_password_must_be_12_to_1024_characters")
    public_key_pem, public_key_hash, normalized_mac = _normalized_device(new_device_public_key_pem, mac)
    try:
        verify_device_proof(public_key_pem, device_proof_message("recovery", owner_id, challenge), signature_hex)
    except RecoveryError:
        _record_failed_attempt("owner.recovery", owner_id, "invalid_device_proof")
        raise

    _record_audit("owner.recovery_started", owner_id, "attempted")
    replacement_key, replacement_raw = generate_recovery_key()
    failure: RecoveryError | None = None
    try:
        with gateway.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            owner = conn.execute("SELECT * FROM users WHERE id=?", (owner_id,)).fetchone()
            active_key = conn.execute(
                "SELECT id,verifier_sha256,generation FROM owner_recovery_keys "
                "WHERE owner_user_id=? AND status='active'", (owner_id,),
            ).fetchone()
            if not owner or owner["role"] != "owner" or owner["status"] != "active":
                gateway.audit(conn, owner_id, "owner.recovery", owner_id, "denied", {"reason": "active_owner_required"})
                conn.commit()
                failure = RecoveryError("active_owner_required")
            elif not active_key or not _key_verifies(recovery_key, active_key["verifier_sha256"]):
                gateway.audit(conn, owner_id, "owner.recovery", owner_id, "denied", {"reason": "invalid_or_consumed_recovery_key"})
                conn.commit()
                failure = RecoveryError("invalid_or_consumed_recovery_key")
            else:
                password_hash = gateway.PASSWORDS.hash(new_password)
                now_epoch = int(time.time())
                conn.execute("UPDATE users SET password_hash=?,credential_version=credential_version+1 WHERE id=?",
                             (password_hash, owner_id))
                conn.execute("UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now_epoch, owner_id))
                device_id = _insert_new_device(conn, owner_id, public_key_pem, public_key_hash, normalized_mac)
                conn.execute("UPDATE owner_recovery_keys SET status='consumed',consumed_at=? WHERE id=? AND status='active'",
                             (gateway.utcnow(), active_key["id"]))
                if conn.execute("SELECT changes()").fetchone()[0] != 1:
                    raise RecoveryError("recovery_key_consumption_conflict")
                generation = _rotate_recovery_key(conn, owner_id, replacement_raw, "owner_recovery")
                gateway.audit(conn, owner_id, "owner.recovery", owner_id, "success",
                              {"device_id": device_id, "credential_version_incremented": True,
                               "sessions_invalidated": True, "generation": generation})
                conn.commit()
                result = {"owner_id": owner_id, "device_id": device_id, "recovery_key": replacement_key,
                          "recovery_key_display": "one_time_only_store_offline"}
    except Exception as exc:
        # The db context has closed the connection, which rolls back any open transaction.
        _record_failed_attempt("owner.recovery", owner_id, "transaction_failed")
        _restore_db_sidecar_ownership()
        if isinstance(exc, RecoveryError):
            raise
        raise RecoveryError("recovery_transaction_failed") from exc
    _restore_db_sidecar_ownership()
    if failure:
        raise failure
    return result


def _restore_db_sidecar_ownership() -> None:
    """If root performed local SQLite writes, keep WAL sidecars writable by the service account."""
    path = Path(gateway.DB_PATH)
    try:
        st = path.stat()
    except OSError:
        return
    if os.geteuid() != 0:
        return
    for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        try:
            os.chown(candidate, st.st_uid, st.st_gid)
        except FileNotFoundError:
            pass
        except OSError:
            gateway.LOG.error("Could not restore database file ownership after local recovery operation")


def create_consistent_backup() -> Path:
    """Create and verify a protected SQLite backup using SQLite's online backup API."""
    source_path = Path(gateway.DB_PATH)
    if not source_path.is_file():
        raise RecoveryError("database_not_found_backup_not_created")
    backup_root = source_path.parent / "backup"
    if backup_root.is_symlink():
        raise RecoveryError("backup_directory_must_not_be_a_symlink")
    backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    run_dir = backup_root / f"emergency-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(mode=0o700)
    if os.geteuid() == 0:
        os.chown(run_dir, 0, 0)
    os.chmod(run_dir, 0o700)
    backup_path = run_dir / "gateway-pre-emergency.db"
    fd = os.open(backup_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    os.chmod(backup_path, 0o600)
    source = sqlite3.connect(source_path, timeout=10)
    target = sqlite3.connect(backup_path)
    try:
        source.execute("PRAGMA busy_timeout=10000")
        source.backup(target)
        target.commit()
        check = target.execute("PRAGMA integrity_check").fetchone()
        if not check or check[0] != "ok":
            raise RecoveryError("backup_integrity_check_failed")
    finally:
        target.close()
        source.close()
    os.chmod(backup_path, 0o600)
    if os.geteuid() == 0:
        os.chown(backup_path, 0, 0)
    with backup_path.open("rb") as f:
        os.fsync(f.fileno())
    dir_fd = os.open(run_dir, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    return backup_path


def emergency_reset(owner_id: str, new_password: str, new_device_public_key_pem: str,
                    mac: str, challenge: str, signature_hex: str) -> dict[str, str]:
    """OS-admin recovery path: preserve data, back up DB, replace owner credentials/device."""
    if not isinstance(new_password, str) or not MIN_PASSWORD_LENGTH <= len(new_password) <= 1024:
        raise RecoveryError("new_password_must_be_12_to_1024_characters")
    public_key_pem, public_key_hash, normalized_mac = _normalized_device(new_device_public_key_pem, mac)
    try:
        verify_device_proof(public_key_pem, device_proof_message("emergency", owner_id, challenge), signature_hex)
    except RecoveryError:
        _record_failed_attempt("owner.emergency_recovery", owner_id, "invalid_device_proof")
        raise

    backup_path = create_consistent_backup()
    _record_audit("owner.emergency_recovery_started", owner_id, "attempted",
                  {"backup_path": str(backup_path.relative_to(Path(gateway.DB_PATH).parent))})
    replacement_key, replacement_raw = generate_recovery_key()
    try:
        with gateway.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            owner = conn.execute("SELECT * FROM users WHERE id=?", (owner_id,)).fetchone()
            if not owner or owner["role"] != "owner" or owner["status"] != "active":
                gateway.audit(conn, owner_id, "owner.emergency_recovery", owner_id, "denied", {"reason": "active_owner_required"})
                conn.commit()
                raise RecoveryError("active_owner_required")
            password_hash = gateway.PASSWORDS.hash(new_password)
            conn.execute("UPDATE users SET password_hash=?,credential_version=credential_version+1 WHERE id=?",
                         (password_hash, owner_id))
            conn.execute("UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (int(time.time()), owner_id))
            device_id = _insert_new_device(conn, owner_id, public_key_pem, public_key_hash, normalized_mac)
            generation = _rotate_recovery_key(conn, owner_id, replacement_raw, "emergency_recovery")
            gateway.audit(conn, owner_id, "owner.emergency_recovery", owner_id, "success",
                          {"device_id": device_id, "backup_path": str(backup_path.relative_to(Path(gateway.DB_PATH).parent)),
                           "credential_version_incremented": True, "sessions_invalidated": True,
                           "generation": generation})
            conn.commit()
    except Exception as exc:
        # The db context has closed the connection, which rolls back any open transaction.
        _record_failed_attempt("owner.emergency_recovery", owner_id, "transaction_failed")
        _restore_db_sidecar_ownership()
        if isinstance(exc, RecoveryError):
            raise
        raise RecoveryError("emergency_recovery_transaction_failed_backup_preserved") from exc
    _restore_db_sidecar_ownership()
    return {"owner_id": owner_id, "device_id": device_id, "recovery_key": replacement_key,
            "backup_path": str(backup_path), "recovery_key_display": "one_time_only_store_offline"}
