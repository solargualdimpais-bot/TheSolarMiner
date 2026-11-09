from __future__ import annotations

import hashlib
import http.client
import ipaddress
import math
import asyncio
import base64
import csv
from html.parser import HTMLParser
import json
import logging
import io
import os
import re
import socket
import shutil
import secrets
import ssl
import subprocess
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import sqlite3
import threading
import time
import unicodedata
import uuid
import zipfile
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode, urlsplit
from urllib.request import Request as URLRequest, urlopen
from urllib.error import HTTPError, URLError

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
from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from . import connectors as connector_manager
from . import energy_registry
from . import energy_engine
from . import tuya_dps_registry
from . import site_profile
from . import integrations as hardware_integrations
from . import network_scanner
from . import shelly_credentials
from . import shelly_product_registry
from . import update_helper_client
from . import updates as update_manager
from . import error_reporting
from .error_reporting import install_error_queue_handler

VERSION = "0.6.0"  # Public API compatibility contract; package version is tracked separately.
PACKAGE_VERSION = "0.6.226"
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

# Deye polling is deliberately bounded to avoid overlapping slow Modbus reads.
_energy_sample_lock = threading.Lock()
_deye_read_lock = threading.Lock()
_deye_latency_state_lock = threading.Lock()
_deye_last_success_latency_seconds: float | None = None
_deye_next_poll_delay_seconds = 5.0
_last_deye_diagnostic_log_at = 0.0
_latest_deye_sample: dict[str, Any] | None = None
_recent_deye_samples: list[dict[str, Any]] = []
DEYE_IP_RECOVERY_AFTER_SECONDS = 60.0
DEYE_IP_RECOVERY_RETRY_SECONDS = 60.0
_deye_ip_recovery_lock = threading.Lock()
_deye_unreachable_since: dict[tuple[str, str, str, str], float] = {}
_deye_last_ip_recovery_attempt: dict[tuple[str, str, str, str], float] = {}
_tuya_last_diagnostic_log_at = 0.0
_dispatch_lock = threading.Lock()
_dispatch_last_sent: dict[str, tuple[str, float]] = {}
_deye_history_jobs_lock = threading.Lock()
_deye_history_jobs: dict[str, dict[str, Any]] = {}
_tesla_oauth_pending_lock = threading.Lock()
_tesla_oauth_pending: dict[str, dict[str, Any]] = {}


def _expire_tesla_oauth_pending(state: str) -> None:
    with _tesla_oauth_pending_lock:
        pending = _tesla_oauth_pending.get(state)
        if pending and pending.get("expires_at", 0) <= time.time():
            _tesla_oauth_pending.pop(state, None)
