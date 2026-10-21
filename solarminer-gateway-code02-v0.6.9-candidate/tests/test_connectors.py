from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from solarminer_gateway import app as gateway
from solarminer_gateway import connectors as manager
from solarminer_gateway import connector_plugins

ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "packaging" / "catalog"


@pytest.fixture
def catalog_paths(monkeypatch):
    monkeypatch.setattr(manager, "catalog_paths", lambda: (
        CATALOG_DIR / "catalog.json", CATALOG_DIR / "catalog.sig", CATALOG_DIR / "catalog.pub"))


def connection(path=":memory:"):
    conn = sqlite3.connect(path, timeout=5, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("CREATE TABLE audit(id INTEGER PRIMARY KEY AUTOINCREMENT,occurred_at TEXT NOT NULL,actor_user_id TEXT,action TEXT NOT NULL,target TEXT,outcome TEXT NOT NULL,details_json TEXT NOT NULL);")
    manager.ensure_schema(conn)
    return conn


def test_signed_catalog_and_builtin_hash(catalog_paths):
    catalog = manager.public_catalog()
    assert catalog["signature_verified"] is True
    assert [entry["id"] for entry in catalog["connectors"]] == ["tcp-readonly-probe"]
    entry = catalog["connectors"][0]
    assert entry["sha256"] == hashlib.sha256(Path(connector_plugins.__file__).read_bytes()).hexdigest()
    assert entry["capabilities"]["control"] == []
    assert entry["read_only"] is True


def test_catalog_tampering_fails_closed(tmp_path, monkeypatch, catalog_paths):
    raw = (CATALOG_DIR / "catalog.json").read_bytes()
    sig = (CATALOG_DIR / "catalog.sig").read_bytes()
    pub = (CATALOG_DIR / "catalog.pub").read_bytes()
    cat = tmp_path / "catalog.json"
    sig_path = tmp_path / "catalog.sig"
    pub_path = tmp_path / "catalog.pub"
    cat.write_bytes(raw + b" ")
    sig_path.write_bytes(sig)
    pub_path.write_bytes(pub)
    monkeypatch.setattr(manager, "catalog_paths", lambda: (cat, sig_path, pub_path))
    with pytest.raises(ValueError, match="catalog_signature_or_format_invalid"):
        manager.load_catalog()


def test_install_configure_test_remove_and_audit(catalog_paths, monkeypatch):
    conn = connection()
    with pytest.raises(PermissionError):
        manager.install(conn, "tcp-readonly-probe", "owner-test", False)
    installed = manager.install(conn, "tcp-readonly-probe", "owner-test", True)
    assert installed["status"] == "INSTALLED"
    assert installed["execution_isolated"] is False
    with pytest.raises(PermissionError, match="explicit_update_confirmation_required"):
        manager.update(conn, "tcp-readonly-probe", "owner-test", False)
    updated = manager.update(conn, "tcp-readonly-probe", "owner-test", True)
    assert updated["status"] == "ALREADY_CURRENT"
    configured = manager.configure(conn, "tcp-readonly-probe", "owner-test", {"timeout_seconds": 0.8})
    assert configured["config"]["timeout_seconds"] == 0.8
    with pytest.raises(ValueError, match="unsupported_or_secret_config_field"):
        manager.configure(conn, "tcp-readonly-probe", "owner-test", {"password": "never-store"})

    class FakeWorker:
        def __init__(self, *args, **kwargs): self.connector_id = args[0]
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def call(self, operation, arguments):
            assert operation == "tcp_probe"
            assert arguments["host"] == "192.168.1.12"
            return {"reachable": True, "host": arguments["host"], "port": arguments["port"],
                    "error_type": None, "application_protocol_verified": False,
                    "hardware_commands_sent": False, "payload_sent": False}

    monkeypatch.setattr("solarminer_gateway.runtime_manager.ConnectorWorkerRuntime", FakeWorker)
    result = manager.test_connection(conn, "tcp-readonly-probe", "owner-test", "192.168.1.12", 502)
    assert result["result"] == "TCP_REACHABLE"
    assert result["payload_sent"] is True
    assert result["execution_worker"] is True
    removed = manager.remove(conn, "tcp-readonly-probe", "owner-test", True)
    assert removed["status"] == "REMOVED"
    assert conn.execute("SELECT COUNT(*) FROM audit WHERE outcome='success'").fetchone()[0] == 5
    conn.close()


def test_audit_failure_rolls_back_install(catalog_paths):
    conn = connection()
    conn.execute("CREATE TRIGGER reject_connector_audit BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT,'audit unavailable'); END")
    with pytest.raises(sqlite3.IntegrityError, match="audit unavailable"):
        manager.install(conn, "tcp-readonly-probe", "owner-test", True)
    assert conn.execute("SELECT COUNT(*) FROM connectors_installed").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM connector_operations").fetchone()[0] == 0
    conn.execute("DROP TRIGGER reject_connector_audit")
    def deny(_conn):
        raise RuntimeError("session_revalidation_denied")
    with pytest.raises(RuntimeError, match="session_revalidation_denied"):
        manager.install(conn, "tcp-readonly-probe", "owner-test", True, revalidate=deny)
    assert conn.execute("SELECT COUNT(*) FROM connectors_installed").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM connector_operations").fetchone()[0] == 0
    conn.close()


def test_discovery_is_bounded_and_only_reports_transport(catalog_paths, monkeypatch):
    conn = connection()
    calls = []
    class FakeWorker:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def call(self, operation, arguments):
            assert operation == "tcp_probe"
            calls.append((arguments["host"], arguments["port"]))
            return {"reachable": arguments["host"] == "192.168.5.1", "host": arguments["host"],
                    "port": arguments["port"], "payload_sent": False, "hardware_commands_sent": False}
    monkeypatch.setattr("solarminer_gateway.runtime_manager.ConnectorWorkerRuntime", FakeWorker)
    result = manager.discover(conn, "owner-test", "192.168.5.0/30", [80], 0.1)
    assert len(calls) == 2
    assert result["control_commands_sent"] is False
    assert result["protocol_identification"] == "NOT_PERFORMED"
    assert len(result["hits"]) == 1
    cap = manager.capabilities(conn, result["hits"][0]["id"])
    assert cap["capabilities"][0]["name"] == "tcp_reachable"
    assert cap["device_capabilities_verified"] is False
    with pytest.raises(ValueError, match="discovery_requires_private_network"):
        manager.discover(conn, "owner-test", "8.8.8.0/30", [80])
    with pytest.raises(ValueError, match="discovery_attempt_limit_exceeded"):
        manager.discover(conn, "owner-test", "192.168.0.0/24", list(range(100, 116)))
    conn.close()


def test_public_ip_and_loopback_targets_rejected(monkeypatch):
    with pytest.raises(ValueError, match="private_or_link_local_address_required"):
        connector_plugins.tcp_readonly_probe("8.8.8.8", 443)
    with pytest.raises(ValueError, match="target_address_not_allowed"):
        connector_plugins.tcp_readonly_probe("127.0.0.1", 443)


def test_concurrent_install_is_serialized_and_consistent(tmp_path, catalog_paths):
    db_path = tmp_path / "connectors.db"
    initial = connection(str(db_path)); initial.close()
    barrier = threading.Barrier(3)
    def worker():
        conn = sqlite3.connect(db_path, timeout=10, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        barrier.wait()
        try:
            return manager.install(conn, "tcp-readonly-probe", "owner-test", True)["status"]
        finally:
            conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(worker); b = pool.submit(worker)
        barrier.wait()
        assert a.result(timeout=10) == "INSTALLED"
        assert b.result(timeout=10) == "INSTALLED"
    check = sqlite3.connect(db_path)
    assert check.execute("SELECT COUNT(*) FROM connectors_installed WHERE id='tcp-readonly-probe'").fetchone()[0] == 1
    assert check.execute("SELECT COUNT(*) FROM connector_operations WHERE operation='install' AND phase='COMPLETED'").fetchone()[0] == 2
    check.close()


def test_interrupted_operation_is_marked_for_recovery(catalog_paths):
    conn = connection()
    conn.execute("INSERT INTO connector_operations VALUES(?,?,?,?,?,?,?,?)",
                 ("op-1", "tcp-readonly-probe", "install", "PREPARING", "owner-test", "{}", manager.utcnow(), manager.utcnow()))
    assert manager.recover_incomplete_operations(conn) == 1
    assert conn.execute("SELECT phase FROM connector_operations WHERE id='op-1'").fetchone()[0] == "RECOVERY_REQUIRED"
    conn.close()


def _make_owner(client):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import time
    token = gateway.BOOTSTRAP_PATH.read_text().strip()
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    ts, nonce = int(time.time()), "connector-bootstrap-nonce-0001"
    canonical = f"BOOTSTRAP\nowner2\nAA:BB:CC:DD:EE:02\n{ts}\n{nonce}"
    response = client.post("/api/v1/bootstrap/owner", json={
        "bootstrap_token": token, "username": "owner2", "password": "a-long-passphrase-02",
        "mac": "AA:BB:CC:DD:EE:02", "public_key_pem": public,
        "signature": private.sign(canonical.encode()).hex(), "timestamp": ts, "nonce": nonce})
    assert response.status_code == 201, response.text
    ts, nonce = int(time.time()), "connector-login-nonce-0001"
    canonical = f"LOGIN\nowner2\n{response.json()['device_id']}\n{ts}\n{nonce}"
    login = client.post("/api/v1/auth/login", json={"username":"owner2", "password":"a-long-passphrase-02",
        "device_id":response.json()["device_id"], "timestamp":ts, "nonce":nonce,
        "signature":private.sign(canonical.encode()).hex()})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_api_auth_catalog_install_and_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr(manager, "catalog_paths", lambda: (
        CATALOG_DIR / "catalog.json", CATALOG_DIR / "catalog.sig", CATALOG_DIR / "catalog.pub"))
    monkeypatch.setattr(gateway, "DB_PATH", tmp_path / "gateway.db")
    monkeypatch.setattr(gateway, "BOOTSTRAP_PATH", tmp_path / "bootstrap.token")
    monkeypatch.setattr(gateway, "INSTANCE_MARKER", tmp_path / "initialized.marker")
    with TestClient(gateway.app) as client:
        assert client.get("/api/v1/connectors/catalog").status_code == 401
        headers = _make_owner(client)
        catalog = client.get("/api/v1/connectors/catalog", headers=headers)
        assert catalog.status_code == 200 and catalog.json()["signature_verified"] is True
        installed = client.post("/api/v1/connectors/tcp-readonly-probe/install", headers=headers, json={"confirmed":True})
        assert installed.status_code == 201, installed.text
        listing = client.get("/api/v1/connectors", headers=headers)
        assert listing.status_code == 200 and listing.json()["connectors"][0]["status"] == "INSTALLED"
        update = client.post("/api/v1/connectors/tcp-readonly-probe/update", headers=headers, json={"confirmed":True})
        assert update.status_code == 200 and update.json()["status"] == "ALREADY_CURRENT"
        bad_discovery = client.post("/api/v1/devices/discover", headers=headers, json={"cidr":"8.8.8.0/30", "ports":[80]})
        assert bad_discovery.status_code == 422
