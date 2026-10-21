"""Consistent SQLite backup and offline restore helpers for CODE02.

Backups use SQLite's online backup API, so committed WAL contents are included.
Restoration is intentionally offline-only: callers must stop all writers first.
The helper refuses symlink targets and lingering WAL/SHM sidecars rather than
silently replacing a database that may still be in use.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
from typing import Any


class DatabaseBackupError(RuntimeError):
    """A backup or restore could not be proven safe."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_integrity(conn: sqlite3.Connection, label: str) -> None:
    row = conn.execute("PRAGMA integrity_check").fetchone()
    if not row or row[0] != "ok":
        raise DatabaseBackupError(f"{label}_integrity_check_failed")


def _schema_metadata(conn: sqlite3.Connection) -> tuple[int, int]:
    user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    migration_version = 0
    if "schema_migrations" in tables:
        row = conn.execute("SELECT COALESCE(MAX(version),0) FROM schema_migrations").fetchone()
        migration_version = int(row[0] or 0)
    return user_version, migration_version


def create_database_backup(source_path: str | Path, backup_dir: str | Path) -> dict[str, Any]:
    """Create a consistent, integrity-checked SQLite backup plus metadata sidecar."""
    source = Path(source_path)
    destination = Path(backup_dir)
    if source.is_symlink() or not source.is_file():
        raise DatabaseBackupError("source_database_missing_or_symlink")
    if destination.is_symlink():
        raise DatabaseBackupError("backup_directory_must_not_be_symlink")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(destination, 0o700)
    backup_id = uuid.uuid4().hex
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    final_path = destination / f"gateway-{timestamp.replace(':', '').replace('-', '')}-{backup_id[:8]}.sqlite3"
    fd, temporary_name = tempfile.mkstemp(prefix=".backup-", suffix=".sqlite3.tmp", dir=destination)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with closing(sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True, timeout=10)) as src:
            src.execute("PRAGMA busy_timeout=10000")
            _check_integrity(src, "source")
            user_version, migration_version = _schema_metadata(src)
            with closing(sqlite3.connect(temporary, timeout=10)) as dst:
                src.backup(dst)
                _check_integrity(dst, "backup")
                copied_user_version, copied_migration_version = _schema_metadata(dst)
                if (copied_user_version, copied_migration_version) != (user_version, migration_version):
                    raise DatabaseBackupError("backup_schema_version_mismatch")
                dst.commit()
        os.chmod(temporary, 0o600)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, final_path)
        dir_fd = os.open(destination, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        metadata = {
            "format_version": 1,
            "backup_id": backup_id,
            "created_at_utc": timestamp,
            "source_name": source.name,
            "database_user_version": user_version,
            "schema_migration_version": migration_version,
            "integrity_check": "ok",
            "size_bytes": final_path.stat().st_size,
            "sha256": _sha256(final_path),
            "backup_path": final_path.name,
        }
        metadata_path = final_path.with_suffix(final_path.suffix + ".json")
        metadata_tmp = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
        metadata_tmp.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(metadata_tmp, 0o600)
        with metadata_tmp.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(metadata_tmp, metadata_path)
        return {**metadata, "backup_path": str(final_path), "metadata_path": str(metadata_path)}
    except Exception:
        temporary.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        final_path.with_suffix(final_path.suffix + ".json").unlink(missing_ok=True)
        final_path.with_suffix(final_path.suffix + ".json.tmp").unlink(missing_ok=True)
        raise


def restore_database_backup(backup_path: str | Path, target_path: str | Path, *, offline: bool = False) -> dict[str, Any]:
    """Restore a validated backup atomically. Requires explicit offline=True.

    Stop the Gateway and every process that could access the target DB before
    calling this function. Existing -wal/-shm files cause a fail-closed refusal.
    """
    if offline is not True:
        raise DatabaseBackupError("restore_requires_explicit_offline_mode")
    backup = Path(backup_path)
    target = Path(target_path)
    if backup.is_symlink() or not backup.is_file():
        raise DatabaseBackupError("backup_missing_or_symlink")
    if target.is_symlink():
        raise DatabaseBackupError("restore_target_must_not_be_symlink")
    sidecars = (Path(str(target) + "-wal"), Path(str(target) + "-shm"))
    if any(path.exists() or path.is_symlink() for path in sidecars):
        raise DatabaseBackupError("restore_target_has_sqlite_sidecars_stop_service_and_checkpoint_first")
    metadata_path = backup.with_suffix(backup.suffix + ".json")
    if metadata_path.is_symlink() or not metadata_path.is_file():
        raise DatabaseBackupError("backup_metadata_missing_or_symlink")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatabaseBackupError("backup_metadata_invalid") from exc
    if not isinstance(metadata, dict) or metadata.get("format_version") != 1 or metadata.get("integrity_check") != "ok":
        raise DatabaseBackupError("backup_metadata_contract_invalid")
    if metadata.get("sha256") != _sha256(backup):
        raise DatabaseBackupError("backup_sha256_mismatch")
    if metadata.get("size_bytes") != backup.stat().st_size:
        raise DatabaseBackupError("backup_size_mismatch")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.parent.is_symlink():
        raise DatabaseBackupError("restore_target_parent_must_not_be_symlink")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.restore-", suffix=".tmp", dir=target.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with closing(sqlite3.connect(f"file:{backup.resolve().as_posix()}?mode=ro", uri=True, timeout=10)) as src:
            _check_integrity(src, "restore_source")
            source_user_version, source_migration_version = _schema_metadata(src)
            with closing(sqlite3.connect(temporary, timeout=10)) as dst:
                src.backup(dst)
                _check_integrity(dst, "restored_candidate")
                candidate_versions = _schema_metadata(dst)
                if candidate_versions != (source_user_version, source_migration_version):
                    raise DatabaseBackupError("restore_schema_version_mismatch")
                if metadata and (metadata.get("database_user_version"), metadata.get("schema_migration_version")) != candidate_versions:
                    raise DatabaseBackupError("backup_metadata_schema_version_mismatch")
                dst.commit()
        os.chmod(temporary, 0o600)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        dir_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        with closing(sqlite3.connect(target, timeout=10)) as restored:
            _check_integrity(restored, "restored_database")
            restored_versions = _schema_metadata(restored)
        return {"status": "restored", "target_path": str(target), "integrity_check": "ok",
                "database_user_version": restored_versions[0], "schema_migration_version": restored_versions[1],
                "sha256": _sha256(target), "size_bytes": target.stat().st_size}
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