_shelly_blu_read_cache_lock = threading.Lock()
_shelly_blu_read_cache: dict[tuple[str, ...], tuple[float, list[dict[str, Any]], list[dict[str, Any]]]] = {}

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
CREATE TABLE IF NOT EXISTS network_device_inventory(
 mac TEXT PRIMARY KEY, name TEXT NOT NULL, device_type TEXT NOT NULL DEFAULT 'unknown',
 manufacturer TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '', last_ip TEXT NOT NULL DEFAULT '',
 product_id TEXT NOT NULL DEFAULT '',
 source_provider TEXT NOT NULL DEFAULT '', source_device_id TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_seen_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS gateway_device_inventory(
 device_key TEXT PRIMARY KEY, source_provider TEXT NOT NULL DEFAULT '', source_device_id TEXT NOT NULL DEFAULT '',
 source_links_json TEXT NOT NULL DEFAULT '[]', name TEXT NOT NULL, name_source TEXT NOT NULL DEFAULT 'source',
 device_type TEXT NOT NULL DEFAULT 'unknown', mac TEXT NOT NULL DEFAULT '', last_ip TEXT NOT NULL DEFAULT '',
 manufacturer TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '', product_id TEXT NOT NULL DEFAULT '',
 confirmation_status TEXT NOT NULL DEFAULT 'pending' CHECK(confirmation_status IN ('pending','confirmed')),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_seen_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS shelly_command_history(
 command_id TEXT PRIMARY KEY, device_id TEXT NOT NULL, channel_id INTEGER NOT NULL,
 requested_on INTEGER NOT NULL, command_state TEXT NOT NULL, observed_on INTEGER,
 occurred_at TEXT NOT NULL, completed_at TEXT
);
CREATE TABLE IF NOT EXISTS shelly_devices(
 device_id TEXT PRIMARY KEY, mac TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 host TEXT NOT NULL, model TEXT NOT NULL DEFAULT '', generation INTEGER NOT NULL,
 device_type TEXT NOT NULL DEFAULT 'smart',
 protocol TEXT NOT NULL, firmware TEXT NOT NULL DEFAULT '', capabilities_json TEXT NOT NULL DEFAULT '[]',
 room TEXT NOT NULL DEFAULT '', auth_ciphertext BLOB NOT NULL DEFAULT X'', enabled INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_seen_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS shelly_blu_devices(
 mac TEXT PRIMARY KEY, name TEXT NOT NULL, model TEXT NOT NULL DEFAULT '', device_type TEXT NOT NULL DEFAULT 'smart_sensor',
 bridge_mac TEXT NOT NULL, bridge_host TEXT NOT NULL, last_rssi INTEGER, values_json TEXT NOT NULL DEFAULT '[]',
 last_seen_at TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shelly_blu_scan_observations(
 bridge_mac TEXT NOT NULL, mac TEXT NOT NULL, observed_at REAL NOT NULL, details_json TEXT NOT NULL DEFAULT '{}',
 PRIMARY KEY(bridge_mac,mac)
);
CREATE INDEX IF NOT EXISTS idx_shelly_blu_scan_observations_age ON shelly_blu_scan_observations(observed_at);
CREATE INDEX IF NOT EXISTS idx_shelly_devices_host ON shelly_devices(host);
CREATE TABLE IF NOT EXISTS tuya_product_dps_map(
 protocol TEXT NOT NULL DEFAULT 'tuya', manufacturer TEXT NOT NULL DEFAULT 'Tuya',
 product_id TEXT NOT NULL, product_name TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',
 device_kind TEXT NOT NULL DEFAULT 'unknown', dps_id INTEGER NOT NULL, dps_code TEXT NOT NULL DEFAULT '',
 semantic_code TEXT NOT NULL DEFAULT 'unknown', description TEXT NOT NULL DEFAULT '',
 data_type TEXT NOT NULL DEFAULT 'unknown', unit TEXT, scale REAL, confidence TEXT NOT NULL DEFAULT 'UNKNOWN',
 source TEXT NOT NULL DEFAULT '', validation_status TEXT NOT NULL DEFAULT 'reference_only',
 read_supported INTEGER NOT NULL DEFAULT 1, write_supported INTEGER NOT NULL DEFAULT 0,
 updated_at TEXT NOT NULL, PRIMARY KEY(protocol, product_id, dps_id)
);
CREATE TABLE IF NOT EXISTS tuya_canonical_features(
 canonical_key TEXT PRIMARY KEY, display_name TEXT NOT NULL, category TEXT NOT NULL DEFAULT '',
 canonical_unit TEXT NOT NULL DEFAULT '', canonical_type TEXT NOT NULL DEFAULT 'unknown',
 units_json TEXT NOT NULL DEFAULT '[]', description TEXT NOT NULL DEFAULT '',
 source TEXT NOT NULL DEFAULT 'solarminer_registry', registry_version INTEGER NOT NULL DEFAULT 1,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS smart_product_catalog(
 manufacturer TEXT NOT NULL, protocol TEXT NOT NULL, product_code TEXT NOT NULL,
 product_name TEXT NOT NULL DEFAULT '', device_kind TEXT NOT NULL DEFAULT 'smart',
 capabilities_json TEXT NOT NULL DEFAULT '[]', source TEXT NOT NULL DEFAULT '',
 confidence TEXT NOT NULL DEFAULT 'observed', updated_at TEXT NOT NULL,
 PRIMARY KEY(manufacturer,protocol,product_code)
);
CREATE TABLE IF NOT EXISTS smart_product_profile_details(
 manufacturer TEXT NOT NULL, protocol TEXT NOT NULL, product_code TEXT NOT NULL,
 profile_json TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '', source_revision TEXT NOT NULL DEFAULT '',
 updated_at TEXT NOT NULL,
 PRIMARY KEY(manufacturer,protocol,product_code),
 FOREIGN KEY(manufacturer,protocol,product_code) REFERENCES smart_product_catalog(manufacturer,protocol,product_code)
);
CREATE TABLE IF NOT EXISTS smart_product_catalog_sources(
 source_key TEXT PRIMARY KEY, source_revision TEXT NOT NULL, imported_count INTEGER NOT NULL,
 imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shelly_product_profiles(
 manufacturer TEXT NOT NULL, protocol TEXT NOT NULL, product_code TEXT NOT NULL,
 product_name TEXT NOT NULL, generation INTEGER NOT NULL, device_kind TEXT NOT NULL,
 capabilities_json TEXT NOT NULL, metrics_json TEXT NOT NULL, commands_json TEXT NOT NULL,
 settings_sections_json TEXT NOT NULL, sources_json TEXT NOT NULL, confidence TEXT NOT NULL,
 updated_at TEXT NOT NULL, PRIMARY KEY(manufacturer,protocol,product_code)
);
CREATE INDEX IF NOT EXISTS idx_tuya_dps_category ON tuya_product_dps_map(protocol, category, device_kind, product_id);
CREATE TABLE IF NOT EXISTS tuya_product_identity(
 product_id TEXT NOT NULL, product TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',
 device_kind TEXT NOT NULL DEFAULT 'unknown', product_name_pt TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
 PRIMARY KEY(product_id,product,category,device_kind)
);
CREATE TABLE IF NOT EXISTS tuya_product_dps_map_scoped(
 product_id TEXT NOT NULL, product TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',
 device_kind TEXT NOT NULL DEFAULT 'unknown', dps_id INTEGER NOT NULL, dps_code TEXT NOT NULL DEFAULT '',
 semantic_code TEXT NOT NULL DEFAULT 'unknown', description TEXT NOT NULL DEFAULT '', data_type TEXT NOT NULL DEFAULT 'unknown',
 unit TEXT, scale REAL, write_supported INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
 PRIMARY KEY(product_id,product,category,device_kind,dps_id)
);
CREATE TABLE IF NOT EXISTS tuya_pid_dps_editor(
 product_id TEXT NOT NULL, dps_id INTEGER NOT NULL, payload_json TEXT NOT NULL,
 updated_at TEXT NOT NULL, PRIMARY KEY(product_id,dps_id)
);
CREATE TABLE IF NOT EXISTS tuya_pid_capabilities(
 product_id TEXT NOT NULL, source_kind TEXT NOT NULL CHECK(source_kind IN ('function','status')),
 code TEXT NOT NULL, payload_json TEXT NOT NULL, synchronized_at TEXT NOT NULL,
 PRIMARY KEY(product_id,source_kind,code)
);
CREATE TABLE IF NOT EXISTS device_card_templates(
 card_code TEXT PRIMARY KEY, manufacturer TEXT NOT NULL, protocol TEXT NOT NULL,
 product_id TEXT NOT NULL DEFAULT '', product_name TEXT NOT NULL DEFAULT '',
 available INTEGER NOT NULL DEFAULT 1, layout_json TEXT NOT NULL DEFAULT '{}',
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_device_card_templates_product
 ON device_card_templates(manufacturer,protocol,product_id);
CREATE TABLE IF NOT EXISTS device_card_assignments(
 device_id TEXT PRIMARY KEY, card_code TEXT NOT NULL REFERENCES device_card_templates(card_code),
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shelly_command_history_device_time ON shelly_command_history(device_id,occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_gateway_device_inventory_mac ON gateway_device_inventory(mac);
CREATE INDEX IF NOT EXISTS idx_gateway_device_inventory_status ON gateway_device_inventory(confirmation_status, name);
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


def _inventory_mac(value: Any) -> str:
    """Normalize saved MAC aliases to a single uppercase colon form."""
    if not isinstance(value, str):
        return ""
    compact = re.sub(r"[^0-9A-Fa-f]", "", value)
    if len(compact) != 12 or not re.fullmatch(r"[0-9A-Fa-f]{12}", compact):
        return ""
    compact = compact.upper()
    return ":".join(compact[index:index + 2] for index in range(0, 12, 2))


def _enrich_shelly_scan(report: dict[str, Any]) -> None:
    """Ask announced Shelly hosts for their authoritative full MAC identity."""
    for host in report.get("hosts", []):
        if not isinstance(host, dict):
            continue
        evidence = " ".join(str(host.get(key) or "") for key in
                            ("hostname", "friendly_name", "manufacturer", "model")).casefold()
        if "shelly" not in evidence:
            continue
        try:
            identity = hardware_integrations.shelly_integration.identify_and_read(str(host.get("ip") or ""))
            shelly_mac = _inventory_mac(identity.get("mac"))
            arp_mac = _inventory_mac(host.get("mac"))
            if shelly_mac and (not arp_mac or arp_mac == shelly_mac):
                host["mac"] = shelly_mac
                host["mac_source"] = "shelly_device_info"
                host["manufacturer"] = "Shelly"
                host["model"] = identity.get("model") or host.get("model")
                host["shelly_generation"] = identity.get("generation")
                host["protocol"] = identity.get("protocol")
                host["shelly_firmware"] = identity.get("firmware")
                host["discovery_methods"] = sorted(set(host.get("discovery_methods", [])) | {"shelly_device_info"})
                if "bluetooth" in identity.get("capabilities", []):
                    try:
                        bridge = hardware_integrations.shelly_integration.inspect_bluetooth_bridge(str(host.get("ip") or ""))
                        host["shelly_bluetooth_bridge"] = {
                            "candidate": bool(bridge.get("bridge_candidate")),
                            "bthome_discovery_api": bridge.get("bthome_discovery_api", "not_supported"),
                            "model": bridge.get("model") or identity.get("model"),
                            "firmware": bridge.get("firmware") or identity.get("firmware"),
                        }
                    except (OSError, ValueError, RuntimeError):
                        host["shelly_bluetooth_bridge"] = {"candidate": True, "bthome_discovery_api": "probe_failed"}
            elif shelly_mac and arp_mac and shelly_mac != arp_mac:
                host["identity_conflict"] = {"arp_mac": arp_mac, "device_mac": shelly_mac}
        except (OSError, ValueError, RuntimeError):
            continue


def _remember_shelly_blu_scan(conn: sqlite3.Connection, devices: list[dict[str, Any]]) -> None:
    """Keep short-lived proof that a bridge recently observed each sensor."""
    now = time.time()
    conn.execute("DELETE FROM shelly_blu_scan_observations WHERE observed_at<?", (now - 300,))
    for item in devices:
        if not isinstance(item, dict):
            continue
        bridge_mac, mac = _inventory_mac(item.get("bridge_mac")), _inventory_mac(item.get("mac"))
        if not bridge_mac or not mac:
            continue
        conn.execute("""INSERT INTO shelly_blu_scan_observations(bridge_mac,mac,observed_at,details_json)
            VALUES(?,?,?,?) ON CONFLICT(bridge_mac,mac) DO UPDATE SET observed_at=excluded.observed_at,
            details_json=excluded.details_json""",
            (bridge_mac, mac, now, json.dumps(item, separators=(",", ":"))))


def _recent_shelly_blu_scan_observations(conn: sqlite3.Connection, *, max_age_seconds: int = 300) -> list[dict[str, Any]]:
    """Return recent BLE observations without starting a blocking bridge scan."""
    cutoff = time.time() - max(1, int(max_age_seconds))
    rows = conn.execute("""SELECT mac,observed_at,details_json FROM shelly_blu_scan_observations
        WHERE observed_at>=? ORDER BY observed_at DESC""", (cutoff,)).fetchall()
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        mac = _inventory_mac(row["mac"])
        if not mac or mac in latest:
            continue
        try:
            item = json.loads(row["details_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(item, dict):
            latest[mac] = {**item, "mac": mac, "observed_at": float(row["observed_at"])}
    return list(latest.values())


def _scan_registered_shelly_blu_bridges(conn: sqlite3.Connection, *, duration_seconds: float = 30.0,
                                        bridge_macs: set[str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read nearby BLU advertisements through already registered local gateways."""
    rows = conn.execute("""SELECT mac,name,host,model,device_type,auth_ciphertext FROM shelly_devices
        WHERE enabled=1 AND (device_type IN ('smart_blugw','smart_gateway') OR model LIKE '%BLU Gateway%'
            OR model LIKE '%BLU GW%' OR model LIKE '%BLUGW%' OR model LIKE '%GWF-KZ01%' OR model LIKE '%SNGW-BT01%'
            OR upper(model) LIKE '%SN-GW-BT01%' OR upper(model) LIKE '%SN GW BT01%')
        ORDER BY name COLLATE NOCASE LIMIT 8""").fetchall()
    if bridge_macs is not None:
        wanted = {_inventory_mac(value) for value in bridge_macs if _inventory_mac(value)}
        rows = [row for row in rows if _inventory_mac(row["mac"]) in wanted]
    devices: dict[str, dict[str, Any]] = {}
    bridges: list[dict[str, Any]] = []
    for row in rows:
        bridge_mac = _inventory_mac(row["mac"])
        try:
            credentials = shelly_credentials.open_credentials(DATA_DIR, row["auth_ciphertext"] or b"")
            result = hardware_integrations.shelly_integration.discover_bluetooth_devices(
                str(row["host"] or ""), username=str(credentials.get("username") or ""),
                password=str(credentials.get("password") or ""), duration_seconds=duration_seconds)
        except (OSError, RuntimeError, ValueError) as exc:
            bridges.append({"mac": bridge_mac, "name": str(row["name"] or "Shelly BLU Gateway")[:120],
                            "state": "unavailable", "reason": str(exc)[:100]})
            continue
        bridge = result.get("bridge") if isinstance(result.get("bridge"), dict) else {}
        scan_diagnostic = result.get("diagnostic") if isinstance(result.get("diagnostic"), dict) else {}
        if scan_diagnostic:
            # Diagnostic contains only bridge-reported scanner state and RPC
            # error metadata; never credentials or script contents.
            LOG.info("Shelly BLU scan diagnostic mac=%s stage=%s result=%s",
                     bridge_mac, str(scan_diagnostic.get("stage") or "unknown")[:48],
                     json.dumps(scan_diagnostic, ensure_ascii=True, separators=(",", ":"))[:1200])
        bridges.append({"mac": bridge_mac or _inventory_mac(bridge.get("mac")),
                        "name": str(row["name"] or "Shelly BLU Gateway")[:120],
                        "model": str(bridge.get("model") or row["model"] or "")[:120],
                        "state": "scanned" if result.get("supported") else "unsupported",
                        "reason": str(result.get("reason") or "")[:100],
                        "diagnostic": scan_diagnostic})
        for item in result.get("devices", []) if isinstance(result.get("devices"), list) else []:
            if not isinstance(item, dict):
                continue
            mac = _inventory_mac(item.get("mac"))
            if not mac:
                continue
            current = devices.get(mac)
            if current is None or (int(item.get("rssi") or -127) > int(current.get("rssi") or -127)):
                devices[mac] = {**item, "bridge_mac": bridge_mac or _inventory_mac(item.get("bridge_mac")),
                                "bridge_host": str(row["host"] or item.get("bridge_host") or "")[:64],
                                "bridge_name": str(row["name"] or "Shelly BLU Gateway")[:120]}
    return list(devices.values()), bridges


def _read_shelly_blu_bridges_cached(conn: sqlite3.Connection, bridge_macs: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Bound live BLE polling to one bridge scan per cache window."""
    key = tuple(sorted({_inventory_mac(value) for value in bridge_macs if _inventory_mac(value)}))
    if not key:
        return [], []
    with _shelly_blu_read_cache_lock:
        cached = _shelly_blu_read_cache.get(key)
        now = time.monotonic()
        if cached and now - cached[0] < 30.0:
            return cached[1], cached[2]
        devices, bridges = _scan_registered_shelly_blu_bridges(
            conn, duration_seconds=5.0, bridge_macs=set(key))
        _shelly_blu_read_cache.clear()
        _shelly_blu_read_cache[key] = (time.monotonic(), devices, bridges)
        return devices, bridges


def register_shelly_blu_device(payload: dict[str, Any],
                               session: dict[str, Any]) -> dict[str, Any]:
    """Verify a Shelly BLU sensor through its registered bridge and add it to inventory."""
    if not isinstance(payload, dict) or set(payload) - {"mac", "name", "device_type", "bridge_mac"}:
        raise HTTPException(422, "shelly_blu_registration_payload_invalid")
    mac, bridge_mac = _inventory_mac(payload.get("mac")), _inventory_mac(payload.get("bridge_mac"))
    name = str(payload.get("name") or "").strip()
    device_type = str(payload.get("device_type") or "smart_sensor").strip().lower()[:48]
    if not mac or not bridge_mac:
        raise HTTPException(422, "shelly_blu_mac_invalid")
    if not name or len(name) > 120:
        raise HTTPException(422, "shelly_blu_name_required")
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        bridge_row = conn.execute("""SELECT mac,name,host,model,device_type,auth_ciphertext FROM shelly_devices
            WHERE mac=? AND enabled=1 AND (device_type IN ('smart_blugw','smart_gateway') OR model LIKE '%BLU Gateway%'
                OR model LIKE '%BLU GW%' OR model LIKE '%BLUGW%' OR model LIKE '%GWF-KZ01%' OR model LIKE '%SNGW-BT01%'
                OR upper(model) LIKE '%SN-GW-BT01%' OR upper(model) LIKE '%SN GW BT01%')""",
            (bridge_mac,)).fetchone()
        if not bridge_row:
            raise HTTPException(404, "shelly_blu_bridge_not_registered")
        observation = conn.execute("""SELECT details_json FROM shelly_blu_scan_observations
            WHERE bridge_mac=? AND mac=? AND observed_at>=?""", (bridge_mac, mac, time.time() - 300)).fetchone()
        observed = None
        if observation:
            try:
                candidate = json.loads(observation["details_json"])
                if isinstance(candidate, dict): observed = candidate
            except (TypeError, json.JSONDecodeError):
                observed = None
        if not observed:
            try:
                credentials = shelly_credentials.open_credentials(DATA_DIR, bridge_row["auth_ciphertext"] or b"")
                scan = hardware_integrations.shelly_integration.discover_bluetooth_devices(
                    str(bridge_row["host"] or ""), username=str(credentials.get("username") or ""),
                    password=str(credentials.get("password") or ""), duration_seconds=30.0)
                _remember_shelly_blu_scan(conn, scan.get("devices", []))
                observed = next((item for item in scan.get("devices", []) if isinstance(item, dict)
                                 and _inventory_mac(item.get("mac")) == mac), None)
            except (OSError, RuntimeError, ValueError) as exc:
                raise HTTPException(502, "shelly_blu_bridge_scan_failed") from exc
        if not observed:
            raise HTTPException(409, "shelly_blu_device_not_seen_through_bridge")
        conn.execute("BEGIN IMMEDIATE")
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        now = utcnow()
        values = observed.get("values") if isinstance(observed.get("values"), list) else []
        conn.execute("""INSERT INTO shelly_blu_devices
            (mac,name,model,device_type,bridge_mac,bridge_host,last_rssi,values_json,last_seen_at,enabled,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,1,?,?) ON CONFLICT(mac) DO UPDATE SET name=excluded.name,
            model=CASE WHEN excluded.model<>'' THEN excluded.model ELSE shelly_blu_devices.model END,
            device_type=excluded.device_type,bridge_mac=excluded.bridge_mac,bridge_host=excluded.bridge_host,
            last_rssi=excluded.last_rssi,values_json=excluded.values_json,last_seen_at=excluded.last_seen_at,
            enabled=1,updated_at=excluded.updated_at""",
            (mac, name, str(observed.get("model") or "")[:120], device_type, bridge_mac,
             str(bridge_row["host"] or "")[:64], observed.get("rssi"), json.dumps(values, separators=(",", ":")),
             now, now, now))
        source_id = f"shelly-blu:{mac}"
        conn.execute("""INSERT INTO network_device_inventory
            (mac,name,device_type,manufacturer,model,last_ip,source_provider,source_device_id,created_at,updated_at,last_seen_at)
            VALUES(?,?,?,'Shelly',?,'','shelly_blu',?,?,?,?) ON CONFLICT(mac) DO UPDATE SET
            name=excluded.name,device_type=excluded.device_type,manufacturer='Shelly',model=excluded.model,
            source_provider='shelly_blu',source_device_id=excluded.source_device_id,
            updated_at=excluded.updated_at,last_seen_at=excluded.last_seen_at""",
            (mac, name, device_type, str(observed.get("model") or "")[:120], source_id, now, now, now))
        central = _upsert_gateway_inventory_device(conn, provider="shelly_blu", source_device_id=source_id,
            name=name, device_type=device_type, mac=mac, manufacturer="Shelly",
            model=str(observed.get("model") or ""), status="confirmed", name_source="owner")
        _upsert_smart_product_catalog(conn, manufacturer="Shelly", protocol="shelly_blu",
            product_code=str(observed.get("model") or "Shelly BLU sensor"),
            product_name=str(observed.get("model") or "Shelly BLU sensor"), device_kind=device_type,
            capabilities=[str(value.get("name") or "") for value in values if isinstance(value, dict)],
            source="shelly_blu_advertisement", confidence="device_reported")
        _sync_gateway_device_inventory(conn, hardware_integrations.load_config())
        central = dict(conn.execute("SELECT * FROM gateway_device_inventory WHERE device_key=?",
                                    (central["device_key"],)).fetchone())
        audit(conn, session["user_id"], "smart_device.shelly_blu.register", mac, "success",
              {"bridge_mac": bridge_mac, "model": observed.get("model"), "value_count": len(values)})
        conn.commit()
        return {"device": central, "values": values, "bridge": {"mac": bridge_mac, "name": bridge_row["name"]},
                "source": "shelly_blu_gateway", "cloud_used": False, "commands_sent": False}


def discover_shelly_blu_bridge(device_id: str, session: dict[str, Any]) -> dict[str, Any]:
    """Scan one registered Shelly BLU bridge for nearby BTHome advertisements."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        row = conn.execute("""SELECT mac,name,host,model,device_type FROM shelly_devices
            WHERE device_id=? AND enabled=1 AND (device_type IN ('smart_blugw','smart_gateway') OR model LIKE '%BLU Gateway%'
                OR model LIKE '%BLU GW%' OR model LIKE '%BLUGW%' OR model LIKE '%GWF-KZ01%' OR model LIKE '%SNGW-BT01%'
                OR upper(model) LIKE '%SN-GW-BT01%' OR upper(model) LIKE '%SN GW BT01%')""",
            (device_id,)).fetchone()
        if not row:
            raise HTTPException(404, "shelly_blu_bridge_not_registered")
        bridge = dict(row)
    try:
        with db() as conn:
            devices, bridges = _scan_registered_shelly_blu_bridges(
                conn, duration_seconds=30.0, bridge_macs={bridge["mac"]})
            _remember_shelly_blu_scan(conn, devices)
            result = bridges[0] if bridges else {"mac": _inventory_mac(bridge["mac"]), "name": bridge["name"],
                                             "model": bridge["model"], "state": "unavailable",
                                             "reason": "bridge_not_scanned"}
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(502, "shelly_blu_bridge_scan_failed") from exc
    return {"bridge": result, "devices": devices, "device_count": len(devices),
            "source": "registered_shelly_blu_bridge", "commands_sent": False}


def _unique_lan_ip_for_mac(report: dict[str, Any], mac_value: Any) -> str:
    """Return a current private IP only when this scan ties one IP to one MAC."""
    mac = _inventory_mac(mac_value)
    if not mac:
        return ""
    conflicts = {_inventory_mac(item.get("mac")) for item in report.get("mac_ip_conflicts", [])
                 if isinstance(item, dict)}
    if mac in conflicts:
        return ""
    ips: set[str] = set()
    for host in report.get("hosts", []):
        if not isinstance(host, dict) or _inventory_mac(host.get("mac")) != mac:
            continue
        if not host.get("mac_ip_conflict") and host.get("ip"):
            ips.add(str(host["ip"]).strip())
        candidates = host.get("ip_candidates", [])
        if isinstance(candidates, list):
            ips.update(str(value).strip() for value in candidates if isinstance(value, str) and value.strip())
    if len(ips) != 1:
        return ""
    try:
        return hardware_integrations._private_ip(next(iter(ips)))
    except ValueError:
        return ""


def _lan_ips_for_mac(report: dict[str, Any], mac_value: Any) -> list[str]:
    """Return every private IP candidate attributed to a MAC, including conflicts."""
    mac = _inventory_mac(mac_value)
    if not mac:
        return []
    candidates: set[str] = set()
    for host in report.get("hosts", []):
        if not isinstance(host, dict) or _inventory_mac(host.get("mac")) != mac:
            continue
        if host.get("ip"):
            candidates.add(str(host["ip"]).strip())
        values = host.get("ip_candidates", [])
        if isinstance(values, list):
            candidates.update(str(value).strip() for value in values if isinstance(value, str) and value.strip())
    for conflict in report.get("mac_ip_conflicts", []):
        if not isinstance(conflict, dict) or _inventory_mac(conflict.get("mac")) != mac:
            continue
        values = conflict.get("ip_candidates", conflict.get("ips", []))
        if isinstance(values, list):
            candidates.update(str(value).strip() for value in values if isinstance(value, str) and value.strip())
    valid = set()
    for value in candidates:
        try:
            valid.add(hardware_integrations._private_ip(value))
        except ValueError:
            continue
    return sorted(valid)


def _refresh_deye_host_by_inventory_mac(deye_config: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve an inverter MAC to the sole IP candidate that answers the Deye Modbus probe."""
    try:
        with db() as conn:
            current_config = hardware_integrations.load_config()
            _sync_gateway_device_inventory(conn, current_config)
            rows = conn.execute("""SELECT mac,device_key FROM gateway_device_inventory
                WHERE mac<>'' AND (device_type='inverter' OR source_provider='deye')""").fetchall()
            by_mac = {_inventory_mac(row["mac"]): row["device_key"] for row in rows if _inventory_mac(row["mac"])}
            conn.commit()
        if len(by_mac) != 1:
            return None
        mac, device_key = next(iter(by_mac.items()))
        report = network_scanner.scan_attached_networks()
        candidates = _lan_ips_for_mac(report, mac)
        if not candidates:
            return None
        responsive: list[tuple[str, dict[str, Any]]] = []
        for candidate in candidates:
            try:
                probe = hardware_integrations.read_deye({**deye_config, "host": candidate})
            except (OSError, RuntimeError, TimeoutError, ValueError):
                continue
            state = str(probe.get("connection_state") or "") if isinstance(probe, dict) else ""
            if state in {"mapped_registers_response", "modbus_identity_response", "modbus_register_probe_response",
                         "modbus_exception_response"}:
                responsive.append((candidate, probe))
        # A duplicated MAC is resolved only when exactly one address speaks Modbus.
        # If both answer (or neither does), preserve the current configuration.
        if len(responsive) != 1:
            LOG.warning("Deye IP recovery not applied: %s Modbus-responsive candidates for inventoried MAC", len(responsive))
            return None
        discovered_ip, verified_snapshot = responsive[0]
        latest_config = hardware_integrations.load_config()
        latest_deye = latest_config.get("deye") if isinstance(latest_config.get("deye"), dict) else {}
        old_host = str(latest_deye.get("host") or deye_config.get("host") or "")
        try:
            old_host = hardware_integrations._private_ip(old_host)
        except ValueError:
            old_host = ""
        latest_deye["host"] = discovered_ip
        latest_config["deye"] = latest_deye
        if old_host != discovered_ip:
            hardware_integrations.save_config(latest_config)
        with db() as conn:
            now = utcnow()
            conn.execute("UPDATE gateway_device_inventory SET last_ip=?,last_seen_at=?,updated_at=? WHERE device_key=?",
                         (discovered_ip, now, now, device_key))
            conn.commit()
        return {**latest_deye, "host": discovered_ip, "inventory_mac": mac,
                "ip_changed": old_host != discovered_ip, "verified_snapshot": verified_snapshot}
    except (OSError, RuntimeError, ValueError, sqlite3.Error, subprocess.SubprocessError) as exc:
        LOG.warning("Deye IP refresh by inventory MAC failed (%s)", type(exc).__name__)
        return None


def _deye_recovery_key(deye_config: dict[str, Any]) -> tuple[str, str, str, str]:
    return (str(deye_config.get("host") or ""), str(deye_config.get("port", 502)),
            str(deye_config.get("unit_id", 1)), _inventory_mac(deye_config.get("local_mac")))


def _read_deye_with_inventory_recovery(deye_config: dict[str, Any]) -> dict[str, Any]:
    """Avoid overlapping periodic and manual Modbus conversations."""
    global _deye_last_success_latency_seconds, _deye_next_poll_delay_seconds, _last_deye_diagnostic_log_at
    if not _deye_read_lock.acquire(blocking=False):
        return {"host": deye_config.get("host"), "port": deye_config.get("port", 502),
                "connection_state": "read_in_progress", "reason": "deye_read_already_in_progress",
                "metrics_decoded": False, "trust": "UNAVAILABLE"}
    started = time.perf_counter()
    result: dict[str, Any] | None = None
    try:
        result = _read_deye_with_inventory_recovery_locked(deye_config)
        return result
    finally:
        elapsed = max(0.0, time.perf_counter() - started)
        outcome = str(result.get("connection_state") or "failed") if result else "no_response"
        with _deye_latency_state_lock:
            if result is not None and result.get("connection_state") == "mapped_registers_response":
                _deye_last_success_latency_seconds = elapsed
                _deye_next_poll_delay_seconds = _deye_poll_delay_for_latency(elapsed)
            else:
                _deye_next_poll_delay_seconds = _deye_failure_backoff_seconds(
                    _deye_last_success_latency_seconds)
            next_delay = _deye_next_poll_delay_seconds
            now = time.monotonic()
            should_summarize_success = now - _last_deye_diagnostic_log_at >= 60.0
            if outcome != "mapped_registers_response" or elapsed >= 2.0 or should_summarize_success:
                _last_deye_diagnostic_log_at = now
                if outcome == "mapped_registers_response" and elapsed < 2.0:
                    LOG.info("Deye polling diagnostic outcome=%s latency_ms=%d next_wait_ms=%d",
                             outcome, round(elapsed * 1000), round(next_delay * 1000))
                else:
                    LOG.warning("Deye polling diagnostic outcome=%s latency_ms=%d next_wait_ms=%d",
                                outcome, round(elapsed * 1000), round(next_delay * 1000))
        _deye_read_lock.release()


def _read_deye_with_inventory_recovery_locked(deye_config: dict[str, Any]) -> dict[str, Any]:
    """Read Deye; only search another IP after 60s of continuous no-response failures."""
    try:
        snapshot = hardware_integrations.read_deye(deye_config)
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        snapshot = {"host": deye_config.get("host"), "port": deye_config.get("port", 502),
                    "connection_state": "tcp_unreachable", "reason": str(exc)[:120],
                    "metrics_decoded": False, "trust": "UNAVAILABLE"}
    if not isinstance(snapshot, dict):
        snapshot = {"connection_state": "failed", "metrics_decoded": False}
    state = str(snapshot.get("connection_state") or "")
    key = _deye_recovery_key(deye_config)
    no_response_states = {"tcp_unreachable", "modbus_timeout", "modbus_transport_error", "invalid_modbus_response"}
    response_states = {"mapped_registers_response", "mapped_register_read_failed", "modbus_identity_response",
                       "modbus_register_probe_response", "modbus_exception_response"}
    if state not in no_response_states:
        # A Modbus response (including an unsupported map/function) proves the
        # configured IP is reachable, so never launch IP discovery for it.
        if state in response_states:
            with _deye_ip_recovery_lock:
                _deye_unreachable_since.pop(key, None)
                _deye_last_ip_recovery_attempt.pop(key, None)
        return snapshot

    now = time.monotonic()
    with _deye_ip_recovery_lock:
        failed_since = _deye_unreachable_since.setdefault(key, now)
        failure_duration = now - failed_since
        if failure_duration < DEYE_IP_RECOVERY_AFTER_SECONDS:
            return snapshot
        last_attempt = _deye_last_ip_recovery_attempt.get(key)
        if last_attempt is not None and now - last_attempt < DEYE_IP_RECOVERY_RETRY_SECONDS:
            return snapshot
        # Reserve the attempt before network scanning so concurrent manual and
        # periodic reads cannot start duplicate LAN scans.
        _deye_last_ip_recovery_attempt[key] = now

    refreshed = _refresh_deye_host_by_inventory_mac(deye_config)
    if not refreshed:
        return snapshot
    try:
        retried = refreshed.pop("verified_snapshot", None) or hardware_integrations.read_deye(refreshed)
        retried["ip_refreshed_by_mac"] = bool(refreshed.get("ip_changed"))
        retried["mac_verified_on_lan"] = True
        if str(retried.get("connection_state") or "") in response_states:
            with _deye_ip_recovery_lock:
                _deye_unreachable_since.pop(key, None)
                _deye_last_ip_recovery_attempt.pop(key, None)
        return retried
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        return {"host": refreshed["host"], "port": refreshed.get("port", 502),
                "connection_state": "tcp_unreachable", "reason": str(exc)[:120],
                "metrics_decoded": False, "trust": "UNAVAILABLE",
                "ip_refreshed_by_mac": bool(refreshed.get("ip_changed")),
                "mac_verified_on_lan": True}


def _upsert_gateway_inventory_device(conn: sqlite3.Connection, *, provider: str, source_device_id: str,
                                     name: str, device_type: str = "unknown", mac: str = "", ip: str = "",
                                     manufacturer: str = "", model: str = "", status: str = "pending",
                                     name_source: str = "source", replace_ip: bool = False,
                                     product_id: str = "") -> dict[str, Any]:
    """Merge a source identity or manually named LAN device into one inventory row."""
    provider, source_device_id = str(provider or "unknown")[:48], str(source_device_id or "")[:160]
    mac = _inventory_mac(mac)
    name, device_type = str(name or "Dispositivo")[:120], str(device_type or "unknown")[:48]
    manufacturer, model, ip, product_id = str(manufacturer or "")[:120], str(model or "")[:120], str(ip or "")[:64], str(product_id or "")[:128]
    status = status if status in {"pending", "confirmed"} else "pending"
    name_source = "owner" if name_source in {"owner", "local"} else "source"
    current = conn.execute("SELECT * FROM gateway_device_inventory WHERE mac=? LIMIT 1", (mac,)).fetchone() if mac else None
    if current is None and source_device_id:
        current = conn.execute("SELECT * FROM gateway_device_inventory WHERE source_provider=? AND source_device_id=? LIMIT 1",
                               (provider, source_device_id)).fetchone()
    now = utcnow()
    if current is None:
        key = f"mac:{mac}" if mac else f"source:{provider}:{source_device_id or uuid.uuid4().hex}"
        links = [{"provider": provider, "device_id": source_device_id}] if source_device_id else []
        conn.execute("""INSERT INTO gateway_device_inventory
            (device_key,source_provider,source_device_id,source_links_json,name,name_source,device_type,mac,last_ip,
             manufacturer,model,product_id,confirmation_status,created_at,updated_at,last_seen_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (key, provider, source_device_id, json.dumps(links, separators=(",", ":")), name, name_source,
             device_type, mac, ip, manufacturer, model, product_id, status, now, now, ""))
        current = conn.execute("SELECT * FROM gateway_device_inventory WHERE device_key=?", (key,)).fetchone()
    else:
        # A source-only record gains its stable MAC key as soon as the MAC is
        # known. The MAC lookup above prevents creating a second row for it.
        mac_key = f"mac:{mac}" if mac else ""
        if mac_key and current["device_key"] != mac_key:
            conn.execute("UPDATE gateway_device_inventory SET device_key=? WHERE device_key=?",
                         (mac_key, current["device_key"]))
            current = conn.execute("SELECT * FROM gateway_device_inventory WHERE device_key=?",
                                   (mac_key,)).fetchone()
        try:
            links = json.loads(current["source_links_json"] or "[]")
        except (TypeError, ValueError):
            links = []
        if not isinstance(links, list):
            links = []
        if source_device_id and not any(isinstance(item, dict) and item.get("provider") == provider and
                                        item.get("device_id") == source_device_id for item in links):
            links.append({"provider": provider, "device_id": source_device_id})
        keep_owner_name = current["name_source"] == "owner" and name_source != "owner"
        resolved_name = current["name"] if keep_owner_name else name
        resolved_name_source = current["name_source"] if keep_owner_name else name_source
        resolved_ip = ip if replace_ip and ip else current["last_ip"] or ip
        resolved_status = "confirmed" if status == "confirmed" else current["confirmation_status"]
        conn.execute("""UPDATE gateway_device_inventory SET
            source_provider=CASE WHEN ?='network' AND source_provider<>'' THEN source_provider ELSE ? END,
            source_device_id=CASE WHEN ?='' THEN source_device_id ELSE ? END,
            source_links_json=?,name=?,name_source=?,device_type=CASE WHEN ?='unknown' THEN device_type ELSE ? END,
            mac=CASE WHEN ?='' THEN mac ELSE ? END,last_ip=?,
            manufacturer=CASE WHEN ?='' THEN manufacturer ELSE ? END,
            model=CASE WHEN ?='' THEN model ELSE ? END,confirmation_status=?,updated_at=?,
            product_id=CASE WHEN ?='' THEN product_id ELSE ? END,
            last_seen_at=CASE WHEN ?<>'' THEN ? ELSE last_seen_at END WHERE device_key=?""",
            (provider, provider, source_device_id, source_device_id, json.dumps(links, separators=(",", ":")),
             resolved_name, resolved_name_source, device_type, device_type, mac, mac, resolved_ip,
             manufacturer, manufacturer, model, model, resolved_status, now, product_id, product_id,
             now if replace_ip and ip else "", now, current["device_key"]))
        current = conn.execute("SELECT * FROM gateway_device_inventory WHERE device_key=?", (current["device_key"],)).fetchone()
    return dict(current)


def _sync_miner_name_from_inventory(conn: sqlite3.Connection, device_key: str, name: str) -> bool:
    """Propagate an Owner-assigned MAC identity name into its miner load/card."""
    config = energy_engine.get_config(conn)
    loads = list(config.get("loads", []))
    matches = [item for item in loads if isinstance(item, dict) and item.get("kind") == "miner"
               and item.get("control_type") == "antminer_braiins" and item.get("device_key") == device_key]
    if len(matches) != 1:
        return False
    load = matches[0]
    load["name"] = name
    saved = energy_engine.save_config(conn, {"loads": loads})
    equipment_id = load.get("equipment_id")
    if equipment_id:
        conn.execute("UPDATE energy_equipment SET name=?,updated_at=? WHERE id=? AND category='mineradoras'",
                     (name, utcnow(), equipment_id))
    return bool(saved)


def _upsert_smart_product_catalog(conn: sqlite3.Connection, *, manufacturer: str, protocol: str,
                                  product_code: str, product_name: str = "", device_kind: str = "smart",
                                  capabilities: list[str] | None = None, source: str = "observed",
                                  confidence: str = "observed") -> None:
    manufacturer, protocol, product_code = str(manufacturer or "").strip()[:80], str(protocol or "").strip()[:48], str(product_code or "").strip()[:128]
    if not manufacturer or not protocol or not product_code:
        return
    caps = sorted({str(value)[:64] for value in (capabilities or []) if isinstance(value, str)})
    conn.execute("""INSERT INTO smart_product_catalog(manufacturer,protocol,product_code,product_name,device_kind,capabilities_json,source,confidence,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(manufacturer,protocol,product_code) DO UPDATE SET
        product_name=CASE WHEN excluded.product_name<>'' THEN excluded.product_name ELSE smart_product_catalog.product_name END,
        device_kind=CASE WHEN excluded.device_kind<>'smart' THEN excluded.device_kind ELSE smart_product_catalog.device_kind END,
        capabilities_json=CASE WHEN excluded.capabilities_json<>'[]' THEN excluded.capabilities_json ELSE smart_product_catalog.capabilities_json END,
        source=excluded.source,confidence=excluded.confidence,updated_at=excluded.updated_at""",
        (manufacturer, protocol, product_code, str(product_name or "")[:120], str(device_kind or "smart")[:64],
         json.dumps(caps, separators=(",", ":")), str(source or "observed")[:80], str(confidence or "observed")[:40], utcnow()))


def _sync_zigbee2mqtt_catalog(conn: sqlite3.Connection) -> int:
    """Import Zigbee2MQTT models into the shared protocol-keyed product catalog once per source revision."""
    source_key = "zigbee2mqtt-device-catalog"
    expected_revision = "e4881099197488956c6ea500355a839e052be764"
    previous = conn.execute("SELECT source_revision FROM smart_product_catalog_sources WHERE source_key=?", (source_key,)).fetchone()
    if previous and previous["source_revision"] == expected_revision:
        return 0
    path = Path(__file__).with_name("zigbee2mqtt-device-catalog.json")
    if not path.is_file():
        # Development/tests keep the generated source artifact under resources/;
        # the Debian package copies it alongside this module.
        path = Path(__file__).resolve().parents[2] / "resources" / "zigbee2mqtt-device-catalog.json"
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOG.warning("Bundled Zigbee2MQTT catalog unavailable (%s)", type(exc).__name__)
        return 0
    revision = str(catalog.get("source_commit") or "")[:64]
    if revision != expected_revision or not isinstance(catalog.get("profiles"), list):
        LOG.warning("Bundled Zigbee2MQTT catalog has invalid metadata")
        return 0
    stamp = utcnow()
    catalog_rows, detail_rows = [], []
    for profile in catalog["profiles"]:
        if not isinstance(profile, dict):
            continue
        manufacturer = str(profile.get("manufacturer") or "").strip()[:80]
        model = str(profile.get("model") or profile.get("product_id") or "").strip()[:128]
        if not manufacturer or not model:
            continue
        capabilities = profile.get("capabilities") if isinstance(profile.get("capabilities"), list) else []
        features = profile.get("features") if isinstance(profile.get("features"), list) else []
        labels = sorted({str(item.get("label") or "")[:64] for item in capabilities if isinstance(item, dict) and item.get("label")})
        catalog_rows.append((manufacturer, "zigbee2mqtt", model, str(profile.get("description") or model)[:120],
            "smart", json.dumps(labels or features, ensure_ascii=False, separators=(",", ":")),
            "Koenkk/zigbee2mqtt.io", "manufacturer_documented", stamp))
        detail_rows.append((manufacturer, "zigbee2mqtt", model,
            json.dumps(profile, ensure_ascii=False, separators=(",", ":")), str(profile.get("source_url") or "")[:512], revision, stamp))
    conn.executemany("""INSERT INTO smart_product_catalog(manufacturer,protocol,product_code,product_name,device_kind,capabilities_json,source,confidence,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(manufacturer,protocol,product_code) DO UPDATE SET
        product_name=excluded.product_name,capabilities_json=excluded.capabilities_json,source=excluded.source,
        confidence=excluded.confidence,updated_at=excluded.updated_at""", catalog_rows)
    conn.executemany("""INSERT INTO smart_product_profile_details(manufacturer,protocol,product_code,profile_json,source_url,source_revision,updated_at)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(manufacturer,protocol,product_code) DO UPDATE SET
        profile_json=excluded.profile_json,source_url=excluded.source_url,source_revision=excluded.source_revision,updated_at=excluded.updated_at""", detail_rows)
    conn.execute("""INSERT INTO smart_product_catalog_sources(source_key,source_revision,imported_count,imported_at)
        VALUES(?,?,?,?) ON CONFLICT(source_key) DO UPDATE SET source_revision=excluded.source_revision,
        imported_count=excluded.imported_count,imported_at=excluded.imported_at""", (source_key, revision, len(detail_rows), stamp))
    LOG.info("Imported %d Zigbee2MQTT models into the shared catalog (%s)", len(detail_rows), revision)
    return len(detail_rows)


def _sync_gateway_device_inventory(conn: sqlite3.Connection, config: dict[str, Any]) -> None:
    """Project saved provider identities into the Gateway's shared inventory."""
    tuya = config.get("tuya", {}) if isinstance(config.get("tuya"), dict) else {}
    devices = tuya.get("devices", []) if isinstance(tuya.get("devices"), list) else []
    for device in devices:
        if not isinstance(device, dict) or not device.get("device_id"):
            continue
        product_name = str(device.get("product_name") or "")
        manufacturer = str(device.get("manufacturer") or ("Moes" if "moes" in product_name.casefold() else ""))
        product_id = str(device.get("product_id") or "")
        if product_id:
            product = str(device.get("product") or "")[:160]
            category = str(device.get("category") or "")[:64].casefold()
            device_kind = str(device.get("device_kind") or "unknown")[:32].casefold()
            conn.execute("""INSERT INTO tuya_product_identity(product_id,product,category,device_kind,product_name_pt,updated_at)
                VALUES(?,?,?,?,?,?) ON CONFLICT(product_id,product,category,device_kind) DO UPDATE SET
                product_name_pt=CASE WHEN excluded.product_name_pt<>'' THEN excluded.product_name_pt ELSE tuya_product_identity.product_name_pt END,
                updated_at=excluded.updated_at""",
                (product_id[:128], product, category, device_kind, str(device.get("product_name_pt") or "")[:160], utcnow()))
        tuya_capabilities = [str(value) for value in (device.get("capability_labels") or {}).keys() if isinstance(value, str)]
        _upsert_smart_product_catalog(conn, manufacturer=manufacturer or "Tuya", protocol="tuya",
            product_code=product_id, product_name=product_name or str(device.get("model") or ""),
            device_kind=str(device.get("device_kind") or "smart"),
            capabilities=tuya_capabilities, source="tuya_cloud_inventory", confidence="cloud_synced")
        _upsert_gateway_inventory_device(conn, provider="tuya", source_device_id=str(device["device_id"]),
            name=str(device.get("name") or "Tuya"), device_type=(str(device.get("device_kind") or "tuya") if str(device.get("device_kind") or "unknown") in hardware_integrations.TUYA_DEVICE_KINDS and device.get("device_kind") != "unknown" else "tuya"),
            mac=str(device.get("local_mac") or device.get("mac") or device.get("mac_address") or ""),
            ip=str(device.get("local_ip") or ""), manufacturer=manufacturer,
            model=str(device.get("model") or product_name),
            product_id=str(device.get("product_id") or ""),
            status="confirmed" if device.get("local_verified") is True else "pending",
            name_source="owner" if device.get("name_source") == "local" else "source")
    for provider, device_type, default_name in (("deye", "inverter", "Deye inverter"),
                                                 ("antminer", "miner", "Antminer"),
                                                 ("tesla", "vehicle", "Tesla")):
        item = config.get(provider, {}) if isinstance(config.get(provider), dict) else {}
        if not any(item.get(key) for key in ("host", "local_ip", "local_mac", "model", "name", "vehicle_ids")):
            continue
        _upsert_gateway_inventory_device(conn, provider=provider, source_device_id="main",
            name=str(item.get("name") or item.get("model") or default_name), device_type=device_type,
            mac=str(item.get("local_mac") or item.get("mac") or ""), ip=str(item.get("local_ip") or item.get("host") or ""),
            manufacturer=str(item.get("manufacturer") or ""), model=str(item.get("model") or ""),
            status="confirmed" if item.get("local_verified") is True else "pending")
    for item in conn.execute("SELECT * FROM shelly_devices WHERE enabled=1").fetchall():
        try:
            capabilities = json.loads(item["capabilities_json"] or "[]")
        except (TypeError, ValueError):
            capabilities = []
        shelly_model = str(item["model"] or "")
        _upsert_smart_product_catalog(conn, manufacturer="Shelly", protocol=str(item["protocol"] or "shelly"),
            product_code=shelly_model, product_name=shelly_model, device_kind=str(item["device_type"] or "smart"),
            capabilities=capabilities if isinstance(capabilities, list) else [], source="shelly_device_identification",
            confidence="device_reported")
        _upsert_gateway_inventory_device(conn, provider="shelly", source_device_id=str(item["device_id"]),
            name=str(item["name"] or item["model"] or "Smart device"), device_type=str(item["device_type"] or "smart"),
            mac=str(item["mac"] or ""), ip=str(item["host"] or ""), manufacturer="Shelly",
            model=str(item["model"] or ""), status="confirmed" if item["protocol"] else "pending")
    # Import scanner labels saved by older versions into the central inventory.
    for item in conn.execute("SELECT * FROM network_device_inventory").fetchall():
        _upsert_gateway_inventory_device(conn, provider=str(item["source_provider"] or "network"),
            source_device_id=str(item["source_device_id"] or item["mac"]), name=str(item["name"]),
            device_type=str(item["device_type"] or "unknown"), mac=str(item["mac"] or ""),
            ip=str(item["last_ip"] or ""), manufacturer=str(item["manufacturer"] or ""),
            model=str(item["model"] or ""), status="pending",
            product_id=str(item["product_id"] or ""),
            name_source="owner" if not item["source_provider"] or item["source_provider"] == "network" else "source")


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


@contextmanager
def db() -> Any:
    started = time.perf_counter()
    outcome = "ok"
    if INSTANCE_MARKER.exists() and not DB_PATH.is_file():
        LOG.error("Database operation failed stage=connect reason=initialized_database_missing")
        raise sqlite3.OperationalError("database missing for initialized instance")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Once initialized, never let SQLite's default create-if-missing behavior
    # resurrect an empty database if another task removes the file after the
    # check above. The read-write URI closes that TOCTOU window.
    if INSTANCE_MARKER.exists():
        conn = sqlite3.connect(DB_PATH.resolve().as_uri() + "?mode=rw", uri=True,
                               timeout=10, isolation_level=None)
    else:
        conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA recursive_triggers=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    try:
        yield conn
    except Exception as exc:
        outcome = type(exc).__name__
        raise
    finally:
        conn.close()
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        if elapsed_ms >= 1000 or outcome != "ok":
            level = logging.ERROR if outcome != "ok" else logging.WARNING
            LOG.log(level, "Database operation %s reason=%s duration_ms=%d",
                    "failed" if outcome != "ok" else "slow", outcome, elapsed_ms)


def audit(conn: sqlite3.Connection, actor: str | None, action: str, target: str | None, outcome: str, details: dict | None = None) -> None:
    conn.execute("INSERT INTO audit(occurred_at,actor_user_id,action,target,outcome,details_json) VALUES(?,?,?,?,?,?)",
                 (utcnow(), actor, action, target, outcome, json.dumps(details or {}, separators=(",", ":"))))


def _persist_tuya_product_dps_map(conn: sqlite3.Connection, product_schemas: Any) -> int:
    """Index product-scoped Tuya DP meanings in SQLite for reuse and inspection."""
    if not isinstance(product_schemas, dict):
        return 0
    saved = 0
    stamp = utcnow()
    for product_id, product in product_schemas.items():
        if not isinstance(product_id, str) or not product_id or not isinstance(product, dict):
            continue
        profile = product.get("dps_profile") if isinstance(product.get("dps_profile"), dict) else {}
        manufacturer = str(product.get("manufacturer") or "Tuya")[:80]
        product_name = str(product.get("product_name") or "")[:120]
        _upsert_smart_product_catalog(conn, manufacturer=manufacturer, protocol="tuya", product_code=product_id,
            product_name=product_name, device_kind=str(product.get("device_kind") or "smart"),
            capabilities=[str(row.get("semantic_code") or "") for row in (profile.get("dps") if isinstance(profile.get("dps"), list) else []) if isinstance(row, dict)],
            source="tuya_product_dps_profile", confidence="product_scoped")
        rows = profile.get("dps") if isinstance(profile.get("dps"), list) else []
        overrides = product.get("custom_dps_overrides") if isinstance(product.get("custom_dps_overrides"), dict) else {}
        for item in rows:
            if not isinstance(item, dict):
                continue
            dps_id = item.get("dps_id")
            if isinstance(dps_id, bool) or not isinstance(dps_id, int) or not 1 <= dps_id <= 65535:
                continue
            override = overrides.get(str(dps_id)) if isinstance(overrides.get(str(dps_id)), dict) else {}
            scale = override.get("scale", item.get("scale"))
            if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(float(scale)):
                scale = None
            values = (
                "tuya", str(product.get("manufacturer") or "Tuya")[:64], product_id[:128],
                str(product.get("product_name") or "")[:120], str(product.get("category") or "")[:64],
                str(product.get("device_kind") or "unknown")[:32], dps_id,
                str(override.get("function_code") or item.get("function_code") or "")[:64],
                str(override.get("semantic_code") or item.get("semantic_code") or "unknown")[:64],
                str(override.get("label") or item.get("display_name") or f"DPS {dps_id}")[:80],
                str(override.get("data_type") or item.get("data_type") or "unknown")[:24],
                str(override.get("unit") or item.get("unit") or "")[:16] or None, scale,
                "OWNER_CUSTOM" if override else str(item.get("confidence") or "UNKNOWN")[:32],
                "Gateway Product ID mapping" if override else str(item.get("source") or "")[:160],
                str(item.get("validation_status") or "reference_only")[:64],
                int(bool(item.get("read_supported", item.get("source_kind") == "status"))),
                int(bool(item.get("write_supported")) and item.get("source_kind") == "function"
                    or bool(override.get("write_enabled")) and str(override.get("semantic_code")) in {"switch", "countdown", "child_lock"}), stamp,
            )
            conn.execute("""INSERT INTO tuya_product_dps_map(protocol,manufacturer,product_id,product_name,category,device_kind,dps_id,dps_code,semantic_code,description,data_type,unit,scale,confidence,source,validation_status,read_supported,write_supported,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(protocol,product_id,dps_id) DO UPDATE SET
                manufacturer=excluded.manufacturer,product_name=excluded.product_name,category=excluded.category,device_kind=excluded.device_kind,
                dps_code=excluded.dps_code,semantic_code=excluded.semantic_code,description=excluded.description,data_type=excluded.data_type,
                unit=excluded.unit,scale=excluded.scale,confidence=excluded.confidence,source=excluded.source,
                validation_status=excluded.validation_status,read_supported=excluded.read_supported,write_supported=excluded.write_supported,updated_at=excluded.updated_at""", values)
            saved += 1
    return saved


def _persist_tuya_pid_capabilities(conn: sqlite3.Connection, product_schemas: Any) -> int:
    """Index cloud-declared functions and statuses by exact Tuya Product ID."""
    if not isinstance(product_schemas, dict):
        return 0
    saved = 0
    stamp = utcnow()
    for product_id, product in product_schemas.items():
        if not isinstance(product_id, str) or not product_id or not isinstance(product, dict):
            continue
        for source_kind, key in (("function", "functions"), ("status", "status_spec")):
            entries = product.get(key)
            if not isinstance(entries, list) or not entries:
                continue
            # A cloud refresh is authoritative for the declared schema of this
            # exact PID; stale capabilities of the same origin are removed.
            conn.execute("DELETE FROM tuya_pid_capabilities WHERE product_id=? AND source_kind=?",
                         (product_id, source_kind))
            seen: set[str] = set()
            for item in entries[:128]:
                if not isinstance(item, dict) or not isinstance(item.get("code"), str):
                    continue
                code = item["code"].strip()[:128]
                if not code or code in seen:
                    continue
                seen.add(code)
                payload = {**item, "code": code, "source_kind": source_kind,
                           "read_supported": source_kind == "status",
                           "write_supported": source_kind == "function"}
                conn.execute("""INSERT INTO tuya_pid_capabilities(product_id,source_kind,code,payload_json,synchronized_at)
                    VALUES(?,?,?,?,?) ON CONFLICT(product_id,source_kind,code) DO UPDATE SET
                    payload_json=excluded.payload_json,synchronized_at=excluded.synchronized_at""",
                    (product_id, source_kind, code,
                     json.dumps(payload, ensure_ascii=False, separators=(",", ":")), stamp))
                saved += 1
    return saved


def _persist_tuya_product_dps_maps_scoped(conn: sqlite3.Connection, product_maps: Any) -> int:
    """Persist Owner DPS meanings canonically by Tuya Product ID."""
    if not isinstance(product_maps, dict):
        return 0
    saved = 0
    stamp = utcnow()
    for mapping in product_maps.values():
        if not isinstance(mapping, dict):
            continue
        product_id = str(mapping.get("product_id") or "")[:128]
        product = str(mapping.get("product") or "")[:160]
        category = str(mapping.get("category") or "")[:64].casefold()
        device_kind = str(mapping.get("device_kind") or "unknown")[:32].casefold()
        if not product_id:
            continue
        overrides = mapping.get("custom_dps_overrides") if isinstance(mapping.get("custom_dps_overrides"), dict) else {}
        profile = mapping.get("dps_profile") if isinstance(mapping.get("dps_profile"), dict) else {}
        rows = [row for row in profile.get("dps", []) if isinstance(row, dict)
                and isinstance(row.get("dps_id"), int) and not isinstance(row.get("dps_id"), bool)
                and 1 <= row["dps_id"] <= 65535] if isinstance(profile.get("dps"), list) else []
        if not rows:
            continue
        conn.execute("DELETE FROM tuya_product_dps_map_scoped WHERE product_id=?", (product_id,))
        for row in rows:
            dps_id = row.get("dps_id")
            if isinstance(dps_id, bool) or not isinstance(dps_id, int) or not 1 <= dps_id <= 65535:
                continue
            override = overrides.get(str(dps_id)) if isinstance(overrides.get(str(dps_id)), dict) else {}
            scale = override.get("scale", row.get("scale"))
            if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(float(scale)):
                scale = None
            conn.execute("""INSERT INTO tuya_product_dps_map_scoped
                (product_id,product,category,device_kind,dps_id,dps_code,semantic_code,description,data_type,unit,scale,write_supported,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(product_id,product,category,device_kind,dps_id) DO UPDATE SET
                dps_code=excluded.dps_code,semantic_code=excluded.semantic_code,description=excluded.description,
                data_type=excluded.data_type,unit=excluded.unit,scale=excluded.scale,
                write_supported=excluded.write_supported,updated_at=excluded.updated_at""",
                (product_id, product, category, device_kind, dps_id,
                 str(override.get("function_code") or row.get("function_code") or "")[:64],
                 str(override.get("semantic_code") or row.get("semantic_code") or "unknown")[:64],
                 str(override.get("label") or row.get("display_name") or f"DPS {dps_id}")[:80],
                 str(override.get("data_type") or row.get("data_type") or "unknown")[:24],
                 str(override.get("unit") or row.get("unit") or "")[:16] or None, scale,
                 int(bool(override.get("write_enabled"))), stamp))
            saved += 1
    return saved


def _sync_tuya_canonical_features(conn: sqlite3.Connection) -> int:
    """Idempotently seed/update canonical meanings without deleting old rows."""
    return tuya_dps_registry.sync_canonical_features(conn, utcnow())


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
    # WAL is a database-level mode. Set it once during startup instead of
    # asking for it on every API connection, which can contend with active
    # readers/writers and make short health/bootstrap requests time out.
    try:
        with sqlite3.connect(DB_PATH, timeout=10) as journal_conn:
            journal_mode = journal_conn.execute("PRAGMA journal_mode=WAL").fetchone()
            if not journal_mode or str(journal_mode[0]).lower() != "wal":
                raise sqlite3.OperationalError("database_wal_mode_unavailable")
    except sqlite3.Error as exc:
        LOG.critical("Database journal mode could not be initialized (%s)", type(exc).__name__)
        return
    with db() as conn:
        conn.executescript(SCHEMA)
        shelly_product_registry.ensure_schema(conn)
        _sync_tuya_canonical_features(conn)
        bootstrap_columns = {row[1] for row in conn.execute("PRAGMA table_info(bootstrap)")}
        if "setup_password_hash" not in bootstrap_columns:
            conn.execute("ALTER TABLE bootstrap ADD COLUMN setup_password_hash TEXT")
        password_attempt_columns = {row[1] for row in conn.execute("PRAGMA table_info(password_device_attempts)")}
        if "account_hash" not in password_attempt_columns:
            conn.execute("ALTER TABLE password_device_attempts ADD COLUMN account_hash TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_password_device_attempts_account_time ON password_device_attempts(account_hash,attempted_at)")
        network_inventory_columns = {row[1] for row in conn.execute("PRAGMA table_info(network_device_inventory)")}
        if "product_id" not in network_inventory_columns:
            conn.execute("ALTER TABLE network_device_inventory ADD COLUMN product_id TEXT NOT NULL DEFAULT ''")
        gateway_inventory_columns = {row[1] for row in conn.execute("PRAGMA table_info(gateway_device_inventory)")}
        if "product_id" not in gateway_inventory_columns:
            conn.execute("ALTER TABLE gateway_device_inventory ADD COLUMN product_id TEXT NOT NULL DEFAULT ''")
        shelly_columns = {row[1] for row in conn.execute("PRAGMA table_info(shelly_devices)")}
        if "device_type" not in shelly_columns:
            conn.execute("ALTER TABLE shelly_devices ADD COLUMN device_type TEXT NOT NULL DEFAULT 'smart'")
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
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(7,?)", (utcnow(),))
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(8,?)", (utcnow(),))
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(9,?)", (utcnow(),))
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(10,?)", (utcnow(),))
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(11,?)", (utcnow(),))
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(12,?)", (utcnow(),))
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(12,?)", (utcnow(),))
        _upsert_smart_product_catalog(conn, manufacturer="Shelly", protocol="shelly_bluetooth_gateway",
            product_code="family:blu-gateway", product_name="Shelly BLU Gateway (modelo por confirmar)",
            device_kind="smart_blugw", capabilities=["bluetooth_gateway"], source="manufacturer_family",
            confidence="family_only")
        for profile in shelly_product_registry.PROFILES:
            _upsert_smart_product_catalog(conn, manufacturer=profile["manufacturer"], protocol=profile["protocol"],
                product_code=profile["product_code"], product_name=profile["product_name"],
                device_kind=profile["device_kind"], capabilities=profile["capabilities"],
                source="manufacturer_documented", confidence=profile["confidence"])
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(11,?)", (utcnow(),))
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


def _energy_sample_interval_seconds() -> float:
    with _deye_latency_state_lock:
        return _deye_next_poll_delay_seconds


def _deye_poll_delay_for_latency(latency_seconds: float) -> float:
    """Use one measured latency after success and five times after a failed read."""
    try:
        value = float(latency_seconds)
    except (TypeError, ValueError):
        value = 5.0
    if not math.isfinite(value):
        value = 5.0
    return max(0.1, min(3600.0, value))


def _deye_failure_backoff_seconds(last_success_latency_seconds: float | None) -> float:
    reference = last_success_latency_seconds if last_success_latency_seconds is not None else 5.0
    return _deye_poll_delay_for_latency(reference * 5.0)


def _prune_historical_records(now_utc: datetime | None = None) -> dict[str, int]:
    """Prune time-series and structured event history older than 90 days."""
    now = now_utc.astimezone(timezone.utc) if now_utc else datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=90)).isoformat(timespec="seconds")
    cutoff_epoch = int((now - timedelta(days=90)).timestamp())
    cutoff_day = (now - timedelta(days=90)).date().isoformat()
    removed: dict[str, int] = {}
    with db() as conn:
        connector_manager.ensure_schema(conn)
        energy_registry.ensure_schema(conn)
        energy_engine._ensure_solar_forecast_history(conn)
        for table, column in (
            ("energy_readings", "observed_at"),
            ("audit", "occurred_at"),
            ("device_events", "occurred_at"),
            ("connector_operations", "updated_at"),
            ("energy_test_evidence", "observed_at"),
        ):
            cursor = conn.execute(f"DELETE FROM {table} WHERE {column}<?", (cutoff,))
            removed[table] = max(0, cursor.rowcount)
        cursor = conn.execute("DELETE FROM energy_solar_day_forecasts WHERE local_date<?", (cutoff_day,))
        removed["energy_solar_day_forecasts"] = max(0, cursor.rowcount)
        cursor = conn.execute("DELETE FROM update_operations WHERE updated_at<?", (cutoff_epoch,))
        removed["update_operations"] = max(0, cursor.rowcount)
        for table in ("bootstrap_attempts", "password_device_attempts", "invite_attempts"):
            cursor = conn.execute(f"DELETE FROM {table} WHERE attempted_at<?", (cutoff_epoch,))
            removed[table] = max(0, cursor.rowcount)
        cursor = conn.execute("DELETE FROM invite_nonces WHERE timestamp<?", (cutoff_epoch,))
        removed["invite_nonces"] = max(0, cursor.rowcount)
        conn.commit()
    return removed


async def _history_retention_loop() -> None:
    """Catch up on startup, then prune daily at the Gateway's local midnight."""
    while True:
        try:
            # Do not let the retention worker create an empty SQLite file if
            # an initialized Gateway has lost its database. initialize()
            # deliberately fails closed in that situation.
            if DB_PATH.is_file() and (not INSTANCE_MARKER.exists() or DB_PATH.stat().st_size > 0):
                removed = await asyncio.to_thread(_prune_historical_records)
                total = sum(removed.values())
                if total:
                    LOG.info("Pruned %s historical rows older than 90 days", total)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOG.warning("Daily history retention failed (%s)", type(exc).__name__)
        local_now = datetime.now().astimezone()
        next_midnight = datetime.combine(local_now.date() + timedelta(days=1), datetime.min.time(),
                                          tzinfo=local_now.tzinfo)
        await asyncio.sleep(max(1.0, (next_midnight - local_now).total_seconds()))


async def _energy_sampling_loop() -> None:
    """Adapt Deye polling delay to measured Modbus latency and failures."""
    global _latest_deye_sample
    persist_interval = 15.0
    last_persisted_bucket: int | None = None
    while True:
        next_poll_at: float | None = None
        try:
            config = hardware_integrations.load_config().get("deye", {})
            if config.get("host") and config.get("enabled", True):
                snapshot = await asyncio.to_thread(_read_deye_with_inventory_recovery, config)
                # Start the next interval at response receipt, so local processing
                # and persistence time do not get added to the measured wait.
                next_poll_at = time.monotonic() + _energy_sample_interval_seconds()
                if isinstance(snapshot, dict) and snapshot.get("connection_state") == "read_in_progress":
                    LOG.debug("Periodic Deye sample skipped because another read is in progress")
                elif isinstance(snapshot, dict) and snapshot.get("connection_state") == "mapped_registers_response":
                    with _energy_sample_lock:
                        sample = {**snapshot, "sampled_at": datetime.now(timezone.utc).isoformat(timespec="microseconds")}
                        _latest_deye_sample = sample
                        _recent_deye_samples.append(sample)
                        # Bound RAM use and keep enough high-rate samples for
                        # the SOC integrator to bridge persisted samples.
                        if len(_recent_deye_samples) > 240:
                            del _recent_deye_samples[:-240]
                    # The SOC estimator sees every successful sample in RAM;
                    # SQLite stores at most one representative sample per 15s.
                    persist_bucket = int(time.time() // persist_interval)
                    if persist_bucket != last_persisted_bucket:
                        with db() as conn:
                            conn.execute("BEGIN")
                            count = _persist_deye_telemetry(conn, snapshot)
                            conn.commit()
                        last_persisted_bucket = persist_bucket
                        if not count:
                            LOG.warning("Periodic Deye sample returned no mapped readings")
                elif snapshot is not None:
                    LOG.warning("Periodic Deye sample returned no mapped readings")
            else:
                with _energy_sample_lock:
                    _latest_deye_sample = None
                    _recent_deye_samples.clear()
                # No Deye read is possible until configuration changes; avoid
                # waking the sampler on the short adaptive interval while idle.
                next_poll_at = time.monotonic() + 15.0
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Keep the service alive; diagnostic data contains only safe error type.
            LOG.warning("Periodic energy sample failed (%s)", type(exc).__name__)
        if next_poll_at is None:
            # Includes failed reads and failures before a response was returned.
            next_poll_at = time.monotonic() + _energy_sample_interval_seconds()
        # A small floor prevents a zero-delay loop if local work outlasts the interval.
        await asyncio.sleep(max(0.1, next_poll_at - time.monotonic()))


def _run_automatic_dispatch() -> dict[str, Any]:
    """Execute the Owner-enabled plan only when fresh, commissioned telemetry is available."""
    with db() as conn:
        with _energy_sample_lock:
            sample = dict(_latest_deye_sample) if _latest_deye_sample else None
            recent_samples = [dict(item) for item in _recent_deye_samples]
        summary = energy_engine.build_summary(conn, latest_sample=sample, recent_samples=recent_samples)
        plan = summary["dispatch"]
        config = summary["configuration"]
        if plan.get("state") not in {"PLAN_READY", "WAITING_FOR_BATTERY", "WAITING_FOR_BATTERY_RESERVE"}:
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
                energy_engine.persist_tuya_telemetry(conn, tuya_readings, tuya_config.get("devices", []), tuya_config.get("product_schemas", {}))
                _update_tuya_device_records(integration_config, tuya_readings)
                hardware_integrations.save_config(integration_config)
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
        action_order = {action.get("load_id"): index for index, action in enumerate(plan_actions)}
        plan_actions = sorted(plan_actions, key=lambda action: (
            0 if loads_by_id.get(action.get("load_id"), {}).get("control_type") == "antminer_braiins"
            and int(action.get("target_power_w", 0)) == 0 else 1,
            action_order.get(action.get("load_id"), 1000),
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
            if action.get("state") not in {"ON", "TARGET", "WAITING_FOR_SURPLUS", "BELOW_MINIMUM_SURPLUS", "BLOCKED_RELAY_NOT_READY", "OFF_FOR_BATTERY", "STOP_FOR_BATTERY", "STOP_FOR_TESLA_HOME", "OFF_FOR_TESLA_HOME", "OFF_TESLA_AWAY"}:
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


def _activate_energy_manual_override(conn: sqlite3.Connection, actor_id: str, source: str) -> None:
    """Pause automatic dispatch after any successful explicit Owner command."""
    config = energy_engine.get_config(conn)
    manager = {**config.get("surplus_manager", {}), "manual_override": True}
    config["surplus_manager"] = manager
    conn.execute("INSERT INTO system_state(key,value) VALUES('energy_engine_config',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (json.dumps(config, separators=(",", ":")),))
    audit(conn, actor_id, "energy.dispatch.manual_override", source, "paused", {"automatic_dispatch_paused": True})


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


def _read_tesla_local_presence() -> dict[str, Any]:
    """Match the configured Tesla MAC against locally learned neighbours."""
    config = hardware_integrations.load_config()
    tesla = config.get("tesla", {}) if isinstance(config.get("tesla"), dict) else {}
    mac = str(tesla.get("local_mac") or "").strip().upper()
    checked_at = utcnow()
    if not mac:
        return {"state": "NOT_CONFIGURED", "checked_at": checked_at, "ip": None}
    ip = local_arp_entries().get(mac)
    return {"state": "DETECTED" if ip else "NOT_DETECTED", "checked_at": checked_at,
            "ip": ip, "reason": None}


def _persist_tesla_presence(snapshot: dict[str, Any]) -> None:
    with db() as conn:
        conn.execute("INSERT INTO system_state(key,value) VALUES('energy_tesla_presence',?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (json.dumps(snapshot, separators=(",", ":")),))
        conn.commit()


async def _tesla_presence_loop() -> None:
    """Refresh Tesla LAN presence without requiring the PWA to stay open."""
    while True:
        try:
            config = hardware_integrations.load_config()
            tesla = config.get("tesla", {}) if isinstance(config.get("tesla"), dict) else {}
            if tesla.get("local_mac"):
                snapshot = await asyncio.to_thread(_read_tesla_local_presence)
                await asyncio.to_thread(_persist_tesla_presence, snapshot)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOG.warning("Tesla LAN presence check failed (%s)", type(exc).__name__)
        await asyncio.sleep(60)


def _collect_tuya_device_events_once() -> int:
    """Poll configured Tuya Wi-Fi devices and save observed transitions locally."""
    global _tuya_last_diagnostic_log_at
    started = time.perf_counter()
    integration_config = hardware_integrations.load_config()
    config = integration_config.get("tuya", {})
    devices = [item for item in config.get("devices", [])
               if isinstance(item, dict) and item.get("local_key")
               and (item.get("local_ip") or item.get("local_mac"))]
    if not devices:
        return 0
    recorded = 0

    def persist_completed_reading(reading: dict[str, Any]) -> None:
        nonlocal recorded
        # Persist each device independently as its LAN response arrives. A slow
        # or retrying device must not hold back fresh telemetry from its peers.
        with db() as conn:
            recorded += _persist_tuya_device_events(conn, [reading])
            energy_engine.persist_tuya_telemetry(conn, [reading], devices, config.get("product_schemas", {}))
            conn.commit()

    try:
        readings = hardware_integrations.read_tuya(
            {**config, "devices": devices}, on_reading=persist_completed_reading, background_poll=True)
    except Exception as exc:
        LOG.error("Periodic Tuya poll diagnostic outcome=error configured=%d duration_ms=%d error_type=%s",
                  len(devices), round((time.perf_counter() - started) * 1000), type(exc).__name__)
        raise
    duration_ms = round((time.perf_counter() - started) * 1000)
    successful = sum(1 for item in readings if item.get("connection_state") == "local_responded")
    failed = max(0, len(devices) - successful)
    now = time.monotonic()
    if failed or duration_ms >= 2000 or now - _tuya_last_diagnostic_log_at >= 60.0:
        _tuya_last_diagnostic_log_at = now
        message = "Periodic Tuya poll diagnostic outcome=%s configured=%d successful=%d failed=%d duration_ms=%d parallel_limit=%d"
        values = ("partial" if failed else "success", len(devices), successful, failed, duration_ms, min(4, len(devices)))
        if failed or duration_ms >= 2000:
            LOG.warning(message, *values)
        else:
            LOG.info(message, *values)
    if _update_tuya_device_records(integration_config, readings, record_status=False):
        hardware_integrations.save_config(integration_config)
    return recorded


def _tuya_event_poll_interval_seconds() -> float:
    try:
        # Keep a quiet interval after each completed fleet pass. A slow/offline
        # device set must not turn the observer into a continuous LAN sweep.
        return max(5.0, min(3600.0, float(os.environ.get("SOLARMINER_TUYA_EVENT_POLL_SECONDS", "5"))))
    except (TypeError, ValueError):
        return 5.0


async def _tuya_device_event_loop() -> None:
    """Poll Tuya LAN devices sequentially, with a quiet interval after each pass."""
    interval = _tuya_event_poll_interval_seconds()
    while True:
        try:
            # Background reads use saved protocol/IP only. Protocol probing and
            # MAC-based rediscovery remain explicit Owner actions.
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
    hardware_integrations.remove_legacy_huawei_config()
    with _energy_sample_lock:
        _latest_deye_sample = None
        _recent_deye_samples.clear()
    sampler = asyncio.create_task(_energy_sampling_loop(), name="solarminer-energy-sampler")
    dispatcher = asyncio.create_task(_energy_dispatch_loop(), name="solarminer-energy-dispatcher")
    tesla_presence = asyncio.create_task(_tesla_presence_loop(), name="solarminer-tesla-presence")
    tuya_observer = asyncio.create_task(_tuya_device_event_loop(), name="solarminer-tuya-event-observer")
    history_retention = asyncio.create_task(_history_retention_loop(), name="solarminer-history-retention")
    try:
        yield
    finally:
        sampler.cancel()
        dispatcher.cancel()
        tesla_presence.cancel()
        tuya_observer.cancel()
        history_retention.cancel()
        try:
            await sampler
        except asyncio.CancelledError:
            pass
        try:
            await dispatcher
        except asyncio.CancelledError:
            pass
        try:
            await tesla_presence
        except asyncio.CancelledError:
            pass
        try:
            await tuya_observer
        except asyncio.CancelledError:
            pass
        try:
            await history_retention
        except asyncio.CancelledError:
            pass


app = FastAPI(title="SolarMiner Gateway", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.middleware("http")
async def report_http_server_errors(request: Request, call_next):
    started = time.perf_counter()
    def route_label() -> str:
        route = request.scope.get("route")
        value = getattr(route, "path", "unmatched")
        return value if isinstance(value, str) and value.startswith("/api/v1/") else "unmatched_or_non_api"
    diagnostic_probe = request.url.path in {
        "/api/v1/health", "/api/v1/info", "/api/v1/bootstrap/status",
    }
    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        LOG.error("Unhandled Gateway request exception route=%s type=%s latency_ms=%d",
                  route_label(), type(exc).__name__, elapsed_ms)
        raise
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    if response.status_code >= 500:
        LOG.error("Gateway returned HTTP server error status=%s route=%s latency_ms=%d",
                  response.status_code, route_label(), elapsed_ms)
    elif elapsed_ms >= 1000:
        LOG.warning("Gateway request slow status=%s route=%s latency_ms=%d",
                    response.status_code, route_label(), elapsed_ms)
    elif diagnostic_probe and elapsed_ms >= 1000:
        LOG.warning("Gateway diagnostic probe slow status=%s route=%s latency_ms=%d",
                    response.status_code, request.url.path, elapsed_ms)
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
            "img-src 'self' data:; font-src 'self'; connect-src 'self' wss: ws://localhost:* ws://127.0.0.1:* http://localhost:* http://127.0.0.1:*; "
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


def register_shelly_blu_device_endpoint(payload: dict[str, Any],
                                        session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    return register_shelly_blu_device(payload, session)


app.post("/api/v1/integrations/shelly/blu/register")(register_shelly_blu_device_endpoint)


def discover_shelly_blu_bridge_endpoint(device_id: str,
                                         session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    return discover_shelly_blu_bridge(device_id, session)


app.post("/api/v1/integrations/shelly/{device_id}/blu/discover")(discover_shelly_blu_bridge_endpoint)


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
async def health() -> dict[str, Any]:
    # Liveness must stay independent of SQLite. Bootstrap and data readiness
    # have their own API routes; a brief database lock must not make the
    # watchdog restart a running server or make endpoint checks flap. Keep
    # this async and I/O-free so slow synchronous device routes cannot occupy
    # the worker thread needed to answer liveness probes.
    return {"status": "ok", "version": VERSION, "package_version": PACKAGE_VERSION}


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


@app.put("/api/v1/site/profile/photo")
def write_site_profile_photo(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    with db() as conn:
        _require_owner(session, conn)
        if not isinstance(payload, dict) or set(payload) != {"kind", "floor_id", "room_id", "photo_data_url"}:
            raise HTTPException(422, "invalid_site_photo_request")
        kind, floor_id, room_id = payload["kind"], payload["floor_id"], payload["room_id"]
        if kind not in {"house", "floor", "plan", "room"} or not isinstance(floor_id, str):
            raise HTTPException(422, "invalid_site_photo_target")
        profile = site_profile.get_profile(conn)
        if kind == "house":
            if floor_id or room_id:
                raise HTTPException(422, "invalid_site_photo_target")
            profile["photo_data_url"] = payload["photo_data_url"]
        else:
            floor = next((item for item in profile["floors"] if item["id"] == floor_id), None)
            if floor is None:
                raise HTTPException(404, "site_floor_not_found")
            if kind == "room":
                room = next((item for item in floor["rooms"] if item["id"] == room_id), None)
                if room is None:
                    raise HTTPException(404, "site_room_not_found")
                room["photo_data_url"] = payload["photo_data_url"]
            elif kind == "plan":
                floor["plan_data_url"] = payload["photo_data_url"]
            else:
                floor["photo_data_url"] = payload["photo_data_url"]
        try:
            result = site_profile.save_profile(conn, profile)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        audit(conn, session["user_id"], "site.profile.photo_configure", f"{kind}:{floor_id or 'property'}", "success", {})
        return result


@app.get("/api/v1/energy/engine")
def energy_engine_summary(history_hours: int = 24, history_until: datetime | None = None,
                          session: dict[str, Any] = Depends(require_permission("read"))) -> dict[str, Any]:
    if isinstance(history_hours, bool) or not 1 <= history_hours <= 168:
        raise HTTPException(422, "history_hours_must_be_1_to_168")
    if history_until is not None:
        if history_until.tzinfo is None:
            raise HTTPException(422, "history_until_requires_timezone")
        history_until_utc = history_until.astimezone(timezone.utc)
        now_utc = datetime.now(timezone.utc)
        if history_until_utc > now_utc + timedelta(minutes=2) or history_until_utc < now_utc - timedelta(days=90):
            raise HTTPException(422, "history_until_outside_retention_window")
    else:
        history_until_utc = None
    with db() as conn:
        with _energy_sample_lock:
            latest_sample = dict(_latest_deye_sample) if _latest_deye_sample else None
            recent_samples = [dict(item) for item in _recent_deye_samples]
        result = energy_engine.build_summary(conn, history_hours, latest_sample=latest_sample,
                                             history_until=history_until_utc, recent_samples=recent_samples)
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
            current_integrations = hardware_integrations.load_config()
            configured_tuya = current_integrations.get("tuya", {}).get("devices", [])
            configured_antminer = current_integrations.get("antminer", {})
            proposed_loads = payload.get("loads", energy_engine.get_config(conn).get("loads", []))
            config_payload = dict(payload)
            if "site_location_name" in config_payload:
                config_payload.update(energy_engine.resolve_site_location(config_payload.pop("site_location_name")))
            tuya_by_id = {item.get("device_id"): item for item in configured_tuya if isinstance(item, dict)}
            if not isinstance(proposed_loads, list):
                raise ValueError("invalid_flexible_loads")
            _sync_gateway_device_inventory(conn, current_integrations)
            for load in proposed_loads:
                if not isinstance(load, dict):
                    raise ValueError("invalid_flexible_load")
                if load.get("control_type") in {"tuya_smart", "tuya_breaker"}:
                    device = tuya_by_id.get(load.get("tuya_device_id"))
                    specs = [entry for entry in [*(device or {}).get("functions", []), *(device or {}).get("status_spec", [])] if isinstance(entry, dict)]
                    allowed_codes = {entry.get("code") for entry in specs if str(entry.get("type", "")).lower() in {"bool", "boolean"}}
                    if device and device.get("switch_code"):
                        allowed_codes.add(device["switch_code"])
                    if not device or load.get("tuya_switch_code") not in allowed_codes:
                        raise ValueError("load_tuya_device_or_switch_code_not_configured")
                    measurement_codes = load.get("tuya_measurement_codes", {})
                    schema_codes = {entry.get("code") for entry in specs if isinstance(entry.get("code"), str)}
                    if not isinstance(measurement_codes, dict) or any(code not in schema_codes for code in measurement_codes.values()):
                        raise ValueError("load_tuya_measurement_code_not_configured")
                    mac = _inventory_mac(device.get("local_mac") or device.get("mac") or device.get("mac_address") or "") if device else ""
                    if mac:
                        linked = conn.execute("SELECT device_key FROM gateway_device_inventory WHERE mac=?", (mac,)).fetchall()
                        if len(linked) == 1:
                            load["control_device_key"] = linked[0]["device_key"]
            conn.execute("BEGIN IMMEDIATE")
            antminer_config = current_integrations.get("antminer", {}) if isinstance(current_integrations, dict) else {}
            antminer_host = antminer_config.get("host") if isinstance(antminer_config, dict) else None
            antminer_equipment_id = (f"braiins-antminer-{hashlib.sha256(antminer_host.encode('utf-8')).hexdigest()[:16]}"
                                     if isinstance(antminer_host, str) and antminer_host else None)
            for load in proposed_loads:
                if not isinstance(load, dict) or load.get("kind") != "miner" or load.get("control_type") != "antminer_braiins":
                    continue
                if load.get("device_key"):
                    identity = conn.execute("SELECT mac FROM gateway_device_inventory WHERE device_key=?", (load["device_key"],)).fetchone()
                    if not identity or not identity["mac"]:
                        raise ValueError("miner_mac_identity_not_found")
                if antminer_equipment_id:
                    load.setdefault("equipment_id", antminer_equipment_id)
                if not load.get("device_key"):
                    local_mac = _inventory_mac(antminer_config.get("local_mac") or antminer_config.get("mac") or "")
                    if local_mac:
                        identity = conn.execute("SELECT device_key FROM gateway_device_inventory WHERE mac=?", (local_mac,)).fetchone()
                    else:
                        candidates = conn.execute("SELECT device_key FROM gateway_device_inventory WHERE mac<>'' AND (source_provider='antminer' OR device_type='miner')").fetchall()
                        identity = candidates[0] if len(candidates) == 1 else None
                    if identity:
                        load["device_key"] = identity["device_key"]
            config_payload["loads"] = proposed_loads
            result = energy_engine.save_config(conn, config_payload)
            # Keep the flexible-load settings attached to the canonical miner
            # equipment record, so its display name and characteristics do not
            # diverge between Energy and the miner management page.
            energy_registry.ensure_schema(conn)
            antminer_host = configured_antminer.get("host") if isinstance(configured_antminer, dict) else None
            miner_equipment_id = (f"braiins-antminer-{hashlib.sha256(antminer_host.encode('utf-8')).hexdigest()[:16]}"
                                  if isinstance(antminer_host, str) and antminer_host else None)
            for load in result.get("loads", []):
                if load.get("kind") != "miner" or load.get("control_type") != "antminer_braiins":
                    continue
                equipment_id = load.get("equipment_id") or miner_equipment_id
                if not equipment_id:
                    continue
                equipment = conn.execute("SELECT id,category,config_json FROM energy_equipment WHERE id=?", (equipment_id,)).fetchone()
                if not equipment or equipment["category"] != "mineradoras":
                    continue
                try:
                    equipment_config = json.loads(equipment["config_json"] or "{}")
                except (TypeError, ValueError):
                    equipment_config = {}
                if not isinstance(equipment_config, dict):
                    equipment_config = {}
                equipment_config["load_characteristics"] = {
                    "rated_power_w": load["rated_power_w"],
                    "minimum_power_w": load["minimum_power_w"],
                    "maximum_power_w": load["maximum_power_w"],
                    "priority": load["priority"],
                    "automatic": load["automatic"],
                }
                conn.execute("UPDATE energy_equipment SET name=?,config_json=?,updated_at=? WHERE id=?",
                             (load["name"], json.dumps(equipment_config, separators=(",", ":")), utcnow(), equipment_id))
                # Update the physical identity by its stable inventory key/MAC.
                if load.get("device_key"):
                    identity = conn.execute("SELECT device_key,mac FROM gateway_device_inventory WHERE device_key=?", (load["device_key"],)).fetchone()
                    if identity and identity["mac"]:
                        conn.execute("UPDATE gateway_device_inventory SET name=?,name_source='owner',updated_at=? WHERE device_key=?",
                                     (load["name"], utcnow(), identity["device_key"]))
            audit(conn, session["user_id"], "energy.engine.configure", "energy-engine", "success", {
                "battery_capacity_kwh_configured": result["battery_capacity_kwh"] is not None,
                "minimum_soc_percent": result["minimum_soc_percent"],
                "maximum_soc_percent": result["maximum_soc_percent"],
            })
            conn.commit()
            return result
        except ValueError as exc:
            if conn.in_transaction:
                conn.rollback()
            raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/energy/engine/config")
def energy_engine_configuration(session: dict[str, Any] = Depends(require_permission("read"))) -> dict[str, Any]:
    """Return saved Engine settings only to the Owner who can edit them."""
    with db() as conn:
        _require_owner(session, conn)
        return energy_engine.get_config(conn)


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
        result = hardware_integrations.public_config()
        with db() as conn:
            # A failed poll is not proof that the last successful sample vanished.
            # Keep that sample usable for a short grace window while exposing the
            # latest attempt reason separately; UI clients retain values through
            # transient LAN timeouts instead of flickering offline immediately.
            telemetry = energy_engine.read_tuya_telemetry(conn, max_age_seconds=15)
            feature_rows = conn.execute("SELECT canonical_key,display_name,canonical_type,units_json FROM tuya_canonical_features ORDER BY category,display_name COLLATE NOCASE").fetchall()
        normalized = []
        for feature in feature_rows:
            try:
                units = json.loads(feature["units_json"] or "[]")
            except (TypeError, json.JSONDecodeError):
                units = []
            normalized.append({"code": feature["canonical_key"], "label": feature["display_name"],
                               "data_type": feature["canonical_type"], "units": units if isinstance(units, list) else []})
        result.setdefault("tuya", {})["normalized_characteristics"] = normalized
        for product in result.get("tuya", {}).get("product_catalog", {}).values():
            if isinstance(product, dict):
                profile = product.get("dps_profile")
                if not isinstance(profile, dict):
                    profile = {}
                    product["dps_profile"] = profile
                profile["normalized_characteristics"] = normalized
        for device in result.get("tuya", {}).get("devices", []):
            if not isinstance(device, dict):
                continue
            row = telemetry.get(device.get("device_id"), {})
            if not row:
                continue
            device["current_status"] = row.get("status", [])
            device["last_status_at"] = row.get("observed_at")
            device["local_control_state"] = "ready" if row.get("fresh") else "unavailable"
            device["local_verified"] = bool(device.get("local_verified") or row.get("verified"))
            device["current_connection_state"] = "local_responded" if row.get("fresh") else "failed"
            device["current_status_reason"] = None if row.get("fresh") else row.get("reason")
            device["last_read_attempt_state"] = row.get("connection_state", "failed")
            device["last_read_attempt_at"] = row.get("last_attempt_at")
            device["last_read_error"] = row.get("reason")
        return result
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
                "providers": sorted(k for k in ("deye", "deye_cloud", "antminer", "tuya") if k in payload),
                "provider_secrets_returned": False,
            })
            return result
        except ValueError as exc:
            audit(conn, session["user_id"], "hardware.integrations.configure", "gateway", "rejected", {"reason": str(exc)[:120]})
            raise HTTPException(422, str(exc)) from exc
        except (OSError, json.JSONDecodeError) as exc:
            LOG.error("Hardware integration configuration save failed (%s)", type(exc).__name__)
            raise HTTPException(500, "integration_config_save_failed") from exc


def _require_deye_cloud_config() -> dict[str, Any]:
    config = hardware_integrations.load_config().get("deye_cloud", {})
    if not isinstance(config, dict) or not config.get("app_id") or not config.get("app_secret") or not config.get("email") or not config.get("password"):
        raise HTTPException(409, "deye_cloud_not_configured")
    return config


@app.post("/api/v1/integrations/deye-cloud/stations")
def deye_cloud_stations(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
    try:
        stations = hardware_integrations.deye_cloud_list_stations(_require_deye_cloud_config())
        with db() as conn:
            audit(conn, session["user_id"], "hardware.deye_cloud.stations", "deye-cloud", "success", {"station_count": len(stations)})
        return {"stations": stations, "secrets_returned": False}
    except HTTPException:
        raise
    except (RuntimeError, ValueError, OSError) as exc:
        reason = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "deye_cloud_connection_failed"
        raise HTTPException(502, reason) from exc


@app.post("/api/v1/integrations/deye-cloud/history/import")
def deye_cloud_history_import(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
    station_id = payload.get("station_id") if isinstance(payload, dict) else None
    if isinstance(station_id, bool) or not str(station_id or "").isdigit() or len(str(station_id)) > 32:
        raise HTTPException(422, "invalid_deye_cloud_station_id")
    job_id = secrets.token_urlsafe(18)
    with _deye_history_jobs_lock:
        for existing_id, existing in _deye_history_jobs.items():
            if existing.get("owner_id") == session["user_id"] and existing.get("status") in {"queued", "running"}:
                return {"job_id": existing_id, "status": existing["status"], "progress": existing["progress"],
                        "phase": existing["phase"], "message": existing["message"]}
        _deye_history_jobs[job_id] = {"owner_id": session["user_id"], "status": "queued", "progress": 0,
                                      "phase": "queued", "message": "Importação na fila…", "updated_at": time.time()}
    threading.Thread(target=_run_deye_cloud_history_import,
                     args=(job_id, session["user_id"], str(station_id)), daemon=True,
                     name="deye-cloud-history-import").start()
    return {"job_id": job_id, "status": "queued", "progress": 0, "phase": "queued", "message": "Importação na fila…"}


def _set_deye_history_job(job_id: str, **updates: Any) -> None:
    with _deye_history_jobs_lock:
        job = _deye_history_jobs.get(job_id)
        if job is not None:
            job.update(updates, updated_at=time.time())


def _run_deye_cloud_history_import(job_id: str, owner_id: str, station_id: str) -> None:
    try:
        _set_deye_history_job(job_id, status="running", phase="connecting", progress=1,
                              message="A autenticar e a ligar à Deye Cloud…")
        rows = hardware_integrations.deye_cloud_history(
            _require_deye_cloud_config(), station_id, days=90,
            progress_callback=lambda value, message: _set_deye_history_job(
                job_id, status="running", phase="downloading", progress=max(1, min(78, value)), message=message))
        total_rows = len(rows)
        _set_deye_history_job(job_id, phase="saving", progress=80,
                              message=f"A gravar {total_rows} amostras no histórico local…", source_rows=total_rows)
        now_text = datetime.now(timezone.utc).isoformat(timespec="seconds")
        hardware_config = hardware_integrations.load_config()
        deye_lan = hardware_config.get("deye", {}) if isinstance(hardware_config.get("deye", {}), dict) else {}
        identity_source = (f"{deye_lan.get('host', '')}|{deye_lan.get('unit_id', 1)}" if deye_lan.get("host")
                           else f"deye-cloud|{station_id}")
        identity = hashlib.sha256(identity_source.encode("utf-8")).hexdigest()[:16]
        inverter_equipment_id = f"deye-inverter-{identity}"
        battery_equipment_id = f"deye-battery-{identity}"
        with db() as conn:
            energy_registry.ensure_schema(conn)
            if not conn.execute("SELECT 1 FROM energy_equipment WHERE id=?", (inverter_equipment_id,)).fetchone():
                energy_registry.upsert_equipment(conn, {"category": "inversores", "name": "Deye Inversor",
                    "manufacturer": "Deye", "model": "Cloud history", "protocol": "Deye Cloud OpenAPI",
                    "connection_state": "CONNECTED", "declared_capabilities": ["pv_power", "load_power"],
                    "implemented_capabilities": ["historical_readings"], "verified_capabilities": [], "config": {}, "limitations": []},
                    equipment_id=inverter_equipment_id)
            if not conn.execute("SELECT 1 FROM energy_equipment WHERE id=?", (battery_equipment_id,)).fetchone():
                energy_registry.upsert_equipment(conn, {"category": "baterias", "name": "Deye Bateria",
                    "manufacturer": "Deye", "model": "Cloud history", "protocol": "Deye Cloud OpenAPI",
                    "connection_state": "CONNECTED", "declared_capabilities": ["battery_power", "battery_soc"],
                    "implemented_capabilities": ["historical_readings"], "verified_capabilities": [], "config": {}, "limitations": []},
                    equipment_id=battery_equipment_id)
            inserted = 0
            mapped = {"generationPower": (inverter_equipment_id, "pv_total_power", "W"),
                      "consumptionPower": (inverter_equipment_id, "load_total_power", "W"),
                      "gridPower": (inverter_equipment_id, "grid_power", "W"),
                      "batterySOC": (battery_equipment_id, "battery_soc_percent", "%"),
                      "batteryVoltage": (battery_equipment_id, "battery_voltage", "V"),
                      "chargePower": (battery_equipment_id, "battery_charge_power", "W"),
                      "dischargePower": (battery_equipment_id, "battery_discharge_power", "W")}
            for index, item in enumerate(rows, start=1):
                observed = hardware_integrations._deye_cloud_timestamp(item.get("timeStamp", item.get("dateTime", item.get("timestamp"))))
                if not observed:
                    continue
                values = dict(item)
                charge, discharge = values.get("chargePower"), values.get("dischargePower")
                if isinstance(charge, (int, float)) and not isinstance(charge, bool) and isinstance(discharge, (int, float)) and not isinstance(discharge, bool):
                    values["batteryOutputPower"] = float(discharge) - float(charge)
                mapped["batteryOutputPower"] = (battery_equipment_id, "battery_output_power", "W")
                for source_field, (equipment_id, field, unit) in mapped.items():
                    value = values.get(source_field)
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                        continue
                    cur = conn.execute("INSERT OR IGNORE INTO energy_readings VALUES(?,?,?,?,?,?,?,?,?)",
                        (str(uuid.uuid4()), equipment_id, field, json.dumps(float(value)), unit, observed,
                         "DEYE_CLOUD_HISTORY", "LIVE_UNVERIFIED", json.dumps({"station_id": str(station_id), "origin": "Deye Cloud OpenAPI"})))
                    inserted += cur.rowcount
                if index == total_rows or index % 100 == 0:
                    progress = 80 + round(18 * index / max(1, total_rows))
                    _set_deye_history_job(job_id, phase="saving", progress=progress,
                                          message=f"A gravar amostras: {index} de {total_rows} processadas…",
                                          processed_rows=index, readings_added=inserted)
            audit(conn, owner_id, "hardware.deye_cloud.history_import", "deye-cloud", "success",
                  {"station_id": str(station_id), "source_rows": len(rows), "readings_added": inserted, "days": 90})
            result = {"status": "imported", "station_id": str(station_id), "source_rows": len(rows),
                      "readings_added": inserted, "range_days": 90, "source": "DEYE_CLOUD_HISTORY",
                      "local_history_preserved": True, "secrets_returned": False, "completed_at": now_text}
            _set_deye_history_job(job_id, status="completed", phase="completed", progress=100,
                                  message=f"Importação concluída: {inserted} leituras novas.", result=result)

    except HTTPException as exc:
        _set_deye_history_job(job_id, status="failed", phase="failed", error={"status": exc.status_code,
                              "message": str(exc.detail)})
    except ValueError as exc:
        _set_deye_history_job(job_id, status="failed", phase="failed", error={"status": 422, "message": str(exc)})
    except (RuntimeError, OSError) as exc:
        reason = str(exc) if isinstance(exc, RuntimeError) else "deye_cloud_connection_failed"
        _set_deye_history_job(job_id, status="failed", phase="failed", error={"status": 502, "message": reason})
    except Exception as exc:
        LOG.exception("Deye Cloud history import failed (%s)", type(exc).__name__)
        _set_deye_history_job(job_id, status="failed", phase="failed",
                              error={"status": 500, "message": "deye_cloud_history_import_failed"})


@app.get("/api/v1/integrations/deye-cloud/history/import/{job_id}")
def deye_cloud_history_import_status(job_id: str, session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
    with _deye_history_jobs_lock:
        job = _deye_history_jobs.get(job_id)
        if not job or job.get("owner_id") != session["user_id"]:
            raise HTTPException(404, "deye_cloud_history_job_not_found")
        return {key: value for key, value in job.items() if key != "owner_id"}


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
            tuya["product_schemas"] = synced.get("product_schemas", tuya.get("product_schemas", {}))
            tuya["category_schemas"] = synced.get("category_schemas", tuya.get("category_schemas", {}))
            tuya["product_dps_maps"] = synced.get("product_dps_maps", tuya.get("product_dps_maps", {}))
            config["tuya"] = tuya
            hardware_integrations.save_config(config)
            _sync_gateway_device_inventory(conn, config)
            dps_maps_saved = _persist_tuya_product_dps_map(conn, tuya.get("product_schemas"))
            capabilities_saved = _persist_tuya_pid_capabilities(conn, tuya.get("product_schemas"))
            audit(conn, session["user_id"], "hardware.tuya.sync", "gateway", "success", {
                "device_count": synced["device_count"],
                "product_dps_maps": dps_maps_saved,
                "product_capabilities": capabilities_saved,
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


def _deye_energy_identity(conn: sqlite3.Connection, deye: dict[str, Any]) -> tuple[str, str | None]:
    """Prefer the inventoried network MAC over an IP that may change.

    The gateway inventory can have more than one inverter. Use a MAC only when
    the snapshot carries it or exactly one applicable Deye/inverter MAC can be
    resolved; otherwise retain the host-based identity rather than merging
    potentially different physical equipment.
    """
    unit_id = deye.get("unit_id", 1)
    mac = _inventory_mac(deye.get("inventory_mac") or deye.get("local_mac") or deye.get("mac") or "")
    if not mac:
        host = str(deye.get("host") or "")
        try:
            rows = conn.execute("""SELECT mac,last_ip FROM gateway_device_inventory
                WHERE mac<>'' AND (device_type='inverter' OR source_provider='deye')""").fetchall()
        except sqlite3.Error:
            rows = []
        matching = {_inventory_mac(row["mac"]) for row in rows
                    if _inventory_mac(row["mac"]) and str(row["last_ip"] or "") == host}
        if len(matching) == 1:
            mac = next(iter(matching))
        else:
            unique = {_inventory_mac(row["mac"]) for row in rows if _inventory_mac(row["mac"])}
            if len(unique) == 1:
                mac = next(iter(unique))
    if mac:
        identity_source = f"deye-mac|{mac}|{unit_id}"
        return hashlib.sha256(identity_source.encode("utf-8")).hexdigest()[:16], mac
    identity_source = f"{deye.get('host', '')}|{unit_id}"
    return hashlib.sha256(identity_source.encode("utf-8")).hexdigest()[:16], None


def _merge_legacy_deye_energy_history(conn: sqlite3.Connection, *, category: str,
                                      equipment_id: str, model: str | None,
                                      unit_id: Any, identity_mac: str | None) -> int:
    """Reattach old IP-keyed Deye samples only when the installation is unambiguous.

    Older releases keyed the equipment row by IP and did not retain that IP in
    its metadata. Require a unique inventoried inverter MAC plus exact model
    and Modbus unit matches before moving samples; keep the old equipment row
    as an archived reference for any associated evidence.
    """
    if not identity_mac or not model:
        return 0
    try:
        inventory_macs = {_inventory_mac(row[0]) for row in conn.execute(
            "SELECT DISTINCT mac FROM gateway_device_inventory WHERE mac<>'' AND (device_type='inverter' OR source_provider='deye')")
            if _inventory_mac(row[0])}
    except sqlite3.Error:
        return 0
    if inventory_macs != {identity_mac}:
        return 0
    canonical_model = str(model).strip().casefold()
    try:
        canonical_unit = int(unit_id)
    except (TypeError, ValueError):
        return 0
    prefix = "deye-inverter-" if category == "inversores" else "deye-battery-"
    candidates = conn.execute("""SELECT id,model,config_json FROM energy_equipment
        WHERE category=? AND protocol='Modbus TCP FC03' AND id LIKE ? AND id<>?""",
                              (category, prefix + "%", equipment_id)).fetchall()
    moved = 0
    for row in candidates:
        if str(row["model"] or "").strip().casefold() != canonical_model:
            continue
        try:
            legacy_config = json.loads(row["config_json"] or "{}")
            legacy_unit = int(legacy_config.get("unit_id", 1))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        legacy_mac = _inventory_mac(legacy_config.get("identity_mac") or "")
        if legacy_unit != canonical_unit or (legacy_mac and legacy_mac != identity_mac):
            continue
        old_id = row["id"]
        conn.execute("""DELETE FROM energy_readings AS old WHERE old.equipment_id=? AND EXISTS(
            SELECT 1 FROM energy_readings AS current WHERE current.equipment_id=?
              AND current.field=old.field AND current.observed_at=old.observed_at
              AND current.source=old.source)""", (old_id, equipment_id))
        cursor = conn.execute("UPDATE energy_readings SET equipment_id=? WHERE equipment_id=?",
                              (equipment_id, old_id))
        moved += max(0, cursor.rowcount)
        archived_config = {**legacy_config, "identity_mac": identity_mac,
                           "historical_identity_merged_into": equipment_id}
        archived_name = "Inversor Deye · identidade antiga" if category == "inversores" else "Bateria Deye · identidade antiga"
        conn.execute("""UPDATE energy_equipment SET name=?,protocol=?,connection_state='UNKNOWN',
            config_json=?,status='ARCHIVED',updated_at=? WHERE id=?""",
            (archived_name, "Modbus TCP FC03 (histórico associado)",
             json.dumps(archived_config, sort_keys=True, separators=(",", ":")), utcnow(), old_id))
    return moved


def _persist_deye_telemetry(conn: sqlite3.Connection, deye: dict[str, Any] | None) -> int:
    """Store a successful Deye FC03 snapshot in the canonical energy registry."""
    if not isinstance(deye, dict) or deye.get("connection_state") != "mapped_registers_response":
        return 0
    metrics = deye.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        return 0
    identity, identity_mac = _deye_energy_identity(conn, deye)
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
            "config": {"unit_id": deye.get("unit_id", 1), "trust": "LIVE_UNVERIFIED",
                       "identity_mac": identity_mac, "last_communicated_ip": deye.get("host")},
        }, equipment_id=equipment_id)
        if category in {"inversores", "baterias"}:
            _merge_legacy_deye_energy_history(conn, category=category, equipment_id=equipment_id,
                model=deye.get("model"), unit_id=deye.get("unit_id", 1), identity_mac=identity_mac)
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
    host = miner.get("host") if isinstance(miner, dict) else None
    if not isinstance(host, str) or not host:
        return 0
    equipment_id = f"braiins-antminer-{hashlib.sha256(host.encode('utf-8')).hexdigest()[:16]}"
    if miner.get("connection_state") != "api_responded":
        conn.execute("UPDATE energy_equipment SET connection_state='DISCONNECTED',updated_at=? WHERE id=?",
                     (datetime.now(timezone.utc).isoformat(timespec="microseconds"), equipment_id))
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

    observed_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    try:
        timestamp = miner.get("observed_at")
        if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool) and math.isfinite(float(timestamp)):
            observed_at = datetime.fromtimestamp(float(timestamp), timezone.utc).isoformat(timespec="microseconds")
    except (OverflowError, OSError, ValueError):
        pass
    # A user-assigned equipment name is canonical; periodic telemetry must not
    # replace it with the connector's model label.
    saved_identity = conn.execute("SELECT name,config_json FROM energy_equipment WHERE id=? AND category='mineradoras'",
                                  (equipment_id,)).fetchone()
    owner_identity = conn.execute("SELECT name FROM gateway_device_inventory WHERE mac<>'' AND source_provider='antminer' AND name_source='owner' ORDER BY updated_at DESC LIMIT 1").fetchone()
    display_name = (owner_identity["name"] if owner_identity else
                    saved_identity["name"] if saved_identity else "Antminer S19K Pro")
    try:
        equipment_config = json.loads(saved_identity["config_json"] or "{}") if saved_identity else {}
    except (TypeError, ValueError):
        equipment_config = {}
    if not isinstance(equipment_config, dict):
        equipment_config = {}
    equipment_config.update({"host": host, "port": miner.get("port", 4028), "trust": "LIVE_UNVERIFIED"})
    energy_registry.upsert_equipment(conn, {
        "category": "mineradoras", "name": display_name, "manufacturer": "Bitmain",
        "model": "S19K Pro", "protocol": "Braiins OS · telemetria CGMiner + controlo REST",
        "connection_state": "CONNECTED", "status": "CONFIGURED",
        "declared_capabilities": ["mining telemetry", "mining control via Braiins OS REST"],
        "implemented_capabilities": ["CGMiner summary/stats/devs telemetry", "Braiins REST start/pause/stop/power target", "Braiins tuner status when available"],
        "verified_capabilities": [], "limitations": ["Model identity is configured, not verified by the API response."],
        "config": equipment_config,
    }, equipment_id=equipment_id)
    for field, value, unit, api_field in metrics:
        energy_registry.add_reading(conn, equipment_id, {
            "field": field, "value": value, "unit": unit, "observed_at": observed_at,
            "source": "BRAIINS_CGMINER_READ_ONLY", "trust": "LIVE_UNVERIFIED",
            "evidence": {"api_field": api_field, "control_commands_sent": False},
        })
    return len(metrics)


def _mark_antminer_disconnected(conn: sqlite3.Connection, config: dict[str, Any]) -> None:
    """Do not leave a stale successful miner read labelled as currently connected."""
    host = config.get("host") if isinstance(config, dict) else None
    if isinstance(host, str) and host:
        equipment_id = f"braiins-antminer-{hashlib.sha256(host.encode('utf-8')).hexdigest()[:16]}"
        conn.execute("UPDATE energy_equipment SET connection_state='DISCONNECTED',updated_at=? WHERE id=?",
                     (datetime.now(timezone.utc).isoformat(timespec="microseconds"), equipment_id))


def _persist_antminer_braiins_tuner(conn: sqlite3.Connection, config: dict[str, Any],
                                    result: dict[str, Any] | None) -> int:
    """Feed authenticated Braiins tuner readings into the same live equipment card."""
    if (not isinstance(result, dict) or result.get("operation") != "tuner"
            or result.get("state") not in {"read", "read_data"}):
        return 0
    host = config.get("host") if isinstance(config, dict) else None
    data = result.get("data")
    if not isinstance(host, str) or not host or not isinstance(data, dict):
        return 0
    mode = data.get("mode_state", data.get("modeState", {}))
    if not isinstance(mode, dict):
        mode = {}
    power_state = (mode.get("powertargetmodestate") or mode.get("power_target_mode_state")
                   or mode.get("powerTargetModeState") or {})
    if not isinstance(power_state, dict):
        power_state = {}
    profile = power_state.get("profile") or {}
    if not isinstance(profile, dict):
        profile = {}
    current = power_state.get("current_target", power_state.get("currentTarget")) or {}
    if not isinstance(current, dict):
        current = {}
    measured = profile.get("measured_hashrate", profile.get("measuredHashrate")) or {}
    estimated = profile.get("estimated_power_consumption", profile.get("estimatedPowerConsumption")) or {}
    profile_target = profile.get("target", profile.get("power_target")) or {}
    if not isinstance(measured, dict):
        measured = {}
    if not isinstance(estimated, dict):
        estimated = {}
    if not isinstance(profile_target, dict):
        profile_target = {}

    metrics: list[tuple[str, float, str, str]] = []

    def add_metric(field: str, value: Any, unit: str, api_field: str) -> None:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) and value >= 0:
            metrics.append((field, round(float(value), 3), unit, api_field))

    add_metric("miner_hashrate_avg_ghs", measured.get("gigahash_per_second", measured.get("gigahashPerSecond")),
               "GH/s", "tuner_state.profile.measured_hashrate.gigahash_per_second")
    add_metric("miner_power_w", estimated.get("watt"), "W",
               "tuner_state.profile.estimated_power_consumption.watt")
    add_metric("miner_power_limit_w", current.get("watt"), "W",
               "tuner_state.current_target.watt")
    add_metric("miner_power_profile_w", profile_target.get("watt"), "W",
               "tuner_state.profile.target.watt")
    if not metrics:
        return 0

    identity = hashlib.sha256(host.encode("utf-8")).hexdigest()[:16]
    equipment_id = f"braiins-antminer-{identity}"
    observed_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    energy_registry.upsert_equipment(conn, {
        "category": "mineradoras", "name": "Antminer S19K Pro", "manufacturer": "Bitmain",
        "model": "S19K Pro", "protocol": "Braiins OS REST · tuner",
        "connection_state": "CONNECTED", "status": "CONFIGURED",
        "declared_capabilities": ["Braiins tuner telemetry", "mining control via Braiins OS REST"],
        "implemented_capabilities": ["Braiins REST tuner state", "CGMiner summary/stats/devs telemetry"],
        "verified_capabilities": [], "limitations": ["Model identity is configured, not verified by the API response."],
        "config": {"host": host, "trust": "LIVE_UNVERIFIED"},
    }, equipment_id=equipment_id)
    for field, value, unit, api_field in metrics:
        energy_registry.add_reading(conn, equipment_id, {
            "field": field, "value": value, "unit": unit, "observed_at": observed_at,
            "source": "BRAIINS_REST_TUNER", "trust": "LIVE_UNVERIFIED",
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
            if result.get("antminer") is None:
                _mark_antminer_disconnected(conn, hardware_integrations.load_config().get("antminer", {}))
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
        raw_observed_at = reading.get("observed_at")
        try:
            observed_at = (datetime.fromtimestamp(float(raw_observed_at), timezone.utc).isoformat()
                           if isinstance(raw_observed_at, (int, float)) else
                           datetime.fromisoformat(str(raw_observed_at).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat())
        except (TypeError, ValueError, OSError, OverflowError):
            observed_at = datetime.now(timezone.utc).isoformat()
        latest = conn.execute("SELECT observed_at FROM device_observations WHERE device_id=? AND observation_key='__availability'",
                              (device_id,)).fetchone()
        if latest:
            try:
                if datetime.fromisoformat(latest["observed_at"].replace("Z", "+00:00")) >= datetime.fromisoformat(observed_at):
                    continue
            except (TypeError, ValueError):
                pass
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


def _update_tuya_device_records(config: dict[str, Any], readings: list[dict[str, Any]], *,
                                record_status: bool = True) -> bool:
    """Persist device availability and, when requested, the last valid status."""
    tuya = config.get("tuya", {}) if isinstance(config.get("tuya"), dict) else {}
    by_id = {item.get("device_id"): item for item in readings if isinstance(item, dict)}
    changed = False
    for device in tuya.get("devices", []):
        if not isinstance(device, dict):
            continue
        reading = by_id.get(device.get("device_id"))
        if reading is None:
            continue
        valid = (reading.get("connection_state") == "local_responded"
                 and isinstance(reading.get("status"), list) and bool(reading.get("status")))
        state = "ready" if valid else "unavailable"
        if device.get("local_control_state") != state:
            device["local_control_state"] = state
            changed = True
        if record_status:
            was_verified = bool(device.get("local_verified"))
            device["local_verified"] = bool(was_verified or valid)
            changed = changed or device["local_verified"] != was_verified
        if valid and record_status:
            device["current_status"] = reading["status"]
            device["last_status_at"] = int(time.time())
            changed = True
    return changed


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
    """Measure read-only Tuya LAN response times for all devices or one selected device."""
    payload = payload or {}
    if set(payload) - {"rounds", "device_id"}:
        raise HTTPException(422, "tuya_diagnostic_payload_invalid")
    rounds = payload.get("rounds", 3)
    if isinstance(rounds, bool) or not isinstance(rounds, int) or not 1 <= rounds <= 5:
        raise HTTPException(422, "tuya_diagnostic_rounds_must_be_1_to_5")
    selected_device_id = payload.get("device_id")
    if selected_device_id is not None and (not isinstance(selected_device_id, str)
                                           or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", selected_device_id)):
        raise HTTPException(422, "tuya_diagnostic_device_id_invalid")
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        full_config = hardware_integrations.load_config()
        config = full_config.get("tuya", {}) if isinstance(full_config.get("tuya"), dict) else {}
        devices = [item for item in config.get("devices", [])
                   if isinstance(item, dict) and isinstance(item.get("device_id"), str)]
        if selected_device_id is not None:
            devices = [item for item in devices if item.get("device_id") == selected_device_id]
            if not devices:
                raise HTTPException(404, "tuya_device_not_configured")
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
                mac = hardware_integrations._tuya_normalize_mac(item.get("local_mac"))
                if not item.get("local_key") or (not host and not mac):
                    continue
                if host:
                    try:
                        hardware_integrations._private_ip(host)
                    except ValueError:
                        if not mac:
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
                    mac = hardware_integrations._tuya_normalize_mac(item.get("local_mac"))
                    if not item.get("local_key"):
                        reason = "tuya_local_key_missing"
                    elif not host:
                        reason = "tuya_local_ip_unresolved_from_mac" if mac else "private_lan_target_required"
                    else:
                        try:
                            hardware_integrations._private_ip(host)
                            reason = "tuya_lan_read_unavailable"
                        except ValueError as exc:
                            reason = str(exc)
                    samples[device_id].append({"ok": False, "latency_ms": None,
                                               "reason": reason, "status": []})
                else:
                    ok = row.get("connection_state") == "local_responded"
                    samples[device_id].append({"ok": ok,
                                               # Only successful LAN replies are response-time samples.
                                               # Setup failures are not network latency.
                                               "latency_ms": row.get("latency_ms") if ok else None,
                                               "reason": row.get("reason"),
                                               "status": row.get("status", []) if ok else [],
                                               "local_protocol": row.get("local_protocol") if ok else None,
                                               "ip_refreshed_by_mac": bool(row.get("ip_refreshed_by_mac")),
                                               "ip_cleared_missing_mac": bool(row.get("ip_cleared_missing_mac"))})
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        verified_ids = {device_id for device_id, rows in samples.items()
                        if any(row.get("ok") and row.get("status") for row in rows)}
        if verified_ids:
            configured_devices = config.get("devices", []) if isinstance(config.get("devices"), list) else []
            for item in configured_devices:
                if not isinstance(item, dict) or item.get("device_id") not in verified_ids:
                    continue
                item["local_verified"] = True
                item["local_control_state"] = "ready"
                latest_protocol = next((row.get("local_protocol") for row in reversed(samples[item["device_id"]])
                                        if row.get("ok") and row.get("local_protocol")), None)
                if latest_protocol:
                    item["local_protocol"] = latest_protocol
            full_config["tuya"] = config
            hardware_integrations.save_config(full_config)
            _sync_gateway_device_inventory(conn, full_config)
            conn.commit()
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
                           "connection_state": "local_responded" if times else "failed",
                           "status": next((row["status"] for row in reversed(rows) if row["ok"]), []),
                           "local_protocol": next((row["local_protocol"] for row in reversed(rows) if row["ok"]), None),
                           "ip_refreshed_by_mac": any(row.get("ip_refreshed_by_mac") for row in rows),
                           "ip_cleared_missing_mac": any(row.get("ip_cleared_missing_mac") for row in rows),
                           "power_telemetry_configured": power_telemetry,
                           "reason": next((row["reason"] for row in rows if row.get("reason")),
                                          "private_lan_target_required" if not item.get("local_ip") else None)})
        return {"rounds": rounds, "configured_count": len(devices),
                "lan_testable_count": len(configured_lan),
                "confirmed_device_count": len(verified_ids),
                "elapsed_ms": elapsed_ms, "sweep_times_ms": sweep_times,
                "devices": result, "control_commands_sent": False}


@app.post("/api/v1/integrations/tuya/lan-reachability")
def tuya_lan_reachability(payload: dict[str, Any],
                          session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Test only the selected configured device's LAN TCP reachability; no Tuya status or cloud calls."""
    device_id = payload.get("device_id") if isinstance(payload, dict) else None
    if not isinstance(device_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", device_id):
        raise HTTPException(422, "tuya_device_id_invalid")
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        devices = hardware_integrations.load_config().get("tuya", {}).get("devices", [])
        device = next((item for item in devices if isinstance(item, dict) and item.get("device_id") == device_id), None)
        if device is None:
            raise HTTPException(404, "tuya_device_not_configured")
        host = device.get("local_ip")
        if not host:
            return {"device_id": device_id, "connection_state": "failed", "reason": "private_lan_target_required",
                    "local_mac": device.get("local_mac", ""), "status_read": False, "cloud_requested": False}
        try:
            probe = hardware_integrations.probe_tuya_lan_reachability(host)
        except ValueError as exc:
            return {"device_id": device_id, "connection_state": "failed", "reason": str(exc),
                    "local_mac": device.get("local_mac", ""), "status_read": False, "cloud_requested": False}
        state = probe["state"]
        return {"device_id": device_id, "connection_state": state, "reason": probe.get("reason"),
                "local_ip": probe.get("host", host), "local_mac": device.get("local_mac", ""),
                "port": probe.get("port"), "latency_ms": probe.get("latency_ms"),
                "status_read": False, "dps_read": False, "cloud_requested": False}


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
                discovered = hardware_integrations.discover_tuya_lan_devices(devices, scan_seconds=10)
            except Exception as exc:
                # Broadcast discovery can be blocked by Wi-Fi isolation; still try configured MACs.
                scan_error = type(exc).__name__[:64]
                LOG.exception("Tuya LAN discovery failed (%s); trying neighbor cache", scan_error)
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
                    found = {"ip": host, "version": value.get("version"), "mac": value.get("mac")}
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


@app.get("/api/v1/device-inventory")
def read_gateway_device_inventory(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Read the shared inventory, including cloud-synced and manually named devices."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        _sync_gateway_device_inventory(conn, hardware_integrations.load_config())
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM gateway_device_inventory ORDER BY CASE confirmation_status WHEN 'pending' THEN 0 ELSE 1 END, name COLLATE NOCASE")]
        conn.commit()
        return {"devices": rows, "device_count": len(rows)}


@app.get("/api/v1/smart-products/catalog")
def read_smart_product_catalog(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Return product identities and protocol capabilities known to the local catalog."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        # Keep legacy Tuya/Shelly clients light; the complete Zigbee catalog is
        # available through the paginated protocol-specific endpoint below.
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM smart_product_catalog WHERE protocol<>'zigbee2mqtt' ORDER BY manufacturer COLLATE NOCASE, product_name COLLATE NOCASE, product_code")]
        config = hardware_integrations.load_config()
        tuya = config.get("tuya") if isinstance(config.get("tuya"), dict) else {}
        schemas = hardware_integrations._bounded_tuya_product_schemas(tuya.get("product_schemas"))
        catalog_schemas = hardware_integrations._bounded_tuya_product_schemas(tuya.get("product_catalog"))
        for product_id, product_schema in catalog_schemas.items():
            current = schemas.get(product_id, {})
            schemas[product_id] = {**current, **product_schema}
            for key in ("functions", "status_spec"):
                if not schemas[product_id].get(key) and current.get(key): schemas[product_id][key] = current[key]
            if not isinstance(schemas[product_id].get("dps_profile"), dict) or not schemas[product_id]["dps_profile"].get("dps"):
                if isinstance(current.get("dps_profile"), dict): schemas[product_id]["dps_profile"] = current["dps_profile"]
        # The local capability index is the durable, PID-scoped copy of what
        # Tuya declared during the last successful cloud synchronization.
        for row in conn.execute("SELECT product_id,source_kind,code,payload_json FROM tuya_pid_capabilities ORDER BY code"):
            product_id, source_kind = str(row["product_id"]), str(row["source_kind"])
            schema = schemas.setdefault(product_id, {"product_id": product_id, "dps_profile": {"dps": []}})
            key = "functions" if source_kind == "function" else "status_spec"
            try: capability = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError): continue
            if not isinstance(capability, dict): continue
            entries = schema.setdefault(key, [])
            if not isinstance(entries, list): entries = []; schema[key] = entries
            if not any(isinstance(item, dict) and item.get("code") == row["code"] for item in entries):
                entries.append(capability)
        scoped = tuya.get("product_dps_maps") if isinstance(tuya.get("product_dps_maps"), dict) else {}
        owner_rows: dict[str, dict[int, dict[str, Any]]] = {}
        for row in conn.execute("SELECT product_id,dps_id,payload_json FROM tuya_pid_dps_editor"):
            try: value = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError): continue
            if isinstance(value, dict): owner_rows.setdefault(str(row["product_id"]), {})[int(row["dps_id"])] = value
        profiles = []
        product_ids = set(schemas)
        # Older imported Tuya reference profiles are persisted canonically in
        # tuya_product_dps_map. Include these rows in the product editor even
        # when the integration config has no product_schemas entry.
        product_ids.update(str(row["product_id"]) for row in conn.execute(
            "SELECT DISTINCT product_id FROM tuya_product_dps_map WHERE protocol='tuya'"))
        product_ids.update(str(row["product_id"]) for row in conn.execute("SELECT DISTINCT product_id FROM tuya_product_dps_map_scoped"))
        product_ids.update(owner_rows)
        for product_id in sorted(product_ids):
            schema = schemas.get(product_id) if isinstance(schemas.get(product_id), dict) else {}
            merged: dict[int, dict[str, Any]] = {}
            def add_rows(source_rows: Any, origin: str) -> None:
                if isinstance(source_rows, dict): source_rows = list(source_rows.values())
                if not isinstance(source_rows, list): return
                for item in source_rows:
                    if not isinstance(item, dict): continue
                    raw_id = item.get("dps_id", item.get("dp_id", item.get("dpId", item.get("id"))))
                    try: dps_id = int(raw_id)
                    except (TypeError, ValueError): continue
                    if not 1 <= dps_id <= 65535: continue
                    current = merged.setdefault(dps_id, {"dps_id": dps_id, "origin": origin})
                    current.update({key: value for key, value in item.items() if value is not None})
                    current["dps_id"] = dps_id
                    current.setdefault("origin", origin)
            add_rows(schema.get("functions"), "function")
            add_rows(schema.get("status_spec"), "status")
            profile = schema.get("dps_profile") if isinstance(schema.get("dps_profile"), dict) else {}
            add_rows(profile.get("dps"), "schema")
            add_rows(profile.get("reference_dps"), "reference")
            for mapping in scoped.values():
                if isinstance(mapping, dict) and str(mapping.get("product_id") or "") == product_id:
                    scoped_profile = mapping.get("dps_profile") if isinstance(mapping.get("dps_profile"), dict) else {}
                    add_rows(scoped_profile.get("dps"), "owner_map")
            for row in conn.execute("""SELECT dps_id,dps_code,semantic_code,description,data_type,unit,scale,
                confidence,source,read_supported,write_supported FROM tuya_product_dps_map
                WHERE protocol='tuya' AND product_id=?""", (product_id,)):
                add_rows([{**dict(row), "dps_id": row["dps_id"], "display_name": row["description"],
                           "code": row["dps_code"]}], "reference")
            for row in conn.execute("SELECT dps_id,dps_code,semantic_code,description,data_type,unit,scale,write_supported FROM tuya_product_dps_map_scoped WHERE product_id=?", (product_id,)):
                add_rows([{**dict(row), "dps_id": row["dps_id"], "display_name": row["description"], "code": row["dps_code"]}], "owner_map")
            for dps_id, override in owner_rows.get(product_id, {}).items():
                merged.setdefault(dps_id, {"dps_id": dps_id}).update(override)
            for item in merged.values():
                explicit_source = item.get("source_kind") or item.get("source")
                item["origin"] = explicit_source if explicit_source in {"function", "status", "unknown"} else item.get("origin") or ("function" if item.get("type") in {"function", "function_point"} else "status")
                item["read_supported"] = bool(item.get("read_supported", item["origin"] == "status"))
                item["write_supported"] = bool(item.get("write_supported", item["origin"] == "function"))
            profiles.append({"product_id": product_id, "product_name": schema.get("product_name") or "",
                "product_name_pt": ((tuya.get("product_metadata") or {}).get(product_id) or {}).get("product_name_pt", "") if isinstance(tuya.get("product_metadata"), dict) else "",
                "category": schema.get("category") or "", "device_kind": schema.get("device_kind") or "unknown",
                "schema_source": schema.get("schema_source") or "Gateway / mapa DPS", "dps": sorted(merged.values(), key=lambda item: item["dps_id"]),
                "functions": schema.get("functions") if isinstance(schema.get("functions"), list) else [],
                "status_spec": schema.get("status_spec") if isinstance(schema.get("status_spec"), list) else []})
        return {"products": rows, "product_count": len(rows), "tuya_profiles": profiles,
                "tuya_profile_count": len(profiles), "source": "gateway_sqlite_and_product_schema"}


@app.get("/api/v1/smart-products/zigbee2mqtt-catalog")
def read_zigbee2mqtt_device_catalog(request: Request, session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Search protocol-specific profiles from the shared catalog without mixing them into Tuya DPS data."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        # Import on explicit Owner catalog use, not on Gateway startup. This
        # keeps normal device polling and startup independent from the 16 MB dataset.
        _sync_zigbee2mqtt_catalog(conn)
    query = request.query_params.get("q", "").strip().casefold()[:120]
    try:
        limit = max(1, min(100, int(request.query_params.get("limit", "50"))))
        offset = max(0, min(100000, int(request.query_params.get("offset", "0"))))
    except ValueError as exc:
        raise HTTPException(422, "zigbee2mqtt_catalog_pagination_invalid") from exc
    with db() as conn:
        where = "WHERE c.protocol='zigbee2mqtt'"
        params: list[Any] = []
        if query:
            where += " AND (lower(c.manufacturer) LIKE ? OR lower(c.product_code) LIKE ? OR lower(c.product_name) LIKE ?)"
            term = f"%{query}%"
            params.extend((term, term, term))
        total = int(conn.execute(f"SELECT COUNT(*) FROM smart_product_catalog c {where}", params).fetchone()[0])
        rows = conn.execute(f"""SELECT c.manufacturer,c.protocol,c.product_code,c.product_name,c.device_kind,c.capabilities_json,
            c.source,c.confidence,d.profile_json,d.source_url,d.source_revision FROM smart_product_catalog c
            LEFT JOIN smart_product_profile_details d USING(manufacturer,protocol,product_code) {where}
            ORDER BY c.manufacturer COLLATE NOCASE,c.product_code LIMIT ? OFFSET ?""", [*params, limit, offset]).fetchall()
        source = conn.execute("SELECT source_revision FROM smart_product_catalog_sources WHERE source_key='zigbee2mqtt-device-catalog'").fetchone()
    profiles = []
    for row in rows:
        item = dict(row)
        # Keep product identifiers consistent with Tuya's Product ID and the card-template API.
        item["product_id"] = item["product_code"]
        try: item["capabilities"] = json.loads(item.pop("capabilities_json") or "[]")
        except (TypeError, json.JSONDecodeError): item["capabilities"] = []
        try: item["profile"] = json.loads(item.pop("profile_json")) if item.get("profile_json") else None
        except (TypeError, json.JSONDecodeError): item["profile"] = None
        profiles.append(item)
    return {"protocol": "zigbee2mqtt", "profiles": profiles, "total": total,
            "limit": limit, "offset": offset,
            "source_revision": source["source_revision"] if source else None,
            "source_url": "https://github.com/Koenkk/zigbee2mqtt.io",
            "tuya_dps_merged": False}


@app.put("/api/v1/integrations/tuya/product-dps-map")
def save_tuya_pid_dps_map(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Save editable DPS metadata under the exact Product ID; command semantics remain schema-bound."""
    with db() as conn:
        _require_owner(session, conn)
        if not isinstance(payload, dict) or set(payload) != {"product_id", "rows"}:
            raise HTTPException(422, "tuya_pid_dps_map_invalid")
        product_id, rows = payload.get("product_id"), payload.get("rows")
        if not isinstance(product_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", product_id) or not isinstance(rows, list) or len(rows) > 128:
            raise HTTPException(422, "tuya_pid_dps_map_invalid")
        type_aliases = {"booleano": "bool", "boolean": "bool", "valor numérico": "value", "valor numerico": "value", "numérico": "value", "numerico": "value", "numérico inteiro": "value", "enumeração": "enum", "enumeracao": "enum", "falha": "fault", "texto": "string", "dados binários": "raw", "dados binarios": "raw", "desconhecido": "unknown"}
        allowed_types = {"bool", "value", "enum", "fault", "string", "raw", "unknown"}
        accepted = []
        seen = set()
        seen_codes = set()
        config = hardware_integrations.load_config()
        tuya_config = config.get("tuya") if isinstance(config.get("tuya"), dict) else {}
        product_schemas = tuya_config.get("product_schemas") if isinstance(tuya_config.get("product_schemas"), dict) else {}
        cloud_schema = product_schemas.get(product_id) if isinstance(product_schemas.get(product_id), dict) else {}
        declared_functions = {str(item.get("code")) for item in cloud_schema.get("functions", []) if isinstance(item, dict) and isinstance(item.get("code"), str)}
        declared_statuses = {str(item.get("code")) for item in cloud_schema.get("status_spec", []) if isinstance(item, dict) and isinstance(item.get("code"), str)}
        for item in conn.execute("SELECT source_kind,code FROM tuya_pid_capabilities WHERE product_id=?", (product_id,)):
            (declared_functions if item["source_kind"] == "function" else declared_statuses).add(str(item["code"]))
        seen_code_rows = {}
        for row_index, row in enumerate(rows, start=1):
            def row_error(code: str, field: str, reason: str, dps: Any = None) -> HTTPException:
                return HTTPException(422, f"{code}|row={row_index}|dps={dps if dps is not None else '?'}|field={field}|reason={reason}")
            if not isinstance(row, dict):
                raise row_error("tuya_pid_dps_row_invalid", "linha", "object_expected")
            extra_fields = sorted(set(row) - {"dps_id", "code", "label_pt", "source", "data_type", "unit", "scale", "details", "semantic_code", "write_supported"})
            if extra_fields:
                raise row_error("tuya_pid_dps_row_invalid", ",".join(extra_fields), "unexpected_field", row.get("dps_id"))
            dps_id = row.get("dps_id")
            if isinstance(dps_id, bool) or not isinstance(dps_id, int) or not 1 <= dps_id <= 65535 or dps_id in seen:
                raise row_error("tuya_pid_dps_id_invalid", "dps_id", "invalid_or_repeated", dps_id)
            seen.add(dps_id)
            code, label = row.get("code", ""), row.get("label_pt", "")
            source, data_type = row.get("source", "status"), row.get("data_type", "unknown")
            if isinstance(data_type, str):
                data_type = type_aliases.get(data_type.strip().lower(), data_type.strip().lower())
            if not isinstance(code, str) or len(code) > 96:
                raise row_error("tuya_pid_dps_row_invalid", "code", "must_be_text_up_to_96_chars", dps_id)
            if not isinstance(label, str) or len(label.strip()) > 120:
                raise row_error("tuya_pid_dps_row_invalid", "label_pt", "must_be_text_up_to_120_chars", dps_id)
            if not isinstance(source, str) or source not in {"function", "status", "unknown"}:
                raise row_error("tuya_pid_dps_row_invalid", "source", "unsupported_value", dps_id)
            if not isinstance(data_type, str) or data_type not in allowed_types:
                raise row_error("tuya_pid_dps_row_invalid", "data_type", "unsupported_value", dps_id)
            unit, scale = row.get("unit", ""), row.get("scale")
            if not isinstance(unit, str) or len(unit) > 24:
                raise row_error("tuya_pid_dps_row_invalid", "unit", "must_be_text_up_to_24_chars", dps_id)
            if scale is not None and (isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(float(scale)) or abs(float(scale)) > 1e12):
                raise row_error("tuya_pid_dps_row_invalid", "scale", "must_be_finite_number_or_empty", dps_id)
            semantic = row.get("semantic_code", "unknown")
            if not isinstance(semantic, str) or semantic not in {"unknown", "voltage", "current", "power", "daily_accumulated_energy", "total_energy", "switch", "countdown", "child_lock", "relay_status", "power_on_state", "custom_label", "brightness", "color_temperature"}:
                raise row_error("tuya_pid_dps_semantic_invalid", "semantic_code", "unsupported_value", dps_id)
            if source == "function" and (not code.strip() or code.strip() not in declared_functions):
                raise row_error("tuya_pid_dps_function_not_in_cloud_schema", "code", "function_not_declared_for_pid", dps_id)
            if source == "status" and (not code.strip() or code.strip() not in declared_statuses):
                raise row_error("tuya_pid_dps_status_not_in_cloud_schema", "code", "status_not_declared_for_pid", dps_id)
            code_identity = (source, code.strip())
            if source in {"function", "status"} and code_identity in seen_codes:
                raise row_error("tuya_pid_dps_cloud_code_mapped_more_than_once", "code", f"already_used_on_row_{seen_code_rows[code_identity]}", dps_id)
            if source in {"function", "status"}:
                seen_codes.add(code_identity)
                seen_code_rows[code_identity] = row_index
            # An order is recognized only when its code exists in the exact PID
            # cloud function list; status codes remain read-only.
            accepted.append({"dps_id": dps_id, "code": code.strip(), "label_pt": label.strip(), "source": source,
                "data_type": data_type, "unit": unit.strip(), "scale": scale, "details": str(row.get("details") or "")[:512],
                "semantic_code": semantic, "read_supported": source in {"status", "unknown"},
                "write_supported": source == "function" and code.strip() in declared_functions})
        stamp = utcnow()
        conn.execute("DELETE FROM tuya_pid_dps_editor WHERE product_id=?", (product_id,))
        conn.executemany("INSERT INTO tuya_pid_dps_editor(product_id,dps_id,payload_json,updated_at) VALUES(?,?,?,?)",
            [(product_id, row["dps_id"], json.dumps(row, ensure_ascii=False, separators=(",", ":")), stamp) for row in accepted])
        tuya = config.setdefault("tuya", {})
        schemas = tuya.setdefault("product_schemas", {})
        if not isinstance(schemas, dict): schemas = {}; tuya["product_schemas"] = schemas
        schema = schemas.setdefault(product_id, {"protocol": "tuya", "manufacturer": "Tuya", "product_name": "", "device_kind": "unknown", "dps_profile": {"dps": []}})
        if not isinstance(schema, dict): schema = {"protocol": "tuya", "manufacturer": "Tuya", "dps_profile": {"dps": []}}; schemas[product_id] = schema
        old_profile = schema.get("dps_profile") if isinstance(schema.get("dps_profile"), dict) else {}
        old_rows = old_profile.get("dps") if isinstance(old_profile.get("dps"), list) else []
        old_by_id = {int(row.get("dps_id")): row for row in old_rows if isinstance(row, dict) and isinstance(row.get("dps_id"), int) and not isinstance(row.get("dps_id"), bool)}
        profile_rows = []
        for row in accepted:
            base = old_by_id.get(row["dps_id"], {})
            profile_rows.append({**base, "dps_id": row["dps_id"], "dp_id": row["dps_id"],
                "code": row["code"] or str(base.get("code") or f"dps_{row['dps_id']}"),
                "function_code": row["code"] or str(base.get("function_code") or ""),
                "display_name": row["label_pt"] or str(base.get("display_name") or base.get("name") or f"DPS {row['dps_id']}"),
                "semantic_code": row["semantic_code"], "data_type": row["data_type"], "unit": row["unit"] or None,
                "scale": row["scale"], "source_kind": row["source"], "details": row["details"],
                "confidence": "OWNER_CUSTOM", "source": "Gateway PID DPS editor",
                "read_supported": row["read_supported"], "write_supported": row["write_supported"]})
        schema["dps_profile"] = {**old_profile, "dps": profile_rows}
        maps = tuya.setdefault("product_dps_maps", {})
        if not isinstance(maps, dict): maps = {}; tuya["product_dps_maps"] = maps
        matching_devices = [device for device in tuya.get("devices", []) if isinstance(device, dict) and str(device.get("product_id") or "") == product_id]
        identities = {hardware_integrations.tuya_product_identity_key(device): hardware_integrations.tuya_product_identity(device) for device in matching_devices}
        for identity_key, identity in identities.items():
            mapping = maps.get(identity_key)
            if not isinstance(mapping, dict): mapping = {"product_id": identity[0], "product": identity[1], "category": identity[2], "device_kind": identity[3]}
            mapping["dps_profile"] = {"dps": profile_rows}
            maps[identity_key] = mapping
        config["tuya"] = tuya
        try:
            hardware_integrations.save_config(config)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(500, "tuya_pid_dps_map_save_failed") from exc
        _persist_tuya_product_dps_map(conn, schemas)
        _persist_tuya_pid_capabilities(conn, schemas)
        _persist_tuya_product_dps_maps_scoped(conn, maps)
        audit(conn, session["user_id"], "hardware.tuya.product_dps_map", product_id, "success", {"dps_count": len(accepted)})
        return {"saved": True, "product_id": product_id, "dps_count": len(accepted), "write_commands_enabled": False}


@app.get("/api/v1/device-cards")
def list_device_cards(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    with db() as conn:
        _require_owner(session, conn)
        config = hardware_integrations.load_config()
        integrations = config if isinstance(config, dict) else {}
        candidates = []
        tuya = integrations.get("tuya") if isinstance(integrations.get("tuya"), dict) else {}
        for device in tuya.get("devices", []) if isinstance(tuya.get("devices"), list) else []:
            if isinstance(device, dict) and device.get("device_id") and device.get("product_id"):
                candidates.append((str(device["device_id"]), "Tuya", "tuya", str(device["product_id"]), str(device.get("product_name_pt") or device.get("product_name") or device.get("name") or "Tuya")))
        for device in conn.execute("SELECT device_id,name,model,protocol,device_type FROM shelly_devices WHERE enabled=1").fetchall():
            model = str(device["model"] or device["device_type"] or "")
            product_id = model or str(device["device_id"])
            protocol = "shelly_blu" if "blu" in str(device["protocol"] or "").casefold() or "blu" in str(device["device_type"] or "").casefold() else "shelly"
            candidates.append((str(device["device_id"]), "Shelly", protocol, product_id, str(device["name"] or model or "Shelly")))
        for device_id, manufacturer, protocol, product_id, product_name in candidates:
            existing = conn.execute("SELECT card_code FROM device_card_assignments WHERE device_id=?", (device_id,)).fetchone()
            if existing: continue
            digest = hashlib.sha256(f"{protocol}:{product_id}".encode("utf-8")).hexdigest()[:8].upper()
            prefix = {"tuya": "T", "zigbee2mqtt": "Z"}.get(protocol, "S")
            kind = "D" if any(word in (product_name + " " + product_id).casefold() for word in ("breaker", "switch", "disjuntor", "interruptor", "dlq")) else "E"
            card_code = f"{prefix}{kind}-{digest}"
            layout = {"version": 1, "width": 360, "height": 520, "items": [
                {"id": "title", "type": "text", "label": product_name, "x": 16, "y": 16, "width": 328, "height": 48, "font_size": 20, "color": "#f3f0e8", "visible": True},
                {"id": "status", "type": "status", "label": "Estado", "x": 16, "y": 72, "width": 328, "height": 32, "font_size": 14, "color": "#d6c17c", "visible": True},
                {"id": "metrics", "type": "metrics", "label": "Leituras", "x": 16, "y": 120, "width": 328, "height": 96, "font_size": 14, "color": "#e9e6df", "visible": True},
                {"id": "controls", "type": "controls", "label": "Controlos", "x": 16, "y": 240, "width": 328, "height": 160, "font_size": 16, "color": "#e9e6df", "visible": True}
            ]}
            conn.execute("INSERT OR IGNORE INTO device_card_templates(card_code,manufacturer,protocol,product_id,product_name,available,layout_json,updated_at) VALUES(?,?,?,?,?,1,?,?)",
                (card_code, manufacturer, protocol, product_id, product_name[:160], json.dumps(layout, ensure_ascii=False, separators=(",", ":")), utcnow()))
            conn.execute("INSERT OR IGNORE INTO device_card_assignments(device_id,card_code,updated_at) VALUES(?,?,?)", (device_id, card_code, utcnow()))
        rows = [dict(row) for row in conn.execute("SELECT * FROM device_card_templates ORDER BY manufacturer COLLATE NOCASE,card_code COLLATE NOCASE")]
        for row in rows:
            try: row["layout"] = json.loads(row.pop("layout_json") or "{}")
            except (TypeError, json.JSONDecodeError): row["layout"] = {}
        bindings = {row["device_id"]: row["card_code"] for row in conn.execute("SELECT device_id,card_code FROM device_card_assignments")}
        return {"cards": rows, "assignments": bindings}


@app.put("/api/v1/device-cards/{card_code}")
def save_device_card(card_code: str, payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    with db() as conn:
        _require_owner(session, conn)
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,32}", card_code) or not isinstance(payload, dict) or set(payload) != {"code", "manufacturer", "protocol", "product_id", "product_name", "available", "layout"}:
            raise HTTPException(422, "device_card_invalid")
        new_code = payload.get("code")
        manufacturer, protocol, product_id, product_name = (payload.get(key) for key in ("manufacturer", "protocol", "product_id", "product_name"))
        layout = payload.get("layout")
        if not isinstance(new_code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{2,32}", new_code) or any(not isinstance(value, str) for value in (manufacturer, protocol, product_id, product_name)) or len(manufacturer) > 80 or protocol not in {"tuya", "shelly", "shelly_blu", "zigbee2mqtt", "other"} or len(product_id) > 128 or len(product_name) > 160 or not isinstance(payload.get("available"), bool) or not isinstance(layout, dict) or len(json.dumps(layout)) > 20000:
            raise HTTPException(422, "device_card_invalid")
        stamp = utcnow()
        if new_code != card_code:
            if conn.execute("SELECT 1 FROM device_card_templates WHERE card_code=?", (new_code,)).fetchone():
                raise HTTPException(409, "device_card_code_exists")
            old = conn.execute("SELECT manufacturer,protocol,product_id,product_name,available,layout_json FROM device_card_templates WHERE card_code=?", (card_code,)).fetchone()
            if old:
                conn.execute("INSERT INTO device_card_templates(card_code,manufacturer,protocol,product_id,product_name,available,layout_json,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (new_code, *tuple(old), utcnow()))
            conn.execute("UPDATE device_card_assignments SET card_code=?,updated_at=? WHERE card_code=?", (new_code, stamp, card_code))
            conn.execute("DELETE FROM device_card_templates WHERE card_code=?", (card_code,))
            card_code = new_code
        conn.execute("""INSERT INTO device_card_templates(card_code,manufacturer,protocol,product_id,product_name,available,layout_json,updated_at)
            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(card_code) DO UPDATE SET manufacturer=excluded.manufacturer,protocol=excluded.protocol,
            product_id=excluded.product_id,product_name=excluded.product_name,available=excluded.available,layout_json=excluded.layout_json,updated_at=excluded.updated_at""",
            (card_code, manufacturer.strip(), protocol, product_id.strip(), product_name.strip(), int(payload["available"]), json.dumps(layout, ensure_ascii=False, separators=(",", ":")), stamp))
        audit(conn, session["user_id"], "device.card.save", card_code, "success", {"protocol": protocol, "product_id": product_id})
        return {"saved": True, "card_code": card_code, "updated_at": stamp}


@app.get("/api/v1/smart-products/shelly-profiles")
def read_shelly_product_profiles(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Return versioned, source-linked Shelly product capabilities and settings groups."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        shelly_product_registry.ensure_schema(conn)
        profiles = shelly_product_registry.list_profiles(conn)
        return {"profiles": profiles, "profile_count": len(profiles), "source": "gateway_sqlite"}


class _ProductTableParser(HTMLParser):
    """Extract simple HTML tables without executing or rendering source markup."""
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table = False
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table = True
            self.tables.append([])
        elif self._table and tag == "tr":
            self._row = []
        elif self._table and self._row is not None and tag in {"td", "th"}:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._table and tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif self._table and tag == "tr" and self._row is not None:
            if self._row:
                self.tables[-1].append(self._row)
            self._row = None
        elif tag == "table" and self._table:
            self._table = False


def _product_import_json_value(value: Any) -> dict[str, dict[str, Any]]:
    """Normalize explicitly structured product schemas; never infer DPS meaning."""
    if isinstance(value, dict):
        for key in ("product_schemas", "products", "items", "results", "data"):
            nested = value.get(key)
            if isinstance(nested, (dict, list)):
                value = nested
                break
    rows: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        rows = [(str(key), profile) for key, profile in value.items() if isinstance(profile, dict)]
    elif isinstance(value, list):
        for row in value:
            if isinstance(row, dict):
                product_id = row.get("product_id") or row.get("productId") or row.get("product_code") or row.get("code")
                if product_id:
                    rows.append((str(product_id), row))
    result: dict[str, dict[str, Any]] = {}
    for product_id, row in rows[:1000]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", product_id):
            continue
        if not isinstance(row, dict):
            continue
        profile = {key: row[key] for key in ("product_name", "productName", "name", "category", "device_kind", "channel_count", "functions", "status_spec", "dps_profile") if key in row}
        profile["product_name"] = str(profile.get("product_name") or profile.get("productName") or profile.get("name") or "")[:120]
        profile.pop("productName", None)
        profile.pop("name", None)
        if "dps" in row and "dps_profile" not in profile and isinstance(row["dps"], (list, dict)):
            profile["dps_profile"] = row["dps"] if isinstance(row["dps"], dict) else {"dps": row["dps"]}
        profile.update({"protocol": "tuya", "manufacturer": str(row.get("manufacturer") or "Tuya")[:64],
                        "schema_source": "EXTERNAL_REFERENCE", "cached_at": int(time.time())})
        if not profile.get("functions") and not profile.get("status_spec") and not (profile.get("dps_profile") or {}).get("dps"):
            continue
        result[product_id] = profile
    return result


def _product_import_csv_value(text: str, *, html_source: bool = False) -> dict[str, dict[str, Any]]:
    if html_source:
        parser = _ProductTableParser()
        parser.feed(text)
        table = next((rows for rows in parser.tables if len(rows) > 1), [])
        if not table:
            raise ValueError("product_import_no_html_table")
        text = "\n".join("\t".join(cell.replace("\t", " ") for cell in row) for row in table)
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("product_import_headers_required")
    normalize = lambda key: re.sub(r"[^a-z0-9]+", "_", str(key or "").strip().casefold()).strip("_")
    headers = {normalize(key): key for key in reader.fieldnames}
    pid_key = next((headers[key] for key in ("product_id", "productid", "product_code", "productcode", "code", "id") if key in headers), None)
    if not pid_key:
        raise ValueError("product_import_product_id_column_required")
    result: dict[str, dict[str, Any]] = {}
    for raw in reader:
        if not isinstance(raw, dict):
            continue
        product_id = str(raw.get(pid_key) or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", product_id):
            continue
        name_key = next((headers[key] for key in ("product_name", "productname", "name", "model", "description") if key in headers), None)
        category_key = next((headers[key] for key in ("category", "device_kind", "type") if key in headers), None)
        profile = result.setdefault(product_id, {"protocol": "tuya", "manufacturer": "Tuya", "schema_source": "EXTERNAL_REFERENCE", "cached_at": int(time.time()), "functions": [], "status_spec": [], "dps_profile": {"dps": []}})
        if name_key and raw.get(name_key): profile["product_name"] = str(raw[name_key]).strip()[:120]
        if category_key and raw.get(category_key): profile["category"] = str(raw[category_key]).strip()[:64]
        for field_name, target in (("functions", "functions"), ("status_spec", "status_spec"), ("dps", "dps"), ("dps_profile", "dps_profile")):
            key = headers.get(field_name)
            if key and raw.get(key):
                try: parsed = json.loads(raw[key])
                except (ValueError, TypeError): continue
                if target == "dps_profile" and isinstance(parsed, dict): profile[target] = parsed
                elif target == "dps" and isinstance(parsed, list): profile["dps_profile"] = {"dps": parsed}
                elif target in {"functions", "status_spec"} and isinstance(parsed, list): profile[target] = parsed
        dps_key = headers.get("dps_id") or headers.get("dpsid") or headers.get("dp_id")
        if dps_key and raw.get(dps_key):
            try: dps_id = int(str(raw[dps_key]).strip())
            except (ValueError, TypeError): dps_id = 0
            if 1 <= dps_id <= 65535:
                profile["dps_profile"]["dps"].append({"dps_id": dps_id, "display_name": str(raw.get(headers.get("dps_name", "")) or f"DPS {dps_id}")[:80], "semantic_code": "unknown", "data_type": "unknown", "confidence": "REFERENCE_ONLY", "source": "external_reference", "read_supported": True, "write_supported": False})
        elif not any(profile.get(key) for key in ("functions", "status_spec")) and not profile["dps_profile"]["dps"]:
            # Common product tables put one datapoint per column (for example,
            # “DPS 1”, “DPS 2”) instead of one datapoint per row.
            for normalized, source_header in headers.items():
                match = re.fullmatch(r"dps_(\d{1,5})", normalized)
                value = str(raw.get(source_header) or "").strip()
                if not match or not value:
                    continue
                try:
                    parsed = json.loads(value) if value[:1] in "{[\"" else value
                except (ValueError, TypeError):
                    parsed = value
                if isinstance(parsed, dict):
                    entry = dict(parsed)
                    entry.setdefault("dps_id", int(match.group(1)))
                    entry.setdefault("display_name", entry.get("name") or f"DPS {match.group(1)}")
                    entry.setdefault("semantic_code", "unknown")
                    entry.setdefault("confidence", "REFERENCE_ONLY")
                    entry.setdefault("source", "external_reference")
                    entry.setdefault("read_supported", True)
                    entry["write_supported"] = False
                elif isinstance(parsed, list):
                    continue
                else:
                    entry = {"dps_id": int(match.group(1)), "display_name": str(parsed)[:80], "semantic_code": "unknown", "data_type": "unknown", "confidence": "REFERENCE_ONLY", "source": "external_reference", "read_supported": True, "write_supported": False}
                profile["dps_profile"]["dps"].append(entry)
    return {key: value for key, value in result.items() if value.get("functions") or value.get("status_spec") or value.get("dps_profile", {}).get("dps")}


def _read_public_product_url(url: str) -> tuple[str | bytes, str]:
    parsed = urlsplit(url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in (None, 80, 443) or len(url) > 2048):
        raise ValueError("product_import_url_invalid")
    host = parsed.hostname.rstrip(".")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = sorted({entry[4][0] for entry in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})
    except OSError as exc:
        raise ValueError("product_import_url_dns_failed") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("product_import_url_host_not_public")
    # Connect to the already-validated address to prevent DNS rebinding between
    # validation and request. Redirects are deliberately not followed.
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    connection = http.client.HTTPSConnection(host, port, timeout=8) if parsed.scheme == "https" else http.client.HTTPConnection(host, port, timeout=8)
    try:
        raw_socket = socket.create_connection((addresses[0], port), timeout=8)
        if parsed.scheme == "https":
            connection.sock = ssl.create_default_context().wrap_socket(raw_socket, server_hostname=host)
        else:
            connection.sock = raw_socket
        connection.request("GET", path, headers={"Host": parsed.netloc, "User-Agent": "SolarMiner-ProductCatalog/1.0", "Accept": "application/json,text/csv,text/tab-separated-values,text/html,text/plain", "Connection": "close"})
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise ValueError("product_import_url_redirect_not_supported")
        if response.status < 200 or response.status >= 300:
            raise ValueError("product_import_url_fetch_failed")
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("product_import_source_too_large")
        content_type = response.headers.get_content_type()
        return (raw if "spreadsheet" in content_type or "excel" in content_type else raw.decode("utf-8-sig")), content_type
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("product_import_url_fetch_failed") from exc
    finally:
        connection.close()


def _xlsx_product_rows(raw: bytes) -> str:
    if len(raw) > 2_000_000:
        raise ValueError("product_import_source_too_large")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) > 64 or sum(item.file_size for item in infos) > 12_000_000 or any(item.file_size > 4_000_000 for item in infos):
                raise ValueError("product_import_spreadsheet_too_large")
            names = {item.filename for item in infos}
            workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
            rels_xml = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
            package_rel_ns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
            sheet = workbook_xml.find(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")
            if sheet is None:
                raise ValueError("product_import_spreadsheet_has_no_sheet")
            rel_id = sheet.attrib.get(rel_ns + "id")
            relationship = next((item for item in rels_xml.findall(package_rel_ns + "Relationship") if item.attrib.get("Id") == rel_id), None)
            if relationship is None:
                raise ValueError("product_import_spreadsheet_sheet_invalid")
            target = relationship.attrib.get("Target", "").lstrip("/")
            sheet_path = target if target.startswith("xl/") else "xl/" + target
            if ".." in sheet_path.split("/") or sheet_path not in names:
                raise ValueError("product_import_spreadsheet_sheet_invalid")
            shared: list[str] = []
            if "xl/sharedStrings.xml" in names:
                strings_xml = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = ["".join(node.itertext()) for node in strings_xml.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si")]
            sheet_xml = ET.fromstring(archive.read(sheet_path))
    except ValueError:
        raise
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise ValueError("product_import_spreadsheet_invalid") from exc
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    output = io.StringIO()
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    for row in sheet_xml.findall(".//" + ns + "row")[:5000]:
        values: dict[int, str] = {}
        for cell in row.findall(ns + "c"):
            reference = cell.attrib.get("r", "")
            letters = re.match(r"([A-Z]+)", reference.upper())
            if not letters:
                continue
            column = 0
            for char in letters.group(1):
                column = column * 26 + ord(char) - 64
            column -= 1
            cell_type = cell.attrib.get("t")
            value = cell.findtext(ns + "v", default="")
            if cell_type == "s":
                try: value = shared[int(value)]
                except (ValueError, IndexError): value = ""
            elif cell_type == "inlineStr":
                inline = cell.find(ns + "is")
                value = "".join(inline.itertext()) if inline is not None else ""
            values[column] = value
        if values:
            writer.writerow([values.get(index, "") for index in range(max(values) + 1)])
    return output.getvalue()


def _parse_tuya_product_import(text: str | bytes, filename: str = "") -> dict[str, dict[str, Any]]:
    if isinstance(text, bytes):
        if not filename.lower().endswith(".xlsx"):
            raise ValueError("product_import_binary_format_unsupported")
        text = _xlsx_product_rows(text)
    if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > 2_000_000:
        raise ValueError("product_import_source_empty_or_too_large")
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        parsed = None
    if parsed is not None:
        profiles = _product_import_json_value(parsed)
    else:
        profiles = _product_import_csv_value(text, html_source=filename.lower().endswith((".html", ".htm")) or "<table" in text[:2048].lower())
    bounded = hardware_integrations._bounded_tuya_product_schemas(profiles)
    if not bounded:
        raise ValueError("product_import_no_supported_product_schemas")
    return bounded


def _tuya_product_import_equal(current: Any, proposed: Any) -> bool:
    if not isinstance(current, dict) or not isinstance(proposed, dict):
        return False
    def canonical(profile: dict[str, Any]) -> str:
        content = {key: profile.get(key) for key in ("product_name", "category", "device_kind", "channel_count", "functions", "status_spec")}
        dps_profile = profile.get("dps_profile") if isinstance(profile.get("dps_profile"), dict) else {}
        content["dps_profile"] = dps_profile
        return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return canonical(current) == canonical(proposed)


@app.post("/api/v1/integrations/tuya/product-catalog/preview")
def preview_tuya_product_catalog_import(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Read a bounded public URL or uploaded text and return a non-persistent diff."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner": raise HTTPException(403, "owner_required")
    if set(payload) - {"url", "content", "content_base64", "filename"}:
        raise HTTPException(422, "product_import_payload_invalid")
    try:
        if payload.get("url"):
            text, content_type = _read_public_product_url(str(payload.get("url")))
            filename = ".html" if "html" in content_type else ".csv" if "csv" in content_type or "tab-separated" in content_type else ".xlsx" if "spreadsheet" in content_type or "excel" in content_type else ".json" if "json" in content_type else ""
        else:
            filename = str(payload.get("filename") or "")[:128]
            if payload.get("content_base64") is not None:
                encoded = payload.get("content_base64")
                if not isinstance(encoded, str) or len(encoded) > 2_700_000:
                    raise ValueError("product_import_source_too_large")
                try: text = base64.b64decode(encoded, validate=True)
                except (ValueError, base64.binascii.Error) as exc: raise ValueError("product_import_file_encoding_invalid") from exc
            else:
                text = payload.get("content")
        proposed = _parse_tuya_product_import(text, filename)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    current = hardware_integrations.public_config().get("tuya", {}).get("product_catalog", {})
    with db() as conn:
        known_rows = {str(row["product_code"]): dict(row) for row in conn.execute(
            "SELECT * FROM smart_product_catalog WHERE protocol='tuya'")}
    changes = []
    for product_id, profile in proposed.items():
        old = current.get(product_id)
        known = known_rows.get(product_id)
        status_value = "added" if old is None and known is None else "unchanged" if _tuya_product_import_equal(old, profile) else "changed"
        changes.append({"product_id": product_id, "status": status_value,
                        "current_name": (old.get("product_name") if isinstance(old, dict) else known.get("product_name", "") if known else ""),
                        "proposed_name": profile.get("product_name", ""),
                        "current_dps_count": (len(old.get("functions", []) + old.get("status_spec", [])) + len((old.get("dps_profile") or {}).get("dps", []))) if isinstance(old, dict) else 0,
                        "proposed_dps_count": len(profile.get("functions", []) + profile.get("status_spec", [])) + len((profile.get("dps_profile") or {}).get("dps", []))})
    return {"changes": changes, "profiles": proposed, "source_count": len(proposed), "unchanged_count": sum(1 for row in changes if row["status"] == "unchanged"), "persisted": False}


@app.post("/api/v1/integrations/tuya/product-catalog/apply")
def apply_tuya_product_catalog_import(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Apply only the accepted rows from an Owner-reviewed preview."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner": raise HTTPException(403, "owner_required")
        if set(payload) - {"profiles", "excluded_product_ids"} or not isinstance(payload.get("profiles"), dict) or not isinstance(payload.get("excluded_product_ids", []), list):
            raise HTTPException(422, "product_import_apply_payload_invalid")
        profiles = hardware_integrations._bounded_tuya_product_schemas(payload["profiles"])
        excluded = {str(value) for value in payload.get("excluded_product_ids", []) if isinstance(value, str)}
        accepted = {product_id: profile for product_id, profile in profiles.items() if product_id not in excluded}
        config = hardware_integrations.load_config()
        tuya = config.setdefault("tuya", {})
        existing = hardware_integrations._bounded_tuya_product_schemas(tuya.get("product_schemas"))
        existing.update(accepted)
        tuya["product_schemas"] = existing
        try:
            saved = hardware_integrations.save_config(config)
        except (OSError, ValueError) as exc:
            raise HTTPException(500, "product_import_save_failed") from exc
        _persist_tuya_product_dps_map(conn, tuya.get("product_schemas", {}))
        _persist_tuya_pid_capabilities(conn, tuya.get("product_schemas", {}))
        audit(conn, session["user_id"], "hardware.tuya.product_catalog.import", "product-catalog", "success",
              {"accepted_count": len(accepted), "excluded_count": len(excluded)})
        return {"applied_count": len(accepted), "excluded_count": len(excluded), "product_schema_count": len(existing)}


@app.post("/api/v1/integrations/tuya/product-metadata")
def save_tuya_product_metadata(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Save owner-curated display name and functional kind for one immutable PID."""
    with db() as conn:
        _require_owner(session, conn)
        if not isinstance(payload, dict) or set(payload) != {"product_id", "product_name_pt", "device_kind"}:
            raise HTTPException(422, "tuya_product_metadata_invalid")
        product_id = payload.get("product_id")
        product_name = payload.get("product_name_pt")
        device_kind = payload.get("device_kind")
        if (not isinstance(product_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", product_id)
                or not isinstance(product_name, str) or len(product_name.strip()) > 160
                or not isinstance(device_kind, str) or device_kind not in hardware_integrations.TUYA_DEVICE_KINDS):
            raise HTTPException(422, "tuya_product_metadata_invalid")
        config = hardware_integrations.load_config()
        tuya = config.setdefault("tuya", {})
        metadata = tuya.setdefault("product_metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
            tuya["product_metadata"] = metadata
        metadata[product_id] = {"product_name_pt": product_name.strip(), "device_kind": device_kind}
        try:
            hardware_integrations.save_config(config)
        except (OSError, ValueError) as exc:
            raise HTTPException(500, "tuya_product_metadata_save_failed") from exc
        affected = sum(1 for item in tuya.get("devices", []) if isinstance(item, dict)
                       and str(item.get("product_id") or "") == product_id)
        audit(conn, session["user_id"], "hardware.tuya.product_metadata", product_id, "success",
              {"device_kind": device_kind, "affected_devices": affected})
        return {"saved": True, "product_id": product_id, "product_name_pt": product_name.strip(),
                "device_kind": device_kind, "affected_device_count": affected}


@app.post("/api/v1/integrations/shelly/register")
def register_shelly_device(payload: dict[str, Any],
                           session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Identify a Shelly locally, verify its MAC, and add it to the shared inventory."""
    if set(payload) - {"name", "host", "mac", "username", "password", "device_type"}:
        raise HTTPException(422, "shelly_registration_payload_invalid")
    name = str(payload.get("name") or "").strip()
    device_type = str(payload.get("device_type") or "smart").strip().lower()[:64]
    if not name or len(name) > 120:
        raise HTTPException(422, "shelly_name_required")
    try:
        host = hardware_integrations._private_ip(payload.get("host"))
    except ValueError as exc:
        raise HTTPException(422, "shelly_private_ip_required") from exc
    if payload.get("mac") is not None:
        expected_mac = _inventory_mac(payload.get("mac"))
        if not expected_mac:
            raise HTTPException(422, "shelly_mac_invalid")
    else:
        expected_mac = ""
    username, password = payload.get("username", ""), payload.get("password", "")
    if (not isinstance(username, str) or not isinstance(password, str)
            or len(username) > 128 or len(password) > 256):
        raise HTTPException(422, "shelly_credentials_invalid")
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
    try:
        reading = hardware_integrations.shelly_integration.identify_and_read(host, username=username, password=password)
    except (RuntimeError, OSError) as exc:
        raise HTTPException(502, "shelly_identification_failed") from exc
    mac = _inventory_mac(reading.get("mac"))
    if not mac:
        raise HTTPException(502, "shelly_mac_not_returned_by_device")
    if expected_mac and expected_mac != mac:
        raise HTTPException(409, "shelly_mac_does_not_match_device")
    shelly_device_id = f"shelly:{mac}"
    try:
        with db() as conn:
            actor = _revalidate_actor(conn, session, "manage_gateway")
            if actor["role"] != "owner":
                raise HTTPException(403, "owner_required")
            existing = conn.execute("SELECT device_id FROM shelly_devices WHERE mac=?", (mac,)).fetchone()
            if existing is None and conn.execute("SELECT COUNT(*) FROM shelly_devices").fetchone()[0] >= 100:
                raise HTTPException(409, "shelly_device_limit_reached")
            now = utcnow()
            capabilities = json.dumps(reading.get("capabilities", []), separators=(",", ":"))
            auth_ciphertext = shelly_credentials.seal(DATA_DIR, username, password)
            conn.execute("""INSERT INTO shelly_devices
                (device_id,mac,name,host,model,generation,device_type,protocol,firmware,capabilities_json,room,auth_ciphertext,enabled,created_at,updated_at,last_seen_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,'',?,1,?,?,?)
                ON CONFLICT(mac) DO UPDATE SET name=excluded.name,host=excluded.host,model=excluded.model,
                generation=excluded.generation,device_type=excluded.device_type,protocol=excluded.protocol,firmware=excluded.firmware,
                capabilities_json=excluded.capabilities_json,
                auth_ciphertext=CASE WHEN length(excluded.auth_ciphertext)>0 THEN excluded.auth_ciphertext ELSE shelly_devices.auth_ciphertext END,
                enabled=1,updated_at=excluded.updated_at,last_seen_at=excluded.last_seen_at""",
                (shelly_device_id, mac, name, host, str(reading.get("model") or "")[:120],
                 int(reading.get("generation") or 1), device_type, str(reading.get("protocol") or "")[:40],
                 str(reading.get("firmware") or "")[:80], capabilities, auth_ciphertext, now, now, now))
            central = _upsert_gateway_inventory_device(conn, provider="shelly", source_device_id=shelly_device_id,
                name=name, device_type=device_type, mac=mac, ip=host, manufacturer="Shelly",
                model=str(reading.get("model") or ""), status="confirmed", name_source="owner", replace_ip=True)
            _upsert_smart_product_catalog(conn, manufacturer="Shelly", protocol=str(reading.get("protocol") or "shelly"),
                product_code=str(reading.get("model") or ""), product_name=str(reading.get("model") or ""),
                device_kind=device_type, capabilities=reading.get("capabilities", []),
                source="shelly_device_identification", confidence="device_reported")
            audit(conn, session["user_id"], "smart_device.shelly.register", mac, "success", {
                "generation": reading.get("generation"), "protocol": reading.get("protocol"), "model": reading.get("model")})
            conn.commit()
    except HTTPException:
        raise
    except (OSError, ValueError, sqlite3.Error) as exc:
        LOG.warning("Shelly inventory registration failed (%s)", type(exc).__name__)
        raise HTTPException(500, "shelly_registration_failed") from exc
    return {"device": central, "reading": reading}


@app.post("/api/v1/integrations/shelly/name")
def rename_shelly_device(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Rename a Shelly device in the Gateway inventory without contacting hardware."""
    if not isinstance(payload, dict) or set(payload) not in ({"device_id", "name"}, {"device_id", "name", "room"}):
        raise HTTPException(422, "shelly_name_payload_invalid")
    device_id, name, room = payload.get("device_id"), payload.get("name"), payload.get("room")
    if (not isinstance(device_id, str) or len(device_id) > 140
            or not isinstance(name, str) or not name.strip() or len(name.strip()) > 120
            or (room is not None and (not isinstance(room, str) or len(room.strip()) > 120))):
        raise HTTPException(422, "shelly_name_invalid")
    with db() as conn:
        _require_owner(session, conn)
        if device_id.startswith("shelly-blu:"):
            mac = _inventory_mac(device_id.removeprefix("shelly-blu:"))
            cursor = conn.execute("UPDATE shelly_blu_devices SET name=?,updated_at=? WHERE mac=? AND enabled=1",
                                  (name.strip(), utcnow(), mac))
            provider, source_id = "shelly", f"shelly-blu:{mac}"
        else:
            if room is None:
                cursor = conn.execute("UPDATE shelly_devices SET name=?,updated_at=? WHERE device_id=? AND enabled=1",
                                      (name.strip(), utcnow(), device_id))
            else:
                cursor = conn.execute("UPDATE shelly_devices SET name=?,room=?,updated_at=? WHERE device_id=? AND enabled=1",
                                      (name.strip(), room.strip(), utcnow(), device_id))
            provider, source_id = "shelly", device_id
        if not cursor.rowcount:
            raise HTTPException(404, "shelly_device_not_found")
        conn.execute("UPDATE gateway_device_inventory SET name=?,name_source='owner',updated_at=? WHERE source_provider=? AND source_device_id=?",
                     (name.strip(), utcnow(), provider, source_id))
        audit(conn, session["user_id"], "hardware.shelly.rename", device_id, "success", {})
    return {"saved": True, "device_id": device_id, "name": name.strip(), **({"room": room.strip()} if room is not None else {})}


@app.post("/api/v1/integrations/shelly/read")
def read_shelly_devices(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Read registered Shelly devices over the local network; failures are isolated per device."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        shelly_rows = [dict(row) for row in conn.execute(
            "SELECT device_id,name,room,host,mac,model,generation,protocol,firmware,auth_ciphertext FROM shelly_devices WHERE enabled=1")]
    shelly_devices, credential_failures = [], []
    for item in shelly_rows:
        try:
            item.update(shelly_credentials.open_credentials(DATA_DIR, item.pop("auth_ciphertext", b"")))
            shelly_devices.append(item)
        except ValueError:
            credential_failures.append({"device_id": item.get("device_id"), "name": item.get("name"),
                "host": item.get("host"), "manufacturer": "Shelly", "connection_state": "failed",
                "reason": "shelly_credentials_unavailable", "command_sent": False})
    # Device I/O is deliberately outside SQLite transactions: a sleeping device
    # must not hold up unrelated inventory writes.
    readings = credential_failures + hardware_integrations.shelly_integration.read_devices({"devices": shelly_devices})
    shelly_room_by_id = {item["device_id"]: item.get("room", "") for item in shelly_rows}
    for reading in readings:
        if reading.get("device_id") in shelly_room_by_id:
            reading["room"] = shelly_room_by_id[reading["device_id"]]
    with db() as conn:
        blu_rows = [dict(row) for row in conn.execute(
            "SELECT mac,name,model,device_type,bridge_mac,bridge_host,last_rssi,values_json,last_seen_at FROM shelly_blu_devices WHERE enabled=1")]
        blu_bridges = [dict(row) for row in conn.execute("""SELECT mac,name,host,model,device_type,auth_ciphertext FROM shelly_devices
            WHERE enabled=1 AND (device_type IN ('smart_blugw','smart_gateway') OR model LIKE '%BLU Gateway%'
                OR model LIKE '%BLU GW%' OR model LIKE '%BLUGW%' OR model LIKE '%GWF-KZ01%' OR model LIKE '%SNGW-BT01%'
                OR upper(model) LIKE '%SN-GW-BT01%' OR upper(model) LIKE '%SN GW BT01%')""")]
    if blu_rows and blu_bridges:
        try:
            required_bridge_macs = {_inventory_mac(item.get("bridge_mac")) for item in blu_rows
                                    if _inventory_mac(item.get("bridge_mac"))}
            with db() as conn:
                observed_blu, _ = _read_shelly_blu_bridges_cached(conn, required_bridge_macs)
            observed_by_mac = {_inventory_mac(item.get("mac")): item for item in observed_blu if _inventory_mac(item.get("mac"))}
            for item in blu_rows:
                mac = _inventory_mac(item.get("mac"))
                found = observed_by_mac.get(mac)
                if found:
                    values = found.get("values") if isinstance(found.get("values"), list) else []
                    item.update({"last_rssi": found.get("rssi"), "values_json": json.dumps(values, separators=(",", ":")),
                                 "last_seen_at": utcnow(), "bridge_host": found.get("bridge_host") or item.get("bridge_host")})
                    with db() as conn:
                        conn.execute("UPDATE shelly_blu_devices SET last_rssi=?,values_json=?,last_seen_at=?,bridge_host=?,updated_at=? WHERE mac=?",
                            (item["last_rssi"], item["values_json"], item["last_seen_at"], item["bridge_host"], item["last_seen_at"], mac))
                    values_display = [{"name": str(value.get("name") or "Sensor")[:64], "value": value.get("val"),
                                       "unit": str(value.get("unit") or "")[:16]} for value in values if isinstance(value, dict)]
                    readings.append({"device_id": f"shelly-blu:{mac}", "name": item["name"], "model": item["model"],
                        "mac": mac, "host": item["bridge_host"], "manufacturer": "Shelly", "protocol": "shelly_blu_bthome",
                        "connection_state": "connected", "components": [{"component": "bthome", "id": 0, "status": {}}],
                        "capabilities": sorted({str(value.get("name")) for value in values if isinstance(value, dict) and value.get("name")} ),
                        "bthome_values": values_display, "rssi": item["last_rssi"], "observed_at": time.time(),
                        "bridge_mac": item["bridge_mac"], "command_sent": False})
                else:
                    try:
                        old_values = json.loads(item.get("values_json") or "[]")
                    except (TypeError, ValueError):
                        old_values = []
                    readings.append({"device_id": f"shelly-blu:{mac}", "name": item["name"], "model": item["model"],
                        "mac": mac, "host": item["bridge_host"], "manufacturer": "Shelly", "protocol": "shelly_blu_bthome",
                        "connection_state": "failed", "reason": "blu_advertisement_not_seen", "components": [],
                        "capabilities": [], "bthome_values": old_values, "rssi": item.get("last_rssi"),
                        "observed_at": time.time(), "bridge_mac": item["bridge_mac"], "command_sent": False})
        except Exception as exc:
            LOG.info("Shelly BLU reading unavailable (%s)", type(exc).__name__)
    elif blu_rows:
        for item in blu_rows:
            mac = _inventory_mac(item.get("mac"))
            readings.append({"device_id": f"shelly-blu:{mac}", "name": item["name"], "model": item["model"],
                "mac": mac, "host": item["bridge_host"], "manufacturer": "Shelly", "protocol": "shelly_blu_bthome",
                "connection_state": "failed", "reason": "bluetooth_bridge_unavailable", "components": [],
                "capabilities": [], "bthome_values": [], "observed_at": time.time(),
                "bridge_mac": item["bridge_mac"], "command_sent": False})
    failed_ids = {item.get("device_id") for item in readings if item.get("connection_state") != "connected"
                  and not str(item.get("device_id") or "").startswith("shelly-blu:")}
    if failed_ids:
        try:
            report = network_scanner.scan_attached_networks()
            _enrich_shelly_scan(report)
            by_id = {item.get("device_id"): item for item in shelly_devices}
            for index, reading in enumerate(readings):
                if reading.get("device_id") not in failed_ids:
                    continue
                saved = by_id.get(reading.get("device_id"), {})
                mac = _inventory_mac(saved.get("mac"))
                candidate_ip = _unique_lan_ip_for_mac(report, mac)
                if not candidate_ip:
                    continue
                retry_device = {**saved, "host": candidate_ip}
                retry = hardware_integrations.shelly_integration.read_devices({"devices": [retry_device]})
                if retry and retry[0].get("connection_state") == "connected" and _inventory_mac(retry[0].get("mac")) == mac:
                    readings[index] = retry[0]
        except Exception as exc:
            # The original local read result remains authoritative for this
            # cycle; a failed recovery scan must not erase a saved address.
            LOG.info("Shelly MAC-based IP recovery unavailable (%s)", type(exc).__name__)
    now = utcnow()
    connected_by_mac = {_inventory_mac(item.get("mac")): item for item in readings
                        if item.get("connection_state") == "connected" and _inventory_mac(item.get("mac"))}
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        _sync_gateway_device_inventory(conn, hardware_integrations.load_config())
        for mac, reading in connected_by_mac.items():
            conn.execute("UPDATE shelly_devices SET host=?,last_seen_at=?,updated_at=? WHERE mac=? AND enabled=1",
                (str(reading.get("host") or "")[:64], now, now, mac))
            conn.execute("""UPDATE gateway_device_inventory SET last_ip=?,last_seen_at=?,updated_at=?
                WHERE mac=? AND source_provider='shelly'""",
                (str(reading.get("host") or "")[:64], now, now, mac))
        audit(conn, session["user_id"], "smart_device.shelly.read", "shelly_devices",
              "partial" if any(item.get("connection_state") != "connected" for item in readings) else "success",
              {"device_count": len(readings), "connected_count": sum(item.get("connection_state") == "connected" for item in readings),
               "cloud_used": False, "commands_sent": False})
        conn.commit()
        return {"devices": readings, "device_count": len(readings),
                "connected_count": sum(item.get("connection_state") == "connected" for item in readings),
                "observed_at": now, "source": "local_lan", "cloud_used": False, "commands_sent": False}


@app.post("/api/v1/integrations/shelly/discover")
def discover_shelly_devices(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Return Shelly devices found by the existing attached-LAN scanner, without persisting them."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
    try:
        report = network_scanner.scan_attached_networks()
        _enrich_shelly_scan(report)
    except Exception as exc:
        LOG.warning("Shelly LAN discovery failed (%s)", type(exc).__name__)
        raise HTTPException(502, "shelly_discovery_failed") from exc
    found = []
    for item in report.get("hosts", []):
        evidence = " ".join(str(item.get(key) or "") for key in ("manufacturer", "model", "friendly_name", "hostname"))
        if not re.search(r"shelly", evidence, re.I) or not item.get("ip"):
            continue
        found.append({key: item.get(key) for key in ("ip", "mac", "mac_source", "manufacturer", "model",
                      "friendly_name", "hostname", "shelly_generation", "protocol", "shelly_firmware",
                      "discovery_methods", "identity_conflict") if item.get(key) is not None})
    found.sort(key=lambda item: str(item.get("ip") or ""))
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        for item in found:
            if str(item.get("manufacturer") or "").casefold() == "shelly" and item.get("model"):
                _upsert_smart_product_catalog(conn, manufacturer="Shelly", protocol=str(item.get("protocol") or "shelly"),
                    product_code=str(item["model"]), product_name=str(item["model"]),
                    device_kind="smart", capabilities=[], source="shelly_lan_discovery", confidence="discovered_unverified")
        audit(conn, session["user_id"], "smart_device.shelly.discover", "lan", "success", {
            "scanned_count": report.get("scanned_count", 0), "found_count": len(found),
            "cloud_used": False, "devices_registered": False})
        conn.commit()
        return {"devices": found, "device_count": len(found), "scanned_count": report.get("scanned_count", 0),
                "networks": report.get("networks", []), "source": "attached_lan_scanner", "cloud_used": False,
                "registered": False}


@app.post("/api/v1/integrations/shelly/{device_id}/switch")
def command_shelly_switch(device_id: str, payload: dict[str, Any],
                          session: dict[str, Any] = Depends(require_permission("operate"))) -> dict[str, Any]:
    """Send one idempotent relay target state and verify it with a fresh local read."""
    if set(payload) - {"channel", "on"} or not isinstance(payload.get("on"), bool):
        raise HTTPException(422, "shelly_switch_command_invalid")
    channel = payload.get("channel", 0)
    if isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel <= 31:
        raise HTTPException(422, "shelly_switch_channel_invalid")
    with db() as conn:
        actor = _revalidate_actor(conn, session, "operate")
        if actor["role"] not in {"owner", "admin", "operator"}:
            raise HTTPException(403, "permission_denied")
        config = hardware_integrations.load_config()
        device = conn.execute("SELECT * FROM shelly_devices WHERE device_id=? AND enabled=1", (device_id,)).fetchone()
        if not device:
            raise HTTPException(404, "shelly_device_not_found")
        device = dict(device)
        try:
            device.update(shelly_credentials.open_credentials(DATA_DIR, device.get("auth_ciphertext")))
        except ValueError as exc:
            raise HTTPException(409, "shelly_credentials_unavailable") from exc
        host = str(device.get("host") or "")
        try:
            host = hardware_integrations._private_ip(host)
        except ValueError as exc:
            raise HTTPException(422, "shelly_private_ip_required") from exc
        command_id = str(uuid.uuid4())
        occurred_at = utcnow()
        conn.execute("INSERT INTO shelly_command_history(command_id,device_id,channel_id,requested_on,command_state,occurred_at) VALUES(?,?,?,?,?,?)",
                     (command_id, device_id, channel, int(payload["on"]), "PENDING", occurred_at))
        conn.commit()
        try:
            result = hardware_integrations.shelly_integration.control_switch(
                host, int(device.get("generation") or 0), channel, payload["on"],
                username=str(device.get("username") or ""), password=str(device.get("password") or ""))
            state = str(result.get("command_state") or "UNKNOWN")
            observed = result.get("observed_on")
            completed_at = utcnow()
            conn.execute("UPDATE shelly_command_history SET command_state=?,observed_on=?,completed_at=? WHERE command_id=?",
                         (state, int(observed) if isinstance(observed, bool) else None, completed_at, command_id))
            audit(conn, session["user_id"], "smart_device.shelly.switch", device_id,
                  "confirmed" if state == "CONFIRMED" else "accepted_unconfirmed",
                  {"command_id": command_id, "channel": channel, "requested_on": payload["on"],
                   "observed_on": observed if isinstance(observed, bool) else None})
            conn.commit()
            return {"command_id": command_id, "command_state": state,
                    "command_accepted": bool(result.get("command_accepted")),
                    "command_confirmed": state == "CONFIRMED", "requested_on": payload["on"],
                    "observed_on": observed if isinstance(observed, bool) else None,
                    "device_command_latency_ms": result.get("device_command_latency_ms"),
                    "readback_latency_ms": result.get("readback_latency_ms"),
                    "observed_at": result.get("reading", {}).get("observed_at")}
        except (RuntimeError, OSError, ValueError) as exc:
            conn.execute("UPDATE shelly_command_history SET command_state='FAILED',completed_at=? WHERE command_id=?",
                         (utcnow(), command_id))
            audit(conn, session["user_id"], "smart_device.shelly.switch", device_id, "failed",
                  {"command_id": command_id, "channel": channel, "reason": str(exc)[:100]})
            conn.commit()
            raise HTTPException(502, "shelly_command_failed") from exc


@app.post("/api/v1/integrations/shelly/{device_id}/light")
def command_shelly_light(device_id: str, payload: dict[str, Any],
                          session: dict[str, Any] = Depends(require_permission("operate"))) -> dict[str, Any]:
    """Set a supported Shelly light property over LAN, then verify with a fresh read."""
    allowed = {"component", "channel", "on", "brightness", "rgb", "white", "color_temperature"}
    if not isinstance(payload, dict) or set(payload) - allowed or not payload.get("component"):
        raise HTTPException(422, "shelly_light_command_invalid")
    component, channel = payload.get("component"), payload.get("channel", 0)
    if component not in {"light", "rgb", "rgbw", "cct", "color"}:
        raise HTTPException(422, "shelly_light_component_invalid")
    if isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel <= 31:
        raise HTTPException(422, "shelly_light_channel_invalid")
    values = {key: payload[key] for key in ("on", "brightness", "rgb", "white", "color_temperature") if key in payload}
    if not values:
        raise HTTPException(422, "shelly_light_command_empty")
    with db() as conn:
        actor = _revalidate_actor(conn, session, "operate")
        if actor["role"] not in {"owner", "admin", "operator"}:
            raise HTTPException(403, "permission_denied")
        row = conn.execute("SELECT * FROM shelly_devices WHERE device_id=? AND enabled=1", (device_id,)).fetchone()
    if not row:
        raise HTTPException(404, "shelly_device_not_found")
    device = dict(row)
    try:
        credentials = shelly_credentials.open_credentials(DATA_DIR, device.get("auth_ciphertext"))
        host = hardware_integrations._private_ip(device.get("host"))
        result = hardware_integrations.shelly_integration.control_light(
            host, int(device.get("generation") or 0), str(component), channel,
            username=str(credentials.get("username") or ""), password=str(credentials.get("password") or ""), **values)
    except (RuntimeError, OSError, ValueError) as exc:
        with db() as conn:
            actor = _revalidate_actor(conn, session, "operate")
            audit(conn, session["user_id"], "smart_device.shelly.light", device_id, "failed",
                  {"component": component, "channel": channel, "reason": str(exc)[:100]})
            conn.commit()
        raise HTTPException(502, "shelly_light_command_failed") from exc
    with db() as conn:
        actor = _revalidate_actor(conn, session, "operate")
        audit(conn, session["user_id"], "smart_device.shelly.light", device_id,
              "confirmed" if result.get("command_confirmed") else "accepted_unconfirmed",
              {"component": component, "channel": channel, "requested": values,
               "command_state": result.get("command_state")})
        conn.commit()
    return {"device_id": device_id, "component": component, "channel": channel,
            "command_accepted": result.get("command_accepted", False),
            "command_confirmed": result.get("command_confirmed", False),
            "command_state": result.get("command_state", "UNKNOWN"),
            "device_command_latency_ms": result.get("device_command_latency_ms"),
            "readback_latency_ms": result.get("readback_latency_ms"),
            "observed_at": result.get("reading", {}).get("observed_at")}


@app.post("/api/v1/network/scan")
def scan_local_network(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Scan attached private networks and refresh saved Tuya IPs for unique MAC/IP matches."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        try:
            report = network_scanner.scan_attached_networks()
            _enrich_shelly_scan(report)
            # The general LAN scan must not wait on BLE bridge scans. Those can
            # take up to 30 seconds per bridge; explicit bridge discovery owns
            # that work. Show only observations collected by a recent explicit scan.
            report["blu_devices"] = _recent_shelly_blu_scan_observations(conn)
            report["blu_bridges"] = []
            report["blu_scan_source"] = "recent_observations_only"
            report.setdefault("networks", [])
            report.setdefault("skipped_networks", [])
            report.setdefault("scanned_count", 0)
            report.setdefault("responsive_count", len(report.get("hosts", [])))
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            LOG.warning("Local network scan failed (%s)", type(exc).__name__)
            raise HTTPException(502, "local_network_scan_failed") from exc
        except Exception as exc:
            LOG.exception("Unexpected local network scan failure")
            raise HTTPException(502, "local_network_scan_failed") from exc
        config = hardware_integrations.load_config()
        identities: dict[str, list[dict[str, str]]] = {}
        tuya = config.get("tuya", {}) if isinstance(config.get("tuya"), dict) else {}
        for device in tuya.get("devices", []):
            if not isinstance(device, dict) or not isinstance(device.get("device_id"), str):
                continue
            mac = hardware_integrations._tuya_normalize_mac(device.get("local_mac"))
            mac = ":".join(mac[index:index + 2] for index in range(0, 12, 2)) if mac else ""
            if re.fullmatch(MAC_RE, mac):
                identities.setdefault(mac, []).append({"device_id": device["device_id"],
                    "name": str(device.get("name") or "Tuya")[:120], "provider": "tuya",
                    "device_type": (str(device.get("device_kind") or "tuya") if str(device.get("device_kind") or "unknown") in hardware_integrations.TUYA_DEVICE_KINDS and device.get("device_kind") != "unknown" else "tuya")[:48],
                    "manufacturer": str(device.get("manufacturer") or "")[:120],
                    "model": str(device.get("model") or device.get("product_name") or "")[:120]})
        for provider, device_type, default_name in (("deye", "inverter", "Deye inverter"),
                                                     ("antminer", "miner", "Antminer"),
                                                     ("tesla", "vehicle", "Tesla")):
            item = config.get(provider, {}) if isinstance(config.get(provider), dict) else {}
            compact_mac = hardware_integrations._tuya_normalize_mac(item.get("local_mac"))
            mac = ":".join(compact_mac[index:index + 2] for index in range(0, 12, 2)) if compact_mac else ""
            if re.fullmatch(MAC_RE, mac):
                identities.setdefault(mac, []).append({"device_id": f"{provider}:main",
                    "name": str(item.get("name") or item.get("model") or default_name)[:120],
                    "provider": provider, "device_type": device_type,
                    "manufacturer": str(item.get("manufacturer") or "")[:120],
                    "model": str(item.get("model") or "")[:120]})
        shelly_devices = [dict(row) for row in conn.execute("SELECT * FROM shelly_devices WHERE enabled=1")]
        shelly_by_mac = {_inventory_mac(item.get("mac")): item for item in shelly_devices if _inventory_mac(item.get("mac"))}
        conflicted_macs = {_inventory_mac(item.get("mac"))
                           for item in report.get("mac_ip_conflicts", []) if isinstance(item, dict)}
        ips_by_mac: dict[str, set[str]] = {}
        for host in report.get("hosts", []):
            mac = _inventory_mac(host.get("mac"))
            ip = str(host.get("ip") or "").strip()
            if not mac:
                continue
            if ip and not host.get("mac_ip_conflict"):
                ips_by_mac.setdefault(mac, set()).add(ip)
            for candidate in host.get("ip_candidates", []):
                if isinstance(candidate, str) and candidate:
                    ips_by_mac.setdefault(mac, set()).add(candidate)
        for item in shelly_devices:
            mac = _inventory_mac(item.get("mac"))
            if mac:
                identities.setdefault(mac, []).append({"device_id": str(item.get("device_id") or "")[:128],
                    "name": str(item.get("name") or "Smart device")[:120], "provider": "shelly",
                    "device_type": "smart", "manufacturer": "Shelly", "model": str(item.get("model") or "")[:120]})
        now = utcnow()
        for mac, refs in identities.items():
            preferred = refs[0]
            conn.execute("""INSERT INTO network_device_inventory
                (mac,name,device_type,source_provider,source_device_id,created_at,updated_at,last_seen_at)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(mac) DO UPDATE SET
                source_provider=CASE WHEN network_device_inventory.source_provider='' THEN excluded.source_provider ELSE network_device_inventory.source_provider END,
                source_device_id=CASE WHEN network_device_inventory.source_device_id='' THEN excluded.source_device_id ELSE network_device_inventory.source_device_id END,
                device_type=CASE WHEN network_device_inventory.device_type='unknown' THEN excluded.device_type ELSE network_device_inventory.device_type END,
                name=CASE WHEN network_device_inventory.name='' THEN excluded.name ELSE network_device_inventory.name END,
                updated_at=excluded.updated_at""",
                (mac, preferred["name"], preferred["device_type"], preferred["provider"],
                 preferred["device_id"], now, now, ""))
        for mac, device in shelly_by_mac.items():
            candidates = ips_by_mac.get(mac, set())
            if mac not in conflicted_macs and len(candidates) == 1:
                current_ip = next(iter(candidates))
                try:
                    current_ip = hardware_integrations._private_ip(current_ip)
                except ValueError:
                    continue
                if current_ip != device.get("host"):
                    conn.execute("UPDATE shelly_devices SET host=?,updated_at=?,last_seen_at=? WHERE mac=? AND enabled=1",
                                 (current_ip, now, now, mac))
                    conn.execute("UPDATE gateway_device_inventory SET last_ip=?,updated_at=?,last_seen_at=? WHERE mac=? AND source_provider='shelly'",
                                 (current_ip, now, now, mac))
        _sync_gateway_device_inventory(conn, config)
        stored = {row["mac"]: dict(row) for row in conn.execute("SELECT * FROM network_device_inventory")}
        tuya_devices = tuya.get("devices", []) if isinstance(tuya.get("devices"), list) else []
        tuya_by_mac: dict[str, list[dict[str, Any]]] = {}
        for device in tuya_devices:
            if not isinstance(device, dict):
                continue
            mac = _inventory_mac(device.get("local_mac") or device.get("mac") or device.get("mac_address"))
            if mac:
                tuya_by_mac.setdefault(mac, []).append(device)
        configured_ip_updates = 0
        ambiguous_configured_macs = 0
        for mac, devices_for_mac in tuya_by_mac.items():
            candidates = ips_by_mac.get(mac, set())
            if mac in conflicted_macs or len(candidates) != 1 or len(devices_for_mac) != 1:
                if mac in ips_by_mac and (mac in conflicted_macs or len(candidates) != 1 or len(devices_for_mac) != 1):
                    ambiguous_configured_macs += 1
                continue
            observed_ip = next(iter(candidates))
            try:
                observed_ip = hardware_integrations._private_ip(observed_ip)
            except ValueError:
                continue
            if devices_for_mac[0].get("local_ip") != observed_ip:
                devices_for_mac[0]["local_ip"] = observed_ip
                configured_ip_updates += 1
        if configured_ip_updates:
            hardware_integrations.save_config(config)
        report["configured_ip_update_count"] = configured_ip_updates
        report["ambiguous_configured_mac_count"] = ambiguous_configured_macs
        for host in report["hosts"]:
            mac = _inventory_mac(host.get("mac"))
            candidates = sorted(ips_by_mac.get(mac, set()))
            if mac and (len(candidates) > 1 or mac in conflicted_macs):
                host["mac_ip_conflict"] = True
                host["ip_candidates"] = candidates or list(host.get("ip_candidates", []))
                host["ip"] = ""
        for host in report["hosts"]:
            mac = _inventory_mac(host.get("mac"))
            inventory = stored.get(mac)
            refs = identities.get(mac, [])
            central = conn.execute("SELECT * FROM gateway_device_inventory WHERE mac=? LIMIT 1", (mac,)).fetchone() if mac else None
            if central:
                matches = [{"name": central["name"], "device_id": central["source_device_id"] or None,
                            "provider": central["source_provider"] or "local", "device_type": central["device_type"],
                            "manufacturer": central["manufacturer"], "model": central["model"], "local_mac": mac,
                            "inventory_key": central["device_key"], "confirmation_status": central["confirmation_status"]}]
            elif refs:
                # Configured cloud-synced devices are the canonical labels when
                # their saved MAC matches. Preserve multiple references rather
                # than silently selecting the first configured device.
                matches = [{**item, "local_mac": mac} for item in refs]
            elif inventory:
                matches = [{"name": inventory["name"], "device_id": inventory["source_device_id"] or None,
                            "provider": inventory["source_provider"] or "local",
                            "device_type": inventory["device_type"],
                            "manufacturer": inventory["manufacturer"], "model": inventory["model"],
                            "local_mac": mac}]
            else:
                matches = []
            host["matched_devices"] = matches
            if matches:
                primary = matches[0]
                if not host.get("friendly_name"):
                    host["friendly_name"] = primary.get("name") or ""
                if not host.get("manufacturer"):
                    host["manufacturer"] = primary.get("manufacturer") or ""
                if not host.get("model"):
                    host["model"] = primary.get("model") or ""
            if inventory and mac:
                if host.get("mac_ip_conflict"):
                    conn.execute("UPDATE network_device_inventory SET last_seen_at=?,updated_at=? WHERE mac=?",
                                 (now, now, mac))
                else:
                    try:
                        observed_ip = hardware_integrations._private_ip(str(host.get("ip") or ""))
                    except ValueError:
                        observed_ip = ""
                    conn.execute("UPDATE network_device_inventory SET last_seen_at=?,last_ip=CASE WHEN ?<>'' THEN ? ELSE last_ip END,updated_at=? WHERE mac=?",
                                 (now, observed_ip, observed_ip, now, mac))
            if central and mac:
                if host.get("mac_ip_conflict"):
                    conn.execute("UPDATE gateway_device_inventory SET last_seen_at=?,updated_at=? WHERE device_key=?",
                                 (now, now, central["device_key"]))
                else:
                    try:
                        observed_ip = hardware_integrations._private_ip(str(host.get("ip") or ""))
                    except ValueError:
                        observed_ip = ""
                    if observed_ip:
                        conn.execute("UPDATE gateway_device_inventory SET last_ip=?,last_seen_at=?,updated_at=? WHERE device_key=?",
                                     (observed_ip, now, now, central["device_key"]))
        audit(conn, session["user_id"], "network.local_scan", "local_network", "success", {
            "scanned_count": report["scanned_count"], "responsive_count": report["responsive_count"],
            "network_count": len(report["networks"]), "skipped_network_count": len(report["skipped_networks"]),
            "blu_device_count": len(report.get("blu_devices", [])), "blu_bridge_count": len(report.get("blu_bridges", [])),
        })
        conn.commit()
        return report


def _tuya_auto_link_by_local_key(tuya: dict[str, Any], *, ip: str, mac: str, name: str,
                                product_id: str, model: str = "") -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    """Associate a discovered LAN endpoint to one synced Tuya identity by read-only DPS authentication.

    Tuya local keys never leave Gateway config. A candidate is accepted only when
    its device ID/key pair returns a non-empty DPS status from this exact IP.
    """
    devices = [item for item in tuya.get("devices", []) if isinstance(item, dict)
               and isinstance(item.get("device_id"), str) and item.get("local_key")]
    if not devices:
        return "no_local_key", None, None
    norm = lambda value: "".join(ch.casefold() for ch in str(value or "") if ch.isalnum())
    ip_matches = [item for item in devices if str(item.get("local_ip") or item.get("ip") or "") == ip]
    pid_matches = [item for item in devices if product_id and str(item.get("product_id") or "") == product_id]
    model_key = norm(model)
    model_matches = [item for item in devices if model_key and model_key in norm(item.get("product_name") or item.get("name"))]
    # Never test a random home's other local keys against this endpoint. Use
    # only inventory rows with an exact product ID, IP, or model association.
    strong_matches = pid_matches or ip_matches or model_matches
    if not strong_matches:
        return "no_matching_cloud_device", None, None
    ordered = list(dict.fromkeys(item["device_id"] for item in strong_matches))
    if len(ordered) > 12:
        return "too_many_cloud_candidates", None, None
    by_id = {item["device_id"]: item for item in devices}
    candidates = [by_id[device_id] for device_id in ordered]
    matched: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    saw_protocol_response = False
    for original in candidates:
        candidate = {**original, "local_ip": ip, "local_mac": mac}
        try:
            reading = hardware_integrations._tuya_local_status(candidate)
        except (RuntimeError, ValueError, OSError, TypeError):
            continue
        if reading.get("connection_state") == "local_responded" and reading.get("status"):
            saw_protocol_response = True
            matched.append((original, candidate, reading))
            if len(matched) > 1:
                return "ambiguous_key_match", None, None
    if len(matched) != 1:
        return ("ambiguous_key_match" if saw_protocol_response else "no_matching_cloud_device",
                None, None)
    original, candidate, reading = matched[0]
    original.update({
        "local_ip": ip,
        "local_mac": mac,
        "local_protocol": candidate.get("local_protocol") or reading.get("local_protocol"),
        "local_control_state": "ready",
        "local_verified": True,
        "name": name,
        "name_source": "local",
        "local_name": name,
        "current_status": reading["status"],
        "last_status_at": int(time.time()),
    })
    if product_id and not original.get("product_id"):
        original["product_id"] = product_id
    return "verified", original, reading


@app.post("/api/v1/network/devices/save")
def save_local_network_device(payload: dict[str, Any],
                              session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Verify a fresh IP/MAC pair and add or update its shared inventory identity."""
    allowed = {"mac", "name", "device_type", "manufacturer", "model", "product_id", "ip"}
    if not isinstance(payload, dict) or set(payload) - allowed or not {"mac", "name", "device_type"}.issubset(payload):
        raise HTTPException(422, "network_device_payload_invalid")
    mac = str(payload.get("mac") or "").strip().upper()
    name = str(payload.get("name") or "").strip()
    device_type = str(payload.get("device_type") or "unknown").strip().lower()
    manufacturer = str(payload.get("manufacturer") or "").strip()[:120]
    model = str(payload.get("model") or "").strip()[:120]
    product_id = str(payload.get("product_id") or "").strip()[:128]
    requested_ip = str(payload.get("ip") or "").strip()
    if not re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", mac):
        raise HTTPException(422, "network_device_mac_invalid")
    if not name or len(name) > 120 or len(device_type) > 64:
        raise HTTPException(422, "network_device_name_or_type_invalid")
    if requested_ip:
        try:
            requested_ip = hardware_integrations._private_ip(requested_ip)
        except ValueError as exc:
            raise HTTPException(422, "network_device_ip_invalid") from exc
    if not manufacturer:
        manufacturer = "Não identificado"
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        try:
            report = network_scanner.scan_attached_networks()
            _enrich_shelly_scan(report)
        except Exception as exc:
            LOG.warning("Network device verification failed (%s)", type(exc).__name__)
            raise HTTPException(502, "network_device_verification_failed") from exc
        matching_hosts = [item for item in report.get("hosts", [])
                          if str(item.get("mac") or "").strip().upper() == mac]
        if not matching_hosts:
            raise HTTPException(409, "network_device_not_seen_in_current_scan")
        if requested_ip and not any(str(item.get("ip") or "") == requested_ip for item in matching_hosts):
            raise HTTPException(409, "network_device_ip_mac_not_confirmed")
        host = matching_hosts[0]
        observed_ips = {str(item.get("ip") or "").strip() for item in matching_hosts if item.get("ip")}
        for item in matching_hosts:
            observed_ips.update(value for value in item.get("ip_candidates", []) if isinstance(value, str) and value)
        conflicted_macs = {str(item.get("mac") or "").strip().upper()
                           for item in report.get("mac_ip_conflicts", []) if isinstance(item, dict)}
        ambiguous_ip = mac in conflicted_macs or any(item.get("mac_ip_conflict") for item in matching_hosts) or len(observed_ips) > 1
        # Persist the identity/name even if the active scan reports more than
        # one candidate IP. Never pick one implicitly; a later unique scan may
        # refresh the address. An explicit IP still has to match this scan.
        current_ip = ""
        if not ambiguous_ip and host.get("ip"):
            try:
                current_ip = hardware_integrations._private_ip(str(host["ip"]))
            except ValueError:
                current_ip = ""
        config = hardware_integrations.load_config()
        tuya = config.get("tuya", {}) if isinstance(config.get("tuya"), dict) else {}
        matching_tuya = [item for item in tuya.get("devices", []) if isinstance(item, dict)
                         and str(item.get("local_mac") or "").strip().upper() == mac]
        known_product_ids = {str(item.get("product_id") or "").strip() for item in matching_tuya if item.get("product_id")}
        if len(known_product_ids) > 1 or (product_id and known_product_ids and product_id not in known_product_ids):
            raise HTTPException(409, "tuya_product_id_conflicts_with_mac_inventory")
        if not product_id and len(known_product_ids) == 1:
            product_id = next(iter(known_product_ids))
        tuya_association = None
        tuya_device_id = ""
        if manufacturer.casefold() in {"tuya", "moes"} and current_ip:
            if not any(isinstance(item.get("local_key"), str) and len(item.get("local_key", "")) >= 8
                       for item in matching_tuya):
                # Refresh the configured Tuya cloud inventory on save so a
                # synced local key can be tested automatically. Failure leaves
                # the network identity saved with a clear connection status.
                if tuya.get("client_id") and tuya.get("client_secret") and tuya.get("uid"):
                    try:
                        synced = hardware_integrations.synchronize_tuya_devices(tuya)
                        old_by_id = {item.get("device_id"): item for item in tuya.get("devices", [])
                                     if isinstance(item, dict) and item.get("device_id")}
                        imported = {item["device_id"]: {**old_by_id.get(item["device_id"], {}), **item}
                                    for item in synced.get("devices", [])
                                    if isinstance(item, dict) and item.get("device_id")}
                        # Cloud sync is an enrichment step, never a destructive
                        # replacement of local keys or local DPS overrides.
                        for device_id, old in old_by_id.items():
                            if device_id not in imported:
                                imported[device_id] = old
                            else:
                                for field in ("local_key", "local_mac", "local_ip", "local_protocol",
                                              "local_dps_map", "handler_value_mappings",
                                              "handler_initial_status_mappings", "handler_type_overrides"):
                                    if old.get(field) and not imported[device_id].get(field):
                                        imported[device_id][field] = old[field]
                        tuya["devices"] = list(imported.values())
                        tuya["product_schemas"] = synced.get("product_schemas", tuya.get("product_schemas", {}))
                        tuya["category_schemas"] = synced.get("category_schemas", tuya.get("category_schemas", {}))
                        config["tuya"] = tuya
                        hardware_integrations.save_config(config)
                        matching_tuya = [item for item in tuya.get("devices", []) if isinstance(item, dict)
                                         and str(item.get("local_mac") or "").strip().upper() == mac]
                    except (ValueError, RuntimeError, OSError) as exc:
                        tuya_association = {"state": "cloud_sync_unavailable", "reason": str(exc)[:80]}
            if not any(isinstance(item.get("local_key"), str) and len(item.get("local_key", "")) >= 8
                       for item in matching_tuya):
                if tuya_association is None:
                    association_state, matched_tuya, matched_reading = _tuya_auto_link_by_local_key(
                        tuya, ip=current_ip, mac=mac, name=name, product_id=product_id, model=model)
                    if association_state == "verified" and matched_tuya:
                        matching_tuya = [matched_tuya]
                        tuya_device_id = str(matched_tuya.get("device_id") or "")
                        if matched_tuya.get("product_id"):
                            product_id = str(matched_tuya["product_id"])
                        tuya_association = {"state": "verified", "device_id": tuya_device_id,
                                            "reading": matched_reading}
                    else:
                        tuya_association = {"state": association_state}
            elif len(matching_tuya) == 1:
                # A direct MAC match still needs a real DPS read before control
                # readiness is reported; this never sends a command.
                matched_tuya = matching_tuya[0]
                probe_device = {**matched_tuya, "local_ip": current_ip, "local_mac": mac}
                try:
                    matched_reading = hardware_integrations._tuya_local_status(probe_device)
                except (RuntimeError, ValueError, OSError, TypeError):
                    matched_reading = None
                if matched_reading and matched_reading.get("status"):
                    matched_tuya.update({"local_ip": current_ip, "local_mac": mac,
                                         "local_protocol": probe_device.get("local_protocol"),
                                         "local_control_state": "ready", "local_verified": True,
                                         "name": name, "name_source": "local", "local_name": name,
                                         "current_status": matched_reading["status"],
                                         "last_status_at": int(time.time())})
                    tuya_device_id = str(matched_tuya.get("device_id") or "")
                    tuya_association = {"state": "verified", "device_id": tuya_device_id,
                                        "reading": matched_reading}
                else:
                    tuya_association = {"state": "dps_read_failed"}
        shelly_detected = str(host.get("manufacturer") or "").casefold() == "shelly" and host.get("protocol") in {"shelly_rpc", "shelly_http_gen1"}
        provider = "tuya" if len(matching_tuya) == 1 else "shelly" if shelly_detected else ""
        provider_device_id = str(matching_tuya[0].get("device_id") or "") if provider == "tuya" else f"shelly:{mac}" if provider == "shelly" else ""
        tuya_probe = None
        if manufacturer.casefold() in {"tuya", "moes"} and current_ip:
            # Read-only TCP check: confirms local Tuya service reachability,
            # but does not claim that DPS authentication/read succeeded.
            try:
                tuya_probe = hardware_integrations.probe_tuya_lan_reachability(current_ip)
            except Exception as exc:
                tuya_probe = {"state": "failed", "host": current_ip,
                              "reason": f"tuya_lan_probe_failed:{type(exc).__name__}"}
        now = utcnow()
        previous = conn.execute("SELECT last_ip,created_at FROM network_device_inventory WHERE mac=?", (mac,)).fetchone()
        last_ip = current_ip or (str(previous["last_ip"]) if previous else "")
        created_at = str(previous["created_at"]) if previous else now
        conn.execute("""INSERT INTO network_device_inventory
            (mac,name,device_type,manufacturer,model,last_ip,product_id,source_provider,source_device_id,created_at,updated_at,last_seen_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(mac) DO UPDATE SET
            name=excluded.name,device_type=excluded.device_type,
            manufacturer=CASE WHEN excluded.manufacturer<>'' THEN excluded.manufacturer ELSE network_device_inventory.manufacturer END,
            model=CASE WHEN excluded.model<>'' THEN excluded.model ELSE network_device_inventory.model END,
            last_ip=CASE WHEN excluded.last_ip<>'' THEN excluded.last_ip ELSE network_device_inventory.last_ip END,
            product_id=CASE WHEN excluded.product_id<>'' THEN excluded.product_id ELSE network_device_inventory.product_id END,
            source_provider=CASE WHEN excluded.source_provider<>'' THEN excluded.source_provider ELSE network_device_inventory.source_provider END,
            source_device_id=CASE WHEN excluded.source_device_id<>'' THEN excluded.source_device_id ELSE network_device_inventory.source_device_id END,
            updated_at=excluded.updated_at,last_seen_at=excluded.last_seen_at""",
            (mac, name, device_type, manufacturer or str(host.get("manufacturer") or "")[:120], model or str(host.get("model") or "")[:120],
             last_ip, product_id, provider, provider_device_id, created_at, now, now))
        if product_id and manufacturer.casefold() in {"tuya", "moes"}:
            _upsert_smart_product_catalog(conn, manufacturer=manufacturer, protocol="tuya", product_code=product_id,
                product_name=model, device_kind=device_type, source="owner_identified_product", confidence="user_declared")
        if provider:
            for item in matching_tuya:
                item["name"] = name
                item["name_source"] = "local"
                item["local_name"] = name
                if current_ip:
                    item["local_ip"] = current_ip
            if provider == "tuya":
                hardware_integrations.save_config(config)
            else:
                shelly_generation = int(host.get("shelly_generation") or 1)
                now = utcnow()
                conn.execute("""INSERT INTO shelly_devices
                    (device_id,mac,name,host,model,generation,protocol,firmware,capabilities_json,room,enabled,created_at,updated_at,last_seen_at)
                    VALUES(?,?,?,?,?,?,?,?,'[]','',1,?,?,?)
                    ON CONFLICT(mac) DO UPDATE SET name=excluded.name,host=excluded.host,model=excluded.model,
                    generation=excluded.generation,protocol=excluded.protocol,firmware=excluded.firmware,
                    enabled=1,updated_at=excluded.updated_at,last_seen_at=excluded.last_seen_at""",
                    (provider_device_id, mac, name, current_ip or str(host.get("ip") or ""),
                     str(host.get("model") or "")[:120], shelly_generation,
                     str(host.get("protocol") or "")[:40], str(host.get("shelly_firmware") or "")[:80], now, now, now))
        central_saved = _upsert_gateway_inventory_device(conn, provider=provider or "network",
            source_device_id=provider_device_id or mac, name=name, device_type=device_type, mac=mac,
            ip=current_ip or last_ip, manufacturer=manufacturer or str(host.get("manufacturer") or ""),
            model=model or str(host.get("model") or ""),
                product_id=product_id,
            # Saving a device from a fresh scan confirms its network identity
            # (MAC, and IP when unique). Connector readiness is tracked
            # separately by the provider integration and must not keep a
            # positively identified device in the generic "pending" list.
            status="confirmed" if current_ip and not ambiguous_ip else "pending",
            name_source="owner", replace_ip=bool(current_ip))
        saved_integrations = hardware_integrations.load_config()
        _sync_gateway_device_inventory(conn, saved_integrations)
        central_saved = dict(conn.execute("SELECT * FROM gateway_device_inventory WHERE device_key=?",
                                         (central_saved["device_key"],)).fetchone())
        if central_saved.get("mac") and central_saved.get("device_type") in {"miner", "mineradora", "antminer"}:
            _sync_miner_name_from_inventory(conn, central_saved["device_key"], central_saved["name"])
        audit(conn, session["user_id"], "network.device.save", mac, "success", {
            "device_type": device_type, "has_current_ip": bool(current_ip), "ambiguous_ip": ambiguous_ip})
        conn.commit()
        return {"device": central_saved, "ambiguous_ip": ambiguous_ip,
                "tuya_lan_probe": tuya_probe,
                "tuya_association": {key: value for key, value in (tuya_association or {}).items()
                                     if key != "reading"},
                "tuya_reading": tuya_association.get("reading") if tuya_association else None}


@app.post("/api/v1/network/scan/apply")
def apply_local_network_matches(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Rescan and persist IPs only where the observed MAC matches a configured device."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_required")
        try:
            report = network_scanner.scan_attached_networks()
            config = hardware_integrations.load_config()
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            LOG.warning("Local network rescan failed (%s)", type(exc).__name__)
            raise HTTPException(502, "local_network_scan_failed") from exc
        except Exception as exc:
            LOG.exception("Unexpected local network rescan failure")
            raise HTTPException(502, "local_network_scan_failed") from exc
        tuya = config.get("tuya", {}) if isinstance(config.get("tuya"), dict) else {}
        devices = tuya.get("devices", [])
        if not isinstance(devices, list):
            devices = []
        by_mac: dict[str, list[str]] = {}
        for item in devices:
            if isinstance(item, dict) and isinstance(item.get("device_id"), str):
                mac = str(item.get("local_mac") or "").strip().upper()
                if re.fullmatch(MAC_RE, mac):
                    by_mac.setdefault(mac, []).append(item["device_id"])
        ips_by_mac: dict[str, set[str]] = {}
        for host in report.get("hosts", []):
            mac = str(host.get("mac") or "").strip().upper()
            ip = str(host.get("ip") or "").strip()
            candidates = host.get("ip_candidates") if isinstance(host.get("ip_candidates"), list) else []
            observed_ips = {str(candidate).strip() for candidate in candidates if str(candidate).strip()}
            if ip:
                observed_ips.add(ip)
            if mac and observed_ips:
                ips_by_mac.setdefault(mac, set()).update(observed_ips)
        ambiguous_macs = {mac for mac, ips in ips_by_mac.items() if len(ips) != 1}
        ambiguous_macs.update(str(item.get("mac") or "").strip().upper()
                              for item in report.get("mac_ip_conflicts", []) if isinstance(item, dict))
        ambiguous_macs.update(mac for mac, device_ids in by_mac.items() if len(set(device_ids)) != 1)
        updates = []
        for mac, ips in ips_by_mac.items():
            device_ids = list(dict.fromkeys(by_mac.get(mac, [])))
            if mac in ambiguous_macs or len(device_ids) != 1:
                continue
            try:
                valid_ip = hardware_integrations._private_ip(next(iter(ips)))
            except ValueError:
                continue
            for item in devices:
                if isinstance(item, dict) and item.get("device_id") == device_ids[0] and item.get("local_ip") != valid_ip:
                    item["local_ip"] = valid_ip
                    updates.append({"device_id": item["device_id"], "name": str(item.get("name") or "Tuya"),
                                    "mac": mac, "ip": valid_ip})
        if updates:
            hardware_integrations.save_config(config)
        audit(conn, session["user_id"], "network.local_scan.apply", "tuya_devices", "success", {
            "updated_device_count": len(updates), "scanned_count": report["scanned_count"],
        })
        conn.commit()
        return {"updated_count": len(updates), "matched_count": sum(1 for mac in ips_by_mac if by_mac.get(mac)),
                "ambiguous_mac_count": len(ambiguous_macs.intersection(by_mac)), "updated_devices": updates,
                "message": "Only devices matched by their configured MAC address were updated."}


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
                deye_result = _read_deye_with_inventory_recovery(item)
                if deye_result.get("connection_state") == "read_in_progress":
                    raise HTTPException(409, "deye_read_already_in_progress")
                result: dict[str, Any] = {"deye": deye_result}
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
                energy_engine.persist_tuya_telemetry(conn, result["tuya"], item.get("devices", []), item.get("product_schemas", {}))
                _update_tuya_device_records(config, result["tuya"])
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
            if provider == "antminer":
                try:
                    with db() as offline_conn:
                        _mark_antminer_disconnected(offline_conn, item)
                        offline_conn.commit()
                except sqlite3.Error:
                    pass
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
            if isinstance(watt, bool) or not isinstance(watt, int) or not 1 <= watt <= 100000:
                raise HTTPException(422, "power_target_out_of_range_1_100000_watts")
        elif watt is not None:
            raise HTTPException(422, "antminer_control_payload_invalid")
        try:
            config = hardware_integrations.load_config().get("antminer", {})
            result = hardware_integrations.control_antminer(config, action, watt)
            _activate_energy_manual_override(conn, session["user_id"], f"antminer:{action}")
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


@app.post("/api/v1/integrations/antminer/test-control")
def antminer_test_control(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Prove control without pausing or stopping: resend the current target unchanged."""
    with db() as conn:
        _require_owner(session, conn)
        try:
            config = hardware_integrations.load_config().get("antminer", {})
            result = hardware_integrations.test_antminer_control(config)
            outcome = "success" if result.get("connection_state") == "control_verified" else "failed"
            audit(conn, session["user_id"], "hardware.antminer.test_control", "antminer", outcome, {
                "previous_target_watt": result.get("previous_target_watt"),
                "applied_watt": result.get("applied_watt"), "control_command_sent": True,
                "mining_state_changed": False,
            })
            return result
        except RuntimeError as exc:
            reason = str(exc)[:120]
            LOG.error("Antminer control probe failed reason=%s", reason)
            audit(conn, session["user_id"], "hardware.antminer.test_control", "antminer", "failed", {
                "reason": reason, "control_command_sent": reason != "antminer_control_probe_target_unavailable",
                "mining_state_changed": False,
            })
            raise HTTPException(502, reason) from exc
        except (OSError, json.JSONDecodeError) as exc:
            LOG.error("Antminer control probe failed (%s)", type(exc).__name__)
            audit(conn, session["user_id"], "hardware.antminer.test_control", "antminer", "failed", {
                "reason": type(exc).__name__, "control_command_sent": False, "mining_state_changed": False,
            })
            raise HTTPException(502, "antminer_control_probe_failed") from exc


@app.post("/api/v1/integrations/antminer/management")
def antminer_management(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Owner-only bridge to the documented Braiins OS management operations."""
    with db() as conn:
        _require_owner(session, conn)
        if not isinstance(payload, dict) or set(payload) - {"operation", "payload", "resource_id"}:
            raise HTTPException(422, "antminer_management_payload_invalid")
        operation = payload.get("operation")
        body = payload.get("payload")
        resource_id = payload.get("resource_id")
        if not isinstance(operation, str) or (resource_id is not None and not isinstance(resource_id, str)):
            raise HTTPException(422, "antminer_management_payload_invalid")
        try:
            config = hardware_integrations.load_config().get("antminer", {})
            result = hardware_integrations.antminer_management(config, operation, payload=body,
                                                                resource_id=resource_id)
            if operation == "tuner":
                result["energy_readings_persisted"] = _persist_antminer_braiins_tuner(conn, config, result)
            if result.get("command_sent"):
                _activate_energy_manual_override(conn, session["user_id"], f"antminer-management:{operation}")
            audit(conn, session["user_id"], f"hardware.antminer.{operation}", "antminer",
                  "success", {"operation": operation, "command_sent": result.get("command_sent", False)})
            conn.commit()
            return result
        except ValueError as exc:
            audit(conn, session["user_id"], f"hardware.antminer.{operation}", "antminer", "rejected",
                  {"reason": str(exc)[:120]})
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            reason = str(exc)[:120]
            LOG.error("Antminer management operation failed operation=%s reason=%s", operation, reason)
            audit(conn, session["user_id"], f"hardware.antminer.{operation}", "antminer", "failed",
                  {"reason": reason, "command_sent": False})
            raise HTTPException(502, reason) from exc
        except (OSError, json.JSONDecodeError) as exc:
            LOG.error("Antminer management operation failed operation=%s (%s)", operation, type(exc).__name__)
            audit(conn, session["user_id"], f"hardware.antminer.{operation}", "antminer", "failed",
                  {"reason": type(exc).__name__, "command_sent": False})
            raise HTTPException(502, "antminer_management_failed") from exc


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
            _activate_energy_manual_override(conn, session["user_id"], f"tuya:{device_id}")
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
            _activate_energy_manual_override(conn, session["user_id"], f"tuya-level:{device_id}")
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


@app.post("/api/v1/integrations/tuya/setting")
def tuya_setting_control(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Owner-only setting command limited to declared, supported DPS functions."""
    with db() as conn:
        _require_owner(session, conn)
        if not isinstance(payload, dict) or set(payload) != {"device_id", "code", "value"}:
            raise HTTPException(422, "tuya_setting_payload_invalid")
        device_id, code, value = payload.get("device_id"), payload.get("code"), payload.get("value")
        if (not isinstance(device_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", device_id)
                or not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", code)
                or isinstance(value, (dict, list, float)) or not isinstance(value, (bool, int, str))):
            raise HTTPException(422, "tuya_setting_payload_invalid")
        try:
            config = hardware_integrations.load_config().get("tuya", {})
            result = hardware_integrations.control_tuya_setting(config, device_id, code, value)
            audit(conn, session["user_id"], "hardware.tuya.setting", device_id,
                  "success" if result.get("state_confirmed") else "unconfirmed",
                  {"setting_code": code, "state_confirmed": bool(result.get("state_confirmed")), "control_command_sent": True})
            return result
        except ValueError as exc:
            audit(conn, session["user_id"], "hardware.tuya.setting", device_id, "rejected", {"reason": str(exc)[:120]})
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            reason = str(exc)[:120]
            audit(conn, session["user_id"], "hardware.tuya.setting", device_id, "failed", {"reason": reason, "control_command_sent": False})
            raise HTTPException(502, reason) from exc
        except (OSError, json.JSONDecodeError) as exc:
            LOG.error("Tuya setting control failed (%s)", type(exc).__name__)
            audit(conn, session["user_id"], "hardware.tuya.setting", device_id, "failed", {"reason": type(exc).__name__, "control_command_sent": False})
            raise HTTPException(502, "tuya_setting_control_failed") from exc


@app.post("/api/v1/integrations/tuya/product-dps-description")
def tuya_product_dps_description(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Save an Owner DPS meaning for devices with one exact Tuya product identity."""
    with db() as conn:
        _require_owner(session, conn)
        allowed_payload = {"device_id", "dps_id", "description", "semantic_code", "unit", "scale"}
        if not isinstance(payload, dict) or set(payload) - allowed_payload or not {"device_id", "dps_id", "description"}.issubset(payload):
            raise HTTPException(422, "tuya_dps_description_payload_invalid")
        device_id, dps_id, description = payload.get("device_id"), payload.get("dps_id"), payload.get("description")
        requested_semantic, requested_unit, requested_scale = payload.get("semantic_code"), payload.get("unit"), payload.get("scale")
        if (not isinstance(device_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", device_id)
                or isinstance(dps_id, bool) or not isinstance(dps_id, int) or not 1 <= dps_id <= 65535
                or not isinstance(description, str) or not 1 <= len(description.strip()) <= 80
                or requested_semantic is not None and requested_semantic not in {item["code"] for item in tuya_dps_registry.NORMALIZED_CHARACTERISTICS}
                or requested_unit is not None and (not isinstance(requested_unit, str) or len(requested_unit) > 16)
                or requested_scale is not None and (isinstance(requested_scale, bool) or not isinstance(requested_scale, (int, float)) or not 1 <= requested_scale <= 1_000_000_000)):
            raise HTTPException(422, "tuya_dps_description_payload_invalid")
        characteristics = {item["code"]: item for item in tuya_dps_registry.NORMALIZED_CHARACTERISTICS}
        accepted_units = {key: set(item.get("units", [])) for key, item in characteristics.items()}
        config = hardware_integrations.load_config()
        tuya = config.get("tuya") if isinstance(config.get("tuya"), dict) else {}
        device = next((item for item in tuya.get("devices", []) if isinstance(item, dict) and item.get("device_id") == device_id), None)
        if not device:
            raise HTTPException(404, "tuya_device_not_configured")
        product_id = str(device.get("product_id") or "")
        if not product_id:
            raise HTTPException(422, "tuya_product_id_required_for_shared_dps_description")
        profiles = hardware_integrations._bounded_tuya_product_schemas(tuya.get("product_schemas"))
        product = profiles.get(product_id)
        if not isinstance(product, dict):
            product = {"category": str(device.get("category") or "")[:64],
                       "product_name": str(device.get("product_name") or "")[:120],
                       "device_kind": str(device.get("device_kind") or "unknown")[:32],
                       "channel_count": int(device.get("channel_count") or 0),
                       "schema_source": str(device.get("schema_source") or "TUYA_DEVICE_SPEC")[:48],
                       "functions": device.get("functions", []) if isinstance(device.get("functions"), list) else [],
                       "status_spec": device.get("status_spec", []) if isinstance(device.get("status_spec"), list) else [],
                       "dps_profile": tuya_dps_registry.product_profile(device), "custom_dps_overrides": {},
                       "cached_at": int(time.time())}
            profiles[product_id] = product
        identity = hardware_integrations.tuya_product_identity(device)
        identity_key = hardware_integrations.tuya_product_identity_key(device)
        if not all(identity):
            raise HTTPException(422, "tuya_product_identity_incomplete")
        scoped_maps = tuya.get("product_dps_maps") if isinstance(tuya.get("product_dps_maps"), dict) else {}
        scoped_map = scoped_maps.get(identity_key)
        if not isinstance(scoped_map, dict):
            scoped_map = {"product_id": identity[0], "product": identity[1], "category": identity[2],
                          "device_kind": identity[3], "custom_dps_overrides": {}, "dps_profile": {"dps": []}}
        product.setdefault("protocol", "tuya")
        product.setdefault("manufacturer", "Tuya")
        product.setdefault("device_kind", str(device.get("device_kind") or device.get("category") or "unknown")[:32])
        recognized: set[int] = set()
        # The periodic reader stores the latest successful LAN DPS snapshot in
        # SQLite. The config file can lag behind it, so include only a fresh,
        # successful observation for this exact device when validating an
        # Owner's Product ID scoped mapping.
        telemetry = energy_engine.read_tuya_telemetry(conn, max_age_seconds=10).get(device_id, {})
        observed_status = (telemetry.get("status", [])
                           if telemetry.get("fresh") and telemetry.get("connection_state") == "local_responded"
                           else [])
        for rows in (observed_status, device.get("current_status"), device.get("functions"), device.get("status_spec")):
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue
                value = row.get("dps_id", row.get("dp_id", row.get("dpId")))
                if value is None and isinstance(row.get("code"), str) and re.fullmatch(r"dps_\d+", row["code"]):
                    value = row["code"][4:]
                try:
                    parsed = int(value)
                except (TypeError, ValueError):
                    continue
                if parsed > 0:
                    recognized.add(parsed)
        profile = tuya_dps_registry.product_profile(device)
        profile_dps = profile.get("dps") if isinstance(profile.get("dps"), list) else []
        reference = next((row for row in profile_dps if isinstance(row, dict) and row.get("dps_id") == dps_id), None)
        if reference:
            recognized.add(dps_id)
        if dps_id not in recognized:
            raise HTTPException(422, "tuya_dps_not_in_product_schema")

        label = description.strip()
        decomposed = unicodedata.normalize("NFKD", label.casefold())
        folded = re.sub(r"[^a-z0-9]+", " ", "".join(char for char in decomposed if not unicodedata.combining(char))).strip()
        aliases = {
            "switch": ({"switch", "interruptor", "relay", "rele", "on off", "on off switch", "estado do disjuntor", "estado do interruptor", "estado ligado desligado"}, ""),
            "voltage": ({"voltage", "volt", "volts", "tensao", "tensao eletrica", "voltagem"}, "V"),
            "current": ({"current", "corrente", "corrente eletrica", "amperagem", "ampere", "amperes"}, "A"),
            "power": ({"power", "potencia", "potencia atual", "potencia ativa", "potencia instantanea", "potencia instantanea atual", "watt", "watts"}, "W"),
            "total_energy": ({"energia total", "energia acumulada", "total energy", "accumulated energy", "energy total"}, "kWh"),
            "daily_accumulated_energy": ({"energia diaria", "consumo diario", "daily energy", "today energy"}, "kWh"),
            "countdown": ({"countdown", "temporizador", "contagem decrescente"}, "s"),
            "child_lock": ({"child lock", "maintenance lock", "bloqueio infantil", "bloqueio de manutencao"}, ""),
            "light_mode": ({"light mode", "modo de iluminacao"}, ""),
            "relay_status": ({"relay status", "estado do rele"}, ""),
            "power_on_state": ({"power on state", "comportamento apos falha de energia"}, ""),
        }
        inferred_semantic, inferred_unit = next(((key, value[1]) for key, value in aliases.items() if folded in value[0]), ("custom_label", ""))
        # An explicit standard characteristic wins. If the editor is left on
        # its descriptive default, recognized labels still become usable
        # metrics (for example, “Potência instantânea” -> power).
        semantic = (inferred_semantic if requested_semantic in {None, "custom_label"}
                    else requested_semantic)
        unit = requested_unit if requested_unit is not None else inferred_unit
        data_type = str(characteristics.get(semantic, {}).get("data_type") or "unknown")
        if unit is not None and unit not in accepted_units.get(semantic, set()):
            raise HTTPException(422, "tuya_dps_unit_not_valid_for_characteristic")
        scale = requested_scale if requested_scale is not None else (reference.get("scale") if isinstance(reference, dict) and isinstance(reference.get("scale"), (int, float)) and not isinstance(reference.get("scale"), bool) else None)
        if scale is None:
            schema_rows = [*(device.get("functions", []) if isinstance(device.get("functions"), list) else []),
                           *(device.get("status_spec", []) if isinstance(device.get("status_spec"), list) else [])]
            spec = next((row for row in schema_rows if isinstance(row, dict) and row.get("dp_id", row.get("dpId")) == dps_id), None)
            values = spec.get("values", {}) if isinstance(spec, dict) else {}
            if isinstance(values, str):
                try: values = json.loads(values)
                except json.JSONDecodeError: values = {}
            if isinstance(values, dict) and isinstance(values.get("scale"), int) and not isinstance(values.get("scale"), bool) and 0 <= values["scale"] <= 9:
                scale = 10 ** values["scale"]
        if characteristics.get(semantic, {}).get("data_type") == "number" and (unit not in accepted_units.get(semantic, set()) or scale is None):
            raise HTTPException(422, "tuya_dps_measurement_requires_unit_and_scale")
        scoped_map.setdefault("custom_dps_overrides", {})[str(dps_id)] = {
            "label": label, "semantic_code": semantic, "unit": unit or None,
            "data_type": data_type, "scale": scale,
            "write_enabled": semantic in {"switch", "countdown", "child_lock"},
        }
        scoped_profile = scoped_map.get("dps_profile") if isinstance(scoped_map.get("dps_profile"), dict) else {"dps": []}
        scoped_rows = scoped_profile.get("dps") if isinstance(scoped_profile.get("dps"), list) else []
        scoped_reference = next((row for row in scoped_rows if isinstance(row, dict) and row.get("dps_id") == dps_id), None)
        if scoped_reference is None:
            scoped_reference = {"dps_id": dps_id, "confidence": "OWNER_CUSTOM", "source": "Gateway scoped Product mapping"}
            scoped_rows.append(scoped_reference)
        scoped_reference.update({"display_name": label, "semantic_code": semantic,
                          "unit": unit or (reference.get("unit") if isinstance(reference, dict) else None), "data_type": data_type,
                          "scale": scale if scale is not None else (reference.get("scale") if isinstance(reference, dict) else None),
                          "confidence": "OWNER_CUSTOM", "source": "Gateway scoped Product mapping",
                          "write_supported": semantic in {"switch", "countdown", "child_lock"}})
        scoped_profile["dps"] = scoped_rows
        scoped_map["dps_profile"] = scoped_profile
        scoped_maps[identity_key] = scoped_map
        tuya["product_schemas"] = profiles
        tuya["product_dps_maps"] = scoped_maps
        config["tuya"] = tuya
        try:
            saved = hardware_integrations.save_config(config)
        except (OSError, ValueError) as exc:
            raise HTTPException(500, "tuya_product_dps_description_save_failed") from exc
        conn.execute("""INSERT INTO tuya_product_identity(product_id,product,category,device_kind,product_name_pt,updated_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(product_id,product,category,device_kind) DO UPDATE SET
            product_name_pt=CASE WHEN excluded.product_name_pt<>'' THEN excluded.product_name_pt ELSE tuya_product_identity.product_name_pt END,
            updated_at=excluded.updated_at""",
            (identity[0][:128], identity[1][:160], identity[2][:64], identity[3][:32],
             str(device.get("product_name_pt") or "")[:160], utcnow()))
        # save_config returns a public view that deliberately omits private
        # schema internals; persist from the validated in-memory profiles.
        _persist_tuya_product_dps_map(conn, profiles)
        _persist_tuya_pid_capabilities(conn, profiles)
        _persist_tuya_product_dps_maps_scoped(conn, scoped_maps)
        audit(conn, session["user_id"], "hardware.tuya.dps_description", f"{product_id}:{dps_id}", "success",
              {"device_id": device_id, "product_id": product_id, "dps_id": dps_id, "semantic_code": semantic})
        affected = sum(1 for item in tuya.get("devices", []) if isinstance(item, dict)
                       and hardware_integrations.tuya_product_identity_key(item) == identity_key)
        return {"saved": True, "product_id": product_id, "product": identity[1],
                "category": identity[2], "device_kind": identity[3], "dps_id": dps_id,
                "description": label, "semantic_code": semantic,
                "unit": unit or None, "scale": scale, "data_type": data_type,
                "affected_device_count": affected,
                "product_profile": scoped_profile}


def _require_owner(session: dict[str, Any], conn) -> None:
    actor = _revalidate_actor(conn, session, "manage_gateway")
    if actor["role"] != "owner": raise HTTPException(403, "owner_required")


def _normalize_tesla_oauth_relay_config(raw_origin: Any, api_key: Any) -> dict[str, str]:
    if not isinstance(raw_origin, str) or not isinstance(api_key, str):
        raise HTTPException(422, "tesla_oauth_relay_invalid_config")
    raw_origin = raw_origin.strip().rstrip("/")
    api_key = api_key.strip()
    try:
        parsed = urlsplit(raw_origin)
        _ = parsed.port
        valid = (parsed.scheme == "https" and bool(parsed.hostname) and parsed.port in (None, 443) and not parsed.username and
                 not parsed.password and not parsed.path and not parsed.query and not parsed.fragment and
                 raw_origin == f"https://{parsed.netloc}")
        if parsed.hostname:
            ipaddress.ip_address(parsed.hostname)
            valid = False
    except ValueError:
        # A normal DNS hostname is expected; IP literal parsing raises ValueError.
        try:
            parsed = urlsplit(raw_origin)
            host = parsed.hostname or ""
            valid = (parsed.scheme == "https" and "." in host and not host.endswith((".local", ".localhost"))
                     and parsed.port in (None, 443)
                     and not parsed.username and not parsed.password and not parsed.path and not parsed.query
                     and not parsed.fragment and raw_origin == f"https://{parsed.netloc}")
        except ValueError:
            valid = False
    if not valid or len(api_key) < 32:
        raise HTTPException(422, "tesla_oauth_relay_invalid_config")
    return {"origin": raw_origin, "api_key": api_key,
            "callback": f"{raw_origin}/oauth/callback"}


def _tesla_oauth_relay_config() -> dict[str, str] | None:
    """Return the outbound-only public callback relay configuration, if installed."""
    raw_origin = os.environ.get("SOLARMINER_TESLA_RELAY_URL", "").strip()
    api_key = os.environ.get("SOLARMINER_TESLA_RELAY_API_KEY", "")
    if raw_origin or api_key:
        try:
            return _normalize_tesla_oauth_relay_config(raw_origin, api_key)
        except HTTPException as exc:
            raise HTTPException(503, "tesla_oauth_relay_not_configured") from exc
    configured = hardware_integrations.load_config().get("tesla_oauth_relay", {})
    if not isinstance(configured, dict) or not configured.get("origin") or not configured.get("api_key"):
        return None
    try:
        return _normalize_tesla_oauth_relay_config(configured.get("origin"), configured.get("api_key"))
    except HTTPException as exc:
        raise HTTPException(503, "tesla_oauth_relay_not_configured") from exc


def _tesla_oauth_relay_request(relay: dict[str, str], method: str, path: str,
                               payload: dict[str, Any] | None = None,
                               bearer: str | None = None) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json", "Authorization": f"Bearer {bearer or relay['api_key']}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = URLRequest(relay["origin"] + path, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=8) as response:
            raw = response.read(16_384)
        decoded = json.loads(raw.decode("utf-8")) if raw else {}
    except (HTTPError, URLError, OSError, TimeoutError, UnicodeError, json.JSONDecodeError) as exc:
        raise HTTPException(502, "tesla_oauth_relay_unavailable") from exc
    if not isinstance(decoded, dict):
        raise HTTPException(502, "tesla_oauth_relay_invalid_response")
    return decoded


def _tesla_oauth_exchange_and_list(pending: dict[str, Any], state: str, code: str) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "solarminer-tesla-oauth-result", "state": state, "ok": False,
                              "message": "A autorização Tesla não foi concluída.", "vehicles": []}
    try:
        with db() as conn:
            owner = conn.execute("SELECT role,status FROM users WHERE id=?", (pending["owner_id"],)).fetchone()
        if not owner or owner["role"] != "owner" or owner["status"] != "active":
            result["message"] = "A sessão Owner deixou de estar ativa. Inicia novamente a ligação na PWA."
            return result
        token_payload = hardware_integrations._tesla_http(hardware_integrations.TESLA_AUTH_URL, form={
            "grant_type": "authorization_code", "client_id": pending["client_id"],
            "client_secret": pending["client_secret"], "code": code,
            "audience": hardware_integrations.TESLA_API_BASES[pending["region"]],
            "redirect_uri": pending["redirect_uri"],
            "scope": "openid offline_access vehicle_device_data",
        })
        access_token, refresh_token = token_payload.get("access_token"), token_payload.get("refresh_token")
        if not isinstance(access_token, str) or not access_token or not isinstance(refresh_token, str) or not refresh_token:
            raise RuntimeError("tesla_oauth_tokens_missing")
        config = hardware_integrations.load_config()
        config["tesla"] = {"region": pending["region"], "client_id": pending["client_id"],
                           "refresh_token": refresh_token, "vehicle_ids": [], "local_mac": pending["local_mac"]}
        hardware_integrations.save_config(config)
        vehicle_payload = hardware_integrations._tesla_http(
            hardware_integrations.TESLA_API_BASES[pending["region"]] + "/api/1/vehicles", token=access_token)
        vehicles = vehicle_payload.get("response")
        if not isinstance(vehicles, list):
            raise RuntimeError("tesla_vehicle_list_invalid")
        safe_vehicles = []
        for vehicle in vehicles:
            if not isinstance(vehicle, dict):
                continue
            vehicle_id = str(vehicle.get("id_s") or vehicle.get("id") or "")
            vin = vehicle.get("vin")
            if vehicle_id.isdigit():
                safe_vehicles.append({"id": vehicle_id, "name": str(vehicle.get("display_name") or "Tesla")[:80],
                                      "vin_suffix": vin[-4:] if isinstance(vin, str) and len(vin) >= 4 else ""})
        result.update({"ok": True, "message": "Conta Tesla autorizada. Escolhe o veículo na PWA.",
                       "vehicles": safe_vehicles})
    except Exception:
        # Never reflect OAuth codes, secrets, tokens, or upstream details into the browser.
        result["message"] = "A Tesla não concluiu a autorização. Confirma Client ID, Client Secret, região e callback registado."
    return result


@app.post("/api/v1/energy/ev/tesla/oauth/start")
def ev_tesla_oauth_start(payload: dict[str, Any], request: Request,
                         session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Start Tesla owner authorization; the app secret remains transient in Gateway memory."""
    with db() as conn:
        _require_owner(session, conn)
        client_id, client_secret = payload.get("client_id"), payload.get("client_secret")
        region = payload.get("region", "europe")
        local_mac = str(payload.get("local_mac") or "").strip().upper()
        origin = request.headers.get("origin", "")
        try:
            parsed = urlsplit(origin)
            _ = parsed.port  # Force validation of a malformed port before constructing the callback.
            valid_origin = parsed.scheme == "https" and bool(parsed.hostname)
        except ValueError:
            valid_origin = False
        if not isinstance(client_id, str) or not 1 <= len(client_id.strip()) <= 256:
            raise HTTPException(422, "tesla_client_id_required")
        if not isinstance(client_secret, str) or not 1 <= len(client_secret) <= 512:
            raise HTTPException(422, "tesla_client_secret_required")
        if region not in hardware_integrations.TESLA_API_BASES:
            raise HTTPException(422, "invalid_tesla_region")
        if not valid_origin or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise HTTPException(400, "tesla_oauth_requires_https_pwa_origin")
        gateway_url = request.url
        gateway_origin = f"{gateway_url.scheme}://{gateway_url.netloc}"
        relay = _tesla_oauth_relay_config()
        try:
            parsed_gateway = urlsplit(gateway_origin)
            _ = parsed_gateway.port
            valid_gateway_origin = (parsed_gateway.scheme == "https" and bool(parsed_gateway.hostname)
                                    and not parsed_gateway.username and not parsed_gateway.password
                                    and not parsed_gateway.path and not parsed_gateway.query and not parsed_gateway.fragment)
        except ValueError:
            valid_gateway_origin = False
        if not relay and not valid_gateway_origin:
            raise HTTPException(400, "tesla_oauth_requires_public_https_gateway_origin")
        if local_mac and not MAC_RE.fullmatch(local_mac):
            raise HTTPException(422, "invalid_tesla_local_mac")
        callback = relay["callback"] if relay else f"{gateway_origin}/api/integration/tesla/callback"
        state = secrets.token_urlsafe(32)
        poll_token = secrets.token_urlsafe(48) if relay else ""
        if relay:
            _tesla_oauth_relay_request(relay, "POST", "/v1/sessions", {
                "state": state, "poll_token": poll_token, "origin": origin,
            })
        with _tesla_oauth_pending_lock:
            now = time.time()
            for key in [key for key, value in _tesla_oauth_pending.items() if value.get("expires_at", 0) < now]:
                _tesla_oauth_pending.pop(key, None)
            _tesla_oauth_pending[state] = {
                "owner_id": session["user_id"], "client_id": client_id.strip(),
                "client_secret": client_secret, "region": region, "local_mac": local_mac,
                "origin": origin, "redirect_uri": callback, "expires_at": now + 600,
                "relay": relay, "poll_token": poll_token, "completing": False,
            }
        expiry_timer = threading.Timer(600, _expire_tesla_oauth_pending, args=(state,))
        expiry_timer.daemon = True
        expiry_timer.start()
        authorize_url = "https://auth.tesla.com/oauth2/v3/authorize?" + urlencode({
            "response_type": "code", "client_id": client_id.strip(), "redirect_uri": callback,
            "scope": "openid offline_access vehicle_device_data", "state": state,
            "prompt_missing_scopes": "true", "require_requested_scopes": "true",
        })
        audit(conn, session["user_id"], "energy.ev.tesla.oauth.start", "ev", "success", {
            "region": region, "redirect_origin": origin, "client_secret_returned": False,
        })
        return {"authorize_url": authorize_url, "state": state, "redirect_uri": callback,
                "allowed_origin": origin, "relay_mode": bool(relay)}


@app.get("/api/integration/tesla/callback", response_class=HTMLResponse)
def ev_tesla_oauth_callback(request: Request) -> HTMLResponse:
    state = request.query_params.get("state", "")
    with _tesla_oauth_pending_lock:
        pending = _tesla_oauth_pending.get(state) if state else None
        if pending and not pending.get("relay"):
            _tesla_oauth_pending.pop(state, None)
    if not pending or pending.get("expires_at", 0) < time.time():
        return HTMLResponse("<!doctype html><meta charset=utf-8><title>Tesla Fleet</title><p>Pedido de autorização expirado ou inválido. Fecha esta janela e inicia novamente na PWA.</p>", status_code=400,
                            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    if pending.get("relay"):
        return HTMLResponse("<!doctype html><meta charset=utf-8><title>Tesla Fleet</title><p>Este fluxo usa o relay público. Fecha esta janela e volta à PWA.</p>", status_code=400,
                            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    if request.query_params.get("error") or not request.query_params.get("code"):
        result = {"type": "solarminer-tesla-oauth-result", "state": state, "ok": False,
                  "message": "A autorização foi cancelada ou recusada na Tesla.", "vehicles": []}
    else:
        result = _tesla_oauth_exchange_and_list(pending, state, request.query_params["code"])
    encoded = json.dumps(result).replace("<", "\\u003c")
    target_origin = json.dumps(pending["origin"])
    page = ("<!doctype html><html lang=pt><meta charset=utf-8><meta name=referrer content=no-referrer>"
            "<title>Tesla Fleet</title><p>Regresso à PWA…</p><script>"
            f"const result={encoded};const origin={target_origin};"
            "if(window.opener){window.opener.postMessage(result,origin);window.close();}"
            "else{document.querySelector('p').textContent=result.message;}"
            "</script></html>")
    return HTMLResponse(page, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@app.post("/api/v1/energy/ev/tesla/oauth/complete")
def ev_tesla_oauth_complete(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Let the authenticated PWA ask the Gateway to retrieve and exchange a code from its public relay."""
    state = payload.get("state") if isinstance(payload, dict) else None
    if not isinstance(state, str) or not 32 <= len(state) <= 256:
        raise HTTPException(422, "tesla_oauth_state_invalid")
    with db() as conn:
        _require_owner(session, conn)
    with _tesla_oauth_pending_lock:
        pending = _tesla_oauth_pending.get(state)
        if (not pending or pending.get("owner_id") != session["user_id"] or
                pending.get("expires_at", 0) < time.time() or not pending.get("relay")):
            raise HTTPException(404, "tesla_oauth_session_not_found")
        if pending.get("completing"):
            return {"ready": False}
        pending["completing"] = True
    relay = pending["relay"]
    try:
        relay_result = _tesla_oauth_relay_request(relay, "GET", f"/v1/sessions/{state}", bearer=pending["poll_token"])
    except HTTPException:
        with _tesla_oauth_pending_lock:
            if _tesla_oauth_pending.get(state) is pending:
                pending["completing"] = False
        raise
    if relay_result.get("ready") is not True:
        with _tesla_oauth_pending_lock:
            if _tesla_oauth_pending.get(state) is pending:
                pending["completing"] = False
        return {"ready": False}
    if relay_result.get("error"):
        result = {"type": "solarminer-tesla-oauth-result", "state": state, "ok": False,
                  "message": "A autorização foi cancelada ou recusada na Tesla.", "vehicles": []}
    else:
        code = relay_result.get("code")
        if not isinstance(code, str) or not code or len(code) > 4096:
            with _tesla_oauth_pending_lock:
                if _tesla_oauth_pending.get(state) is pending:
                    pending["completing"] = False
            raise HTTPException(502, "tesla_oauth_relay_result_invalid")
        result = _tesla_oauth_exchange_and_list(pending, state, code)
    with _tesla_oauth_pending_lock:
        _tesla_oauth_pending.pop(state, None)
    try:
        _tesla_oauth_relay_request(relay, "DELETE", f"/v1/sessions/{state}", bearer=pending["poll_token"])
    except HTTPException:
        pass
    return result


@app.get("/api/v1/energy/ev/tesla")
def ev_tesla_config(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    with db() as conn:
        _require_owner(session, conn)
        try:
            result = hardware_integrations.public_tesla_config()
            relay = _tesla_oauth_relay_config()
            result["oauth_redirect_uri"] = relay["callback"] if relay else ""
            result["relay_url"] = relay["origin"] if relay else ""
            result["relay_configured"] = bool(relay)
            row = conn.execute("SELECT value FROM system_state WHERE key='energy_tesla_presence'").fetchone()
            if row:
                try: result["local_presence"] = json.loads(row["value"])
                except (TypeError, json.JSONDecodeError): pass
            return result
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(500, "ev_tesla_config_unavailable") from exc


@app.put("/api/v1/energy/ev/tesla/relay")
def ev_tesla_relay_configure(payload: dict[str, Any], session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Set and verify the public callback relay; never return its shared API key."""
    with db() as conn:
        _require_owner(session, conn)
        if os.environ.get("SOLARMINER_TESLA_RELAY_URL") or os.environ.get("SOLARMINER_TESLA_RELAY_API_KEY"):
            raise HTTPException(409, "tesla_oauth_relay_managed_by_gateway_environment")
        if payload.get("enabled") is False:
            config = hardware_integrations.load_config()
            config.pop("tesla_oauth_relay", None)
            hardware_integrations.save_config(config)
            audit(conn, session["user_id"], "energy.ev.tesla.relay.configure", "ev", "success", {"enabled": False})
            return {"configured": False, "relay_url": "", "oauth_redirect_uri": "", "secrets_returned": False}
        relay = _normalize_tesla_oauth_relay_config(payload.get("relay_url"), payload.get("api_key"))
        try:
            health = _tesla_oauth_relay_request(relay, "GET", "/v1/health")
        except HTTPException as exc:
            audit(conn, session["user_id"], "energy.ev.tesla.relay.configure", "ev", "failed", {"reason": "relay_unreachable"})
            raise HTTPException(502, "tesla_oauth_relay_unreachable") from exc
        if health.get("status") != "ok":
            audit(conn, session["user_id"], "energy.ev.tesla.relay.configure", "ev", "failed", {"reason": "relay_health_invalid"})
            raise HTTPException(502, "tesla_oauth_relay_health_invalid")
        config = hardware_integrations.load_config()
        config["tesla_oauth_relay"] = {"origin": relay["origin"], "api_key": relay["api_key"]}
        hardware_integrations.save_config(config)
        audit(conn, session["user_id"], "energy.ev.tesla.relay.configure", "ev", "success", {
            "enabled": True, "relay_origin": relay["origin"], "secret_returned": False})
        return {"configured": True, "relay_url": relay["origin"],
                "oauth_redirect_uri": relay["callback"], "secrets_returned": False}


@app.post("/api/v1/energy/ev/tesla/presence")
def ev_tesla_local_presence(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    with db() as conn:
        _require_owner(session, conn)
        try:
            snapshot = _read_tesla_local_presence()
            _persist_tesla_presence(snapshot)
            audit(conn, session["user_id"], "energy.ev.tesla.presence", "ev", "success", {
                "state": snapshot["state"], "source": "gateway_neighbour_cache"})
            return snapshot
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            audit(conn, session["user_id"], "energy.ev.tesla.presence", "ev", "failed", {"reason": type(exc).__name__})
            raise HTTPException(502, "ev_tesla_presence_read_failed") from exc


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


@app.post("/api/v1/invites", status_code=201)
def create_invite(payload: CreateInvite, request: Request,
                  session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
    if payload.role not in {"viewer", "operator", "guest"}:
        raise HTTPException(422, "invite_role_not_allowed")
    role = "viewer" if payload.role == "guest" else payload.role
    # The PWA renders the QR locally. The Gateway returns only the short-lived
    # invitation secret and its stable identity fingerprint.
    fp = _gateway_qr_fingerprint()
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
        invite_code = {"token": token, "fp": fp, "exp": expires}
        audit(conn, actor["user_id"], "invite.created", invite_id, "success", {"role": role, "expires_at": expires})
        conn.commit()
    return {"invite_id": invite_id, "invite_code": invite_code,
            "expires_at": expires, "role": role, "label": payload.label.strip()}


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
            manifest_url, headers={"Accept": "application/json", "User-Agent": f"SolarMiner-CODE02/{PACKAGE_VERSION}"})
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
            preflight_reason = None if activation_available else "update_preflight_not_ready"
        except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
            activation_available = False
            candidate_reason = str(exc)
            preflight_reason = (candidate_reason if re.fullmatch(r"[A-Za-z0-9_.:-]{1,180}", candidate_reason)
                                else "update_preflight_unavailable")
        details = {"manifest_signature": "valid", "package_sha256": checked["sha256"],
                   "package_path": str(package_path), "manifest_path": str(manifest_path),
                   "space_required": needed, "activation_available": activation_available,
                   "preflight_reason": preflight_reason}
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
                  "preflight_reason": preflight_reason,
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


@app.get("/api/v1/system/diagnostics-upload")
def read_diagnostics_upload(session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
    """Owner-only status for the private GitHub diagnostics uploader; never return its token."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_only")
    return error_reporting.diagnostics_upload_status()


@app.post("/api/v1/system/client-diagnostics")
def receive_client_diagnostics(payload: dict[str, Any],
                               session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Persist only a strict, privacy-safe summary of PWA endpoint checks for later GitHub reports."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_only")
    events = payload.get("events") if isinstance(payload, dict) and set(payload) == {"events"} else None
    if not isinstance(events, list) or not events or len(events) > 20:
        raise HTTPException(422, "client_diagnostics_invalid")
    browsers = {"Chrome", "Chrome_iOS", "Safari", "Firefox", "Edge", "Other"}
    endpoints = {"LAN", "Tailscale", "Hosted", "Other"}
    routes = {"/api/v1/health", "/api/v1/info", "/api/v1/bootstrap/status"}
    outcomes = {"success", "auth_required", "http_error", "timeout", "browser_network_error",
                "request_error", "invalid_json", "invalid_response", "gateway_contract_error"}
    safe_events: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict) or set(event) - {"occurred_at", "browser", "endpoint_kind", "route", "outcome", "latency_ms", "http_status", "error_name"}:
            raise HTTPException(422, "client_diagnostics_invalid")
        timestamp, browser, endpoint, route = (event.get("occurred_at"), event.get("browser"),
                                                  event.get("endpoint_kind"), event.get("route"))
        try:
            occurred = datetime.fromisoformat(timestamp.replace("Z", "+00:00")) if isinstance(timestamp, str) else None
        except ValueError:
            occurred = None
        latency = event.get("latency_ms")
        outcome, http_status, error_name = event.get("outcome"), event.get("http_status"), event.get("error_name")
        if (occurred is None or occurred.tzinfo is None or browser not in browsers or endpoint not in endpoints
                or route not in routes or outcome not in outcomes or isinstance(latency, bool)
                or not isinstance(latency, int) or not 0 <= latency <= 120000
                or (http_status is not None and (isinstance(http_status, bool) or not isinstance(http_status, int) or not 100 <= http_status <= 599))
                or (error_name is not None and error_name not in {"AbortError", "TypeError", "Error"})):
            raise HTTPException(422, "client_diagnostics_invalid")
        safe_events.append({"occurred_at": occurred.astimezone(timezone.utc).isoformat(), "browser": browser,
                            "endpoint_kind": endpoint, "route": route, "outcome": outcome,
                            "latency_ms": latency, "http_status": http_status, "error_name": error_name})
    failures = [event for event in safe_events if event["outcome"] not in {"success", "auth_required"}]
    if failures:
        LOG.error("PWA endpoint probe diagnostic events=%s", json.dumps(safe_events, separators=(",", ":")))
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        audit(conn, actor["user_id"], "system.client_diagnostics.submit", "endpoint_probe", "success",
              {"events": len(safe_events), "failures": len(failures)})
    return {"status": "recorded", "events": len(safe_events), "failures": len(failures)}


@app.post("/api/v1/system/diagnostics-upload/send")
def send_manual_diagnostics_report(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Owner-triggered upload of the current timestamped console snapshot to the private diagnostics repo."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_only")
    if not error_reporting.diagnostics_upload_status().get("configured"):
        raise HTTPException(409, "github_diagnostics_not_configured")
    try:
        result = error_reporting.flush_reports(force_system_report=True, report_source="owner_manual")
    except (OSError, ValueError, RuntimeError, TimeoutError, json.JSONDecodeError) as exc:
        LOG.error("Owner manual diagnostics report failed reason=%s", type(exc).__name__)
        raise HTTPException(503, "github_diagnostics_report_failed") from exc
    if result.get("status") != "sent":
        raise HTTPException(503, "github_diagnostics_report_not_sent")
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        audit(conn, actor["user_id"], "system.diagnostics_upload.manual", "private_github_issues", "success", {})
    return {"status": "sent", "issue_url": result.get("issue_url")}


@app.put("/api/v1/system/watchdog")
def configure_gateway_watchdog(payload: dict[str, Any],
                               session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Allow only the authenticated Owner to manually enable/disable the watchdog timer."""
    if not isinstance(payload, dict) or set(payload) != {"enabled"} or not isinstance(payload["enabled"], bool):
        raise HTTPException(422, "watchdog_state_invalid")
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_only")
    try:
        result = update_helper_client.request("watchdog_set", enabled=payload["enabled"])
    except (OSError, RuntimeError, ValueError) as exc:
        LOG.error("Owner watchdog control failed enabled=%s reason=%s",
                  payload["enabled"], type(exc).__name__)
        raise HTTPException(503, "watchdog_state_change_failed") from exc
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        audit(conn, actor["user_id"], "system.watchdog.configure", "gateway_watchdog_timer", "success",
              {"enabled": payload["enabled"]})
    return {"status": "ok", "enabled": result.get("enabled") is True,
            "timer": result.get("timer", "unknown")}


@app.put("/api/v1/system/diagnostics-upload")
def configure_diagnostics_upload(payload: dict[str, Any], session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
    """Store a private-repo issue token without echoing or logging it."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_only")
    token = payload.get("token") if isinstance(payload, dict) else None
    if not isinstance(token, str):
        raise HTTPException(422, "github_token_required")
    try:
        error_reporting.configure_diagnostics_upload(token)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        audit(conn, actor["user_id"], "system.diagnostics_upload.configure", "private_github_issues", "success", {})
    return error_reporting.diagnostics_upload_status()


@app.delete("/api/v1/system/diagnostics-upload")
def disable_diagnostics_upload(session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_only")
    try:
        error_reporting.remove_diagnostics_upload()
    except ValueError as exc:
        raise HTTPException(500, "github_token_path_unsafe") from exc
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        audit(conn, actor["user_id"], "system.diagnostics_upload.disable", "private_github_issues", "success", {})
    return error_reporting.diagnostics_upload_status()


@app.get("/api/v1/system/terminal/diagnostics")
def gateway_terminal_diagnostics(session: dict[str, Any] = Depends(require_permission("manage_gateway"))) -> dict[str, Any]:
    """Explain whether the authenticated Gateway runtime can provide a PTY terminal."""
    with db() as conn:
        actor = _revalidate_actor(conn, session, "manage_gateway")
        if actor["role"] != "owner":
            raise HTTPException(403, "owner_only")
    try:
        import fcntl  # noqa: F401
        import pty  # noqa: F401
        import termios  # noqa: F401
        pty_available = os.name == "posix"
    except ImportError:
        pty_available = False
    shell_available = Path("/bin/bash").is_file()
    return {
        "available": pty_available and shell_available,
        "pty_available": pty_available,
        "shell_available": shell_available,
        "platform": os.name,
    }


@app.websocket("/api/v1/system/terminal/ws")
async def gateway_terminal(websocket: WebSocket) -> None:
    """Interactive bash PTY, restricted to a freshly authenticated Owner session."""
    origin = websocket.headers.get("origin", "").rstrip("/")
    host = websocket.headers.get("host", "").lower()
    same_host = bool(origin and urlsplit(origin).netloc.lower() == host)
    if not origin or not (same_host or origin in _CORS_ORIGINS):
        await websocket.close(code=4403)
        return
    await websocket.accept()
    try:
        auth_message = await websocket.receive_json()
        raw_token = auth_message.get("token") if isinstance(auth_message, dict) and auth_message.get("type") == "authenticate" else None
        if not isinstance(raw_token, str) or not raw_token or len(raw_token) > 512:
            await websocket.close(code=4401)
            return
        token_digest = token_hash(raw_token)
    except (WebSocketDisconnect, ValueError, TypeError):
        await websocket.close(code=4401)
        return
    try:
        with db() as conn:
            row = conn.execute("""SELECT s.*,u.username,u.role,u.status AS user_status,u.account_id,d.status AS device_status
              FROM sessions s JOIN users u ON u.id=s.user_id JOIN devices d ON d.id=s.device_id
              WHERE s.token_sha256=?""", (token_digest,)).fetchone()
            if not row:
                await websocket.close(code=4401)
                return
            session = dict(row)
            actor = _revalidate_actor(conn, session, "manage_gateway")
            if actor["role"] != "owner":
                await websocket.close(code=4403)
                return
    except HTTPException:
        await websocket.close(code=4401)
        return

    try:
        import fcntl
        import pty
        import struct
        import termios
        import signal
    except ImportError:
        await websocket.send_json({"type": "error", "data": "Este Gateway não suporta um terminal PTY."})
        await websocket.close(code=1011)
        return

    master_fd = slave_fd = None
    process = None
    reader_task = None
    output_queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=64)
    loop = asyncio.get_running_loop()
    receive_task = output_task = None
    try:
        master_fd, slave_fd = pty.openpty()
        try:
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))
        except OSError:
            pass
        terminal_env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "TERM": "xterm-256color",
                        "HOME": str(DATA_DIR), "USER": "solarminer", "SHELL": "/bin/bash"}
        process = subprocess.Popen(
            ["/bin/bash", "--noprofile", "--norc", "-i"], stdin=slave_fd, stdout=slave_fd,
            stderr=slave_fd, cwd=str(DATA_DIR), env=terminal_env, close_fds=True, start_new_session=True,
        )
        os.close(slave_fd)
        slave_fd = None

        async def read_terminal_output() -> None:
            normal_eof = False
            try:
                while True:
                    chunk = await loop.run_in_executor(None, os.read, master_fd, 4096)
                    if not chunk:
                        normal_eof = True
                        break
                    await output_queue.put(chunk.decode("utf-8", errors="replace"))
            except (OSError, asyncio.CancelledError):
                pass
            finally:
                if normal_eof:
                    await output_queue.put(None)

        reader_task = asyncio.create_task(read_terminal_output())
        with db() as conn:
            actor = _revalidate_actor(conn, session, "manage_gateway")
            audit(conn, actor["user_id"], "system.terminal.started", "owner_shell", "success", {})
        await websocket.send_json({"type": "ready", "data": "Terminal ligado ao Gateway como utilizador solarminer. Ctrl+C interrompe o comando atual."})
        receive_task = asyncio.create_task(websocket.receive_json())
        output_task = asyncio.create_task(output_queue.get())
        last_session_check = time.monotonic()
        while True:
            done, _ = await asyncio.wait({receive_task, output_task}, timeout=15,
                                         return_when=asyncio.FIRST_COMPLETED)
            if not done:
                if time.monotonic() - last_session_check >= 30:
                    try:
                        with db() as conn:
                            actor = _revalidate_actor(conn, session, "manage_gateway")
                            if actor["role"] != "owner":
                                break
                    except HTTPException:
                        break
                    last_session_check = time.monotonic()
                continue
            if output_task in done:
                output = output_task.result()
                if output is None:
                    await websocket.send_json({"type": "exit", "code": process.poll()})
                    break
                await websocket.send_json({"type": "output", "data": output})
                output_task = asyncio.create_task(output_queue.get())
            if receive_task in done:
                message = receive_task.result()
                kind = message.get("type") if isinstance(message, dict) else None
                if kind == "close":
                    break
                if kind == "input":
                    data = message.get("data")
                    if not isinstance(data, str) or len(data.encode("utf-8")) > 8192:
                        await websocket.send_json({"type": "error", "data": "Entrada demasiado longa."})
                    else:
                        os.write(master_fd, data.encode("utf-8"))
                elif kind == "resize":
                    rows = max(8, min(100, int(message.get("rows", 24))))
                    cols = max(20, min(240, int(message.get("cols", 100))))
                    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
                receive_task = asyncio.create_task(websocket.receive_json())
    except (WebSocketDisconnect, OSError, RuntimeError, ValueError):
        pass
    finally:
        for task in (reader_task, receive_task, output_task):
            if task:
                task.cancel()
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
        for fd in (master_fd, slave_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        pending_tasks = [task for task in (reader_task, receive_task, output_task) if task]
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
        try:
            with db() as conn:
                actor = _revalidate_actor(conn, session, "manage_gateway")
                audit(conn, actor["user_id"], "system.terminal.closed", "owner_shell", "success", {})
        except Exception:
            pass


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


