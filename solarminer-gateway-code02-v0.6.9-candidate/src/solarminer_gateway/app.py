from __future__ import annotations

import hashlib
import math
import asyncio
import json
import logging
import io
import os
import re
import shutil
import secrets
import subprocess
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

# argon2-cffi renamed InvalidHash to InvalidHashError in newer releases.
# Debian stable packages may still expose the older class name.
try:
    from argon2.exceptions import InvalidHashError
except ImportError:
    from argon2.exceptions import InvalidHash as InvalidHashError
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from . import connectors as connector_manager
from . import energy_registry
from . import energy_engine
from . import site_profile
from . import integrations as hardware_integrations
from . import update_helper_client
from . import updates as update_manager
from .error_reporting import install_error_queue_handler

VERSION = "0.6.0"  # Public API compatibility contract; package version is tracked separately.
PACKAGE_VERSION = "0.6.70"
DATA_DIR = Path(os.environ.get("SOLARMINER_DATA_DIR", "/var/lib/solarminer"))
DB_PATH = Path(os.environ.get("SOLARMINER_DB_PATH", str(DATA_DIR / "gateway.db")))
BOOTSTRAP_PATH = Path(os.environ.get("SOLARMINER_BOOTSTRAP_PATH", str(DATA_DIR / "bootstrap.token")))
INSTANCE_MARKER = Path(os.environ.get("SOLARMINER_INSTANCE_MARKER", str(DATA_DIR / "initialized.marker")))
BOOTSTRAP_TTL = 15 * 60
SESSION_TTL = 8 * 60 * 60
PRESENCE_TTL_SECONDS = 120
PRESENCE_MIN_INTERVAL_SECONDS = 5
NONCE_WINDOW = 5 * 60
MAC_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)
LOG = logging.getLogger("solarminer.gateway")
logging.basicConfig(level=os.environ.get("SOLARMINER_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
install_error_queue_handler()

# The live Deye sample is refreshed every 30 seconds. Only one sample per
# minute is written to SQLite; the most recent half-minute sample stays in
# memory for the authenticated energy API and is lost safely on restart.
_energy_sample_lock = threading.Lock()
_latest_deye_sample: dict[str, Any] | None = None
_dispatch_lock = threading.Lock()
_dispatch_last_sent: dict[str, tuple[str, float]] = {}

ROLES = {"owner", "admin", "operator", "viewer"}
PERMISSIONS = {
    "owner": {"read", "operate", "manage_users", "manage_devices", "manage_roles", "manage_gateway", "recover"},
    "admin": {"read", "operate", "manage_users", "manage_devices"},
    "operator": {"read", "operate"},
    "viewer": {"read"},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS system_state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users(
 id TEXT PRIMARY KEY, account_id TEXT NOT NULL, username TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('owner','admin','operator','viewer')),
 status TEXT NOT NULL CHECK(status IN ('active','revoked')), created_at TEXT NOT NULL,
 credential_version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS devices(
 id TEXT PRIMARY KEY, public_key_pem TEXT NOT NULL, public_key_sha256 TEXT NOT NULL UNIQUE,
 mac_declared TEXT NOT NULL, mac_status TEXT NOT NULL CHECK(mac_status IN ('declared','verified')),
 status TEXT NOT NULL CHECK(status IN ('active','revoked')), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_devices(
 user_id TEXT NOT NULL REFERENCES users(id), device_id TEXT NOT NULL REFERENCES devices(id),
 status TEXT NOT NULL CHECK(status IN ('active','revoked')), created_at TEXT NOT NULL,
 PRIMARY KEY(user_id, device_id)
);
CREATE TABLE IF NOT EXISTS bootstrap(
 id INTEGER PRIMARY KEY CHECK(id=1), token_sha256 TEXT NOT NULL, expires_at INTEGER NOT NULL,
 consumed_at INTEGER, state TEXT NOT NULL, setup_password_hash TEXT
);
CREATE TABLE IF NOT EXISTS bootstrap_attempts(ip_hash TEXT NOT NULL, attempted_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_bootstrap_attempts_ip_time ON bootstrap_attempts(ip_hash,attempted_at);
CREATE TABLE IF NOT EXISTS password_device_attempts(ip_hash TEXT NOT NULL, account_hash TEXT NOT NULL, attempted_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_password_device_attempts_ip_time ON password_device_attempts(ip_hash,attempted_at);
CREATE TABLE IF NOT EXISTS sessions(
 token_sha256 TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), device_id TEXT NOT NULL REFERENCES devices(id),
 created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, revoked_at INTEGER, credential_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS nonces(
 device_id TEXT NOT NULL REFERENCES devices(id), nonce TEXT NOT NULL, timestamp INTEGER NOT NULL,
 PRIMARY KEY(device_id, nonce)
);
CREATE TABLE IF NOT EXISTS audit(
 id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT NOT NULL, actor_user_id TEXT,
 action TEXT NOT NULL, target TEXT, outcome TEXT NOT NULL, details_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS device_events(
 id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT NOT NULL, device_id TEXT NOT NULL,
 device_name TEXT NOT NULL, event_type TEXT NOT NULL, channel_code TEXT NOT NULL DEFAULT '',
 old_value_json TEXT, new_value_json TEXT, source TEXT NOT NULL DEFAULT 'TUYA_LAN'
);
CREATE TABLE IF NOT EXISTS device_observations(
 device_id TEXT NOT NULL, observation_key TEXT NOT NULL, value_json TEXT NOT NULL,
 observed_at TEXT NOT NULL, PRIMARY KEY(device_id, observation_key)
);
CREATE INDEX IF NOT EXISTS idx_device_events_device_time ON device_events(device_id, id DESC);
CREATE TABLE IF NOT EXISTS owner_recovery_keys(
 id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL REFERENCES users(id),
 verifier_sha256 TEXT NOT NULL, generation INTEGER NOT NULL CHECK(generation >= 1),
 status TEXT NOT NULL CHECK(status IN ('active','consumed')),
 created_at TEXT NOT NULL, consumed_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_owner_recovery_one_active
 ON owner_recovery_keys(owner_user_id) WHERE status='active';
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_nonces_timestamp ON nonces(timestamp);
CREATE INDEX IF NOT EXISTS idx_user_devices_device ON user_devices(device_id);
CREATE TABLE IF NOT EXISTS device_pairing_codes(
 token_sha256 TEXT PRIMARY KEY, created_by_user_id TEXT NOT NULL REFERENCES users(id),
 target_user_id TEXT NOT NULL REFERENCES users(id), created_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL, used_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_pairing_codes_expiry ON device_pairing_codes(expires_at,used_at);
CREATE TABLE IF NOT EXISTS invites(
 id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, owner_id TEXT NOT NULL REFERENCES users(id),
 role TEXT NOT NULL CHECK(role IN ('viewer','operator')), label TEXT NOT NULL,
 created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, used_at INTEGER,
 revoked_at INTEGER, revoked_by TEXT REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_invites_owner_created ON invites(owner_id,created_at DESC);
CREATE TABLE IF NOT EXISTS invite_nonces(
 token_hash TEXT NOT NULL, nonce TEXT NOT NULL, timestamp INTEGER NOT NULL,
 PRIMARY KEY(token_hash,nonce)
);
CREATE INDEX IF NOT EXISTS idx_invite_nonces_timestamp ON invite_nonces(timestamp);
CREATE TABLE IF NOT EXISTS invite_attempts(
 ip_hash TEXT NOT NULL, attempted_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_invite_attempts_ip_time ON invite_attempts(ip_hash,attempted_at);
CREATE TABLE IF NOT EXISTS update_operations(
 id TEXT PRIMARY KEY, state TEXT NOT NULL, installed_version TEXT NOT NULL, target_version TEXT,
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, details_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_update_operations_updated ON update_operations(updated_at DESC);
"""

# Additive presence migration. User/device identity is derived exclusively from
# the authenticated session; the client cannot name another user or device.
PRESENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_presence(
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
 last_seen INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,
 connection_method TEXT NOT NULL DEFAULT 'unknown' CHECK(connection_method IN ('unknown')),
 PRIMARY KEY(user_id, device_id)
);
CREATE INDEX IF NOT EXISTS idx_user_presence_expiry ON user_presence(expires_at);
"""

# Additive A1 migration. The trigger is the final integrity boundary even if
# a future API path forgets to check the active-owner invariant.
A1_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS protect_last_active_owner_update
BEFORE UPDATE OF role, status ON users
WHEN OLD.role='owner' AND OLD.status='active'
 AND (NEW.role <> 'owner' OR NEW.status <> 'active')
 AND (SELECT COUNT(*) FROM users WHERE role='owner' AND status='active') <= 1
BEGIN
 SELECT RAISE(ABORT, 'last_active_owner_protected');
END;

CREATE TRIGGER IF NOT EXISTS protect_last_active_owner_delete
BEFORE DELETE ON users
WHEN OLD.role='owner' AND OLD.status='active'
 AND (SELECT COUNT(*) FROM users WHERE role='owner' AND status='active') <= 1
BEGIN
 SELECT RAISE(ABORT, 'last_active_owner_protected');
END;

CREATE TRIGGER IF NOT EXISTS protect_last_active_owner_replace
BEFORE INSERT ON users
WHEN (SELECT COUNT(*) FROM users WHERE role='owner' AND status='active') <= 1
 AND EXISTS (SELECT 1 FROM users WHERE (id=NEW.id OR username=NEW.username)
             AND role='owner' AND status='active')
 AND (NEW.role <> 'owner' OR NEW.status <> 'active')
BEGIN
 SELECT RAISE(ABORT, 'last_active_owner_protected');
END;

CREATE TRIGGER IF NOT EXISTS invalidate_sessions_on_role_change
AFTER UPDATE OF role ON users
WHEN OLD.role <> NEW.role
BEGIN
 UPDATE users SET credential_version=credential_version+1 WHERE id=NEW.id;
END;
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def request_source_ip(request: Request) -> str:
    # The app listens only on loopback behind the packaged Nginx proxy. Nginx
    # overwrites X-Real-IP, so this is the actual client address for rate limits.
    forwarded = request.headers.get("x-real-ip", "").strip()
    if forwarded and len(forwarded) <= 64:
        return forwarded
    return request.client.host if request.client else "unknown"


def normalize_mac(value: str) -> str:
    if not isinstance(value, str) or not MAC_RE.fullmatch(value):
        raise HTTPException(422, "invalid_mac")
    return value.upper()


def local_arp_entries(path: Path = Path("/proc/net/arp")) -> dict[str, str]:
    """Return private LAN IPs indexed by MAC from the kernel neighbour cache."""
    entries: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="ascii", errors="ignore").splitlines()[1:]
    except OSError:
        return entries
    for line in lines:
        fields = line.split()
        if len(fields) < 6 or fields[2] != "0x2":
            continue
        try:
            ip = hardware_integrations._private_ip(fields[0])
            mac = normalize_mac(fields[3])
        except (ValueError, HTTPException):
            continue
        entries[mac] = ip
    return entries


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


@contextmanager
def db() -> Any:
    if INSTANCE_MARKER.exists() and not DB_PATH.is_file():
        raise sqlite3.OperationalError("database missing for initialized instance")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA recursive_triggers=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
    finally:
        conn.close()


def audit(conn: sqlite3.Connection, actor: str | None, action: str, target: str | None, outcome: str, details: dict | None = None) -> None:
    conn.execute("INSERT INTO audit(occurred_at,actor_user_id,action,target,outcome,details_json) VALUES(?,?,?,?,?,?)",
                 (utcnow(), actor, action, target, outcome, json.dumps(details or {}, separators=(",", ":"))))


def initialize() -> None:
    ensure_private_dir(DB_PATH.parent)
    if INSTANCE_MARKER.exists():
        if not DB_PATH.is_file():
            try:
                BOOTSTRAP_PATH.unlink(missing_ok=True)
            except OSError:
                LOG.error("Could not remove stale bootstrap token after database loss")
            LOG.critical("Database is missing for an initialized instance; refusing automatic reinitialization")
            return
        try:
            with sqlite3.connect(DB_PATH, timeout=2.0) as check:
                integrity = check.execute("PRAGMA integrity_check").fetchone()
                tables = {r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            required = {"schema_migrations", "system_state", "users", "devices", "user_devices", "bootstrap", "sessions", "nonces", "audit"}
            if not integrity or integrity[0] != "ok" or not required.issubset(tables):
                LOG.critical("Initialized database failed integrity/schema validation; preserving it and refusing automatic repair")
                return
        except sqlite3.Error as exc:
            LOG.critical("Initialized database cannot be validated (%s); preserving it", type(exc).__name__)
            return
    with db() as conn:
        conn.executescript(SCHEMA)
        bootstrap_columns = {row[1] for row in conn.execute("PRAGMA table_info(bootstrap)")}
        if "setup_password_hash" not in bootstrap_columns:
            conn.execute("ALTER TABLE bootstrap ADD COLUMN setup_password_hash TEXT")
        password_attempt_columns = {row[1] for row in conn.execute("PRAGMA table_info(password_device_attempts)")}
        if "account_hash" not in password_attempt_columns:
            conn.execute("ALTER TABLE password_device_attempts ADD COLUMN account_hash TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_password_device_attempts_account_time ON password_device_attempts(account_hash,attempted_at)")
        conn.executescript(PRESENCE_SCHEMA)
        conn.executescript(A1_TRIGGERS)
        connector_manager.ensure_schema(conn)
        energy_registry.ensure_schema(conn)
        connector_manager.recover_incomplete_operations(conn)
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(1,?)", (utcnow(),))
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(2,?)", (utcnow(),))
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(3,?)", (utcnow(),))
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(4,?)", (utcnow(),))
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(5,?)", (utcnow(),))
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(6,?)", (utcnow(),))
        conn.execute("INSERT OR IGNORE INTO system_state(key,value) VALUES('bootstrap_state','UNINITIALIZED')")
        if not INSTANCE_MARKER.exists():
            try:
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                fd = os.open(INSTANCE_MARKER, flags, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as marker:
                    marker.write("solarminer-gateway-v0.6.0-initialized\n")
                    marker.flush()
                    os.fsync(marker.fileno())
                os.chmod(INSTANCE_MARKER, 0o600)
            except OSError:
                LOG.critical("Instance marker could not be created; refusing bootstrap initialization")
                return
        owner = conn.execute("SELECT 1 FROM users WHERE role='owner' AND status='active' LIMIT 1").fetchone()
        if owner:
            conn.execute("UPDATE system_state SET value='OWNER_ACTIVE' WHERE key='bootstrap_state'")
            consumed = conn.execute("SELECT consumed_at FROM bootstrap WHERE id=1").fetchone()
            if consumed and consumed[0] is not None:
                try:
                    BOOTSTRAP_PATH.unlink(missing_ok=True)
                except OSError:
                    LOG.error("Consumed bootstrap token file cleanup failed")
            return
        row = conn.execute("SELECT * FROM bootstrap WHERE id=1").fetchone()
        now = int(time.time())
        if row and row["consumed_at"] is not None:
            conn.execute("UPDATE system_state SET value='RECOVERY_REQUIRED' WHERE key='bootstrap_state'")
            return
        if row and row["setup_password_hash"]:
            conn.execute("UPDATE system_state SET value='BOOTSTRAP_PENDING' WHERE key='bootstrap_state'")
            return
        if row and row["expires_at"] >= now:
            conn.execute("UPDATE system_state SET value='OWNER_SETUP_REQUIRED' WHERE key='bootstrap_state'")
            return
        if row:
            conn.execute("UPDATE bootstrap SET state='expired' WHERE id=1 AND consumed_at IS NULL")
            conn.execute("UPDATE system_state SET value='RECOVERY_REQUIRED' WHERE key='bootstrap_state'")
            try:
                BOOTSTRAP_PATH.unlink(missing_ok=True)
            except OSError:
                LOG.error("Expired bootstrap token file cleanup failed")
            LOG.error("Bootstrap expired; automatic re-issuance is disabled; authorized local recovery is required")
            return
        raw = secrets.token_urlsafe(32)
        expires = now + BOOTSTRAP_TTL
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT OR REPLACE INTO bootstrap(id,token_sha256,expires_at,consumed_at,state) VALUES(1,?,?,NULL,'pending')",
                     (token_hash(raw), expires))
        conn.execute("UPDATE system_state SET value='BOOTSTRAP_PENDING' WHERE key='bootstrap_state'")
        conn.commit()
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(BOOTSTRAP_PATH, flags, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(raw + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.chmod(BOOTSTRAP_PATH, 0o600)
        except OSError:
            # Never expose the secret through logs or HTTP; keep the DB token pending for local recovery.
            LOG.error("Bootstrap token file could not be created; owner setup remains pending")
            with db() as rollback:
                rollback.execute("UPDATE system_state SET value='OWNER_SETUP_REQUIRED' WHERE key='bootstrap_state'")
            return
        LOG.warning("Secure owner bootstrap is pending; token expires in 15 minutes and is available only to the local operator")


def _energy_sample_interval_seconds() -> int:
    try:
        return max(30, min(3600, int(os.environ.get("SOLARMINER_ENERGY_SAMPLE_SECONDS", "30"))))
    except (TypeError, ValueError):
        return 30


async def _energy_sampling_loop() -> None:
    """Read Deye telemetry every 30s; persist a representative sample each minute."""
    global _latest_deye_sample
    interval = _energy_sample_interval_seconds()
    last_persisted_minute: int | None = None
    next_sample_at = asyncio.get_running_loop().time()
    while True:
        try:
            config = hardware_integrations.load_config().get("deye", {})
            if config.get("host") and config.get("enabled", True):
                snapshot = await asyncio.to_thread(hardware_integrations.read_deye, config)
                if isinstance(snapshot, dict) and snapshot.get("connection_state") == "mapped_registers_response":
                    with _energy_sample_lock:
                        _latest_deye_sample = {**snapshot, "sampled_at": datetime.now(timezone.utc).isoformat(timespec="microseconds")}
                    # Keep minute-resolution durable history, while serving
                    # the intervening 30-second reading from memory.
                    minute_bucket = int(time.time() // 60)
                    if minute_bucket != last_persisted_minute:
                        with db() as conn:
                            conn.execute("BEGIN")
                            count = _persist_deye_telemetry(conn, snapshot)
                            conn.execute("DELETE FROM energy_readings WHERE source='DEYE_MODBUS_FC03_CANDIDATE_MAP' AND observed_at < ?",
                                         ((datetime.now(timezone.utc) - timedelta(days=90)).isoformat(timespec="seconds"),))
                            conn.commit()
                        last_persisted_minute = minute_bucket
                        if not count:
                            LOG.warning("Periodic Deye sample returned no mapped readings")
                else:
                    LOG.warning("Periodic Deye sample returned no mapped readings")
            else:
                with _energy_sample_lock:
                    _latest_deye_sample = None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Keep the service alive; diagnostic data contains only safe error type.
            LOG.warning("Periodic energy sample failed (%s)", type(exc).__name__)
        next_sample_at += interval
        delay = next_sample_at - asyncio.get_running_loop().time()
        if delay <= 0:
            # A slow device read must not trigger a burst of catch-up reads.
            next_sample_at = asyncio.get_running_loop().time() + interval
            delay = interval
        await asyncio.sleep(delay)


def _run_automatic_dispatch() -> dict[str, Any]:
    """Execute the Owner-enabled plan only when fresh, commissioned telemetry is available."""
    with db() as conn:
        with _energy_sample_lock:
            sample = dict(_latest_deye_sample) if _latest_deye_sample else None
        summary = energy_engine.build_summary(conn, latest_sample=sample)
        plan = summary["dispatch"]
        config = summary["configuration"]
        if plan.get("state") not in {"PLAN_READY", "WAITING_FOR_BATTERY"}:
            outcome = {"state": plan.get("state", "BLOCKED"), "reason": plan.get("reason"), "actions": []}
            _persist_dispatch_outcome(conn, outcome)
            return outcome
        try:
            integration_config = hardware_integrations.load_config()
            tuya_config = integration_config.get("tuya", {})
            tuya_states = {}
            if any(action.get("control_type") in {"tuya_smart", "tuya_breaker"} for action in plan.get("actions", [])):
                tuya_readings = hardware_integrations.read_tuya(tuya_config)
                _persist_tuya_device_events(conn, tuya_readings)
                tuya_states = {item.get("device_id"): item for item in tuya_readings}
        except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
            outcome = {"state": "BLOCKED_INTEGRATION_READ", "reason": type(exc).__name__, "actions": []}
            _persist_dispatch_outcome(conn, outcome)
            return outcome
        results = []
        result_states: dict[str, str] = {}
        plan_actions = plan.get("actions", [])
        loads_by_id = {item.get("id"): item for item in config.get("loads", [])}
        # On falling surplus, stop the miner before opening its Tuya supply relay.
        plan_actions = sorted(plan_actions, key=lambda action: (
            0 if loads_by_id.get(action.get("load_id"), {}).get("control_type") == "antminer_braiins"
            and int(action.get("target_power_w", 0)) == 0 else 1,
            int(loads_by_id.get(action.get("load_id"), {}).get("priority", 100)),
        ))
        for action in plan_actions:
            load = next((item for item in config.get("loads", []) if item.get("id") == action.get("load_id")), None)
            if not load or not load.get("automatic") or not load.get("enabled"):
                continue
            dependency_id = load.get("requires_load_id")
            if dependency_id and int(action.get("target_power_w", 0)) > 0 and result_states.get(dependency_id) != "ON":
                results.append({"load_id": load["id"], "state": "BLOCKED_RELAY_UNCONFIRMED"})
                result_states[load["id"]] = "BLOCKED_RELAY_UNCONFIRMED"
                continue
            control = load.get("control_type")
            desired = "ON" if action.get("state") == "ON" or (action.get("state") == "TARGET" and action.get("target_power_w", 0) > 0) else "OFF"
            if action.get("state") not in {"ON", "TARGET", "WAITING_FOR_SURPLUS", "BELOW_MINIMUM_SURPLUS", "BLOCKED_RELAY_NOT_READY", "OFF_FOR_BATTERY", "STOP_FOR_BATTERY"}:
                continue
            if control in {"tuya_smart", "tuya_breaker"}:
                device_id, code = load.get("tuya_device_id"), load.get("tuya_switch_code")
                device_state = tuya_states.get(device_id, {})
                values = device_state.get("status", []) if device_state.get("connection_state") == "local_responded" else []
                observed = next((item.get("value") for item in values if isinstance(item, dict) and item.get("code") == code), None)
                if not isinstance(observed, bool):
                    results.append({"load_id": load["id"], "state": "BLOCKED_STATE_UNKNOWN"})
                    result_states[load["id"]] = "BLOCKED_STATE_UNKNOWN"
                    continue
                if observed is (desired == "ON"):
                    results.append({"load_id": load["id"], "state": "ALREADY_AT_TARGET", "target": desired})
                    result_states[load["id"]] = "ON" if observed else "OFF"
                    continue
                with _dispatch_lock:
                    previous = _dispatch_last_sent.get(load["id"])
                dwell_seconds = int(load.get("minimum_on_seconds", 300) if observed else load.get("minimum_off_seconds", 300))
                if previous and time.monotonic() - previous[1] < dwell_seconds:
                    results.append({"load_id": load["id"], "state": "BLOCKED_MINIMUM_DWELL", "target": desired})
                    result_states[load["id"]] = "BLOCKED_MINIMUM_DWELL"
                    continue
                try:
                    result = hardware_integrations.control_tuya_switch(tuya_config, device_id, desired == "ON", code=code)
                    _append_tuya_command_event(conn, device_id, code or "", desired == "ON",
                                               confirmed=bool(result.get("state_confirmed")), automatic=True)
                    outcome = "APPLIED" if result.get("state_confirmed") else "UNCONFIRMED"
                    if result.get("state_confirmed"):
                        with _dispatch_lock:
                            _dispatch_last_sent[load["id"]] = (desired, time.monotonic())
                    results.append({"load_id": load["id"], "state": outcome, "target": desired})
                    result_states[load["id"]] = desired if result.get("state_confirmed") else outcome
                    audit(conn, None, "energy.dispatch.tuya", load["id"], outcome.lower(), {"target": desired, "state_confirmed": bool(result.get("state_confirmed"))})
                except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
                    results.append({"load_id": load["id"], "state": "FAILED", "reason": type(exc).__name__})
                    result_states[load["id"]] = "FAILED"
                    audit(conn, None, "energy.dispatch.tuya", load["id"], "failed", {"reason": type(exc).__name__})
            elif control == "antminer_braiins":
                target = int(action.get("target_power_w", 0))
                target = min(target, int(load.get("maximum_power_w", 2900)))
                target_key = f"antminer:{target}"
                with _dispatch_lock:
                    previous = _dispatch_last_sent.get(load["id"])
                if previous and previous[0] == target_key:
                    results.append({"load_id": load["id"], "state": "UNCHANGED", "target_power_w": target})
                    result_states[load["id"]] = "APPLIED"
                    continue
                if previous:
                    try:
                        previous_target = int(previous[0].split(":", 1)[1])
                    except (IndexError, ValueError):
                        previous_target = 0
                    dwell = int(load.get("minimum_on_seconds", 300) if previous_target > 0 else load.get("minimum_off_seconds", 300))
                    if time.monotonic() - previous[1] < dwell:
                        results.append({"load_id": load["id"], "state": "BLOCKED_MINIMUM_DWELL", "target_power_w": target})
                        result_states[load["id"]] = "BLOCKED_MINIMUM_DWELL"
                        continue
                try:
                    miner_config = integration_config.get("antminer", {})
                    if target > 0:
                        result = hardware_integrations.control_antminer(miner_config, "set_power_target", target)
                        hardware_integrations.control_antminer(miner_config, "start")
                        command = "set_power_target_and_start"
                    else:
                        result = hardware_integrations.control_antminer(miner_config, "stop")
                        command = "stop"
                    with _dispatch_lock:
                        _dispatch_last_sent[load["id"]] = (target_key, time.monotonic())
                    results.append({"load_id": load["id"], "state": "APPLIED", "target_power_w": target,
                                    "command_accepted": bool(result.get("command_accepted", True))})
                    result_states[load["id"]] = "APPLIED"
                    audit(conn, None, "energy.dispatch.antminer", load["id"], "success", {"target_power_w": target, "action": command})
                except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
                    results.append({"load_id": load["id"], "state": "FAILED", "reason": type(exc).__name__})
                    result_states[load["id"]] = "FAILED"
                    audit(conn, None, "energy.dispatch.antminer", load["id"], "failed", {"reason": type(exc).__name__})
        outcome = {"state": "COMPLETED", "actions": results}
        _persist_dispatch_outcome(conn, outcome)
        return outcome


def _persist_dispatch_outcome(conn: sqlite3.Connection, outcome: dict[str, Any]) -> None:
    value = {**outcome, "occurred_at": utcnow()}
    conn.execute("INSERT INTO system_state(key,value) VALUES('energy_dispatch_last',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (json.dumps(value, separators=(",", ":")),))


async def _energy_dispatch_loop() -> None:
    """Run automatic dispatch on its configured cadence; defaults are disabled."""
    last_run = 0.0
    while True:
        try:
            with db() as conn:
                automation = energy_engine.get_config(conn).get("automation", {})
            interval = int(automation.get("decision_interval_seconds", 300))
            now = asyncio.get_running_loop().time()
            if automation.get("enabled") and automation.get("commissioned") and automation.get("deye_map_verified") and now - last_run >= interval:
                outcome = await asyncio.to_thread(_run_automatic_dispatch)
                last_run = now
                LOG.info("Energy dispatch cycle state=%s action_count=%d", outcome.get("state", "unknown"), len(outcome.get("actions", [])))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOG.warning("Energy dispatch cycle blocked (%s)", type(exc).__name__)
        await asyncio.sleep(10)


def _collect_tuya_device_events_once() -> int:
    """Poll configured Tuya Wi-Fi devices and save observed transitions locally."""
    config = hardware_integrations.load_config().get("tuya", {})
    devices = [item for item in config.get("devices", [])
               if isinstance(item, dict) and item.get("local_key") and item.get("local_ip")]
    if not devices:
        return 0
    readings = hardware_integrations.read_tuya({**config, "devices": devices})
    with db() as conn:
        recorded = _persist_tuya_device_events(conn, readings)
        conn.commit()
    return recorded


def _tuya_event_poll_interval_seconds() -> int:
    try:
        return max(60, min(3600, int(os.environ.get("SOLARMINER_TUYA_EVENT_POLL_SECONDS", "60"))))
    except (TypeError, ValueError):
        return 60


async def _tuya_device_event_loop() -> None:
    """Continuously observe Tuya LAN state for the per-device event history."""
    interval = _tuya_event_poll_interval_seconds()
    while True:
        try:
            await asyncio.to_thread(_collect_tuya_device_events_once)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOG.warning("Periodic Tuya LAN observation failed (%s)", type(exc).__name__)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _latest_deye_sample
    initialize()
    with _energy_sample_lock:
        _latest_deye_sample = None
    sampler = asyncio.create_task(_energy_sampling_loop(), name="solarminer-energy-sampler")
    dispatcher = asyncio.create_task(_energy_dispatch_loop(), name="solarminer-energy-dispatcher")
    tuya_observer = asyncio.create_task(_tuya_device_event_loop(), name="solarminer-tuya-event-observer")
    try:
        yield
    finally:
        sampler.cancel()
        dispatcher.cancel()
        tuya_observer.cancel()
        try:
            await sampler
        except asyncio.CancelledError:
            pass
        try:
            await dispatcher
        except asyncio.CancelledError:
            pass
        try:
            await tuya_observer
        except asyncio.CancelledError:
            pass


app = FastAPI(title="SolarMiner Gateway", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.middleware("http")
async def report_http_server_errors(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception as exc:
        LOG.error("Unhandled Gateway request exception route=%s type=%s",
                  request.url.path, type(exc).__name__)
        raise
    if response.status_code >= 500:
        LOG.error("Gateway returned HTTP server error status=%s route=%s",
                  response.status_code, request.url.path)
    return response
# Cross-origin PWA access is opt-in and exact-origin allow-listed. The official
# GitHub Pages origin is enabled by the package; additional origins must be set
# explicitly by the administrator in SOLARMINER_CORS_ORIGINS.
_CORS_ORIGINS = [item.strip().rstrip("/") for item in os.environ.get(
    "SOLARMINER_CORS_ORIGINS", "https://solargualdimpais-bot.github.io"
).split(",") if item.strip()]
if _CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=_CORS_ORIGINS, allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=["Authorization", "Content-Type", "Accept"])


@app.middleware("http")
async def security_response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.path.startswith("/api/v1/"):
        response.headers["Cache-Control"] = "no-store"
    if request.url.path in {"/", "/index.html", "/app.js", "/app-core.js", "/api-client.js", "/auth-client.js", "/gateway-connection.js", "/gateway-auth.js", "/workspace-ui.js", "/features-v053.js", "/demo-mode.js", "/styles.css", "/manifest.webmanifest", "/service-worker.js"} or request.url.path.startswith("/assets/"):
        response.headers["Content-Security-Policy"] = ("default-src 'self'; script-src 'self'; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self' http://localhost:* http://127.0.0.1:*; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
    return response


class BootstrapOwner(BaseModel):
    # bootstrap_token remains optional for older locally issued tokens. Fresh
    # installs use the password chosen on the Gateway console as the one-time
    # bootstrap proof instead.
    bootstrap_token: str | None = Field(default=None, min_length=32, max_length=256)
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=128)
    mac: str | None = None
    public_key_pem: str = Field(min_length=80, max_length=8192)
    signature: str = Field(min_length=80, max_length=256)
    timestamp: int
    nonce: str = Field(min_length=16, max_length=128)


class DeviceLoginRequest(BaseModel):
    user_id: str | None = Field(default=None, min_length=36, max_length=36)
    device_id: str = Field(min_length=36, max_length=36)
    timestamp: int
    nonce: str = Field(min_length=16, max_length=128)
    signature: str = Field(min_length=80, max_length=256)


class LoginRequest(BaseModel):
    username: str
    password: str
    device_id: str
    timestamp: int
    nonce: str = Field(min_length=16, max_length=128)
    signature: str = Field(min_length=80, max_length=256)


class PasswordDeviceLoginRequest(BaseModel):
    """Authenticate a new browser device with an existing account password."""
    model_config = ConfigDict(extra="forbid", strict=True)
    username: StrictStr = Field(min_length=1, max_length=128)
    password: StrictStr = Field(min_length=1, max_length=1024)
    public_key_pem: StrictStr = Field(min_length=80, max_length=8192)
    timestamp: int
    nonce: StrictStr = Field(min_length=16, max_length=128)
    signature: StrictStr = Field(min_length=128, max_length=128, pattern=r"^[0-9a-fA-F]{128}$")


class CreateUser(BaseModel):
    username: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=1024)
    role: str
    device_id: str


class CreateDevice(BaseModel):
    mac: str
    public_key_pem: str = Field(min_length=80, max_length=8192)
    mac_status: str = "declared"


class CreatePairingCode(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    username: StrictStr = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    expires_in: int = Field(default=300, ge=60, le=600)


class ConsumePairingCode(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    pairing_code: StrictStr = Field(min_length=32, max_length=128)
    mac: StrictStr
    public_key_pem: StrictStr = Field(min_length=80, max_length=8192)
    timestamp: int
    nonce: StrictStr = Field(min_length=16, max_length=128)
    signature: StrictStr = Field(min_length=128, max_length=128, pattern=r"^[0-9a-fA-F]{128}$")


class CreateInvite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    role: StrictStr = Field(min_length=1, max_length=32)
    label: StrictStr = Field(min_length=1, max_length=120)


class RedeemInvite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    invite_token: StrictStr = Field(min_length=32, max_length=256)
    username: StrictStr = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    password: StrictStr = Field(min_length=12, max_length=1024)
    mac: StrictStr
    client_pubkey_pem: StrictStr = Field(min_length=80, max_length=8192)
    signature: StrictStr = Field(min_length=128, max_length=128, pattern=r"^[0-9a-fA-F]{128}$")
    timestamp: int
    nonce: StrictStr = Field(min_length=16, max_length=128)


class ChangeUserRole(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    role: StrictStr = Field(min_length=1, max_length=32)
    current_password: StrictStr = Field(min_length=1, max_length=1024)


class ChangeUserStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: StrictStr = Field(min_length=1, max_length=16)
    current_password: StrictStr = Field(min_length=1, max_length=1024)


class RevokeUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    current_password: StrictStr = Field(min_length=1, max_length=1024)


class ConnectorInstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    confirmed: bool


class ConnectorConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    config: dict[str, Any]


class ConnectorTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    host: StrictStr = Field(min_length=3, max_length=64)
    port: int = Field(ge=1, le=65535)


class ConnectorRemoveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    confirmed: bool


class DeviceDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    cidr: StrictStr = Field(min_length=9, max_length=43)
    ports: list[int] = Field(min_length=1, max_length=16)
    timeout_seconds: float = Field(default=0.25, ge=0.05, le=1.0)


def load_public_key(pem: str) -> Ed25519PublicKey:
    try:
        key = serialization.load_pem_public_key(pem.encode())
    except Exception as exc:
        raise HTTPException(422, "invalid_device_public_key") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise HTTPException(422, "ed25519_public_key_required")
    return key


def verify_signature(pem: str, message: bytes, signature: str) -> None:
    try:
        sig = bytes.fromhex(signature)
        load_public_key(pem).verify(sig, message)
    except (ValueError, InvalidSignature) as exc:
        raise HTTPException(401, "device_signature_invalid") from exc


def verify_fresh(timestamp: int, nonce: str) -> None:
    now = int(time.time())
    if abs(now - timestamp) > NONCE_WINDOW:
        raise HTTPException(401, "timestamp_out_of_window")
    if not nonce or len(nonce) < 16:
        raise HTTPException(401, "invalid_nonce")


def consume_nonce(conn: sqlite3.Connection, device_id: str, nonce: str, timestamp: int) -> None:
    try:
        conn.execute("INSERT INTO nonces(device_id,nonce,timestamp) VALUES(?,?,?)", (device_id, nonce, timestamp))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(401, "nonce_replayed") from exc
    # A nonce remains stored until outside the maximum acceptance window plus margin.
    conn.execute("DELETE FROM nonces WHERE timestamp < ?", (int(time.time()) - NONCE_WINDOW - 60,))


def current_session(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "authentication_required")
    digest = token_hash(authorization[7:].strip())
    with db() as conn:
        row = conn.execute("""SELECT s.*,u.username,u.role,u.status AS user_status,u.account_id,d.status AS device_status
          FROM sessions s JOIN users u ON u.id=s.user_id JOIN devices d ON d.id=s.device_id
          WHERE s.token_sha256=?""", (digest,)).fetchone()
        if not row or row["revoked_at"] is not None or row["expires_at"] < int(time.time()):
            raise HTTPException(401, "session_invalid_or_expired")
        if row["user_status"] != "active" or row["device_status"] != "active":
            raise HTTPException(401, "identity_revoked")
        if row["credential_version"] != conn.execute("SELECT credential_version FROM users WHERE id=?", (row["user_id"],)).fetchone()[0]:
            raise HTTPException(401, "session_revoked_by_credential_change")
        return dict(row)


def require_permission(permission: str):
    def dependency(session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
        if permission not in PERMISSIONS.get(session["role"], set()):
            raise HTTPException(403, "permission_denied")
        return session
    return dependency


def _revalidate_actor(conn: sqlite3.Connection, session: dict[str, Any], permission: str) -> sqlite3.Row:
    """Recheck the bearer session and current RBAC state while holding the write lock."""
    row = conn.execute("""SELECT s.token_sha256,s.user_id,s.device_id,s.expires_at,s.revoked_at,
          s.credential_version,u.role,u.status AS user_status,u.credential_version AS current_credential_version,
          d.status AS device_status,
          EXISTS(SELECT 1 FROM user_devices ud WHERE ud.user_id=u.id AND ud.device_id=d.id AND ud.status='active') AS association_active
        FROM sessions s JOIN users u ON u.id=s.user_id JOIN devices d ON d.id=s.device_id
        WHERE s.token_sha256=?""", (session.get("token_sha256"),)).fetchone()
    if not row or row["revoked_at"] is not None or row["expires_at"] < int(time.time()):
        raise HTTPException(401, "session_invalid_or_expired")
    if row["user_status"] != "active" or row["device_status"] != "active" or not row["association_active"]:
        raise HTTPException(401, "identity_revoked")
    if row["credential_version"] != row["current_credential_version"]:
        raise HTTPException(401, "session_revoked_by_credential_change")
    if permission not in PERMISSIONS.get(row["role"], set()):
        raise HTTPException(403, "permission_denied")
    return row


@app.exception_handler(sqlite3.Error)
async def database_error_handler(_: Request, exc: sqlite3.Error) -> JSONResponse:
    LOG.error("Database operation failed (%s)", type(exc).__name__)
    return JSONResponse(status_code=503, content={"error": "database_unavailable"})


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    try:
        with db() as conn:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise HTTPException(503, "database_integrity_failure")
            state = conn.execute("SELECT value FROM system_state WHERE key='bootstrap_state'").fetchone()
        return {"status": "ok", "version": VERSION, "package_version": PACKAGE_VERSION, "bootstrap_state": state[0] if state else "RECOVERY_REQUIRED"}
    except sqlite3.Error:
        raise HTTPException(503, "database_unavailable")


@app.get("/api/v1/info")
def info() -> dict[str, str]:
    return {"product": "SolarMiner Gateway", "version": VERSION, "pwa": "The Solar Miner"}


@app.get("/api/v1/status")
def status_endpoint(session: dict[str, Any] = Depends(require_permission("read"))) -> dict[str, Any]:
    with db() as conn:
        state = conn.execute("SELECT value FROM system_state WHERE key='bootstrap_state'").fetchone()[0]
        users = conn.execute("SELECT COUNT(*) FROM users WHERE status='active'").fetchone()[0]
        devices = conn.execute("SELECT COUNT(*) FROM devices WHERE status='active'").fetchone()[0]
    return {"status": "ok", "bootstrap_state": state, "active_users": users, "active_devices": devices}


@app.get("/api/v1/energy/categories")
def energy_categories(session: dict[str, Any] = Depends(require_permission("read"))) -> dict[str, Any]:
    return {"categories": [{"id": key, "label": label, "api_category": key, "profile_path": "/api/v1/energy/equipment"} for key, label in energy_registry.CATEGORIES.items()], "pwa_source_available": True, "integration_state": "API_READY_PWA_V0_5_7_SAME_ORIGIN"}


@app.get("/api/v1/site/profile")
def read_site_profile(session: dict[str, Any] = Depends(require_permission("read"))) -> dict[str, Any]:
    with db() as conn:
        return site_profile.get_profile(conn)


@app.put("/api/v1/site/profile")
def write_site_profile(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    with db() as conn:
        _require_owner(session, conn)
        try:
            result = site_profile.save_profile(conn, payload)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        audit(conn, session["user_id"], "site.profile.configure", "site-profile", "success", {
            "photo_configured": bool(result.get("photo_data_url")),
            "floor_count": len(result["floors"]),
            "room_count": sum(len(floor["rooms"]) for floor in result["floors"]),
        })
        return result


@app.get("/api/v1/energy/engine")
def energy_engine_summary(history_hours: int = 24, session: dict[str, Any] = Depends(require_permission("read"))) -> dict[str, Any]:
    if isinstance(history_hours, bool) or not 1 <= history_hours <= 168:
        raise HTTPException(422, "history_hours_must_be_1_to_168")
    with db() as conn:
        with _energy_sample_lock:
            latest_sample = dict(_latest_deye_sample) if _latest_deye_sample else None
        result = energy_engine.build_summary(conn, history_hours, latest_sample=latest_sample)
        result["sampling_interval_seconds"] = _energy_sample_interval_seconds()
        result["persistence_interval_seconds"] = 60
        result["live_sample_at"] = latest_sample.get("sampled_at") if latest_sample else None
        if latest_sample and result["live_sample_at"]:
            try:
                stamp = datetime.fromisoformat(result["live_sample_at"].replace("Z", "+00:00"))
                result["live_sample_age_seconds"] = max(0, int((datetime.now(timezone.utc) - stamp).total_seconds()))
                result["live_sample_state"] = "LIVE" if result["live_sample_age_seconds"] <= 90 else "STALE"
            except (TypeError, ValueError):
                result["live_sample_age_seconds"] = None
                result["live_sample_state"] = "UNKNOWN"
        else:
            result["live_sample_age_seconds"] = None
            result["live_sample_state"] = "WAITING_FOR_SAMPLE"
        return result


@app.put("/api/v1/energy/engine/config")
def energy_engine_configure(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    with db() as conn:
        _require_owner(session, conn)
        try:
            configured_tuya = hardware_integrations.load_config().get("tuya", {}).get("devices", [])
            proposed_loads = payload.get("loads", energy_engine.get_config(conn).get("loads", []))
            config_payload = dict(payload)
            if "site_location_name" in config_payload:
                config_payload.update(energy_engine.resolve_site_location(config_payload.pop("site_location_name")))
            tuya_by_id = {item.get("device_id"): item for item in configured_tuya if isinstance(item, dict)}
            if not isinstance(proposed_loads, list):
                raise ValueError("invalid_flexible_loads")
            for load in proposed_loads:
                if not isinstance(load, dict):
                    raise ValueError("invalid_flexible_load")
                if load.get("control_type") in {"tuya_smart", "tuya_breaker"}:
                    device = tuya_by_id.get(load.get("tuya_device_id"))
                    allowed_codes = {entry.get("code") for entry in (device or {}).get("functions", []) if isinstance(entry, dict) and str(entry.get("type", "")).lower() in {"bool", "boolean"}}
                    if device and device.get("switch_code"):
                        allowed_codes.add(device["switch_code"])
                    if not device or load.get("tuya_switch_code") not in allowed_codes:
                        raise ValueError("load_tuya_device_or_switch_code_not_configured")
            result = energy_engine.save_config(conn, config_payload)
            audit(conn, session["user_id"], "energy.engine.configure", "energy-engine", "success", {
                "battery_capacity_kwh_configured": result["battery_capacity_kwh"] is not None,
                "minimum_soc_percent": result["minimum_soc_percent"],
                "maximum_soc_percent": result["maximum_soc_percent"],
            })
            return result
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/energy/equipment")
def energy_equipment_list(category: str | None = None, session: dict[str, Any] = Depends(require_permission("read"))) -> dict[str, Any]:
    try:
        with db() as conn:
            return {"equipment": energy_registry.list_equipment(conn, category), "categories": energy_registry.CATEGORIES, "trust_classes": sorted(energy_registry.TRUST)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/v1/energy/equipment", status_code=201)
def energy_equipment_create(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    try:
        with db() as conn:
            result = energy_registry.upsert_equipment(conn, payload)
            audit(conn, session["user_id"], "energy.equipment.create", result["id"], "success", {"category": result["category"], "status": result["status"]})
            return result
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/integrations/hardware")
def hardware_integrations_status(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner": raise HTTPException(403, "owner_required")
    try:
        return hardware_integrations.public_config()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(500, "integration_config_unavailable") from exc


@app.put("/api/v1/integrations/hardware")
def hardware_integrations_configure(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner": raise HTTPException(403, "owner_required")
        try:
            old = hardware_integrations.load_config()
            updated = hardware_integrations.validate_config(payload, old)
            result = hardware_integrations.save_config(updated)
            audit(conn, session["user_id"], "hardware.integrations.configure", "gateway", "success", {
                "providers": sorted(k for k in ("deye", "antminer", "tuya") if k in payload),
                "provider_secrets_returned": False,
            })
            return result
        except ValueError as exc:
            audit(conn, session["user_id"], "hardware.integrations.configure", "gateway", "rejected", {"reason": str(exc)[:120]})
            raise HTTPException(422, str(exc)) from exc
        except (OSError, json.JSONDecodeError) as exc:
            LOG.error("Hardware integration configuration save failed (%s)", type(exc).__name__)
            raise HTTPException(500, "integration_config_save_failed") from exc


@app.post("/api/v1/integrations/tuya/sync")
async def tuya_devices_sync(request: Request, session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Run a cancellable sync and stop it if the Owner cancels the request."""
    cancelled = threading.Event()
    work = asyncio.create_task(asyncio.to_thread(_tuya_devices_sync_work, session, cancelled))
    while not work.done():
        if await request.is_disconnected():
            cancelled.set()
        await asyncio.sleep(0.2)
    return await work


def _tuya_devices_sync_work(session: dict[str, Any], cancelled: threading.Event) -> dict[str, Any]:
    """Owner-triggered Tuya inventory sync; local keys remain Gateway-only."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        try:
            config = hardware_integrations.load_config()
            tuya = config.get("tuya", {})
            if not tuya.get("client_id") or not tuya.get("client_secret"):
                raise HTTPException(409, "tuya_not_configured")
            if not tuya.get("uid"):
                raise HTTPException(409, "tuya_uid_required")
            synced = hardware_integrations.synchronize_tuya_devices(tuya, cancelled=cancelled)
            current = {item.get("device_id"): item for item in tuya.get("devices", [])
                       if isinstance(item, dict) and isinstance(item.get("device_id"), str)}
            imported = {item["device_id"]: item for item in synced["devices"]}
            # Keep locally managed items and previously cached disconnected
            # entries. Mark cloud-missing entries rather than silently deleting
            # their private keys or user mappings.
            for device_id, item in current.items():
                if device_id not in imported:
                    if item.get("cloud_source") == "TUYA_PROJECT":
                        imported[device_id] = {**item, "cloud_missing": True}
                    else:
                        imported[device_id] = item
            tuya["devices"] = list(imported.values())
            config["tuya"] = tuya
            hardware_integrations.save_config(config)
            audit(conn, session["user_id"], "hardware.tuya.sync", "gateway", "success", {
                "device_count": synced["device_count"],
                "local_keys_available": synced["local_keys_available"],
                "schema_failures": synced["schema_failures"],
                "cloud_pages": synced["pages"],
                "secrets_returned": False,
            })
            conn.commit()
            return {"inventory": hardware_integrations.public_config(config)["tuya"],
                    "device_count": synced["device_count"],
                    "local_keys_available": synced["local_keys_available"],
                    "schema_failures": synced["schema_failures"],
                    "secrets_returned": False}
        except HTTPException:
            raise
        except hardware_integrations.TuyaSyncCancelled:
            audit(conn, session["user_id"], "hardware.tuya.sync", "gateway", "cancelled", {
                "secrets_returned": False,
            })
            conn.commit()
            raise HTTPException(409, "tuya_sync_cancelled") from None
        except (ValueError, RuntimeError) as exc:
            reason = str(exc)[:120]
            audit(conn, session["user_id"], "hardware.tuya.sync", "gateway", "failed", {
                "reason": reason, "secrets_returned": False,
            })
            conn.commit()
            raise HTTPException(502, reason) from exc
        except (OSError, json.JSONDecodeError, sqlite3.Error) as exc:
            conn.rollback()
            LOG.error("Tuya device sync failed (%s)", type(exc).__name__)
            raise HTTPException(503, "tuya_sync_unavailable") from exc


def _persist_deye_telemetry(conn: sqlite3.Connection, deye: dict[str, Any] | None) -> int:
    """Store a successful Deye FC03 snapshot in the canonical energy registry."""
    if not isinstance(deye, dict) or deye.get("connection_state") != "mapped_registers_response":
        return 0
    metrics = deye.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        return 0
    identity = hashlib.sha256(f"{deye.get('host', '')}|{deye.get('unit_id', 1)}".encode("utf-8")).hexdigest()[:16]
    equipment_by_category = {
        "inversores": (f"deye-inverter-{identity}", "Inversor Deye"),
        "baterias": (f"deye-battery-{identity}", "Bateria Deye"),
    }
    observed_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    register_map = deye.get("register_map", {})
    persisted = 0
    for category, (equipment_id, name) in equipment_by_category.items():
        category_metrics = [item for item in metrics if isinstance(item, dict) and item.get("category") == category
                            and isinstance(item.get("field"), str) and isinstance(item.get("value"), (int, float))
                            and not isinstance(item.get("value"), bool)]
        if not category_metrics:
            continue
        energy_registry.upsert_equipment(conn, {
            "category": category, "name": name, "manufacturer": "Deye",
            "model": deye.get("model"), "protocol": "Modbus TCP FC03",
            "connection_state": "CONNECTED",
            "declared_capabilities": ["read-only telemetry"],
            "implemented_capabilities": ["FC03 register-map telemetry"],
            "verified_capabilities": [],
            "limitations": ["Candidate register map; exact device firmware and meter/CT semantics are not manufacturer-validated."],
            "config": {"unit_id": deye.get("unit_id", 1), "trust": "LIVE_UNVERIFIED"},
        }, equipment_id=equipment_id)
        for item in category_metrics:
            energy_registry.add_reading(conn, equipment_id, {
                "field": item["field"], "value": item["value"], "unit": item.get("unit"),
                "observed_at": observed_at, "source": "DEYE_MODBUS_FC03_CANDIDATE_MAP",
                "trust": "LIVE_UNVERIFIED",
                "evidence": {"register": item.get("register"), "registers": item.get("registers"),
                             "raw_value": item.get("raw_value"),
                             "label": item.get("label"), "derived": item.get("derived", False),
                             "register_map_source": register_map.get("source"),
                             "register_map_supplement": register_map.get("supplement"),
                             "register_map_sha256": register_map.get("sha256"),
                             "protocol_reference": register_map.get("protocol_reference")},
            })
            persisted += 1
    return persisted


def _persist_antminer_telemetry(conn: sqlite3.Connection, miner: dict[str, Any] | None) -> int:
    """Store only documented, read-only Braiins/CGMiner measurements."""
    if not isinstance(miner, dict) or miner.get("connection_state") != "api_responded":
        return 0
    host = miner.get("host")
    if not isinstance(host, str) or not host:
        return 0
    data = miner.get("data") if isinstance(miner.get("data"), dict) else {}
    summary_rows = (data.get("summary") or {}).get("SUMMARY", []) if isinstance(data.get("summary"), dict) else []
    tuner_rows = (data.get("tunerstatus") or {}).get("TUNERSTATUS", []) if isinstance(data.get("tunerstatus"), dict) else []
    summary = summary_rows[0] if isinstance(summary_rows, list) and summary_rows and isinstance(summary_rows[0], dict) else {}
    tuner = tuner_rows[0] if isinstance(tuner_rows, list) and tuner_rows and isinstance(tuner_rows[0], dict) else {}
    metrics: list[tuple[str, Any, str | None, str]] = []

    def numeric(value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return None
        return float(value)

    power = numeric(tuner.get("ApproximateMinerPowerConsumption"))
    if power is not None and power >= 0:
        metrics.append(("miner_power_w", round(power, 1), "W", "TUNERSTATUS.ApproximateMinerPowerConsumption"))
    limit = numeric(tuner.get("PowerLimit"))
    if limit is not None and limit >= 0:
        metrics.append(("miner_power_limit_w", round(limit, 1), "W", "TUNERSTATUS.PowerLimit"))
    for suffix, keys in (("avg", ("GHS av", "MHS av")), ("5s", ("GHS 5s", "MHS 5s"))):
        gh_value = numeric(summary.get(keys[0]))
        source_field = keys[0]
        if gh_value is None:
            mh_value = numeric(summary.get(keys[1]))
            gh_value = mh_value / 1000 if mh_value is not None else None
            source_field = keys[1]
        if gh_value is not None and gh_value >= 0:
            metrics.append((f"miner_hashrate_{suffix}_ghs", round(gh_value, 3), "GH/s", f"SUMMARY.{source_field}"))

    identity = hashlib.sha256(host.encode("utf-8")).hexdigest()[:16]
    equipment_id = f"braiins-antminer-{identity}"
    observed_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    try:
        timestamp = miner.get("observed_at")
        if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool) and math.isfinite(float(timestamp)):
            observed_at = datetime.fromtimestamp(float(timestamp), timezone.utc).isoformat(timespec="microseconds")
    except (OverflowError, OSError, ValueError):
        pass
    energy_registry.upsert_equipment(conn, {
        "category": "mineradoras", "name": "Antminer S19K Pro", "manufacturer": "Bitmain",
        "model": "S19K Pro", "protocol": "Braiins OS CGMiner-compatible read-only",
        "connection_state": "CONNECTED", "status": "CONFIGURED",
        "declared_capabilities": ["read-only mining telemetry"],
        "implemented_capabilities": ["CGMiner summary/stats/devs", "Braiins tuner status when available"],
        "verified_capabilities": [], "limitations": ["Model identity is configured, not verified by the API response."],
        "config": {"host": host, "port": miner.get("port", 4028), "trust": "LIVE_UNVERIFIED"},
    }, equipment_id=equipment_id)
    for field, value, unit, api_field in metrics:
        energy_registry.add_reading(conn, equipment_id, {
            "field": field, "value": value, "unit": unit, "observed_at": observed_at,
            "source": "BRAIINS_CGMINER_READ_ONLY", "trust": "LIVE_UNVERIFIED",
            "evidence": {"api_field": api_field, "control_commands_sent": False},
        })
    return len(metrics)


@app.post("/api/v1/integrations/hardware/read")
def hardware_integrations_read(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner": raise HTTPException(403, "owner_required")
        try:
            result = hardware_integrations.collect(hardware_integrations.load_config())
            conn.execute("BEGIN")
            result["energy_readings_persisted"] = _persist_deye_telemetry(conn, result.get("deye"))
            result["antminer_energy_readings_persisted"] = _persist_antminer_telemetry(conn, result.get("antminer"))
            for item in result.get("errors", []):
                LOG.error("Hardware integration failure provider=%s reason=%s",
                          item.get("provider", "unknown"), item.get("reason", "unknown"))
            audit(conn, session["user_id"], "hardware.integrations.read", "gateway", "partial" if result["errors"] else "success", {
                "deye_connected": result["deye"] is not None,
                "antminer_connected": result["antminer"] is not None,
                "tuya_device_count": len(result["tuya"]),
                "deye_energy_readings_persisted": result["energy_readings_persisted"],
                "errors": [{"provider": e["provider"], "reason": e["reason"]} for e in result["errors"]],
                "control_commands_sent": False,
            })
            conn.commit()
            return result
        except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
            conn.rollback()
            LOG.error("Hardware integration read failed (%s)", type(exc).__name__)
            raise HTTPException(503, "integration_read_unavailable") from exc


def _persist_tuya_device_events(conn: sqlite3.Connection, readings: list[dict[str, Any]]) -> int:
    """Persist observed Tuya state/availability transitions from LAN polls."""
    recorded = 0
    for reading in readings:
        device_id = reading.get("device_id")
        if not isinstance(device_id, str):
            continue
        name = str(reading.get("name") or "Tuya device")[:120]
        observed_at = datetime.now(timezone.utc).isoformat()
        available = reading.get("connection_state") == "local_responded"
        observations: list[tuple[str, Any, str]] = [("__availability", available, "availability")]
        if available:
            for row in reading.get("status", []):
                if isinstance(row, dict) and isinstance(row.get("code"), str) and isinstance(row.get("value"), bool):
                    observations.append((row["code"], row["value"], "switch_state"))
        for key, value, event_type in observations:
            new_json = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
            previous = conn.execute("SELECT value_json FROM device_observations WHERE device_id=? AND observation_key=?",
                                    (device_id, key)).fetchone()
            old_json = previous["value_json"] if previous else None
            conn.execute("INSERT INTO device_observations(device_id,observation_key,value_json,observed_at) VALUES(?,?,?,?) "
                         "ON CONFLICT(device_id,observation_key) DO UPDATE SET value_json=excluded.value_json,observed_at=excluded.observed_at",
                         (device_id, key, new_json, observed_at))
            if old_json != new_json:
                conn.execute("INSERT INTO device_events(occurred_at,device_id,device_name,event_type,channel_code,old_value_json,new_value_json,source) VALUES(?,?,?,?,?,?,?,?)",
                             (observed_at, device_id, name, event_type, "" if key == "__availability" else key,
                              old_json, new_json, "TUYA_LAN"))
                recorded += 1
    return recorded


def _append_tuya_command_event(conn: sqlite3.Connection, device_id: str, code: str, requested_on: bool,
                              *, confirmed: bool, automatic: bool = False, source: str = "TUYA_LAN") -> None:
    config = hardware_integrations.load_config().get("tuya", {})
    device = next((item for item in config.get("devices", []) if isinstance(item, dict) and item.get("device_id") == device_id), {})
    conn.execute("INSERT INTO device_events(occurred_at,device_id,device_name,event_type,channel_code,old_value_json,new_value_json,source) VALUES(?,?,?,?,?,?,?,?)",
                 (datetime.now(timezone.utc).isoformat(), device_id, str(device.get("name") or "Tuya device")[:120],
                  ("automation_action" if automatic else "command_confirmed" if confirmed else "command_unconfirmed"),
                  code, None, json.dumps(requested_on),
                  "TUYA_LAN_AUTOMATION" if automatic else source))


@app.get("/api/v1/integrations/tuya/{device_id}/events")
def tuya_device_events(device_id: str, limit: int = 100,
                       session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", device_id) or not 1 <= limit <= 500:
        raise HTTPException(422, "tuya_event_query_invalid")
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        configured = hardware_integrations.load_config().get("tuya", {}).get("devices", [])
        if not any(isinstance(item, dict) and item.get("device_id") == device_id for item in configured):
            raise HTTPException(404, "tuya_device_not_configured")
        rows = conn.execute("SELECT id,occurred_at,device_name,event_type,channel_code,old_value_json,new_value_json,source "
                            "FROM device_events WHERE device_id=? ORDER BY id DESC LIMIT ?", (device_id, limit)).fetchall()
        return {"device_id": device_id, "events": [{"id": row["id"], "occurred_at": row["occurred_at"],
                "device_name": row["device_name"], "event_type": row["event_type"], "channel_code": row["channel_code"],
                "old_value": json.loads(row["old_value_json"]) if row["old_value_json"] is not None else None,
                "new_value": json.loads(row["new_value_json"]) if row["new_value_json"] is not None else None,
                "source": row["source"]} for row in rows]}


@app.post("/api/v1/integrations/tuya/lan-diagnostics")
def tuya_lan_diagnostics(payload: dict[str, Any] | None = None,
                         session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Measure read-only Tuya LAN response times; never sends control commands."""
    payload = payload or {}
    rounds = payload.get("rounds", 3)
    if isinstance(rounds, bool) or not isinstance(rounds, int) or not 1 <= rounds <= 5:
        raise HTTPException(422, "tuya_diagnostic_rounds_must_be_1_to_5")
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        config = hardware_integrations.load_config().get("tuya", {})
        devices = [item for item in config.get("devices", [])
                   if isinstance(item, dict) and isinstance(item.get("device_id"), str)]
        if not devices:
            return {"rounds": rounds, "configured_count": 0, "lan_testable_count": 0,
                    "elapsed_ms": 0, "devices": [], "control_commands_sent": False}
        samples: dict[str, list[dict[str, Any]]] = {item["device_id"]: [] for item in devices}
        started = time.perf_counter()
        sweep_times: list[float] = []
        for _ in range(rounds):
            sweep_started = time.perf_counter()
            configured_lan = []
            for item in devices:
                host = item.get("local_ip")
                if not item.get("local_key") or not host:
                    continue
                try:
                    hardware_integrations._private_ip(host)
                except ValueError:
                    continue
                configured_lan.append(item)
            readings = hardware_integrations.read_tuya({**config, "devices": configured_lan}) if configured_lan else []
            sweep_times.append(round((time.perf_counter() - sweep_started) * 1000, 1))
            by_id = {row.get("device_id"): row for row in readings}
            for item in devices:
                device_id = item["device_id"]
                row = by_id.get(device_id)
                if row is None:
                    host = item.get("local_ip")
                    if not item.get("local_key"):
                        reason = "tuya_local_key_missing"
                    elif not host:
                        reason = "private_lan_target_required"
                    else:
                        try:
                            hardware_integrations._private_ip(host)
                            reason = "tuya_lan_read_unavailable"
                        except ValueError as exc:
                            reason = str(exc)
                    samples[device_id].append({"ok": False, "latency_ms": None,
                                               "reason": reason})
                else:
                    ok = row.get("connection_state") == "local_responded"
                    samples[device_id].append({"ok": ok,
                                               # Only successful LAN replies are response-time samples.
                                               # Setup failures are not network latency.
                                               "latency_ms": row.get("latency_ms") if ok else None,
                                               "reason": row.get("reason")})
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        result = []
        for item in devices:
            rows = samples[item["device_id"]]
            times = [row["latency_ms"] for row in rows if isinstance(row.get("latency_ms"), (int, float))]
            schema = [entry for entry in item.get("status_spec", []) if isinstance(entry, dict)]
            power_telemetry = any(re.search(r"power|watt|cur_power|active_power", str(entry.get("code", "")) + " " + str(entry.get("name", "")), re.I)
                                  for entry in schema)
            result.append({"device_id": item["device_id"], "name": str(item.get("name") or "Tuya device")[:120],
                           "local_ip": item.get("local_ip", ""),
                           "local_key_configured": bool(item.get("local_key")),
                           "success_count": sum(1 for row in rows if row["ok"]), "rounds": rounds,
                           "failure_count": sum(1 for row in rows if not row["ok"]),
                           "average_latency_ms": round(sum(times) / len(times), 1) if times else None,
                           "worst_latency_ms": round(max(times), 1) if times else None,
                           "power_telemetry_configured": power_telemetry,
                           "reason": next((row["reason"] for row in rows if row.get("reason")),
                                          "private_lan_target_required" if not item.get("local_ip") else None)})
        return {"rounds": rounds, "configured_count": len(devices),
                "lan_testable_count": len(configured_lan),
                "elapsed_ms": elapsed_ms, "sweep_times_ms": sweep_times,
                "devices": result, "control_commands_sent": False}


@app.post("/api/v1/integrations/tuya/lan-discovery")
def tuya_lan_discovery(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Discover Tuya LAN addresses and save only matches to configured device IDs."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        try:
            config = hardware_integrations.load_config()
            tuya = config.get("tuya", {}) if isinstance(config.get("tuya"), dict) else {}
            devices = [item for item in tuya.get("devices", [])
                       if isinstance(item, dict) and isinstance(item.get("device_id"), str)]
            if not devices:
                return {"scanned_count": 0, "matched_count": 0, "devices": [],
                        "cloud_used": False, "commands_sent": False}
            scan_error = None
            try:
                if hardware_integrations.tinytuya is None:
                    raise RuntimeError("driver_unavailable")
                discovered = hardware_integrations.tinytuya.deviceScan(
                    verbose=False, maxretry=10, poll=False, byID=True)
            except Exception as exc:
                # Broadcast discovery can be blocked by Wi-Fi isolation; still try configured MACs.
                scan_error = type(exc).__name__[:64]
                LOG.warning("Tuya LAN broadcast discovery failed (%s); trying neighbor cache", scan_error)
                discovered = {}
            if not isinstance(discovered, dict):
                raise HTTPException(502, "tuya_lan_discovery_invalid_result")
            discovered_by_id: dict[str, dict[str, Any]] = {}
            discovered_by_mac: dict[str, dict[str, Any]] = {}
            arp_by_mac = local_arp_entries()
            for key, value in discovered.items():
                if not isinstance(value, dict):
                    continue
                device_id = value.get("gwId") or value.get("id") or key
                host = value.get("ip") or (key if isinstance(key, str) else None)
                if isinstance(device_id, str) and isinstance(host, str):
                    try:
                        host = hardware_integrations._private_ip(host)
                    except ValueError:
                        continue
                    found = {"ip": host, "version": value.get("version"), "mac": None}
                    try:
                        if value.get("mac"):
                            found["mac"] = normalize_mac(str(value["mac"]))
                            discovered_by_mac[found["mac"]] = found
                    except HTTPException:
                        pass
                    discovered_by_id[device_id] = found
            matched = []
            for device in devices:
                found = discovered_by_id.get(device["device_id"])
                matched_by = "device_id"
                if not found and device.get("local_mac"):
                    try:
                        mac = normalize_mac(str(device["local_mac"]))
                    except HTTPException:
                        mac = ""
                    found = discovered_by_mac.get(mac)
                    if not found and mac in arp_by_mac:
                        found = {"ip": arp_by_mac[mac], "version": None, "mac": mac}
                    matched_by = "mac"
                if not found:
                    continue
                device["local_ip"] = found["ip"]
                device["local_mac"] = found.get("mac") or device.get("local_mac", "")
                try:
                    version = str(found.get("version") or "")
                    if version in {"3.1", "3.2", "3.3", "3.4", "3.5"}:
                        device["local_protocol"] = version
                except (TypeError, ValueError):
                    pass
                matched.append({"device_id": device["device_id"],
                                "name": str(device.get("name") or "Tuya device")[:120],
                                "ip": found["ip"], "mac": device.get("local_mac", ""),
                                "matched_by": matched_by,
                                "local_key_available": bool(device.get("local_key"))})
            if scan_error and not matched:
                raise HTTPException(502, f"tuya_lan_discovery_failed:{scan_error};neighbor_cache_empty")
            if matched:
                config["tuya"] = tuya
                hardware_integrations.save_config(config)
            audit(conn, session["user_id"], "hardware.tuya.lan_discovery", "tuya_devices", "success", {
                "scanned_count": len(discovered_by_id), "matched_count": len(matched),
                "cloud_used": False, "commands_sent": False,
            })
            conn.commit()
            return {"scanned_count": len(discovered_by_id), "matched_count": len(matched),
                    "devices": matched, "scan_error": scan_error,
                    "discovery_method": "neighbor_cache" if scan_error else "lan_broadcast",
                    "cloud_used": False, "commands_sent": False}
        except HTTPException:
            raise
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            LOG.warning("Tuya LAN discovery could not be saved (%s)", type(exc).__name__)
            raise HTTPException(500, "tuya_lan_discovery_save_failed") from exc


@app.post("/api/v1/integrations/hardware/{provider}/read")
def hardware_provider_read(provider: str, payload: dict[str, Any] | None = None,
                           session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Read exactly one configured provider (and optionally one Tuya device)."""
    if provider not in {"deye", "antminer", "tuya"}:
        raise HTTPException(404, "hardware_provider_not_found")
    payload = payload or {}
    if set(payload) - {"device_id"}:
        raise HTTPException(422, "hardware_provider_read_payload_invalid")
    if provider != "tuya" and payload.get("device_id") is not None:
        raise HTTPException(422, "hardware_provider_read_payload_invalid")
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        config = hardware_integrations.load_config()
        item = config.get(provider, {})
        try:
            if provider == "deye":
                if not item.get("host"):
                    raise HTTPException(409, "deye_not_configured")
                result: dict[str, Any] = {"deye": hardware_integrations.read_deye(item)}
                metrics_saved = _persist_deye_telemetry(conn, result["deye"])
                result["energy_readings_persisted"] = metrics_saved
            elif provider == "antminer":
                if not item.get("host"):
                    raise HTTPException(409, "antminer_not_configured")
                result = {"antminer": hardware_integrations.read_antminer(item["host"], item.get("port", 4028))}
                result["energy_readings_persisted"] = _persist_antminer_telemetry(conn, result["antminer"])
            else:
                if not item.get("devices"):
                    raise HTTPException(409, "tuya_not_configured")
                device_id = payload.get("device_id")
                tuya_config = item
                if device_id is not None:
                    if not isinstance(device_id, str) or not any(d.get("device_id") == device_id for d in item["devices"]):
                        raise HTTPException(404, "tuya_device_not_configured")
                    tuya_config = {**item, "devices": [d for d in item["devices"] if d.get("device_id") == device_id]}
                result = {"tuya": hardware_integrations.read_tuya(tuya_config)}
                _persist_tuya_device_events(conn, result["tuya"])
                by_id = {row.get("device_id"): row for row in result["tuya"]}
                for configured_device in item.get("devices", []):
                    reading = by_id.get(configured_device.get("device_id"))
                    if not reading:
                        continue
                    configured_device["local_control_state"] = "ready" if reading.get("connection_state") == "local_responded" else "unavailable"
                    if reading.get("connection_state") == "local_responded":
                        configured_device["current_status"] = reading.get("status", [])
                        configured_device["last_status_at"] = int(time.time())
                hardware_integrations.save_config(config)
            result["provider"] = provider
            result["collected_at"] = datetime.now(timezone.utc).isoformat()
            audit(conn, session["user_id"], f"hardware.{provider}.read", "gateway", "success", {
                "device_id": payload.get("device_id") if provider == "tuya" else None,
                "control_commands_sent": False,
            })
            conn.commit()
            return result
        except HTTPException:
            raise
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError, sqlite3.Error) as exc:
            conn.rollback()
            LOG.error("Hardware provider read failed provider=%s (%s)", provider, type(exc).__name__)
            raise HTTPException(503, f"{provider}_read_unavailable") from exc


@app.post("/api/v1/integrations/antminer/control")
def antminer_control(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Owner-only, single-action Braiins OS control endpoint."""
    with db() as conn:
        _require_owner(session, conn)
        action = payload.get("action") if isinstance(payload, dict) else None
        watt = payload.get("watt") if isinstance(payload, dict) else None
        if set(payload) - {"action", "watt"}:
            raise HTTPException(422, "antminer_control_payload_invalid")
        if action not in {"set_power_target", "pause", "stop", "start"}:
            raise HTTPException(422, "unsupported_antminer_control_action")
        if action == "set_power_target":
            if isinstance(watt, bool) or not isinstance(watt, int) or not 1 <= watt <= 2900:
                raise HTTPException(422, "power_target_out_of_range_1_2900_watts")
        elif watt is not None:
            raise HTTPException(422, "antminer_control_payload_invalid")
        try:
            config = hardware_integrations.load_config().get("antminer", {})
            result = hardware_integrations.control_antminer(config, action, watt)
            audit(conn, session["user_id"], "hardware.antminer.control", "antminer", "success", {
                "action": action, "requested_watt": watt if action == "set_power_target" else None,
                "applied_watt": result.get("applied_watt"), "control_command_sent": True,
            })
            return result
        except ValueError as exc:
            audit(conn, session["user_id"], "hardware.antminer.control", "antminer", "rejected", {"reason": str(exc)[:120]})
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            reason = str(exc)[:120]
            LOG.error("Antminer control failed reason=%s", reason)
            audit(conn, session["user_id"], "hardware.antminer.control", "antminer", "failed", {"action": action, "reason": reason, "control_command_sent": False})
            raise HTTPException(502, reason) from exc
        except (OSError, json.JSONDecodeError) as exc:
            LOG.error("Antminer control failed (%s)", type(exc).__name__)
            audit(conn, session["user_id"], "hardware.antminer.control", "antminer", "failed", {"action": action, "reason": type(exc).__name__, "control_command_sent": False})
            raise HTTPException(502, "antminer_control_failed") from exc


@app.post("/api/v1/integrations/tuya/switch")
def tuya_switch_control(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Owner-only explicit Tuya switch command for an already configured device."""
    with db() as conn:
        _require_owner(session, conn)
        if not isinstance(payload, dict) or not {"device_id", "on"}.issubset(payload) or set(payload) - {"device_id", "on", "code"}:
            raise HTTPException(422, "tuya_switch_payload_invalid")
        device_id, requested_on, code = payload.get("device_id"), payload.get("on"), payload.get("code")
        if not isinstance(device_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", device_id) or not isinstance(requested_on, bool) or (code is not None and (not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", code))):
            raise HTTPException(422, "tuya_switch_payload_invalid")
        try:
            config = hardware_integrations.load_config().get("tuya", {})
            result = hardware_integrations.control_tuya_switch(config, device_id, requested_on, code=code)
            _append_tuya_command_event(conn, device_id, code or result.get("switch_code", ""), requested_on,
                                       confirmed=bool(result.get("state_confirmed")))
            outcome = "success" if result.get("state_confirmed") else "unconfirmed"
            audit(conn, session["user_id"], "hardware.tuya.switch", device_id, outcome, {
                "requested_on": requested_on, "channel_code": code or result.get("switch_code"), "state_confirmed": bool(result.get("state_confirmed")),
                "control_command_sent": True,
            })
            return result
        except ValueError as exc:
            audit(conn, session["user_id"], "hardware.tuya.switch", device_id, "rejected", {"reason": str(exc)[:120]})
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            reason = str(exc)[:120]
            audit(conn, session["user_id"], "hardware.tuya.switch", device_id, "failed", {"reason": reason, "control_command_sent": False})
            raise HTTPException(502, reason) from exc
        except (OSError, json.JSONDecodeError) as exc:
            LOG.error("Tuya switch control failed (%s)", type(exc).__name__)
            audit(conn, session["user_id"], "hardware.tuya.switch", device_id, "failed", {"reason": type(exc).__name__, "control_command_sent": False})
            raise HTTPException(502, "tuya_switch_control_failed") from exc


@app.post("/api/v1/integrations/tuya/level")
def tuya_level_control(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Owner-only percentage command for a configured Tuya level datapoint."""
    with db() as conn:
        _require_owner(session, conn)
        if not isinstance(payload, dict) or set(payload) != {"device_id", "percent"}:
            raise HTTPException(422, "tuya_level_payload_invalid")
        device_id, percent = payload.get("device_id"), payload.get("percent")
        if not isinstance(device_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", device_id) or isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 100:
            raise HTTPException(422, "tuya_level_payload_invalid")
        try:
            config = hardware_integrations.load_config().get("tuya", {})
            result = hardware_integrations.control_tuya_level(config, device_id, percent)
            audit(conn, session["user_id"], "hardware.tuya.level", device_id, "accepted", {
                "requested_percent": percent, "control_command_sent": True, "state_confirmed": False,
            })
            return result
        except ValueError as exc:
            audit(conn, session["user_id"], "hardware.tuya.level", device_id, "rejected", {"reason": str(exc)[:120]})
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            reason = str(exc)[:120]
            audit(conn, session["user_id"], "hardware.tuya.level", device_id, "failed", {"reason": reason, "control_command_sent": False})
            raise HTTPException(502, reason) from exc
        except (OSError, json.JSONDecodeError) as exc:
            LOG.error("Tuya level control failed (%s)", type(exc).__name__)
            audit(conn, session["user_id"], "hardware.tuya.level", device_id, "failed", {"reason": type(exc).__name__, "control_command_sent": False})
            raise HTTPException(502, "tuya_level_control_failed") from exc


def _require_owner(session: dict[str, Any], conn) -> None:
    actor = _revalidate_actor(conn, session, "manage_gateway")
    if actor["role"] != "owner": raise HTTPException(403, "owner_required")


@app.get("/api/v1/energy/ev/tesla")
def ev_tesla_config(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    with db() as conn: _require_owner(session, conn)
    try: return hardware_integrations.public_tesla_config()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(500, "ev_tesla_config_unavailable") from exc


@app.put("/api/v1/energy/ev/tesla")
def ev_tesla_configure(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    with db() as conn:
        _require_owner(session, conn)
        try:
            config = hardware_integrations.load_config()
            config["tesla"] = hardware_integrations.validate_tesla_config(payload, config)
            hardware_integrations.save_config(config)
            audit(conn, session["user_id"], "energy.ev.tesla.configure", "ev", "success", {"credentials_returned": False})
            return hardware_integrations.public_tesla_config({**config, "tesla": config["tesla"]})
        except ValueError as exc:
            audit(conn, session["user_id"], "energy.ev.tesla.configure", "ev", "rejected", {"reason": str(exc)[:120]})
            raise HTTPException(422, str(exc)) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(500, "ev_tesla_config_save_failed") from exc


@app.post("/api/v1/energy/ev/tesla/read")
def ev_tesla_read(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    with db() as conn:
        _require_owner(session, conn)
        try:
            config = hardware_integrations.load_config().get("tesla", {})
            if not config.get("refresh_token"): raise HTTPException(409, "ev_tesla_not_configured")
            result = hardware_integrations.read_tesla_ev(config)
            audit(conn, session["user_id"], "energy.ev.tesla.read", "ev", "success", {
                "vehicle_count": len(result.get("vehicles", [])), "source": result["source"], "control_commands_sent": False,
            })
            return result
        except HTTPException:
            raise
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            audit(conn, session["user_id"], "energy.ev.tesla.read", "ev", "failed", {"reason": str(exc)[:120], "control_commands_sent": False})
            raise HTTPException(502, "ev_tesla_read_failed") from exc


@app.get("/api/v1/energy/equipment/{equipment_id}")
def energy_equipment_detail(equipment_id: str, session: dict[str, Any] = Depends(require_permission("read"))) -> dict[str, Any]:
    with db() as conn:
        result = energy_registry.get_equipment(conn, equipment_id)
    if result is None: raise HTTPException(404, "equipment_not_found")
    return result


@app.post("/api/v1/energy/equipment/{equipment_id}/readings", status_code=201)
def energy_equipment_reading(equipment_id: str, payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    try:
        with db() as conn:
            result = energy_registry.add_reading(conn, equipment_id, payload)
            audit(conn, session["user_id"], "energy.reading.record", equipment_id, "success", {"field": payload.get("field"), "trust": payload.get("trust"), "source": payload.get("source")})
            return result
    except LookupError as exc: raise HTTPException(404, str(exc)) from exc
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@app.post("/api/v1/energy/equipment/{equipment_id}/physical-tests", status_code=201)
def energy_physical_test_propose(equipment_id: str, payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    try:
        with db() as conn:
            result = energy_registry.propose_test(conn, equipment_id, session["user_id"], payload)
            audit(conn, session["user_id"], "energy.physical_test.propose", result["id"], "blocked" if result["state"] == "BLOCKED" else "success", {"state": result["state"], "hardware_action": False})
            return result
    except LookupError as exc: raise HTTPException(404, str(exc)) from exc
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/energy/physical-tests/{test_id}")
def energy_physical_test_detail(test_id: str, session: dict[str, Any] = Depends(require_permission("read"))) -> dict[str, Any]:
    with db() as conn: result = energy_registry.get_test(conn, test_id)
    if result is None: raise HTTPException(404, "physical_test_not_found")
    return result


@app.post("/api/v1/energy/physical-tests/{test_id}/approve")
def energy_physical_test_approve(test_id: str, payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    try:
        with db() as conn:
            result = energy_registry.approve_test(conn, test_id, session["user_id"], payload.get("confirmed") is True)
            audit(conn, session["user_id"], "energy.physical_test.approve", test_id, "success", {"state": result["state"], "hardware_action": False})
            return result
    except LookupError as exc: raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc: raise HTTPException(400, str(exc)) from exc
    except ValueError as exc: raise HTTPException(409, str(exc)) from exc


@app.post("/api/v1/energy/physical-tests/{test_id}/evidence")
def energy_physical_test_evidence(test_id: str, payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    try:
        with db() as conn:
            result = energy_registry.record_test_event(conn, test_id, session["user_id"], payload.get("phase"), payload.get("observations", {}), payload.get("notes", ""), payload.get("result"))
            audit(conn, session["user_id"], "energy.physical_test.evidence", test_id, "success", {"state": result["state"], "phase": payload.get("phase"), "result": payload.get("result"), "hardware_action": False})
            return result
    except LookupError as exc: raise HTTPException(404, str(exc)) from exc
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/connectors/catalog")
def connectors_catalog(session: dict[str, Any] = Depends(require_permission("read"))) -> dict[str, Any]:
    try:
        return connector_manager.public_catalog()
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/v1/connectors")
def connectors_list(session: dict[str, Any] = Depends(require_permission("read"))) -> dict[str, Any]:
    with db() as conn:
        return {"connectors": connector_manager.list_installed(conn)}


@app.post("/api/v1/connectors/{connector_id}/install", status_code=201)
def connectors_install(connector_id: str, payload: ConnectorInstallRequest,
                       session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    try:
        with db() as conn:
            result = connector_manager.install(conn, connector_id, session["user_id"], payload.confirmed, revalidate=lambda active_conn: _revalidate_actor(active_conn, session, "manage_gateway"))
        return result
    except PermissionError as exc:
        raise HTTPException(400, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'")) from exc
    except LookupError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/v1/connectors/{connector_id}/update")
def connectors_update(connector_id: str, payload: ConnectorInstallRequest,
                      session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    try:
        with db() as conn:
            result = connector_manager.update(conn, connector_id, session["user_id"], payload.confirmed, revalidate=lambda active_conn: _revalidate_actor(active_conn, session, "manage_gateway"))
        return result
    except PermissionError as exc:
        raise HTTPException(400, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'")) from exc
    except LookupError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.patch("/api/v1/connectors/{connector_id}/config")
def connectors_configure(connector_id: str, payload: ConnectorConfigRequest,
                         session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    try:
        with db() as conn:
            result = connector_manager.configure(conn, connector_id, session["user_id"], payload.config, revalidate=lambda active_conn: _revalidate_actor(active_conn, session, "manage_gateway"))
        return result
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'")) from exc
    except LookupError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/v1/connectors/{connector_id}/test")
def connectors_test(connector_id: str, payload: ConnectorTestRequest,
                    session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    try:
        with db() as conn:
            result = connector_manager.test_connection(conn, connector_id, session["user_id"], payload.host, payload.port, revalidate=lambda active_conn: _revalidate_actor(active_conn, session, "manage_gateway"))
        return result
    except LookupError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.delete("/api/v1/connectors/{connector_id}/remove")
def connectors_remove(connector_id: str, payload: ConnectorRemoveRequest,
                      session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    try:
        with db() as conn:
            result = connector_manager.remove(conn, connector_id, session["user_id"], payload.confirmed, revalidate=lambda active_conn: _revalidate_actor(active_conn, session, "manage_gateway"))
        return result
    except PermissionError as exc:
        raise HTTPException(400, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/v1/devices/discover")
def devices_discover(payload: DeviceDiscoveryRequest,
                     session: dict[str, Any] = Depends(require_permission("manage_devices"))) -> dict[str, Any]:
    try:
        with db() as conn:
            result = connector_manager.discover(conn, session["user_id"], payload.cidr, payload.ports, payload.timeout_seconds, revalidate=lambda active_conn: _revalidate_actor(active_conn, session, "manage_devices"))
        return result
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/devices/discovered")
def devices_discovered(session: dict[str, Any] = Depends(require_permission("read"))) -> dict[str, Any]:
    with db() as conn:
        return {"devices": connector_manager.list_discovered(conn)}


@app.get("/api/v1/devices/{discovered_id}/capabilities")
def devices_discovered_capabilities(discovered_id: str,
                                    session: dict[str, Any] = Depends(require_permission("read"))) -> dict[str, Any]:
    with db() as conn:
        try:
            return connector_manager.capabilities(conn, discovered_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc


@app.get("/api/v1/bootstrap/status")
def bootstrap_status() -> dict[str, str]:
    with db() as conn:
        row = conn.execute("SELECT value FROM system_state WHERE key='bootstrap_state'").fetchone()
    return {"state": row[0] if row else "RECOVERY_REQUIRED"}


@app.post("/api/v1/bootstrap/owner", status_code=201)
def bootstrap_owner(payload: BootstrapOwner, request: Request) -> dict[str, Any]:
    # Remote bootstrap is allowed only from an exact, administratively
    # configured HTTPS origin and requires the password provisioned at the
    # Gateway console (or a legacy one-time token) plus fresh device proof.
    remote = request_source_ip(request)
    origin = request.headers.get("origin", "").rstrip("/")
    same_origin = origin == f"{request.url.scheme}://{request.url.netloc}"
    if remote not in {"127.0.0.1", "::1", "testclient"} and not (same_origin or origin in _CORS_ORIGINS):
        raise HTTPException(403, "bootstrap_origin_not_allowed")
    username = payload.username.strip()
    if not username or any(ord(char) < 32 or ord(char) == 127 for char in username):
        raise HTTPException(422, "invalid_owner_name")
    # Browsers cannot reliably read an iPhone's private/randomized MAC. Keep a
    # neutral sentinel for the new console-password flow. Preserve metadata
    # submitted by older clients that still use the legacy token protocol.
    mac = normalize_mac(payload.mac) if payload.bootstrap_token else "unknown"
    verify_fresh(payload.timestamp, payload.nonce)
    key = load_public_key(payload.public_key_pem)
    canonical = (f"BOOTSTRAP\n{username}\n{mac}\n{payload.timestamp}\n{payload.nonce}" if payload.bootstrap_token
                else f"BOOTSTRAP\n{username}\n{payload.timestamp}\n{payload.nonce}").encode()
    try:
        key.verify(bytes.fromhex(payload.signature), canonical)
    except (ValueError, InvalidSignature) as exc:
        raise HTTPException(401, "device_signature_invalid") from exc
    pub_der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    pub_hash = hashlib.sha256(pub_der).hexdigest()
    from .recovery import generate_recovery_key, recovery_verifier
    recovery_key, recovery_raw = generate_recovery_key()
    now = int(time.time())
    remote_hash = hashlib.sha256((remote or "unknown").encode("utf-8")).hexdigest()
    with db() as attempts:
        attempts.execute("BEGIN IMMEDIATE")
        attempts.execute("DELETE FROM bootstrap_attempts WHERE attempted_at<?", (now - 15 * 60,))
        recent = attempts.execute("SELECT COUNT(*) FROM bootstrap_attempts WHERE ip_hash=?", (remote_hash,)).fetchone()[0]
        if recent >= 5:
            attempts.rollback()
            raise HTTPException(429, "bootstrap_attempts_limited")
        attempts.execute("INSERT INTO bootstrap_attempts(ip_hash,attempted_at) VALUES(?,?)", (remote_hash, now))
        attempts.commit()
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        state = conn.execute("SELECT value FROM system_state WHERE key='bootstrap_state'").fetchone()
        token = conn.execute("SELECT * FROM bootstrap WHERE id=1").fetchone()
        owner = conn.execute("SELECT 1 FROM users WHERE role='owner' AND status='active' LIMIT 1").fetchone()
        if owner or not state or state[0] not in {"BOOTSTRAP_PENDING", "OWNER_SETUP_REQUIRED"} or not token or token["consumed_at"] is not None:
            conn.rollback(); raise HTTPException(409, "bootstrap_unavailable")
        setup_hash = token["setup_password_hash"] if "setup_password_hash" in token.keys() else None
        setup_ok = False
        if setup_hash:
            try:
                setup_ok = PASSWORDS.verify(setup_hash, payload.password)
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                setup_ok = False
        else:
            setup_ok = bool(payload.bootstrap_token and token["expires_at"] >= int(time.time())
                            and secrets.compare_digest(token["token_sha256"], token_hash(payload.bootstrap_token)))
        if not setup_ok:
            conn.rollback(); raise HTTPException(401, "bootstrap_password_invalid")
        try:
            uid, did = str(uuid.uuid4()), str(uuid.uuid4())
            conn.execute("INSERT INTO devices(id,public_key_pem,public_key_sha256,mac_declared,mac_status,status,created_at) VALUES(?,?,?,?,?,'active',?)",
                         (did, payload.public_key_pem, pub_hash, mac, "declared", utcnow()))
            consume_nonce(conn, did, payload.nonce, payload.timestamp)
            conn.execute("INSERT INTO users(id,account_id,username,password_hash,role,status,created_at) VALUES(?,?,?,?, 'owner','active',?)",
                         (uid, str(uuid.uuid4()), username, PASSWORDS.hash(payload.password), utcnow()))
            conn.execute("INSERT INTO user_devices(user_id,device_id,status,created_at) VALUES(?,?,'active',?)", (uid, did, utcnow()))
            conn.execute("INSERT INTO owner_recovery_keys(id,owner_user_id,verifier_sha256,generation,status,created_at,consumed_at) VALUES(?,?,?,?, 'active', ?, NULL)",
                         (str(uuid.uuid4()), uid, recovery_verifier(recovery_raw), 1, utcnow()))
            audit(conn, uid, "owner.recovery_key_issued", uid, "success", {"generation": 1, "source": "bootstrap"})
            conn.execute("UPDATE bootstrap SET consumed_at=?,state='consumed',setup_password_hash=NULL WHERE id=1 AND consumed_at IS NULL", (now,))
            conn.execute("UPDATE system_state SET value='OWNER_ACTIVE' WHERE key='bootstrap_state'")
            audit(conn, uid, "bootstrap.owner_created", uid, "success", {"device_id": did, "mac_status": "unknown"})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    try:
        BOOTSTRAP_PATH.unlink(missing_ok=True)
    except OSError:
        LOG.error("Bootstrap token file cleanup failed after committed owner creation")
    return {"user_id": uid, "device_id": did, "role": "owner", "mac_status": "unknown", "message": "owner_created",
            "recovery_key": recovery_key, "recovery_key_display": "one_time_only_store_offline"}


@app.post("/api/v1/auth/login")
def login(payload: LoginRequest) -> dict[str, Any]:
    verify_fresh(payload.timestamp, payload.nonce)
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE username=?", (payload.username,)).fetchone()
        device = conn.execute("SELECT * FROM devices WHERE id=? AND status='active'", (payload.device_id,)).fetchone()
        if not user or user["status"] != "active" or not device:
            raise HTTPException(401, "invalid_credentials_or_device")
        associated = conn.execute("SELECT 1 FROM user_devices WHERE user_id=? AND device_id=? AND status='active'", (user["id"], device["id"])).fetchone()
        if not associated:
            raise HTTPException(401, "device_not_associated")
        try:
            PASSWORDS.verify(user["password_hash"], payload.password)
        except (VerifyMismatchError, VerificationError):
            audit(conn, user["id"], "auth.login", user["id"], "denied", {"reason": "invalid_credentials"})
            raise HTTPException(401, "invalid_credentials_or_device")
        message = f"LOGIN\n{user['username']}\n{device['id']}\n{payload.timestamp}\n{payload.nonce}".encode()
        verify_signature(device["public_key_pem"], message, payload.signature)
        # Password hashing/verification and signature verification are complete before
        # taking SQLite's write lock. Recheck mutable identity state after the lock.
        try:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute("""SELECT u.id,u.username,u.role,u.status,u.credential_version,
                    d.status AS device_status,
                    EXISTS(SELECT 1 FROM user_devices ud WHERE ud.user_id=u.id AND ud.device_id=d.id AND ud.status='active') AS association_active
                FROM users u JOIN devices d ON d.id=? WHERE u.id=?""", (payload.device_id, user["id"])).fetchone()
            if (not current or current["status"] != "active" or current["device_status"] != "active"
                    or not current["association_active"]
                    or current["credential_version"] != user["credential_version"]):
                conn.rollback()
                raise HTTPException(401, "invalid_credentials_or_device")
            consume_nonce(conn, payload.device_id, payload.nonce, payload.timestamp)
            bearer = secrets.token_urlsafe(48)
            now = int(time.time())
            conn.execute("INSERT INTO sessions(token_sha256,user_id,device_id,created_at,expires_at,revoked_at,credential_version) VALUES(?,?,?,?,?,NULL,?)",
                         (token_hash(bearer), current["id"], payload.device_id, now, now + SESSION_TTL, current["credential_version"]))
            audit(conn, current["id"], "auth.login", current["id"], "success", {"device_id": payload.device_id})
            conn.commit()
        except HTTPException:
            if conn.in_transaction:
                conn.rollback()
            raise
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
    return {"access_token": bearer, "token_type": "Bearer", "expires_in": SESSION_TTL, "device_id": payload.device_id, "user": {"id": current["id"], "username": current["username"], "role": current["role"]}}


@app.post("/api/v1/auth/password-device-login", status_code=201)
def password_device_login(payload: PasswordDeviceLoginRequest, request: Request) -> dict[str, Any]:
    """Register this browser's Ed25519 identity after the account password proves authority.

    This is intentionally the user-visible recovery/login path for a new device.
    TLS protects the password in transit; only a key proof and a password hash
    are included in the signed canonical message. The password is never logged.
    """
    verify_fresh(payload.timestamp, payload.nonce)
    username = payload.username.strip()
    if not username or any(ord(char) < 32 or ord(char) == 127 for char in username):
        raise HTTPException(401, "invalid_credentials_or_device")
    key = load_public_key(payload.public_key_pem)
    public_der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    public_hash = hashlib.sha256(public_der).hexdigest()
    password_hash = hashlib.sha256(payload.password.encode("utf-8")).hexdigest()
    canonical = (f"PASSWORD-DEVICE-LOGIN\n{username}\n{payload.timestamp}\n{payload.nonce}\n"
                 f"{password_hash}\n{public_hash}").encode("utf-8")
    try:
        key.verify(bytes.fromhex(payload.signature), canonical)
    except (ValueError, InvalidSignature) as exc:
        raise HTTPException(401, "invalid_credentials_or_device") from exc

    now = int(time.time())
    source_hash = token_hash(request_source_ip(request))
    account_hash = token_hash(username.casefold())
    with db() as conn:
        conn.execute("DELETE FROM password_device_attempts WHERE attempted_at < ?", (now - 3600,))
        recent = conn.execute("SELECT COUNT(*) FROM password_device_attempts WHERE ip_hash=? AND attempted_at>=?",
                              (source_hash, now - 300)).fetchone()[0]
        account_recent = conn.execute("SELECT COUNT(*) FROM password_device_attempts WHERE account_hash=? AND attempted_at>=?",
                                      (account_hash, now - 300)).fetchone()[0]
        if recent >= 10 or account_recent >= 10:
            raise HTTPException(429, "login_attempts_limited")
        conn.execute("INSERT INTO password_device_attempts(ip_hash,account_hash,attempted_at) VALUES(?,?,?)",
                     (source_hash, account_hash, now))
        user = conn.execute("SELECT * FROM users WHERE username=? AND status='active'", (username,)).fetchone()
        try:
            password_ok = bool(user and PASSWORDS.verify(user["password_hash"], payload.password))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            password_ok = False
        if not password_ok:
            if user:
                audit(conn, user["id"], "auth.password_device_login", None, "denied", {"reason": "invalid_credentials"})
            raise HTTPException(401, "invalid_credentials_or_device")

        try:
            conn.execute("BEGIN IMMEDIATE")
            current_user = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
            if not current_user or current_user["status"] != "active" or current_user["credential_version"] != user["credential_version"]:
                conn.rollback()
                raise HTTPException(401, "invalid_credentials_or_device")
            device = conn.execute("SELECT * FROM devices WHERE public_key_sha256=?", (public_hash,)).fetchone()
            if device:
                association = conn.execute("SELECT status FROM user_devices WHERE user_id=? AND device_id=?",
                                           (current_user["id"], device["id"])).fetchone()
                if device["status"] != "active" or not association or association["status"] != "active":
                    conn.rollback()
                    raise HTTPException(401, "invalid_credentials_or_device")
                device_id = device["id"]
            else:
                device_id = str(uuid.uuid4())
                conn.execute("INSERT INTO devices(id,public_key_pem,public_key_sha256,mac_declared,mac_status,status,created_at) VALUES(?,?,?,?,?,'active',?)",
                             (device_id, payload.public_key_pem, public_hash, "unknown", "declared", utcnow()))
                conn.execute("INSERT INTO user_devices(user_id,device_id,status,created_at) VALUES(?,?,'active',?)",
                             (current_user["id"], device_id, utcnow()))
            consume_nonce(conn, device_id, payload.nonce, payload.timestamp)
            bearer = secrets.token_urlsafe(48)
            conn.execute("INSERT INTO sessions(token_sha256,user_id,device_id,created_at,expires_at,revoked_at,credential_version) VALUES(?,?,?,?,?,NULL,?)",
                         (token_hash(bearer), current_user["id"], device_id, now, now + SESSION_TTL, current_user["credential_version"]))
            audit(conn, current_user["id"], "auth.password_device_login", device_id, "success", {"device_id": device_id})
            conn.commit()
        except HTTPException:
            if conn.in_transaction:
                conn.rollback()
            raise
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
    return {"access_token": bearer, "token_type": "Bearer", "expires_in": SESSION_TTL,
            "device_id": device_id, "user": {"id": current_user["id"], "username": current_user["username"], "role": current_user["role"]}}


@app.post("/api/v1/auth/device-login")
def device_login(payload: DeviceLoginRequest) -> dict[str, Any]:
    """Issue a session to an already-associated device after a fresh key proof."""
    verify_fresh(payload.timestamp, payload.nonce)
    with db() as conn:
        device = conn.execute("SELECT * FROM devices WHERE id=? AND status='active'", (payload.device_id,)).fetchone()
        if not device:
            raise HTTPException(401, "invalid_device")
        message = (f"DEVICE-LOGIN\n{payload.user_id}\n{device['id']}\n{payload.timestamp}\n{payload.nonce}"
                   if payload.user_id else f"DEVICE-LOGIN\n{device['id']}\n{payload.timestamp}\n{payload.nonce}").encode()
        verify_signature(device["public_key_pem"], message, payload.signature)
        try:
            conn.execute("BEGIN IMMEDIATE")
            if payload.user_id:
                actor = conn.execute("""SELECT u.id,u.username,u.role,u.status,u.credential_version,d.status AS device_status
                    FROM users u JOIN user_devices ud ON ud.user_id=u.id JOIN devices d ON d.id=ud.device_id
                    WHERE d.id=? AND u.id=? AND ud.status='active' AND u.status='active'""", (device["id"], payload.user_id)).fetchone()
            else:
                matches = conn.execute("""SELECT u.id,u.username,u.role,u.status,u.credential_version,d.status AS device_status
                    FROM users u JOIN user_devices ud ON ud.user_id=u.id JOIN devices d ON d.id=ud.device_id
                    WHERE d.id=? AND ud.status='active' AND u.status='active' LIMIT 2""", (device["id"],)).fetchall()
                actor = matches[0] if len(matches) == 1 else None
            if not actor or actor["device_status"] != "active":
                conn.rollback()
                raise HTTPException(401, "invalid_device")
            consume_nonce(conn, device["id"], payload.nonce, payload.timestamp)
            bearer = secrets.token_urlsafe(48)
            now = int(time.time())
            conn.execute("INSERT INTO sessions(token_sha256,user_id,device_id,created_at,expires_at,revoked_at,credential_version) VALUES(?,?,?,?,?,NULL,?)",
                         (token_hash(bearer), actor["id"], device["id"], now, now + SESSION_TTL, actor["credential_version"]))
            audit(conn, actor["id"], "auth.device_login", actor["id"], "success", {"device_id": device["id"]})
            conn.commit()
        except HTTPException:
            if conn.in_transaction:
                conn.rollback()
            raise
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
    return {"access_token": bearer, "token_type": "Bearer", "expires_in": SESSION_TTL,
            "device_id": device["id"], "user": {"id": actor["id"], "username": actor["username"], "role": actor["role"]}}


@app.post("/api/v1/auth/logout")
def logout(session: dict[str, Any] = Depends(current_session), authorization: str | None = Header(default=None)) -> dict[str, str]:
    with db() as conn:
        conn.execute("UPDATE sessions SET revoked_at=? WHERE token_sha256=? AND revoked_at IS NULL", (int(time.time()), token_hash(authorization[7:].strip())))
        deleted = conn.execute("DELETE FROM user_presence WHERE user_id=? AND device_id=?", (session["user_id"], session["device_id"])).rowcount
        if deleted:
            audit(conn, session["user_id"], "presence.logout_invalidation", session["device_id"], "success")
        audit(conn, session["user_id"], "auth.logout", session["user_id"], "success")
    return {"status": "revoked"}


def _presence_response(row: sqlite3.Row | None, now: int) -> dict[str, Any]:
    if row is None:
        return {"state": "unknown", "last_seen_at": None, "expires_at": None, "connection_method": "unknown"}
    state = "online" if int(row["expires_at"]) > now else "offline"
    iso = lambda value: datetime.fromtimestamp(int(value), timezone.utc).isoformat(timespec="seconds")
    return {"state": state, "last_seen_at": iso(row["last_seen"]), "expires_at": iso(row["expires_at"]), "connection_method": "unknown"}


@app.post("/api/v1/presence/heartbeat")
def presence_heartbeat(session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
    """Refresh this authenticated session's device presence; no target identity is accepted."""
    now = int(time.time())
    with db() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            actor = _revalidate_actor(conn, session, "read")
            previous = conn.execute("SELECT last_seen,expires_at FROM user_presence WHERE user_id=? AND device_id=?", (actor["user_id"], actor["device_id"])).fetchone()
            if previous and int(previous["expires_at"]) > now and now - int(previous["last_seen"]) < PRESENCE_MIN_INTERVAL_SECONDS:
                conn.commit()
                return {"state": "online", "last_seen_at": datetime.fromtimestamp(int(previous["last_seen"]), timezone.utc).isoformat(timespec="seconds"), "expires_at": datetime.fromtimestamp(int(previous["expires_at"]), timezone.utc).isoformat(timespec="seconds"), "connection_method": "unknown", "ttl_seconds": PRESENCE_TTL_SECONDS, "throttled": True}
            conn.execute("""INSERT INTO user_presence(user_id,device_id,last_seen,expires_at,connection_method)
                VALUES(?,?,?,?, 'unknown') ON CONFLICT(user_id,device_id) DO UPDATE SET
                last_seen=excluded.last_seen, expires_at=excluded.expires_at, connection_method='unknown'""",
                (actor["user_id"], actor["device_id"], now, now + PRESENCE_TTL_SECONDS))
            if not previous or int(previous["expires_at"]) <= now:
                audit(conn, actor["user_id"], "presence.online", actor["device_id"], "success", {"ttl_seconds": PRESENCE_TTL_SECONDS})
            conn.commit()
        except HTTPException:
            if conn.in_transaction: conn.rollback()
            raise
        except Exception:
            if conn.in_transaction: conn.rollback()
            raise
    return {"state": "online", "last_seen_at": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds"), "expires_at": datetime.fromtimestamp(now + PRESENCE_TTL_SECONDS, timezone.utc).isoformat(timespec="seconds"), "connection_method": "unknown", "ttl_seconds": PRESENCE_TTL_SECONDS, "throttled": False}


@app.get("/api/v1/presence/me")
def presence_me(session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
    """Read presence for the caller's own user/device pair only."""
    now = int(time.time())
    with db() as conn:
        _revalidate_actor(conn, session, "read")
        row = conn.execute("SELECT last_seen,expires_at,connection_method FROM user_presence WHERE user_id=? AND device_id=?", (session["user_id"], session["device_id"])).fetchone()
    return _presence_response(row, now)


@app.post("/api/v1/users", status_code=201)
def create_user(payload: CreateUser, session: dict[str, Any] = Depends(require_permission("manage_users"))) -> dict[str, Any]:
    if payload.role not in ROLES:
        raise HTTPException(422, "invalid_role")
    if payload.role == "owner":
        with db() as conn:
            audit(conn, session["user_id"], "user.owner_creation_attempt", payload.username, "denied",
                  {"reason": "owner_creation_requires_bootstrap_or_local_recovery"})
        raise HTTPException(403, "owner_creation_requires_bootstrap_or_local_recovery")
    # Argon2 hashing is deliberately completed before acquiring the SQLite write lock.
    password_hash = PASSWORDS.hash(payload.password)
    with db() as conn:
        uid = str(uuid.uuid4())
        try:
            conn.execute("BEGIN IMMEDIATE")
            actor = _revalidate_actor(conn, session, "manage_users")
            device = conn.execute("SELECT id FROM devices WHERE id=? AND status='active'", (payload.device_id,)).fetchone()
            if not device:
                raise HTTPException(422, "active_device_required")
            try:
                conn.execute("INSERT INTO users(id,account_id,username,password_hash,role,status,created_at) VALUES(?,?,?,?,?,'active',?)",
                             (uid, str(uuid.uuid4()), payload.username, password_hash, payload.role, utcnow()))
                conn.execute("INSERT INTO user_devices(user_id,device_id,status,created_at) VALUES(?,?,'active',?)", (uid, payload.device_id, utcnow()))
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise HTTPException(409, "username_or_association_conflict") from exc
            audit(conn, actor["user_id"], "user.created", uid, "success", {"role": payload.role, "device_id": payload.device_id})
            conn.commit()
        except HTTPException:
            if conn.in_transaction:
                conn.rollback()
            raise
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
    return {"id": uid, "username": payload.username, "role": payload.role, "device_id": payload.device_id}


@app.get("/api/v1/users")
def list_users(session: dict[str, Any] = Depends(require_permission("manage_users"))) -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT id,username,role,status,created_at FROM users ORDER BY created_at").fetchall()
    return {"users": [dict(r) for r in rows]}


def _record_denial(conn: sqlite3.Connection, actor_id: str | None, action: str,
                   target_id: str, reason: str, status_code: int, error: str,
                   extra_details: dict | None = None) -> None:
    """Persist a denial before returning its HTTP error; never include secrets."""
    details = {"reason": reason, **(extra_details or {})}
    audit(conn, actor_id, action, target_id, "denied", details)
    conn.commit()
    raise HTTPException(status_code, error)


def _reauthenticated_owner(conn: sqlite3.Connection, session: dict[str, Any],
                           current_password: str, action: str, target_id: str) -> sqlite3.Row:
    actor = conn.execute("SELECT id,username,password_hash,role,status,credential_version FROM users WHERE id=?",
                         (session["user_id"],)).fetchone()
    if not actor or actor["status"] != "active" or actor["role"] != "owner":
        _record_denial(conn, session.get("user_id"), action, target_id,
                       "actor_not_active_owner", 403, "permission_denied")
    live_session = conn.execute("""SELECT s.revoked_at,s.expires_at,s.credential_version,d.status AS device_status
        FROM sessions s JOIN devices d ON d.id=s.device_id
        WHERE s.token_sha256=? AND s.user_id=?""",
        (session["token_sha256"], actor["id"])).fetchone()
    if (not live_session or live_session["revoked_at"] is not None
            or live_session["expires_at"] < int(time.time())
            or live_session["device_status"] != "active"
            or live_session["credential_version"] != actor["credential_version"]):
        _record_denial(conn, actor["id"], action, target_id,
                       "session_no_longer_valid", 401, "session_invalid_or_expired")
    try:
        password_ok = PASSWORDS.verify(actor["password_hash"], current_password)
    except (InvalidHashError, VerifyMismatchError, VerificationError, TypeError, ValueError):
        password_ok = False
    if not password_ok:
        _record_denial(conn, actor["id"], action, target_id,
                       "reauthentication_failed", 401, "reauthentication_failed")
    return actor


@app.patch("/api/v1/users/{user_id}/role")
def change_user_role(user_id: str, payload: ChangeUserRole,
                     session: dict[str, Any] = Depends(current_session)) -> dict[str, str]:
    action = "user.role_changed"
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        actor = _reauthenticated_owner(conn, session, payload.current_password, action, user_id)
        if payload.role not in ROLES:
            _record_denial(conn, actor["id"], action, user_id,
                           "invalid_role", 400, "invalid_role")
        if user_id == actor["id"]:
            extra = {}
            if actor["role"] == "owner" and actor["status"] == "active" and payload.role != "owner":
                count = conn.execute("SELECT COUNT(*) FROM users WHERE role='owner' AND status='active'").fetchone()[0]
                if count <= 1:
                    extra["invariant"] = "last_active_owner_protected"
            _record_denial(conn, actor["id"], action, user_id,
                           "self_role_change_forbidden", 403, "self_role_change_forbidden", extra)
        target = conn.execute("SELECT id,role,status FROM users WHERE id=?", (user_id,)).fetchone()
        if not target:
            _record_denial(conn, actor["id"], action, user_id,
                           "user_not_found", 404, "user_not_found")
        if target["role"] == "owner" and target["status"] == "active" and payload.role != "owner":
            active_owners = conn.execute("SELECT COUNT(*) FROM users WHERE role='owner' AND status='active'").fetchone()[0]
            if active_owners <= 1:
                _record_denial(conn, actor["id"], action, user_id,
                               "last_active_owner_protected", 409, "last_active_owner_protected")
        old_role = target["role"]
        try:
            conn.execute("UPDATE users SET role=? WHERE id=?", (payload.role, user_id))
            if old_role == "owner" and payload.role != "owner":
                invalidated = conn.execute("UPDATE owner_recovery_keys SET status='consumed',consumed_at=? WHERE owner_user_id=? AND status='active'",
                                           (utcnow(), user_id)).rowcount
                if invalidated:
                    audit(conn, actor["id"], "owner.recovery_key_invalidated", user_id, "success", {"reason": "owner_role_removed"})
            audit(conn, actor["id"], action, user_id, "success",
                  {"previous_role": old_role, "new_role": payload.role})
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            if "last_active_owner_protected" in str(exc):
                conn.execute("BEGIN IMMEDIATE")
                _record_denial(conn, actor["id"], action, user_id,
                               "last_active_owner_protected", 409, "last_active_owner_protected")
            # Best-effort operational audit after rollback. If audit storage itself
            # is unavailable, the role change remains rolled back and the API fails closed.
            try:
                conn.execute("BEGIN IMMEDIATE")
                audit(conn, actor["id"], "user.role_change_failed", user_id, "failed",
                      {"reason": "database_operation_or_audit_failure"})
                conn.commit()
            except sqlite3.Error:
                conn.rollback()
            raise
    return {"id": user_id, "role": payload.role, "status": "updated"}


@app.patch("/api/v1/users/{user_id}/status")
def change_user_status(user_id: str, payload: ChangeUserStatus,
                       session: dict[str, Any] = Depends(current_session)) -> dict[str, str]:
    action = "user.status_changed"
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        actor = _reauthenticated_owner(conn, session, payload.current_password, action, user_id)
        if payload.status not in {"active", "revoked"}:
            _record_denial(conn, actor["id"], action, user_id,
                           "invalid_status", 400, "invalid_status")
        if user_id == actor["id"] and payload.status != "active":
            extra = {}
            if actor["role"] == "owner" and actor["status"] == "active":
                count = conn.execute("SELECT COUNT(*) FROM users WHERE role='owner' AND status='active'").fetchone()[0]
                if count <= 1:
                    extra["invariant"] = "last_active_owner_protected"
            _record_denial(conn, actor["id"], action, user_id,
                           "self_deactivation_forbidden", 403, "self_deactivation_forbidden", extra)
        target = conn.execute("SELECT id,role,status FROM users WHERE id=?", (user_id,)).fetchone()
        if not target:
            _record_denial(conn, actor["id"], action, user_id,
                           "user_not_found", 404, "user_not_found")
        if target["role"] == "owner" and target["status"] == "active" and payload.status != "active":
            active_owners = conn.execute("SELECT COUNT(*) FROM users WHERE role='owner' AND status='active'").fetchone()[0]
            if active_owners <= 1:
                _record_denial(conn, actor["id"], action, user_id,
                               "last_active_owner_protected", 409, "last_active_owner_protected")
        old_status = target["status"]
        try:
            if old_status != payload.status:
                # Advance the generation on every real status transition. In particular,
                # a login begun before deactivation cannot survive a later reactivation,
                # including if deactivation used the legacy owner-only revoke route.
                conn.execute("UPDATE users SET status=?,credential_version=credential_version+1 WHERE id=?", (payload.status, user_id))
            else:
                conn.execute("UPDATE users SET status=? WHERE id=?", (payload.status, user_id))
            if payload.status != "active":
                invalidated = conn.execute("UPDATE owner_recovery_keys SET status='consumed',consumed_at=? WHERE owner_user_id=? AND status='active'",
                                           (utcnow(), user_id)).rowcount
                if invalidated:
                    audit(conn, actor["id"], "owner.recovery_key_invalidated", user_id, "success", {"reason": "account_deactivated"})
                now = int(time.time())
                conn.execute("UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                             (now, user_id))
                conn.execute("UPDATE user_devices SET status='revoked' WHERE user_id=?", (user_id,))
            elif old_status != "active":
                # Reactivation restores eligible device associations, but never old sessions.
                conn.execute("UPDATE user_devices SET status='active' WHERE user_id=? AND EXISTS "
                             "(SELECT 1 FROM devices WHERE devices.id=user_devices.device_id AND devices.status='active')",
                             (user_id,))
            audit(conn, actor["id"], action, user_id, "success",
                  {"previous_status": old_status, "new_status": payload.status})
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            if "last_active_owner_protected" in str(exc):
                conn.execute("BEGIN IMMEDIATE")
                _record_denial(conn, actor["id"], action, user_id,
                               "last_active_owner_protected", 409, "last_active_owner_protected")
            try:
                conn.execute("BEGIN IMMEDIATE")
                audit(conn, actor["id"], "user.status_change_failed", user_id, "failed",
                      {"reason": "database_operation_or_audit_failure"})
                conn.commit()
            except sqlite3.Error:
                conn.rollback()
            raise
    return {"id": user_id, "status": payload.status, "updated": "true"}


def _gateway_identity() -> tuple[Ed25519PrivateKey, str, str]:
    """Load a pre-provisioned Gateway Ed25519 identity; never auto-create or rotate it."""
    private_path = Path(os.environ.get("SOLARMINER_GATEWAY_IDENTITY_PRIVATE_KEY", "/var/lib/solarminer/gateway-identity.key"))
    public_path = Path(os.environ.get("SOLARMINER_GATEWAY_IDENTITY_PUBLIC_KEY", "/etc/solarminer/gateway-identity.pub.pem"))
    try:
        if os.name == "posix" and private_path.exists() and (private_path.stat().st_mode & 0o077):
            raise HTTPException(503, "gateway_identity_private_key_permissions_invalid")
        private = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
        public = serialization.load_pem_public_key(public_path.read_bytes())
    except Exception as exc:
        raise HTTPException(503, "gateway_identity_not_configured; invite_creation_disabled") from exc
    if not isinstance(private, Ed25519PrivateKey) or not isinstance(public, Ed25519PublicKey):
        raise HTTPException(503, "gateway_ed25519_identity_required")
    derived = private.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    configured = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if not secrets.compare_digest(derived, configured):
        raise HTTPException(503, "gateway_identity_key_mismatch")
    fp = hashlib.sha256(configured).hexdigest()
    return private, public_path.read_text(encoding="utf-8"), fp


def _gateway_qr_fingerprint() -> str:
    """Fingerprint of a provisioned Gateway identity key, not a /health response."""
    return _gateway_identity()[2]


@app.get("/api/v1/gateway/identity")
def gateway_identity_challenge(timestamp: int, nonce: str) -> dict[str, Any]:
    verify_fresh(timestamp, nonce)
    private, public_pem, fp = _gateway_identity()
    canonical = f"GET\n/api/v1/gateway/identity\n{timestamp}\n{nonce}".encode()
    return {"public_key_pem": public_pem, "fingerprint_sha256": fp, "timestamp": timestamp,
            "nonce": nonce, "signature": private.sign(canonical).hex(), "signature_algorithm": "Ed25519"}


def _invite_qr_svg(payload: dict[str, Any]) -> str:
    """Render a self-contained SVG QR locally; no third-party network service is used."""
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
    except ImportError as exc:
        raise HTTPException(503, "qr_generation_dependency_unavailable") from exc
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=5, border=4, image_factory=SvgPathImage)
    qr.add_data(encoded)
    qr.make(fit=True)
    return qr.make_image().to_string().decode("utf-8")


@app.post("/api/v1/invites", status_code=201)
def create_invite(payload: CreateInvite, request: Request,
                  session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
    if payload.role not in {"viewer", "operator", "guest"}:
        raise HTTPException(422, "invite_role_not_allowed")
    role = "viewer" if payload.role == "guest" else payload.role
    # Fail closed if the deployment has not configured a separately trusted Gateway identity.
    fp = _gateway_qr_fingerprint()
    public_url = os.environ.get("SOLARMINER_PUBLIC_URL", "").strip()
    if not public_url.startswith("https://") or len(public_url) > 2048:
        raise HTTPException(503, "gateway_https_url_not_configured; invite_creation_disabled")
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            conn.rollback()
            raise HTTPException(403, "owner_only")
        token = secrets.token_urlsafe(32)
        invite_id = str(uuid.uuid4())
        now = int(time.time())
        ttl = int(os.environ.get("SOLARMINER_INVITE_TTL_SECONDS", "43200"))
        if not 300 <= ttl <= 604800:
            conn.rollback()
            raise HTTPException(503, "invite_ttl_configuration_invalid")
        expires = now + ttl
        conn.execute("INSERT INTO invites(id,token_hash,owner_id,role,label,created_at,expires_at) VALUES(?,?,?,?,?,?,?)",
                     (invite_id, token_hash(token), actor["user_id"], role, payload.label.strip(), now, expires))
        qr = {"v": 1, "url": public_url.rstrip("/"), "token": token, "fp": fp, "exp": expires}
        # Render before commit so a missing QR dependency cannot strand an active invite
        # whose one-time secret was never delivered to the Owner.
        qr_svg = _invite_qr_svg(qr)
        audit(conn, actor["user_id"], "invite.created", invite_id, "success", {"role": role, "expires_at": expires})
        conn.commit()
    return {"invite_id": invite_id, "token": token, "qr_payload": qr, "qr_svg": qr_svg, "expires_at": expires, "role": role, "label": payload.label.strip()}


@app.get("/api/v1/invites")
def list_invites(session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_only")
        now = int(time.time())
        rows = conn.execute("SELECT id,role,label,created_at,expires_at,used_at,revoked_at,owner_id FROM invites ORDER BY created_at DESC LIMIT 500").fetchall()
    items = []
    for row in rows:
        state = "revoked" if row["revoked_at"] else "used" if row["used_at"] else "expired" if row["expires_at"] < now else "pending"
        items.append({"invite_id": row["id"], "role": row["role"], "label": row["label"], "created_at": row["created_at"], "expires_at": row["expires_at"], "used_at": row["used_at"], "revoked_at": row["revoked_at"], "state": state})
    return {"invites": items}


@app.post("/api/v1/invites/{invite_id}/revoke")
def revoke_invite(invite_id: str, session: dict[str, Any] = Depends(current_session)) -> dict[str, str]:
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            conn.rollback()
            raise HTTPException(403, "owner_only")
        row = conn.execute("SELECT * FROM invites WHERE id=?", (invite_id,)).fetchone()
        if not row:
            conn.rollback()
            raise HTTPException(404, "invite_not_found")
        if row["used_at"] is not None or row["revoked_at"] is not None or row["expires_at"] < int(time.time()):
            conn.rollback()
            raise HTTPException(409, "invite_not_pending")
        now = int(time.time())
        conn.execute("UPDATE invites SET revoked_at=?,revoked_by=? WHERE id=? AND used_at IS NULL AND revoked_at IS NULL",
                     (now, actor["user_id"], invite_id))
        audit(conn, actor["user_id"], "invite.revoked", invite_id, "success")
        conn.commit()
    return {"status": "revoked"}


@app.post("/api/v1/invites/redeem", status_code=201)
def redeem_invite(payload: RedeemInvite, request: Request) -> dict[str, Any]:
    now = int(time.time())
    try:
        verify_fresh(payload.timestamp, payload.nonce)
        mac = normalize_mac(payload.mac)
        pubkey = load_public_key(payload.client_pubkey_pem)
    except HTTPException:
        raise
    digest = token_hash(payload.invite_token)
    ip_hash = token_hash(request_source_ip(request))
    # Small local rate limit; only hashes of source IPs are retained.
    with db() as conn:
        conn.execute("DELETE FROM invite_attempts WHERE attempted_at < ?", (now - 3600,))
        attempts = conn.execute("SELECT COUNT(*) FROM invite_attempts WHERE ip_hash=? AND attempted_at>=?", (ip_hash, now - 300)).fetchone()[0]
        if attempts >= 20:
            audit(conn, None, "invite.redeem", None, "denied", {"reason": "rate_limited"})
            raise HTTPException(429, "invite_rate_limited")
        conn.execute("INSERT INTO invite_attempts(ip_hash,attempted_at) VALUES(?,?)", (ip_hash, now))
        invite = conn.execute("SELECT * FROM invites WHERE token_hash=?", (digest,)).fetchone()
        if not invite or invite["used_at"] is not None or invite["revoked_at"] is not None or invite["expires_at"] < now:
            audit(conn, None, "invite.redeem", None, "denied", {"reason": "invalid_or_expired"})
            raise HTTPException(400, "invite_invalid_expired_or_used")
        pub_der = pubkey.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        pub_digest = hashlib.sha256(pub_der).hexdigest()
        canonical = "\n".join(["POST", "/api/v1/invites/redeem", str(payload.timestamp), payload.nonce,
            digest, payload.username, hashlib.sha256(payload.password.encode()).hexdigest(), mac, pub_digest]).encode()
        try:
            pubkey.verify(bytes.fromhex(payload.signature), canonical)
        except (ValueError, InvalidSignature) as exc:
            audit(conn, None, "invite.redeem", invite["id"], "denied", {"reason": "signature_invalid"})
            raise HTTPException(401, "invite_signature_invalid") from exc
        try:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute("SELECT * FROM invites WHERE id=?", (invite["id"],)).fetchone()
            if not current or current["used_at"] is not None or current["revoked_at"] is not None or current["expires_at"] < int(time.time()):
                conn.rollback()
                raise HTTPException(409, "invite_already_consumed_or_invalid")
            try:
                conn.execute("INSERT INTO invite_nonces(token_hash,nonce,timestamp) VALUES(?,?,?)", (digest, payload.nonce, payload.timestamp))
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise HTTPException(401, "nonce_replayed") from exc
            conn.execute("DELETE FROM invite_nonces WHERE timestamp < ?", (int(time.time()) - NONCE_WINDOW - 60,))
            if conn.execute("SELECT 1 FROM users WHERE username=?", (payload.username,)).fetchone():
                conn.rollback()
                raise HTTPException(409, "username_unavailable")
            user_id, device_id = str(uuid.uuid4()), str(uuid.uuid4())
            account_id = str(uuid.uuid4())
            password_hash = PASSWORDS.hash(payload.password)
            conn.execute("INSERT INTO users(id,account_id,username,password_hash,role,status,created_at) VALUES(?,?,?,?,?,'active',?)",
                         (user_id, account_id, payload.username, password_hash, current["role"], utcnow()))
            conn.execute("INSERT INTO devices(id,public_key_pem,public_key_sha256,mac_declared,mac_status,status,created_at) VALUES(?,?,?,?, 'declared','active',?)",
                         (device_id, payload.client_pubkey_pem, pub_digest, mac, utcnow()))
            conn.execute("INSERT INTO user_devices(user_id,device_id,status,created_at) VALUES(?,?,'active',?)", (user_id, device_id, utcnow()))
            bearer = secrets.token_urlsafe(48)
            conn.execute("INSERT INTO sessions(token_sha256,user_id,device_id,created_at,expires_at,revoked_at,credential_version) VALUES(?,?,?,?,?,NULL,1)",
                         (token_hash(bearer), user_id, device_id, now, now + SESSION_TTL))
            changed = conn.execute("UPDATE invites SET used_at=? WHERE id=? AND used_at IS NULL AND revoked_at IS NULL AND expires_at>=?", (now, current["id"], now)).rowcount
            if changed != 1:
                conn.rollback()
                raise HTTPException(409, "invite_already_consumed_or_invalid")
            audit(conn, user_id, "invite.redeemed", current["id"], "success", {"device_id": device_id, "role": current["role"]})
            conn.commit()
        except HTTPException:
            if conn.in_transaction: conn.rollback()
            raise
        except Exception:
            if conn.in_transaction: conn.rollback()
            raise
    return {"access_token": bearer, "token_type": "Bearer", "expires_in": SESSION_TTL, "device_id": device_id,
            "user": {"id": user_id, "username": payload.username, "role": current["role"]}}


def _update_state_write(conn: sqlite3.Connection, state: str, target_version: str | None, details: dict[str, Any]) -> str:
    now = int(time.time())
    op = str(uuid.uuid4())
    conn.execute("INSERT INTO update_operations(id,state,installed_version,target_version,created_at,updated_at,details_json) VALUES(?,?,?,?,?,?,?)",
                 (op, state, PACKAGE_VERSION, target_version, now, now, json.dumps(details, separators=(",", ":"))))
    return op


def _check_system_update_manifest(manifest_url: str, session: dict[str, Any], *,
                                  manifest_origins: set[str] | None = None,
                                  package_origins: set[str] | None = None,
                                  repository_url: str | None = None) -> dict[str, Any]:
    key_path = os.environ.get("SOLARMINER_RELEASE_PUBLIC_KEY", "/etc/solarminer/release-pubkey.pem")
    try:
        parsed = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(manifest_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise update_manager.UpdateValidationError("manifest_url_not_authorized_https")
        manifest_origin = update_manager.normalize_https_origin(
            f"https://{parsed.hostname}" + (f":{parsed.port}" if parsed.port else ""))
        allowed_manifest_origins = manifest_origins or {manifest_origin}
        if manifest_origin not in allowed_manifest_origins:
            raise update_manager.UpdateValidationError("manifest_origin_not_authorized")
        request = __import__("urllib.request", fromlist=["Request"]).Request(
            manifest_url, headers={"Accept": "application/json", "User-Agent": "SolarMiner-CODE02/0.6.70"})
        with update_manager.open_allowed_https_url(request, allowed_manifest_origins, timeout=8) as response:
            final = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(response.geturl())
            final_origin = (update_manager.normalize_https_origin(
                f"https://{final.hostname}" + (f":{final.port}" if final.port else ""))
                if final.scheme == "https" and final.hostname else "")
            if final_origin not in allowed_manifest_origins:
                raise update_manager.UpdateValidationError("manifest_redirect_origin_changed")
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise update_manager.UpdateValidationError("manifest_too_large")
        manifest = json.loads(raw)
        key = update_manager.load_release_key(key_path)
        checked = update_manager.verify_manifest(manifest, key, PACKAGE_VERSION)
        comparison = subprocess.run(
            ["/usr/bin/dpkg", "--compare-versions", manifest["version"], "gt", PACKAGE_VERSION],
            capture_output=True, timeout=3, check=False)
        if comparison.returncode == 1:
            with db() as conn:
                conn.execute("BEGIN IMMEDIATE")
                op = _update_state_write(conn, "CURRENT", manifest["version"],
                    {"latest_version": manifest["version"], "signature_valid": True,
                     "repository_url": repository_url})
                audit(conn, session["user_id"], "system.update.check_current", op, "success",
                      {"latest_version": manifest["version"], "repository_url": repository_url})
                conn.commit()
            return {"status": "current", "operation_id": op,
                    "installed_version": PACKAGE_VERSION, "latest_version": manifest["version"],
                    "signature_valid": True, "compatible": True,
                    "activation_available": False, "message": "gateway_already_at_or_newer_than_release",
                    **({"repository_url": repository_url} if repository_url else {})}
        if comparison.returncode != 0:
            raise update_manager.UpdateValidationError("release_version_comparison_failed")
        package_origin = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(manifest["package_url"])
        package_origin_value = update_manager.normalize_https_origin(
            f"https://{package_origin.hostname}" + (f":{package_origin.port}" if package_origin.port else "")) if package_origin.hostname else ""
        allowed_package_origins = package_origins or {manifest_origin}
        if package_origin_value not in allowed_package_origins:
            raise update_manager.UpdateValidationError("package_origin_not_authorized")
        data_dir = Path(os.environ.get("SOLARMINER_DATA_DIR", "/var/lib/solarminer"))
        free = shutil.disk_usage(data_dir if data_dir.exists() else data_dir.parent).free
        needed = int(manifest["package_size"]) * 2 + 64 * 1024 * 1024
        if free < needed:
            raise update_manager.UpdateValidationError("insufficient_disk_space")
        package_dir = data_dir / "releases" / "verified"
        package_path = update_manager.download_and_verify_package(manifest, package_dir, allowed_package_origins)
        manifest_path = package_path.with_suffix(package_path.suffix + ".manifest.json")
        manifest_tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
        manifest_tmp.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        os.chmod(manifest_tmp, 0o600)
        with manifest_tmp.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(manifest_tmp, manifest_path)
        try:
            preflight = update_helper_client.request("preflight")
            activation_available = preflight.get("status") == "ready"
        except (OSError, RuntimeError, TimeoutError, ValueError):
            activation_available = False
        details = {"manifest_signature": "valid", "package_sha256": checked["sha256"],
                   "package_path": str(package_path), "manifest_path": str(manifest_path),
                   "space_required": needed, "activation_available": activation_available}
        if repository_url:
            details["repository_url"] = repository_url
        with db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            op = _update_state_write(conn, "VERIFIED", manifest["version"], details)
            audit(conn, session["user_id"], "system.update.package_verified", op, "success",
                  {"version": manifest["version"], "sha256": checked["sha256"],
                   "activation_available": activation_available, "repository_url": repository_url})
            conn.commit()
        result = {"status": "verified_staged", "operation_id": op, "installed_version": PACKAGE_VERSION,
                  "available_version": manifest["version"], "changelog": manifest["changelog"],
                  "size": checked["package_size"], "sha256": checked["sha256"],
                  "signature_valid": True, "compatible": True, "space_required": needed,
                  "migration_requirements": manifest["migration_requirements"],
                  "activation_available": activation_available,
                  "message": "signed_package_ready_for_apply" if activation_available else "package_verified_but_independent_recovery_preflight_failed"}
        if repository_url:
            result["repository_url"] = repository_url
        return result
    except (update_manager.UpdateValidationError, ValueError, OSError, sqlite3.Error, TimeoutError, subprocess.TimeoutExpired) as exc:
        reason = str(exc) if isinstance(exc, update_manager.UpdateValidationError) else type(exc).__name__
        LOG.error("Signed Gateway update check failed reason=%s", reason)
        with db() as conn:
            op = _update_state_write(conn, "FAILED", None, {"reason": reason})
            audit(conn, session["user_id"], "system.update.manifest_rejected", op, "denied",
                  {"reason": reason[:120], "repository_url": repository_url})
        return {"status": "rejected", "installed_version": PACKAGE_VERSION, "signature_valid": False,
                "compatible": False, "message": reason, "activation_available": False,
                **({"repository_url": repository_url} if repository_url else {})}


@app.get("/api/v1/system/update/check")
def check_system_update(session: dict[str, Any] = Depends(require_permission("read"))) -> dict[str, Any]:
    manifest_url = os.environ.get("SOLARMINER_RELEASE_MANIFEST_URL", "").strip()
    if not manifest_url:
        return {"status": "not_configured", "installed_version": PACKAGE_VERSION, "available_version": None,
                "signature_valid": False, "compatible": False, "message": "release_origin_not_configured", "activation_available": False}
    return _check_system_update_manifest(manifest_url, session)


@app.get("/api/v1/system/update/source")
def read_system_update_source(session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_only")
        row = conn.execute("SELECT value FROM system_state WHERE key='update_repository_url'").fetchone()
    allowlist_path = os.environ.get("SOLARMINER_UPDATE_SOURCE_ALLOWLIST", update_manager.DEFAULT_UPDATE_SOURCES_PATH)
    try:
        sources = update_manager.list_update_sources(allowlist_path)
    except update_manager.UpdateValidationError:
        sources = []
    allowed = [item["repository_url"] for item in sources]
    selected = row["value"] if row and row["value"] in allowed else (allowed[0] if allowed else "")
    return {"repository_url": selected, "allowed_repositories": allowed,
            "policy": "administrative_allowlist"}


def _read_tailscale_status() -> dict[str, Any]:
    """Read sanitized Tailscale identity through the root-owned broker socket."""
    try:
        status_data = update_helper_client.request("tailscale_status")
    except (OSError, RuntimeError, ValueError):
        return {"installed": False, "connected": False, "dns_name": None, "https_url": None,
                "helper_available": False, "certificate_valid": False, "nginx_config_valid": False,
                "nginx_active": False, "gateway_active": False}
    if not isinstance(status_data, dict):
        return {"installed": False, "connected": False, "dns_name": None, "https_url": None,
                "helper_available": False, "certificate_valid": False, "nginx_config_valid": False,
                "nginx_active": False, "gateway_active": False}
    return {**{key: status_data.get(key) for key in ("installed", "connected", "dns_name", "https_url",
              "certificate_valid", "nginx_config_valid", "nginx_config_error", "nginx_active", "gateway_active")},
            "helper_available": True}


def _start_tailscale_auth() -> dict[str, Any]:
    """Start Tailscale through the root-owned broker and expose only a login URL."""
    try:
        payload = update_helper_client.request("tailscale_connect")
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(503, "tailscale_start_unavailable") from exc
    auth_url = payload.get("auth_url")
    if auth_url is not None and (not isinstance(auth_url, str) or
            not re.fullmatch(r"https://login\.tailscale\.com/a/[A-Za-z0-9_-]{6,128}", auth_url)):
        raise HTTPException(503, "tailscale_start_unavailable")
    return {"started": True, "connected": payload.get("connected") is True, "auth_url": auth_url}


def _normalize_tailscale_endpoint(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 253:
        raise HTTPException(422, "invalid_tailscale_endpoint")
    try:
        parsed = urlsplit(value.strip())
        hostname = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(422, "invalid_tailscale_endpoint") from exc
    if (parsed.scheme.lower() != "https" or not hostname.endswith(".ts.net") or
            parsed.username or parsed.password or port not in (None, 443) or
            parsed.path not in ("", "/") or parsed.query or parsed.fragment or
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.ts\.net", hostname)):
        raise HTTPException(422, "invalid_tailscale_endpoint")
    return f"https://{hostname}"


@app.get("/api/v1/system/tailscale")
def read_tailscale_access(session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_only")
        row = conn.execute("SELECT value FROM system_state WHERE key='tailscale_endpoint'").fetchone()
    status_data = _read_tailscale_status()
    detected = status_data.get("https_url") if status_data.get("connected") else None
    configured = row["value"] if row else None
    endpoint = configured or detected
    # The periodic certificate job issues a cert for the live MagicDNS name.
    # Stale files from a previous Tailnet identity must not be reported as ready.
    tls_ready = bool(endpoint and detected and endpoint == detected and
                     status_data.get("certificate_valid") is True and
                     status_data.get("nginx_config_valid") is True and
                     status_data.get("nginx_active") is True and
                     status_data.get("gateway_active") is True)
    return {"installed": bool(status_data.get("installed")), "connected": bool(status_data.get("connected")),
            "dns_name": status_data.get("dns_name"), "detected_endpoint": detected,
            "configured_endpoint": configured, "endpoint": endpoint, "https_ready": tls_ready,
            "checks": {key: status_data.get(key) is True for key in
                       ("certificate_valid", "nginx_config_valid", "nginx_active", "gateway_active")},
            "nginx_config_error": status_data.get("nginx_config_error", ""),
            "helper_available": status_data.get("helper_available") is True,
            "router_ports_required": False,
            "note": "O Gateway tem de ser autorizado no Tailnet; a emissão HTTPS exige MagicDNS e HTTPS Certificates ativos no painel Tailscale."}


@app.get("/api/v1/system/console")
def read_gateway_console(session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_only")
    try:
        result = update_helper_client.request("diagnostics")
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(503, "gateway_console_unavailable") from exc
    logs = result.get("logs")
    if result.get("status") != "ok" or not isinstance(logs, str):
        raise HTTPException(503, "gateway_console_unavailable")
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_only")
        audit(conn, actor["user_id"], "system.console.logs_read", "allowlisted_gateway_services", "success",
              {"characters": len(logs), "truncated": result.get("truncated") is True})
    services = result.get("services")
    resources = result.get("resources")
    return {"state": "available", "captured_at": utcnow(), "logs": logs,
            "services": services if isinstance(services, dict) else {},
            "resources": resources if isinstance(resources, dict) else {},
            "truncated": result.get("truncated") is True,
            "scope": "Allowlisted Gateway service status, CPU/RAM/storage metrics and service logs; recent Tailscale/Nginx setup log tail."}


@app.post("/api/v1/system/tailscale/connect")
def start_tailscale_connection(session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_only")
    result = _start_tailscale_auth()
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_only")
        audit(conn, actor["user_id"], "system.tailscale.auth_started", "tailscale_up", "success",
              {"connected": result["connected"], "auth_url_present": bool(result["auth_url"])})
    return result


@app.put("/api/v1/system/tailscale")
def configure_tailscale_access(payload: dict[str, Any], session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
    if set(payload) != {"endpoint"} or (payload["endpoint"] is not None and not isinstance(payload["endpoint"], str)):
        raise HTTPException(422, "invalid_tailscale_endpoint_request")
    endpoint = _normalize_tailscale_endpoint(payload["endpoint"]) if payload["endpoint"] else None
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            conn.rollback()
            raise HTTPException(403, "owner_only")
        if endpoint is None:
            conn.execute("DELETE FROM system_state WHERE key='tailscale_endpoint'")
        else:
            conn.execute("INSERT INTO system_state(key,value) VALUES('tailscale_endpoint',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (endpoint,))
        audit(conn, actor["user_id"], "system.tailscale.endpoint_configured", endpoint or "automatic", "success",
              {"configured": endpoint is not None})
        conn.commit()
    return read_tailscale_access(session)


@app.post("/api/v1/system/update/check")
def check_system_update_from_repository(payload: dict[str, Any], session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
    if payload != {"repository_url": payload.get("repository_url")} or not isinstance(payload.get("repository_url"), str):
        raise HTTPException(422, "invalid_update_source_request")
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_only")
    allowlist_path = os.environ.get("SOLARMINER_UPDATE_SOURCE_ALLOWLIST", update_manager.DEFAULT_UPDATE_SOURCES_PATH)
    try:
        source = update_manager.load_update_source(payload["repository_url"], allowlist_path)
        with db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            actor = _revalidate_actor(conn, session, "manage_gateway")
            if actor["role"] != "owner":
                conn.rollback()
                raise HTTPException(403, "owner_only")
            conn.execute("INSERT INTO system_state(key,value) VALUES('update_repository_url',?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (source["repository_url"],))
            audit(conn, actor["user_id"], "system.update.source_changed", source["repository_url"], "success")
            conn.commit()
    except update_manager.UpdateValidationError as exc:
        reason = str(exc)
        with db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            op = _update_state_write(conn, "FAILED", None, {"reason": reason})
            audit(conn, session["user_id"], "system.update.source_rejected", op, "denied",
                  {"reason": reason[:120]})
            conn.commit()
        return {"status": "rejected", "installed_version": PACKAGE_VERSION, "signature_valid": False,
                "compatible": False, "message": reason, "activation_available": False}
    return _check_system_update_manifest(source["manifest_url"], session,
        manifest_origins=source["manifest_origins"], package_origins=source["package_origins"],
        repository_url=source["repository_url"])


@app.get("/api/v1/system/update/status")
def system_update_status(session: dict[str, Any] = Depends(require_permission("read"))) -> dict[str, Any]:
    # Timestamps are stored at whole-second precision. Break ties by SQLite
    # insertion order so a fast verify/apply cycle cannot surface an older
    # operation (for example a previous rollback) as the current status.
    with db() as conn:
        row = conn.execute("SELECT * FROM update_operations ORDER BY updated_at DESC, rowid DESC LIMIT 1").fetchone()
    if not row:
        return {"status": "IDLE", "installed_version": PACKAGE_VERSION, "activation_available": False}
    return {"operation_id": row["id"], "status": row["state"], "installed_version": row["installed_version"],
            "target_version": row["target_version"], "created_at": row["created_at"], "updated_at": row["updated_at"],
            "details": json.loads(row["details_json"]),
            "activation_available": bool(json.loads(row["details_json"]).get("activation_available", False))}


@app.post("/api/v1/system/update/apply", status_code=202)
def apply_system_update(payload: dict[str, Any], session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
    if payload != {"version": payload.get("version"), "confirm": True} or not isinstance(payload.get("version"), str):
        raise HTTPException(422, "invalid_update_apply_request")
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            conn.rollback()
            raise HTTPException(403, "owner_only")
        row = conn.execute("SELECT id,state,target_version FROM update_operations ORDER BY updated_at DESC, rowid DESC LIMIT 1").fetchone()
        if not row:
            audit(conn, actor["user_id"], "system.update.apply_rejected", payload["version"], "denied", {"reason": "update_activation_disabled_until_independent_recovery_deployment_is_ready"})
            conn.commit()
            raise HTTPException(503, "update_activation_disabled_until_independent_recovery_deployment_is_ready")
        if row["state"] != "VERIFIED" or row["target_version"] != payload["version"]:
            audit(conn, actor["user_id"], "system.update.apply_rejected", payload["version"], "denied", {"reason": "verified_update_operation_not_found"})
            conn.commit()
            raise HTTPException(409, "verified_update_operation_not_found")
        op_id = row["id"]
        audit(conn, actor["user_id"], "system.update.apply_queued", op_id, "success", {"target_version": payload["version"]})
        conn.commit()
    try:
        response = update_helper_client.request("enqueue", op_id)
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        raise HTTPException(503, str(exc)[:180] or "update_helper_unavailable_or_timed_out") from exc
    if not isinstance(response, dict) or response.get("operation_id") != op_id or response.get("status") != "APPLY_QUEUED":
        raise HTTPException(503, "update_helper_did_not_confirm_queue")
    return response


@app.post("/api/v1/devices/pairing-codes", status_code=201)
def create_device_pairing_code(payload: CreatePairingCode,
                               session: dict[str, Any] = Depends(require_permission("manage_devices"))) -> dict[str, Any]:
    """Issue a short-lived, single-use pairing code after administrator authentication."""
    raw_code = secrets.token_urlsafe(32)
    now = int(time.time())
    with db() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            actor = _revalidate_actor(conn, session, "manage_devices")
            target = conn.execute("SELECT id,username,status FROM users WHERE username=?", (payload.username,)).fetchone()
            if not target or target["status"] != "active":
                conn.rollback()
                raise HTTPException(404, "active_target_user_not_found")
            conn.execute("DELETE FROM device_pairing_codes WHERE used_at IS NOT NULL OR expires_at < ?", (now,))
            conn.execute("INSERT INTO device_pairing_codes(token_sha256,created_by_user_id,target_user_id,created_at,expires_at,used_at) VALUES(?,?,?,?,?,NULL)",
                         (token_hash(raw_code), actor["user_id"], target["id"], now, now + payload.expires_in))
            audit(conn, actor["user_id"], "device.pairing_code_issued", target["id"], "success",
                  {"target_username": target["username"], "expires_in": payload.expires_in})
            conn.commit()
        except HTTPException:
            if conn.in_transaction:
                conn.rollback()
            raise
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
    # The raw code is returned exactly once; only its SHA-256 digest is persisted.
    return {"pairing_code": raw_code, "target_username": payload.username,
            "expires_in": payload.expires_in, "expires_at": now + payload.expires_in,
            "single_use": True}


@app.post("/api/v1/devices/pair", status_code=201)
def pair_device(payload: ConsumePairingCode) -> dict[str, Any]:
    """Consume an administrator-issued code and bind the client's Ed25519 public key."""
    verify_fresh(payload.timestamp, payload.nonce)
    mac = normalize_mac(payload.mac)
    key = load_public_key(payload.public_key_pem)
    public_der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    public_digest = hashlib.sha256(public_der).hexdigest()
    canonical = f"PAIR\n{payload.pairing_code}\n{public_digest}\n{mac}\n{payload.timestamp}\n{payload.nonce}".encode()
    verify_signature(payload.public_key_pem, canonical, payload.signature)
    now = int(time.time())
    with db() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            pairing = conn.execute("""SELECT pc.*,u.username,u.status AS target_status
                FROM device_pairing_codes pc JOIN users u ON u.id=pc.target_user_id
                WHERE pc.token_sha256=?""", (token_hash(payload.pairing_code),)).fetchone()
            if not pairing or pairing["used_at"] is not None or pairing["expires_at"] < now or pairing["target_status"] != "active":
                conn.rollback()
                raise HTTPException(401, "pairing_code_invalid_expired_or_used")
            device_id = str(uuid.uuid4())
            try:
                conn.execute("INSERT INTO devices(id,public_key_pem,public_key_sha256,mac_declared,mac_status,status,created_at) VALUES(?,?,?,?,?,'active',?)",
                             (device_id, payload.public_key_pem, public_digest, mac, "declared", utcnow()))
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise HTTPException(409, "device_public_key_already_registered") from exc
            conn.execute("INSERT INTO user_devices(user_id,device_id,status,created_at) VALUES(?,?, 'active', ?)",
                         (pairing["target_user_id"], device_id, utcnow()))
            consume_nonce(conn, device_id, payload.nonce, payload.timestamp)
            conn.execute("UPDATE device_pairing_codes SET used_at=? WHERE token_sha256=? AND used_at IS NULL",
                         (now, token_hash(payload.pairing_code)))
            audit(conn, pairing["created_by_user_id"], "device.paired", device_id, "success",
                  {"target_user_id": pairing["target_user_id"], "target_username": pairing["username"],
                   "mac_status": "declared", "public_key_sha256": public_digest})
            conn.commit()
        except HTTPException:
            if conn.in_transaction:
                conn.rollback()
            raise
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
    return {"device_id": device_id, "username": pairing["username"], "status": "active",
            "association_status": "active", "mac_status": "declared", "public_key_sha256": public_digest}


@app.post("/api/v1/devices", status_code=201)
def create_device(payload: CreateDevice, session: dict[str, Any] = Depends(require_permission("manage_devices"))) -> dict[str, Any]:
    mac = normalize_mac(payload.mac)
    if payload.mac_status not in {"declared", "verified"}:
        raise HTTPException(422, "invalid_mac_status")
    if payload.mac_status == "verified":
        raise HTTPException(403, "independent_mac_verification_procedure_not_implemented")
    key = load_public_key(payload.public_key_pem)
    digest = hashlib.sha256(key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()
    did = str(uuid.uuid4())
    with db() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            actor = _revalidate_actor(conn, session, "manage_devices")
            try:
                conn.execute("INSERT INTO devices(id,public_key_pem,public_key_sha256,mac_declared,mac_status,status,created_at) VALUES(?,?,?,?,?,'active',?)",
                             (did, payload.public_key_pem, digest, mac, "declared", utcnow()))
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise HTTPException(409, "device_public_key_already_registered") from exc
            audit(conn, actor["user_id"], "device.created", did, "success", {"mac_status": "declared"})
            conn.commit()
        except HTTPException:
            if conn.in_transaction:
                conn.rollback()
            raise
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
    return {"id": did, "mac": mac, "mac_status": "declared", "status": "active", "public_key_sha256": digest}


@app.post("/api/v1/devices/{device_id}/revoke")
def revoke_device(device_id: str, session: dict[str, Any] = Depends(require_permission("manage_devices"))) -> dict[str, str]:
    with db() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            actor = _revalidate_actor(conn, session, "manage_devices")
            row = conn.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone()
            if not row:
                conn.rollback(); raise HTTPException(404, "device_not_found")
            conn.execute("UPDATE devices SET status='revoked' WHERE id=?", (device_id,))
            conn.execute("UPDATE user_devices SET status='revoked' WHERE device_id=?", (device_id,))
            conn.execute("UPDATE sessions SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL", (int(time.time()), device_id))
            audit(conn, actor["user_id"], "device.revoked", device_id, "success")
            conn.commit()
        except HTTPException:
            if conn.in_transaction:
                conn.rollback()
            raise
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
    return {"status": "revoked"}


@app.post("/api/v1/users/{user_id}/revoke")
def revoke_user(user_id: str, payload: RevokeUserRequest | None = None,
                session: dict[str, Any] = Depends(current_session)) -> dict[str, str]:
    # This legacy route changes the same account status as PATCH /status. Keep it
    # owner-only and require reauthentication so it cannot bypass A1b safeguards.
    action = "user.revoke"
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        actor = _reauthenticated_owner(conn, session, payload.current_password if payload else "", action, user_id)
        if user_id == actor["id"]:
            extra = {}
            if actor["role"] == "owner" and actor["status"] == "active":
                count = conn.execute("SELECT COUNT(*) FROM users WHERE role='owner' AND status='active'").fetchone()[0]
                if count <= 1:
                    extra["invariant"] = "last_active_owner_protected"
            _record_denial(conn, actor["id"], action, user_id,
                           "self_deactivation_forbidden", 403, "self_deactivation_forbidden", extra)
        user = conn.execute("SELECT role,status FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            _record_denial(conn, actor["id"], action, user_id,
                           "user_not_found", 404, "user_not_found")
        if user["role"] == "owner" and user["status"] == "active":
            count = conn.execute("SELECT COUNT(*) FROM users WHERE role='owner' AND status='active'").fetchone()[0]
            if count <= 1:
                _record_denial(conn, actor["id"], action, user_id,
                              "last_active_owner_protected", 409, "last_active_owner_protected")
        try:
            conn.execute("UPDATE users SET status='revoked' WHERE id=?", (user_id,))
            invalidated = conn.execute("UPDATE owner_recovery_keys SET status='consumed',consumed_at=? WHERE owner_user_id=? AND status='active'",
                                       (utcnow(), user_id)).rowcount
            if invalidated:
                audit(conn, actor["id"], "owner.recovery_key_invalidated", user_id, "success", {"reason": "account_deactivated"})
            conn.execute("UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                         (int(time.time()), user_id))
            conn.execute("UPDATE user_devices SET status='revoked' WHERE user_id=?", (user_id,))
            audit(conn, actor["id"], action, user_id, "success",
                  {"previous_status": user["status"], "new_status": "revoked"})
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            if "last_active_owner_protected" in str(exc):
                conn.execute("BEGIN IMMEDIATE")
                _record_denial(conn, actor["id"], action, user_id,
                              "last_active_owner_protected", 409, "last_active_owner_protected")
            try:
                conn.execute("BEGIN IMMEDIATE")
                audit(conn, actor["id"], "user.revoke_failed", user_id, "failed",
                      {"reason": "database_operation_or_audit_failure"})
                conn.commit()
            except sqlite3.Error:
                conn.rollback()
            raise
    return {"status": "revoked"}


@app.get("/api/v1/audit")
def read_audit(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT id,occurred_at,actor_user_id,action,target,outcome,details_json FROM audit ORDER BY id DESC LIMIT 500").fetchall()
    return {"events": [{**dict(r), "details": json.loads(r["details_json"])} for r in rows]}


# Serve the independent The Solar Miner PWA from the Gateway's own HTTPS origin.
# Exact static routes avoid a catch-all mount changing unknown API paths from 404
# to 405 and keep the existing API/RBAC route semantics intact.
_module_path = Path(__file__).resolve()
_source_pwa_dir = _module_path.parents[2] / "web" / "pwa"
_packaged_pwa_dir = _module_path.parents[3] / "share" / "solarminer" / "pwa"
_installed_pwa_dir = Path(os.environ.get("SOLARMINER_PWA_DIR", "/usr/share/solarminer/pwa"))
_default_pwa_dir = _source_pwa_dir if _source_pwa_dir.is_dir() else (_packaged_pwa_dir if _packaged_pwa_dir.is_dir() else _installed_pwa_dir)
_pwa_dir = Path(os.environ.get("SOLARMINER_PWA_DIR", str(_default_pwa_dir)))

def _pwa_file(asset: str) -> FileResponse:
    allowed = {"index.html", "styles.css", "app.js", "app-core.js", "api-client.js", "manifest.webmanifest", "service-worker.js",
               "assets/icon.svg", "assets/icon-192.png", "assets/icon-512.png", "assets/heic2any-0.0.4.min.js", "auth-client.js"}
    allowed.update({"gateway-connection.js", "gateway-auth.js", "workspace-ui.js", "features-v053.js", "demo-mode.js"})
    if asset not in allowed:
        raise HTTPException(404, "pwa_asset_not_found")
    path = (_pwa_dir / asset).resolve()
    if _pwa_dir.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404, "pwa_asset_not_found")
    media_type = "application/manifest+json" if asset.endswith(".webmanifest") else None
    return FileResponse(path, media_type=media_type)

def _pwa_endpoint(asset: str):
    def endpoint() -> FileResponse:
        return _pwa_file(asset)
    return endpoint

if _pwa_dir.is_dir():
    app.add_api_route("/", _pwa_endpoint("index.html"), methods=["GET"], include_in_schema=False, name="the-solar-miner-pwa")
    for _asset in ("styles.css", "app.js", "app-core.js", "api-client.js", "manifest.webmanifest", "service-worker.js",
                   "assets/icon.svg", "assets/icon-192.png", "assets/icon-512.png", "assets/heic2any-0.0.4.min.js", "auth-client.js",
                   "gateway-connection.js", "gateway-auth.js", "workspace-ui.js", "features-v053.js", "demo-mode.js"):
        app.add_api_route("/" + _asset, _pwa_endpoint(_asset), methods=["GET"], include_in_schema=False, name="pwa-" + _asset.replace("/", "-"))
else:
    LOG.error("The Solar Miner PWA assets are unavailable; static UI routes were not registered")


def main() -> None:
    import uvicorn
    cert = os.environ.get("SOLARMINER_TLS_CERT", str(DATA_DIR / "server.crt"))
    key = os.environ.get("SOLARMINER_TLS_KEY", str(DATA_DIR / "server.key"))
    host = os.environ.get("SOLARMINER_HOST", "127.0.0.1")
    port = int(os.environ.get("SOLARMINER_PORT", "8443"))
    if not Path(cert).is_file() or not Path(key).is_file():
        LOG.critical("TLS certificate/key missing; refusing to start without TLS")
        raise SystemExit(2)
    os.chmod(key, 0o600)
    uvicorn.run(app, host=host, port=port, ssl_certfile=cert, ssl_keyfile=key, log_config=None, access_log=False)


if __name__ == "__main__":
    main()
