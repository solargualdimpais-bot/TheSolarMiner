"""Signed catalog and conservative Connector Manager lifecycle for CODE 02."""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import socket
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import connector_plugins

CONNECTOR_VERSION = "0.6.3"
CONNECTOR_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
LOCKS_GUARD = threading.Lock()
LOCKS: dict[str, threading.Lock] = {}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _audit(conn: sqlite3.Connection, actor_id: str, action: str, target: str | None, outcome: str, details: dict[str, Any]) -> None:
    conn.execute("INSERT INTO audit(occurred_at,actor_user_id,action,target,outcome,details_json) VALUES(?,?,?,?,?,?)",
                 (utcnow(), actor_id, action, target, outcome, json.dumps(details, separators=(",", ":"))))


def _lock_for(connector_id: str) -> threading.Lock:
    with LOCKS_GUARD:
        return LOCKS.setdefault(connector_id, threading.Lock())


def catalog_paths() -> tuple[Path, Path, Path]:
    root = Path(os.environ.get("SOLARMINER_CATALOG_DIR", "/usr/share/solarminer"))
    return (
        Path(os.environ.get("SOLARMINER_CATALOG_PATH", str(root / "catalog.json"))),
        Path(os.environ.get("SOLARMINER_CATALOG_SIGNATURE_PATH", str(root / "catalog.sig"))),
        Path(os.environ.get("SOLARMINER_CATALOG_PUBLIC_KEY_PATH", str(root / "catalog.pub"))),
    )


def catalog_bytes() -> tuple[bytes, bytes, bytes]:
    catalog_path, signature_path, public_key_path = catalog_paths()
    try:
        return catalog_path.read_bytes(), signature_path.read_bytes(), public_key_path.read_bytes()
    except OSError as exc:
        raise ValueError("signed_catalog_unavailable") from exc


def load_catalog() -> dict[str, Any]:
    raw, signature_raw, public_key_raw = catalog_bytes()
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_raw.decode("ascii").strip()))
        signature = bytes.fromhex(signature_raw.decode("ascii").strip())
        public_key.verify(signature, raw)
        parsed = json.loads(raw)
    except (ValueError, UnicodeError, json.JSONDecodeError, InvalidSignature) as exc:
        raise ValueError("catalog_signature_or_format_invalid") from exc
    if not isinstance(parsed, dict) or parsed.get("schema_version") != 1 or not isinstance(parsed.get("connectors"), list):
        raise ValueError("catalog_schema_invalid")
    seen: set[str] = set()
    runtime_version = tuple(int(part) for part in CONNECTOR_VERSION.split("."))
    for entry in parsed["connectors"]:
        if not isinstance(entry, dict):
            raise ValueError("catalog_entry_invalid")
        connector_id = entry.get("id")
        if not isinstance(connector_id, str) or not CONNECTOR_ID_RE.fullmatch(connector_id) or connector_id in seen:
            raise ValueError("catalog_connector_id_invalid")
        seen.add(connector_id)
        if entry.get("artifact_type") != "builtin" or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", ""))):
            raise ValueError("catalog_artifact_metadata_invalid")
        if not isinstance(entry.get("protocols", []), list) or not isinstance(entry.get("capabilities", {}), dict):
            raise ValueError("catalog_entry_metadata_invalid")
        minimum = entry.get("gateway_min", "0.0.0")
        try:
            minimum_version = tuple(int(p) for p in minimum.split("."))
        except (AttributeError, ValueError) as exc:
            raise ValueError("catalog_compatibility_invalid") from exc
        if runtime_version < minimum_version:
            raise ValueError("catalog_gateway_incompatible")
        if entry["id"] == "tcp-readonly-probe":
            digest = hashlib.sha256(Path(connector_plugins.__file__).read_bytes()).hexdigest()
            if digest != entry["sha256"]:
                raise ValueError("builtin_connector_hash_mismatch")
    return parsed


