from __future__ import annotations

import hashlib
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
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
from . import updates as update_manager

VERSION = "0.6.0"  # Public API compatibility contract; package version is tracked separately.
PACKAGE_VERSION = "0.6.10"
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
 consumed_at INTEGER, state TEXT NOT NULL
);
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


def normalize_mac(value: str) -> str:
    if not isinstance(value, str) or not MAC_RE.fullmatch(value):
        raise HTTPException(422, "invalid_mac")
    return value.upper()


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


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize()
    yield


app = FastAPI(title="SolarMiner Gateway", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
# Cross-origin development is opt-in and exact-origin allow-listed. Production PWA
# is served by this same origin and does not require CORS.
_CORS_ORIGINS = [item.strip() for item in os.environ.get("SOLARMINER_CORS_ORIGINS", "").split(",") if item.strip()]
if _CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=_CORS_ORIGINS, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=["Authorization", "Content-Type", "Accept"])


@app.middleware("http")
async def security_response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.path.startswith("/api/v1/"):
        response.headers["Cache-Control"] = "no-store"
    if request.url.path in {"/", "/index.html", "/app.js", "/app-core.js", "/api-client.js", "/auth-client.js", "/styles.css", "/manifest.webmanifest", "/service-worker.js"} or request.url.path.startswith("/assets/"):
        response.headers["Content-Security-Policy"] = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self' http://localhost:* http://127.0.0.1:*; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
    return response


class BootstrapOwner(BaseModel):
    bootstrap_token: str = Field(min_length=32, max_length=256)
    username: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=1024)
    mac: str
    public_key_pem: str = Field(min_length=80, max_length=8192)
    signature: str = Field(min_length=80, max_length=256)
    timestamp: int
    nonce: str = Field(min_length=16, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str
    device_id: str
    timestamp: int
    nonce: str = Field(min_length=16, max_length=128)
    signature: str = Field(min_length=80, max_length=256)


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
    # Bootstrap is deliberately loopback-only; the operator must read the token locally.
    remote = request.client.host if request.client else ""
    if remote not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(403, "bootstrap_requires_local_access")
    mac = normalize_mac(payload.mac)
    verify_fresh(payload.timestamp, payload.nonce)
    key = load_public_key(payload.public_key_pem)
    canonical = f"BOOTSTRAP\n{payload.username}\n{mac}\n{payload.timestamp}\n{payload.nonce}".encode()
    try:
        key.verify(bytes.fromhex(payload.signature), canonical)
    except (ValueError, InvalidSignature) as exc:
        raise HTTPException(401, "device_signature_invalid") from exc
    pub_der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    pub_hash = hashlib.sha256(pub_der).hexdigest()
    from .recovery import generate_recovery_key, recovery_verifier
    recovery_key, recovery_raw = generate_recovery_key()
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        state = conn.execute("SELECT value FROM system_state WHERE key='bootstrap_state'").fetchone()
        token = conn.execute("SELECT * FROM bootstrap WHERE id=1").fetchone()
        owner = conn.execute("SELECT 1 FROM users WHERE role='owner' AND status='active' LIMIT 1").fetchone()
        if owner or not state or state[0] not in {"BOOTSTRAP_PENDING", "OWNER_SETUP_REQUIRED"} or not token or token["consumed_at"] is not None:
            conn.rollback(); raise HTTPException(409, "bootstrap_unavailable")
        if token["expires_at"] < int(time.time()) or not secrets.compare_digest(token["token_sha256"], token_hash(payload.bootstrap_token)):
            conn.rollback(); raise HTTPException(401, "bootstrap_token_invalid_or_expired")
        try:
            uid, did = str(uuid.uuid4()), str(uuid.uuid4())
            conn.execute("INSERT INTO devices(id,public_key_pem,public_key_sha256,mac_declared,mac_status,status,created_at) VALUES(?,?,?,?,?,'active',?)",
                         (did, payload.public_key_pem, pub_hash, mac, "declared", utcnow()))
            consume_nonce(conn, did, payload.nonce, payload.timestamp)
            conn.execute("INSERT INTO users(id,account_id,username,password_hash,role,status,created_at) VALUES(?,?,?,?, 'owner','active',?)",
                         (uid, str(uuid.uuid4()), payload.username, PASSWORDS.hash(payload.password), utcnow()))
            conn.execute("INSERT INTO user_devices(user_id,device_id,status,created_at) VALUES(?,?,'active',?)", (uid, did, utcnow()))
            conn.execute("INSERT INTO owner_recovery_keys(id,owner_user_id,verifier_sha256,generation,status,created_at,consumed_at) VALUES(?,?,?,?, 'active', ?, NULL)",
                         (str(uuid.uuid4()), uid, recovery_verifier(recovery_raw), 1, utcnow()))
            audit(conn, uid, "owner.recovery_key_issued", uid, "success", {"generation": 1, "source": "bootstrap"})
            conn.execute("UPDATE bootstrap SET consumed_at=?,state='consumed' WHERE id=1 AND consumed_at IS NULL", (int(time.time()),))
            conn.execute("UPDATE system_state SET value='OWNER_ACTIVE' WHERE key='bootstrap_state'")
            audit(conn, uid, "bootstrap.owner_created", uid, "success", {"device_id": did, "mac_status": "declared"})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    try:
        BOOTSTRAP_PATH.unlink(missing_ok=True)
    except OSError:
        LOG.error("Bootstrap token file cleanup failed after committed owner creation")
    return {"user_id": uid, "device_id": did, "role": "owner", "mac_status": "declared", "message": "owner_created",
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
    ip_hash = token_hash(request.client.host if request.client else "unknown")
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
            manifest_url, headers={"Accept": "application/json", "User-Agent": "SolarMiner-CODE02/0.6.10"})
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
        helper = os.environ.get("SOLARMINER_UPDATE_HELPER", "/usr/sbin/solarminer-update-apply")
        try:
            preflight = subprocess.run(["/usr/bin/sudo", "-n", helper, "--preflight"],
                                       capture_output=True, text=True, timeout=7, check=False)
            activation_available = preflight.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
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
    with db() as conn:
        row = conn.execute("SELECT * FROM update_operations ORDER BY updated_at DESC LIMIT 1").fetchone()
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
        row = conn.execute("SELECT id,state,target_version FROM update_operations ORDER BY updated_at DESC LIMIT 1").fetchone()
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
    helper = os.environ.get("SOLARMINER_UPDATE_HELPER", "/usr/sbin/solarminer-update-apply")
    try:
        result = subprocess.run(["/usr/bin/sudo", "-n", helper, "--enqueue", op_id],
                                capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(503, "update_helper_unavailable_or_timed_out") from exc
    if result.returncode != 0:
        reason = "update_pipeline_preflight_failed"
        try:
            error_body = json.loads(result.stderr or result.stdout)
            if isinstance(error_body, dict) and isinstance(error_body.get("reason"), str):
                reason = error_body["reason"][:180]
        except (json.JSONDecodeError, TypeError):
            pass
        raise HTTPException(503, reason)
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(503, "update_helper_response_invalid") from exc
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
               "assets/icon.svg", "assets/icon-192.png", "assets/icon-512.png", "auth-client.js"}
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
                   "assets/icon.svg", "assets/icon-192.png", "assets/icon-512.png", "auth-client.js"):
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
