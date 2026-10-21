from __future__ import annotations
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from solarminer_gateway.database_backup import (
    DatabaseBackupError, create_database_backup, restore_database_backup,
)


def make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        conn.execute("INSERT INTO schema_migrations VALUES(3,'2026-01-01T00:00:00Z')")
        conn.execute("PRAGMA user_version=7")
        conn.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO sample(value) VALUES('original')")
        conn.commit()
    finally:
        conn.close()


def test_online_backup_captures_wal_and_metadata_and_restores_data(tmp_path: Path):
    source = tmp_path / "source.db"
    make_db(source)
    # Keep a writer open in WAL mode so the test proves SQLite backup semantics.
    writer = sqlite3.connect(source)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("INSERT INTO sample(value) VALUES('committed-in-wal')")
    writer.commit()
    result = create_database_backup(source, tmp_path / "backups")
    backup = Path(result["backup_path"])
    assert result["integrity_check"] == "ok"
    assert result["database_user_version"] == 7
    assert result["schema_migration_version"] == 3
    assert result["size_bytes"] == backup.stat().st_size
    assert len(result["sha256"]) == 64
    target = tmp_path / "restored.db"
    restored = restore_database_backup(backup, target, offline=True)
    assert restored["integrity_check"] == "ok"
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT value FROM sample ORDER BY id").fetchall() == [("original",), ("committed-in-wal",)]
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    writer.close()


def test_restore_requires_explicit_offline_mode(tmp_path: Path):
    source = tmp_path / "source.db"
    make_db(source)
    backup = create_database_backup(source, tmp_path / "backups")["backup_path"]
    with pytest.raises(DatabaseBackupError, match="offline"):
        restore_database_backup(backup, tmp_path / "target.db")


def test_restore_refuses_existing_wal_sidecar_without_touching_target(tmp_path: Path):
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    make_db(source)
    make_db(target)
    conn = sqlite3.connect(target)
    try:
        conn.execute("PRAGMA journal_mode=DELETE")
    finally:
        conn.close()
    backup = create_database_backup(source, tmp_path / "backups")["backup_path"]
    original_hash = __import__("hashlib").sha256(target.read_bytes()).hexdigest()
    Path(str(target) + "-wal").write_bytes(b"sentinel")
    with pytest.raises(DatabaseBackupError, match="sidecars"):
        restore_database_backup(backup, target, offline=True)
    assert __import__("hashlib").sha256(target.read_bytes()).hexdigest() == original_hash
    assert Path(str(target) + "-wal").read_bytes() == b"sentinel"
    Path(str(target) + "-wal").unlink()
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT value FROM sample").fetchone()[0] == "original"


def test_restore_rejects_backup_hash_mismatch(tmp_path: Path):
    source = tmp_path / "source.db"
    make_db(source)
    result = create_database_backup(source, tmp_path / "backups")
    backup = Path(result["backup_path"])
    backup.write_bytes(backup.read_bytes() + b"tamper")
    with pytest.raises(DatabaseBackupError, match="sha256"):
        restore_database_backup(backup, tmp_path / "target.db", offline=True)


def test_kill9_during_alter_table_rolls_back_transaction(tmp_path: Path):
    db = tmp_path / "migration.db"
    marker = tmp_path / "migration-ready"
    make_db(db)
    script = r'''import sqlite3,sys,time,pathlib
p=pathlib.Path(sys.argv[1]); marker=pathlib.Path(sys.argv[2])
c=sqlite3.connect(p, timeout=5, isolation_level=None)
c.execute('BEGIN IMMEDIATE')
c.execute('ALTER TABLE sample ADD COLUMN migration_probe TEXT')
marker.write_text('alter-applied-uncommitted')
time.sleep(60)
'''
    child = subprocess.Popen([sys.executable, "-c", script, str(db), str(marker)])
    try:
        deadline = time.time() + 5
        while time.time() < deadline and not marker.exists() and child.poll() is None:
            time.sleep(0.02)
        assert marker.exists(), "migration child did not reach uncommitted ALTER TABLE"
        child.kill()  # POSIX Popen.kill uses SIGKILL; isolated temporary DB only.
        child.wait(timeout=5)
    finally:
        if child.poll() is None:
            child.kill(); child.wait(timeout=5)
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        columns = {row[1] for row in conn.execute("PRAGMA table_info(sample)")}
        assert "migration_probe" not in columns
        assert conn.execute("SELECT value FROM sample").fetchone()[0] == "original"


def test_restore_refuses_backup_without_metadata_sidecar(tmp_path: Path):
    source = tmp_path / "source.db"
    make_db(source)
    result = create_database_backup(source, tmp_path / "backups")
    backup = Path(result["backup_path"])
    Path(result["metadata_path"]).unlink()
    with pytest.raises(DatabaseBackupError, match="metadata_missing"):
        restore_database_backup(backup, tmp_path / "target.db", offline=True)
