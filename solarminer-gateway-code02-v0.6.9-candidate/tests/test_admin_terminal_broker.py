import hashlib
import sqlite3
import time

from solarminer_gateway import admin_terminal_broker as broker


def _database(path, *, role="owner", user_status="active", device_status="active",
              association_status="active", revoked_at=None, expires_at=None,
              session_version=1, user_version=1):
    token = "test-owner-bearer-token"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE users(id TEXT PRIMARY KEY, role TEXT, status TEXT, credential_version INTEGER);
            CREATE TABLE devices(id TEXT PRIMARY KEY, status TEXT);
            CREATE TABLE user_devices(user_id TEXT, device_id TEXT, status TEXT);
            CREATE TABLE sessions(token_sha256 TEXT PRIMARY KEY, user_id TEXT, device_id TEXT,
                                  credential_version INTEGER, expires_at INTEGER, revoked_at INTEGER);
        """)
        conn.execute("INSERT INTO users VALUES('user-1', ?, ?, ?)",
                     (role, user_status, user_version))
        conn.execute("INSERT INTO devices VALUES('device-1', ?)", (device_status,))
        conn.execute("INSERT INTO user_devices VALUES('user-1', 'device-1', ?)", (association_status,))
        conn.execute("INSERT INTO sessions VALUES(?, 'user-1', 'device-1', ?, ?, ?)",
                     (hashlib.sha256(token.encode()).hexdigest(), session_version,
                      expires_at if expires_at is not None else int(time.time()) + 600,
                      revoked_at))
    return token


def test_admin_broker_accepts_only_live_owner_session(tmp_path, monkeypatch):
    database = tmp_path / "gateway.db"
    token = _database(database)
    monkeypatch.setattr(broker, "DB_PATH", database)

    assert broker._read_owner(token) == "user-1"
    assert broker._read_owner("wrong-token") is None


def test_admin_broker_rejects_non_owner_or_invalidated_session(tmp_path, monkeypatch):
    cases = [
        {"role": "operator"},
        {"revoked_at": int(time.time())},
        {"expires_at": int(time.time()) - 1},
        {"session_version": 1, "user_version": 2},
        {"user_status": "revoked"},
        {"device_status": "revoked"},
        {"association_status": "revoked"},
    ]
    for index, options in enumerate(cases):
        database = tmp_path / f"gateway-{index}.db"
        token = _database(database, **options)
        monkeypatch.setattr(broker, "DB_PATH", database)
        assert broker._read_owner(token) is None, options