def public_catalog() -> dict[str, Any]:
    catalog = load_catalog()
    return {"schema_version": catalog["schema_version"], "catalog_version": catalog.get("catalog_version"),
            "signature_verified": True, "connectors": catalog["connectors"]}


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS connectors_installed(
      id TEXT PRIMARY KEY, version TEXT NOT NULL, status TEXT NOT NULL,
      config_json TEXT NOT NULL, installed_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      artifact_sha256 TEXT NOT NULL, last_test_json TEXT
    );
    CREATE TABLE IF NOT EXISTS connector_operations(
      id TEXT PRIMARY KEY, connector_id TEXT NOT NULL, operation TEXT NOT NULL,
      phase TEXT NOT NULL, actor_user_id TEXT, details_json TEXT NOT NULL,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_connector_ops_phase ON connector_operations(phase);
    CREATE TABLE IF NOT EXISTS discovered_devices(
      id TEXT PRIMARY KEY, host TEXT NOT NULL, port INTEGER NOT NULL,
      state TEXT NOT NULL, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
      evidence_json TEXT NOT NULL, UNIQUE(host,port)
    );
    CREATE TABLE IF NOT EXISTS connector_capabilities(
      id TEXT PRIMARY KEY, discovered_id TEXT NOT NULL REFERENCES discovered_devices(id) ON DELETE CASCADE,
      capability TEXT NOT NULL, state TEXT NOT NULL, evidence_json TEXT NOT NULL, verified_at TEXT NOT NULL,
      UNIQUE(discovered_id,capability)
    );
    """)


def recover_incomplete_operations(conn: sqlite3.Connection, state_dir: Path | None = None) -> int:
    """Recover only safe built-in lifecycle states; never executes connector code."""
    ensure_schema(conn)
    rows = conn.execute("SELECT id,connector_id,operation,phase FROM connector_operations WHERE phase IN ('PREPARING','ACTIVATING')").fetchall()
    recovered = 0
    for row in rows:
        # This initial release has no third-party code activation. Any interrupted
        # operation is marked RECOVERY_REQUIRED rather than guessed as successful.
        conn.execute("UPDATE connector_operations SET phase='RECOVERY_REQUIRED',updated_at=? WHERE id=?", (utcnow(), row["id"]))
        if row["operation"] in {"install", "update"}:
            conn.execute("UPDATE connectors_installed SET status='RECOVERY_REQUIRED',updated_at=? WHERE id=? AND status<>'REMOVED'",
                         (utcnow(), row["connector_id"]))
        recovered += 1
    return recovered


def _entry(connector_id: str) -> dict[str, Any]:
    if not CONNECTOR_ID_RE.fullmatch(connector_id):
        raise ValueError("invalid_connector_id")
    catalog = load_catalog()
    for entry in catalog["connectors"]:
        if entry["id"] == connector_id:
            return entry
    raise KeyError("connector_not_in_signed_catalog")


def list_installed(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_schema(conn)
    rows = conn.execute("SELECT * FROM connectors_installed ORDER BY id").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["config"] = json.loads(item.pop("config_json"))
        item["last_test"] = json.loads(item["last_test_json"]) if item.get("last_test_json") else None
        item.pop("last_test_json", None)
        result.append(item)
    return result


def install(conn: sqlite3.Connection, connector_id: str, actor_id: str, confirmed: bool, revalidate: Callable[[sqlite3.Connection], Any] | None = None) -> dict[str, Any]:
    if not confirmed:
        raise PermissionError("explicit_install_confirmation_required")
    with _lock_for(connector_id):
        entry = _entry(connector_id)
        if connector_id != "tcp-readonly-probe":
            raise ValueError("connector_runtime_not_supported_in_v0_6_0")
        digest = hashlib.sha256(Path(connector_plugins.__file__).read_bytes()).hexdigest()
        if digest != entry["sha256"]:
            raise ValueError("connector_artifact_hash_mismatch")
        # Connector Manager owns the worker lifecycle: prove that its isolated
        # subprocess can start and answer the allowlisted IPC health contract
        # before persisting the connector as installed. This is local process
        # integration, not proof of systemd sandbox enforcement.
        from .runtime_manager import ConnectorWorkerRuntime
        with ConnectorWorkerRuntime(connector_id, timeout=3.0) as worker:
            health = worker.health()
            if health.get("worker") != "ready" or health.get("connector_id") != connector_id:
                raise RuntimeError("connector_worker_contract_failed")
        ensure_schema(conn)
        op_id = str(uuid.uuid4())
        now = utcnow()
        conn.execute("BEGIN IMMEDIATE")
        try:
            if revalidate:
                revalidate(conn)
            conn.execute("INSERT INTO connector_operations VALUES(?,?,?,?,?,?,?,?)",
                         (op_id, connector_id, "install", "PREPARING", actor_id,
                          json.dumps({"version": entry["version"], "artifact_sha256": digest}), now, now))
            conn.execute("INSERT INTO connectors_installed(id,version,status,config_json,installed_at,updated_at,artifact_sha256,last_test_json) VALUES(?,?,?,?,?,?,?,NULL) "
                         "ON CONFLICT(id) DO UPDATE SET version=excluded.version,status='INSTALLED',updated_at=excluded.updated_at,artifact_sha256=excluded.artifact_sha256",
                         (connector_id, entry["version"], "INSTALLED", "{}", now, now, digest))
            conn.execute("UPDATE connector_operations SET phase='COMPLETED',updated_at=? WHERE id=?", (utcnow(), op_id))
            _audit(conn, actor_id, "connector.install", connector_id, "success",
                   {"version": entry["version"], "artifact_sha256": digest})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return {"id": connector_id, "version": entry["version"], "status": "INSTALLED", "operation_id": op_id,
                "artifact_sha256": digest, "worker_health_check": "PASS",
                "execution_isolated": False,
                "note": "worker subprocess and IPC health contract passed locally; OS sandbox enforcement is not implied"}


def update(conn: sqlite3.Connection, connector_id: str, actor_id: str, confirmed: bool, revalidate: Callable[[sqlite3.Connection], Any] | None = None) -> dict[str, Any]:
    """Reconcile a package-managed built-in connector against the verified catalog.

    Connector code itself is updated by the signed/verified Debian package, not
    downloaded or executed by this API. This route only refreshes persisted
    metadata after the currently installed module matches the signed catalog.
    """
    if not confirmed:
        raise PermissionError("explicit_update_confirmation_required")
    with _lock_for(connector_id):
        entry = _entry(connector_id)
        if connector_id != "tcp-readonly-probe":
            raise ValueError("connector_runtime_not_supported_in_v0_6_0")
        digest = hashlib.sha256(Path(connector_plugins.__file__).read_bytes()).hexdigest()
        if digest != entry["sha256"]:
            raise ValueError("connector_artifact_hash_mismatch")
        ensure_schema(conn)
        row = conn.execute("SELECT version,status,artifact_sha256 FROM connectors_installed WHERE id=?", (connector_id,)).fetchone()
        if not row:
            raise LookupError("connector_not_installed")
        if row["status"] != "INSTALLED":
            raise LookupError("connector_not_in_updatable_state")
        now = utcnow()
        conn.execute("BEGIN IMMEDIATE")
        try:
            if revalidate:
                revalidate(conn)
            if row["version"] == entry["version"] and row["artifact_sha256"] == digest:
                result_status = "ALREADY_CURRENT"
            else:
                conn.execute("UPDATE connectors_installed SET version=?,artifact_sha256=?,updated_at=? WHERE id=?",
                             (entry["version"], digest, now, connector_id))
                result_status = "METADATA_RECONCILED"
            conn.execute("INSERT INTO connector_operations VALUES(?,?,?,?,?,?,?,?)",
                         (str(uuid.uuid4()), connector_id, "update", "COMPLETED", actor_id,
                          json.dumps({"version": entry["version"], "artifact_sha256": digest,
                                      "code_updated_by": "debian_package_manager"}), now, now))
            _audit(conn, actor_id, "connector.update", connector_id, "success",
                   {"status": result_status, "version": entry["version"], "code_updated_by": "debian_package_manager"})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return {"id": connector_id, "status": result_status, "version": entry["version"],
                "artifact_sha256": digest,
                "code_updated_by": "debian_package_manager",
                "note": "This API does not download or execute code; upgrade connector code via a trusted Debian package."}


def configure(conn: sqlite3.Connection, connector_id: str, actor_id: str, config: dict[str, Any], revalidate: Callable[[sqlite3.Connection], Any] | None = None) -> dict[str, Any]:
    _entry(connector_id)
    if connector_id != "tcp-readonly-probe":
        raise ValueError("connector_runtime_not_supported_in_v0_6_0")
    allowed = {"timeout_seconds"}
    if set(config) - allowed:
        raise ValueError("unsupported_or_secret_config_field")
    timeout = config.get("timeout_seconds", 1.5)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.2 <= timeout <= 3.0:
        raise ValueError("invalid_timeout_seconds")
    ensure_schema(conn)
    row = conn.execute("SELECT status FROM connectors_installed WHERE id=?", (connector_id,)).fetchone()
    if not row or row["status"] != "INSTALLED":
        raise LookupError("connector_not_installed")
    now = utcnow()
    conn.execute("BEGIN IMMEDIATE")
    try:
        if revalidate:
            revalidate(conn)
        conn.execute("UPDATE connectors_installed SET config_json=?,updated_at=? WHERE id=?",
                     (json.dumps({"timeout_seconds": float(timeout)}, separators=(",", ":")), now, connector_id))
        conn.execute("INSERT INTO connector_operations VALUES(?,?,?,?,?,?,?,?)",
                     (str(uuid.uuid4()), connector_id, "configure", "COMPLETED", actor_id,
                      json.dumps({"fields": sorted(config.keys())}), now, now))
        _audit(conn, actor_id, "connector.configure", connector_id, "success", {"fields": sorted(config.keys())})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"id": connector_id, "status": "CONFIGURED", "config": {"timeout_seconds": float(timeout)}}


def test_connection(conn: sqlite3.Connection, connector_id: str, actor_id: str, host: str, port: int, revalidate: Callable[[sqlite3.Connection], Any] | None = None) -> dict[str, Any]:
    row = conn.execute("SELECT status,config_json FROM connectors_installed WHERE id=?", (connector_id,)).fetchone()
    if not row or row["status"] != "INSTALLED":
        raise LookupError("connector_not_installed")
    if connector_id != "tcp-readonly-probe":
        raise ValueError("connector_runtime_not_supported_in_v0_6_0")
    config = json.loads(row["config_json"])
    # Validate arguments in the API process without opening a socket. The worker
    # repeats these checks before performing any network operation.
    host = connector_plugins._validate_private_ip(host)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("invalid_port")
    timeout_seconds = config.get("timeout_seconds", 1.5)
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not 0.2 <= timeout_seconds <= 3.0:
        raise ValueError("invalid_timeout")
    # All connector transport probes execute in the supervised worker process.
    # The Gateway process validates and records the result, but does not open
    # the device TCP socket itself.
    from .runtime_manager import ConnectorWorkerRuntime, WorkerRuntimeError
    try:
        with ConnectorWorkerRuntime(connector_id, timeout=max(3.0, float(config.get("timeout_seconds", 1.5)) + 1.0)) as worker:
            raw = worker.call("tcp_probe", {"host": host, "port": port, "timeout": timeout_seconds})
    except (WorkerRuntimeError, OSError) as exc:
        raise RuntimeError("connector_worker_probe_failed") from exc
    result = {
        "result": "TCP_REACHABLE" if raw.get("reachable") is True else "TCP_UNREACHABLE",
        "host": raw.get("host", host), "port": raw.get("port", port),
        "error_type": raw.get("error_type"),
        "protocol_identified": raw.get("application_protocol_verified") is True,
        "device_capabilities_verified": False,
        "payload_sent": raw.get("payload_sent") is False,
        "hardware_commands_sent": raw.get("hardware_commands_sent") is False,
        "execution_worker": True,
    }
    now = utcnow()
    conn.execute("BEGIN IMMEDIATE")
    try:
        if revalidate:
            revalidate(conn)
        conn.execute("UPDATE connectors_installed SET last_test_json=?,updated_at=? WHERE id=?",
                     (json.dumps(result, separators=(",", ":")), now, connector_id))
        conn.execute("INSERT INTO connector_operations VALUES(?,?,?,?,?,?,?,?)",
                     (str(uuid.uuid4()), connector_id, "test", "COMPLETED", actor_id,
                      json.dumps({"result": result["result"], "host": result["host"], "port": port,
                                  "payload_sent": False}), now, now))
        _audit(conn, actor_id, "connector.test", connector_id, "success",
               {"result": result["result"], "payload_sent": False})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return result


def remove(conn: sqlite3.Connection, connector_id: str, actor_id: str, confirmed: bool, revalidate: Callable[[sqlite3.Connection], Any] | None = None) -> dict[str, Any]:
    if not confirmed:
        raise PermissionError("explicit_removal_confirmation_required")
    with _lock_for(connector_id):
        row = conn.execute("SELECT version FROM connectors_installed WHERE id=?", (connector_id,)).fetchone()
        if not row:
            raise LookupError("connector_not_installed")
        now = utcnow()
        conn.execute("BEGIN IMMEDIATE")
        try:
            if revalidate:
                revalidate(conn)
            conn.execute("UPDATE connectors_installed SET status='REMOVED',updated_at=? WHERE id=?", (now, connector_id))
            conn.execute("INSERT INTO connector_operations VALUES(?,?,?,?,?,?,?,?)",
                         (str(uuid.uuid4()), connector_id, "remove", "COMPLETED", actor_id,
                          json.dumps({"version": row["version"], "runtime_files_removed": False}), now, now))
            _audit(conn, actor_id, "connector.remove", connector_id, "success", {"runtime_files_removed": False})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return {"id": connector_id, "status": "REMOVED", "runtime_files_removed": False,
                "note": "the built-in module remains part of the signed Debian package"}


def discover(conn: sqlite3.Connection, actor_id: str, cidr: str, ports: list[int], timeout: float = 0.25, revalidate: Callable[[sqlite3.Connection], Any] | None = None) -> dict[str, Any]:
    try:
        network = ipaddress.ip_network(cidr, strict=True)
    except ValueError as exc:
        raise ValueError("invalid_network_cidr") from exc
    if not network.is_private or network.is_loopback or network.is_link_local or network.num_addresses > 256:
        raise ValueError("discovery_requires_private_network_of_at_most_256_addresses")
    if not ports or len(ports) > 16 or any(isinstance(p, bool) or not isinstance(p, int) or not 1 <= p <= 65535 for p in ports):
        raise ValueError("invalid_discovery_ports")
    if max(0, network.num_addresses - 2) * len(set(ports)) > 512:
        raise ValueError("discovery_attempt_limit_exceeded")
    if not 0.05 <= timeout <= 1.0:
        raise ValueError("invalid_discovery_timeout")
    found: list[dict[str, Any]] = []
    # Discovery sockets are also executed by a bounded worker process. The
    # Gateway validates the requested CIDR/ports and persists only transport
    # evidence; it does not open target sockets in the API process.
    from .runtime_manager import ConnectorWorkerRuntime, WorkerRuntimeError
    try:
        with ConnectorWorkerRuntime("gateway-discovery", timeout=3.0) as worker:
            for address in network.hosts():
                for port in sorted(set(ports)):
                    try:
                        probe = worker.call("tcp_probe", {"host": str(address), "port": port,
                                                            "timeout": max(0.1, float(timeout))})
                    except WorkerRuntimeError:
                        # A worker failure fails the scan closed rather than
                        # silently reporting a partial scan as complete.
                        raise RuntimeError("discovery_worker_failed")
                    if probe.get("reachable") is True:
                        found.append({"host": str(address), "port": port, "state": "DETECTED",
                                      "evidence": {"tcp_connect_succeeded": True, "payload_sent": False,
                                                   "protocol_identified": False,
                                                   "executed_by_worker": True}})
    except WorkerRuntimeError as exc:
        raise RuntimeError("discovery_worker_failed") from exc
    ensure_schema(conn)
    now = utcnow()
    conn.execute("BEGIN IMMEDIATE")
    try:
        if revalidate:
            revalidate(conn)
        for item in found:
            evidence = json.dumps(item["evidence"], separators=(",", ":"))
            conn.execute("INSERT INTO discovered_devices(id,host,port,state,first_seen_at,last_seen_at,evidence_json) VALUES(?,?,?,?,?,?,?) "
                         "ON CONFLICT(host,port) DO UPDATE SET state='DETECTED',last_seen_at=excluded.last_seen_at,evidence_json=excluded.evidence_json",
                         (str(uuid.uuid4()), item["host"], item["port"], item["state"], now, now, evidence))
            row = conn.execute("SELECT id FROM discovered_devices WHERE host=? AND port=?", (item["host"], item["port"])).fetchone()
            item["id"] = row["id"]
        _audit(conn, actor_id, "connectors.discovery", cidr, "success",
               {"ports": sorted(set(ports)), "hits": len(found), "payload_sent": False})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"state": "DETECTED", "network": str(network), "hits": found,
            "protocol_identification": "NOT_PERFORMED", "control_commands_sent": False}


def list_discovered(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_schema(conn)
    rows = conn.execute("SELECT * FROM discovered_devices ORDER BY last_seen_at DESC LIMIT 1000").fetchall()
    return [{"id": r["id"], "host": r["host"], "port": r["port"], "state": r["state"],
             "first_seen_at": r["first_seen_at"], "last_seen_at": r["last_seen_at"],
             "evidence": json.loads(r["evidence_json"])} for r in rows]


def capabilities(conn: sqlite3.Connection, discovered_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM discovered_devices WHERE id=?", (discovered_id,)).fetchone()
    if not row:
        raise LookupError("discovered_device_not_found")
    return {"id": discovered_id, "host": row["host"], "port": row["port"], "state": row["state"],
            "capabilities": [{"name": "tcp_reachable", "state": "VERIFIED", "evidence": json.loads(row["evidence_json"])}],
            "protocol_identified": False, "device_capabilities_verified": False,
            "operational": False, "note": "Only TCP transport reachability is verified; device protocol and capabilities are unknown."}
