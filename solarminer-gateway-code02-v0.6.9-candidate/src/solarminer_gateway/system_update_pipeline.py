"""Privileged end-to-end updater for verified Debian releases.

The HTTP service only queues an operation. A separate systemd unit performs
activation so restarting solarminer-gateway cannot kill its own updater.
Every non-terminal state is durable and recoverable by the independent timer.
"""
from __future__ import annotations

import hashlib
import json
import os
import fcntl
from contextlib import contextmanager
import re
import shutil
import sqlite3
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database_backup import create_database_backup
from .updates import UpdateValidationError, load_release_key, verify_manifest

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
TERMINAL = {"COMMITTED", "ROLLED_BACK", "FAILED", "RECOVERY_BLOCKED"}
ACTIVE_STATES = {"APPLY_QUEUED", "PRECHECK", "BACKUP_CREATED", "STAGED", "SWITCHED", "SERVICE_RESTARTING", "HEALTH_CHECKING", "ROLLING_BACK"}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PipelineError(RuntimeError):
    pass


def _failure_code(error: Exception) -> str:
    # Preserve concise allowlisted failure reasons so Owner diagnostics can
    # identify the failed step, while excluding arbitrary paths or payloads.
    value = str(error)
    return value[:180] if re.fullmatch(r"[A-Za-z0-9_.:-]{1,180}", value) else type(error).__name__


def _validate_root_owned_not_writable(path_stat: os.stat_result, error_code: str) -> None:
    if path_stat.st_uid != 0 or path_stat.st_mode & 0o022:
        raise PipelineError(error_code)


def _validate_deployment_root_permissions(root_stat: os.stat_result) -> None:
    _validate_root_owned_not_writable(root_stat, "deployment_root_permissions_invalid")


class SystemUpdatePipeline:
    def __init__(self, *, root: str | Path = "/opt/solarminer", data_dir: str | Path | None = None,
                 db_path: str | Path | None = None, public_key: str | Path = "/etc/solarminer/release-pubkey.pem",
                 service: str = "solarminer-gateway.service", recovery_timer: str = "solarminer-recovery.timer",
                 health_url: str = "https://127.0.0.1:8443/api/v1/health", health_timeout: int = 60,
                 runner=subprocess.run, clock=time.monotonic, sleep=time.sleep):
        self.root = Path(root)
        self.data_dir = Path(data_dir or os.environ.get("SOLARMINER_DATA_DIR", "/var/lib/solarminer"))
        self.db_path = Path(db_path or os.environ.get("SOLARMINER_DB_PATH", str(self.data_dir / "gateway.db")))
        self.public_key = Path(public_key)
        self.service = service
        self.recovery_timer = recovery_timer
        self.health_url = health_url
        self.health_timeout = min(max(int(health_timeout), 1), 60)
        self._last_health_diagnostic: dict[str, Any] = {"outcome": "not_run", "attempts": 0}
        self.runner = runner
        self.clock = clock
        self.sleep = sleep
        self.state_path = self.root / "update-state.json"
        self.journal_path = self.root / "update-state.jsonl"
        self.backups = self.root / "backups"
        self.releases = self.root / "releases"
        self.current = self.root / "current"

    def _check_deployment_root_permissions(self) -> None:
        _validate_deployment_root_permissions(self.root.stat())

    @contextmanager
    def _locked(self):
        if self.root.is_symlink():
            raise PipelineError("deployment_root_must_not_be_symlink")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o750)
        self._check_deployment_root_permissions()
        lock_path = self.root / ".update-pipeline.lock"
        if lock_path.is_symlink():
            raise PipelineError("update_pipeline_lock_must_not_be_symlink")
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _run(self, args: list[str], *, timeout: int = 15, check: bool = False) -> subprocess.CompletedProcess:
        try:
            result = self.runner(args, capture_output=True, text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PipelineError(f"command_failed:{Path(args[0]).name}:{type(exc).__name__}") from exc
        if check and result.returncode != 0:
            raise PipelineError(f"command_failed:{Path(args[0]).name}:{result.returncode}")
        return result

    def _record(self, state: str, **details: Any) -> dict[str, Any]:
        if self.state_path.is_symlink() or self.journal_path.is_symlink():
            raise PipelineError("update_state_and_journal_must_not_be_symlinks")
        old = self._read_state() or {}
        record = {**old, **details, "state": state, "updated_at_utc": _utc()}
        self.root.mkdir(parents=True, exist_ok=True, mode=0o750)
        tmp = self.state_path.with_name(".update-state-" + uuid.uuid4().hex + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(record, stream, sort_keys=True, separators=(",", ":"))
                stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
            os.replace(tmp, self.state_path)
            dir_fd = os.open(self.root, os.O_RDONLY)
            try: os.fsync(dir_fd)
            finally: os.close(dir_fd)
            jfd = os.open(self.journal_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                os.write(jfd, (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode())
                os.fsync(jfd)
            finally: os.close(jfd)
        finally:
            tmp.unlink(missing_ok=True)
        op_id = record.get("operation_id")
        if isinstance(op_id, str) and UUID_RE.fullmatch(op_id):
            self._db_state(op_id, state, record)
        return record

    def _read_state(self) -> dict[str, Any] | None:
        if self.state_path.is_symlink():
            raise PipelineError("update_state_must_not_be_symlink")
        if self.journal_path.is_symlink():
            raise PipelineError("update_journal_must_not_be_symlink")
        if not self.state_path.exists():
            return None
        _validate_root_owned_not_writable(self.state_path.stat(), "update_state_permissions_invalid")
        if self.journal_path.exists():
            _validate_root_owned_not_writable(self.journal_path.stat(), "update_journal_permissions_invalid")
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError("update_state_corrupt") from exc
        if not isinstance(value, dict) or not isinstance(value.get("state"), str):
            raise PipelineError("update_state_invalid")
        return value

    def _db_state(self, op_id: str, state: str, record: dict[str, Any]) -> None:
        if self.db_path.is_symlink() or not self.db_path.is_file():
            return
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                row = conn.execute("SELECT details_json FROM update_operations WHERE id=?", (op_id,)).fetchone()
                if not row: return
                details = json.loads(row[0]) if row[0] else {}
                details["pipeline"] = {k: v for k, v in record.items() if k not in {"manifest"}}
                conn.execute("UPDATE update_operations SET state=?,updated_at=?,details_json=? WHERE id=?",
                             (state, int(time.time()), json.dumps(details, separators=(",", ":")), op_id))
        except (sqlite3.Error, json.JSONDecodeError, OSError):
            # The durable root-owned state/journal is authoritative during recovery.
            return

    def _operation(self, op_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        if not UUID_RE.fullmatch(op_id): raise PipelineError("invalid_operation_id")
        if self.db_path.is_symlink() or not self.db_path.is_file(): raise PipelineError("gateway_database_unavailable")
        try:
            with sqlite3.connect(f"file:{self.db_path.resolve().as_posix()}?mode=ro", uri=True, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT * FROM update_operations WHERE id=?", (op_id,)).fetchone()
                if not row: raise PipelineError("update_operation_not_found")
                details = json.loads(row["details_json"])
                if not isinstance(details, dict): raise PipelineError("update_operation_details_invalid")
                return dict(row), details
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise PipelineError("update_operation_unreadable") from exc

    def preflight(self) -> dict[str, Any]:
        if os.geteuid() != 0: raise PipelineError("root_privileges_required")
        if self.root.is_symlink() or self.releases.is_symlink() or self.state_path.is_symlink() or self.journal_path.is_symlink():
            raise PipelineError("deployment_paths_must_not_be_symlinks")
        root_stat, releases_stat = self.root.stat(), self.releases.stat()
        if any(item.st_uid != 0 or item.st_mode & 0o022 for item in (root_stat, releases_stat)):
            raise PipelineError("deployment_directory_permissions_invalid")
        if not self.current.is_symlink(): raise PipelineError("current_release_symlink_missing")
        current_stat = self.current.lstat()
        if current_stat.st_uid != 0: raise PipelineError("current_release_symlink_owner_invalid")
        target = (self.root / os.readlink(self.current)).resolve()
        if self.releases.resolve() not in target.parents or not target.is_dir():
            raise PipelineError("current_release_target_invalid")
        target_stat = target.stat()
        if target_stat.st_uid != 0 or target_stat.st_mode & 0o022:
            raise PipelineError("current_release_permissions_invalid")
        if not (target / "usr/lib/solarminer-gateway/solarminer_gateway/app.py").is_file():
            raise PipelineError("current_release_backend_missing")
        if not (target / "usr/share/solarminer/pwa/index.html").is_file():
            raise PipelineError("current_release_pwa_missing")
        if not (target / "usr/share/solarminer/catalog.json").is_file():
            raise PipelineError("current_release_catalog_missing")
        for unit, expected in ((self.recovery_timer, "active"),):
            result = self._run(["/usr/bin/systemctl", "is-active", unit], timeout=5)
            if result.returncode != 0 or result.stdout.strip() != expected:
                raise PipelineError("independent_recovery_timer_not_active")
        if self.public_key.is_symlink() or not self.public_key.is_file():
            raise PipelineError("release_public_key_missing_or_symlink")
        key_stat = self.public_key.stat()
        if key_stat.st_uid != 0 or key_stat.st_mode & 0o022:
            raise PipelineError("release_public_key_permissions_invalid")
        apply_units = (Path("/etc/systemd/system/solarminer-update-apply@.service"),
                       Path("/lib/systemd/system/solarminer-update-apply@.service"),
                       Path("/usr/lib/systemd/system/solarminer-update-apply@.service"))
        if not any(unit.is_file() and not unit.is_symlink() for unit in apply_units):
            raise PipelineError("independent_apply_unit_missing")
        if not self.db_path.is_file() or self.db_path.is_symlink(): raise PipelineError("gateway_database_unavailable")
        tls_cert = self.data_dir / "server.crt"
        if tls_cert.is_symlink() or not tls_cert.is_file(): raise PipelineError("gateway_tls_certificate_missing_or_symlink")
        return {"status": "ready", "current_target": os.readlink(self.current), "recovery_timer": "active",
                "health_check_seconds": self.health_timeout, "database": str(self.db_path)}

    def _verified_artifact(self, op_id: str, row: dict[str, Any], details: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
        package_raw = details.get("package_path")
        if not isinstance(package_raw, str): raise PipelineError("verified_package_path_missing")
        package = Path(package_raw)
        raw_verified_dir = self.data_dir / "releases" / "verified"
        if self.data_dir.is_symlink() or (self.data_dir / "releases").is_symlink() or raw_verified_dir.is_symlink():
            raise PipelineError("verified_package_directory_must_not_be_symlink")
        verified_dir = raw_verified_dir.resolve()
        if package.is_symlink() or not package.is_file() or package.resolve().parent != verified_dir:
            raise PipelineError("verified_package_path_invalid")
        sidecar = package.with_suffix(package.suffix + ".manifest.json")
        if sidecar.is_symlink() or not sidecar.is_file(): raise PipelineError("signed_manifest_sidecar_missing")
        try: manifest = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise PipelineError("signed_manifest_sidecar_invalid") from exc
        manifest_path = details.get("manifest_path")
        if manifest_path is not None and Path(str(manifest_path)).resolve() != sidecar.resolve():
            raise PipelineError("signed_manifest_path_mismatch")
        key = load_release_key(self.public_key)
        installed_version = str(row.get("installed_version") or "")
        verified = verify_manifest(manifest, key, installed_version)
        digest = _sha256(package)
        if digest != verified["sha256"] or package.stat().st_size != verified["package_size"]:
            raise PipelineError("verified_package_digest_mismatch")
        if package.name != str(manifest.get("package_name")) + ".verified":
            raise PipelineError("verified_package_name_manifest_mismatch")
        if manifest.get("version") != row.get("target_version"):
            raise PipelineError("manifest_target_version_mismatch")
        dpkg_version = self._run(["/usr/bin/dpkg-deb", "--field", str(package), "Version"], timeout=10, check=True).stdout.strip()
        architecture = self._run(["/usr/bin/dpkg-deb", "--field", str(package), "Architecture"], timeout=10, check=True).stdout.strip()
        if dpkg_version != manifest["version"]: raise PipelineError("package_version_manifest_mismatch")
        host_arch = self._run(["/usr/bin/dpkg", "--print-architecture"], timeout=5, check=True).stdout.strip()
        if architecture not in {"all", host_arch}: raise PipelineError("package_architecture_mismatch")
        depends = self._run(["/usr/bin/dpkg-deb", "--field", str(package), "Depends"], timeout=10, check=True).stdout.strip()
        dependencies = []
        for item in depends.split(","):
            match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9.+:-]*)(?:\s*\((<<|<=|=|>=|>>)\s*([^)]+)\))?", item)
            if match: dependencies.append((match.group(1), match.group(2), match.group(3)))
        for dependency, operator, required_version in dependencies:
            installed = self._run(["/usr/bin/dpkg-query", "-W", "-f=${db:Status-Status}", dependency], timeout=5)
            if installed.returncode != 0 or installed.stdout.strip() != "installed":
                raise PipelineError("package_dependency_not_installed:" + dependency)
            if operator and required_version:
                actual = self._run(["/usr/bin/dpkg-query", "-W", "-f=${Version}", dependency], timeout=5, check=True).stdout.strip()
                compared = self._run(["/usr/bin/dpkg", "--compare-versions", actual, operator, required_version.strip()], timeout=5)
                if compared.returncode != 0:
                    raise PipelineError("package_dependency_version_mismatch:" + dependency)
        return package, manifest, digest

    def enqueue(self, op_id: str) -> dict[str, Any]:
        with self._locked():
            return self._enqueue_locked(op_id)

    def _enqueue_locked(self, op_id: str) -> dict[str, Any]:
        row, _details = self._operation(op_id)
        if row["state"] != "VERIFIED": raise PipelineError("update_operation_not_verified")
        self.preflight()
        # Persist the queue state before systemd can start the independent unit.
        unit = f"solarminer-update-apply@{op_id}.service"
        self._record("APPLY_QUEUED", operation_id=op_id, target_version=row["target_version"],
                     previous_target=os.readlink(self.current), unit=unit, health_timeout_seconds=self.health_timeout)
        try:
            self._run(["/usr/bin/systemctl", "start", "--no-block", unit], timeout=8, check=True)
        except PipelineError:
            self._record("FAILED", operation_id=op_id, target_version=row["target_version"],
                         previous_target=os.readlink(self.current), failure="apply_unit_start_failed")
            raise
        return {"status": "APPLY_QUEUED", "operation_id": op_id, "target_version": row["target_version"],
                "status_url": "/api/v1/system/update/status", "health_check_seconds": self.health_timeout}

    def _health(self, expected_package_version: str | None, seconds: int) -> bool:
        deadline = self.clock() + min(max(seconds, 1), 60)
        attempts = 0
        diagnostic: dict[str, Any] = {"outcome": "no_response", "attempts": 0,
                                      "expected_package_version": expected_package_version}
        # Validate the loopback TLS endpoint against the Gateway's provisioned
        # certificate instead of silently disabling TLS verification.
        context = ssl.create_default_context(cafile=str(self.data_dir / "server.crt"))
        while self.clock() < deadline:
            attempts += 1
            try:
                req = urllib.request.Request(self.health_url, headers={"Cache-Control": "no-cache", "Connection": "close"})
                with urllib.request.urlopen(req, timeout=3, context=context) as response:
                    status_code = int(response.status)
                    if status_code != 200:
                        diagnostic = {"outcome": "http_status_not_ok", "http_status": status_code}
                    else:
                        body = json.loads(response.read(65536))
                        reported_version = body.get("package_version") if isinstance(body, dict) else None
                        if (isinstance(body, dict) and body.get("status") == "ok"
                                and (expected_package_version is None or reported_version == expected_package_version)):
                            self._last_health_diagnostic = {
                                "outcome": "healthy", "attempts": attempts,
                                "expected_package_version": expected_package_version,
                                "reported_package_version": reported_version,
                            }
                            return True
                        if not isinstance(body, dict) or body.get("status") != "ok":
                            diagnostic = {"outcome": "health_payload_not_ok", "http_status": status_code}
                        else:
                            diagnostic = {"outcome": "package_version_mismatch", "http_status": status_code,
                                          "reported_package_version": reported_version}
            except urllib.error.HTTPError as exc:
                diagnostic = {"outcome": "http_error", "http_status": int(exc.code)}
            except urllib.error.URLError as exc:
                reason = getattr(exc, "reason", None)
                if isinstance(reason, ssl.SSLError):
                    diagnostic = {"outcome": "tls_error", "error_type": type(reason).__name__}
                elif isinstance(reason, TimeoutError):
                    diagnostic = {"outcome": "timeout", "error_type": type(reason).__name__}
                else:
                    diagnostic = {"outcome": "connection_error", "reason_type": type(reason).__name__}
            except ssl.SSLError as exc:
                diagnostic = {"outcome": "tls_error", "error_type": type(exc).__name__}
            except TimeoutError as exc:
                diagnostic = {"outcome": "timeout", "error_type": type(exc).__name__}
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                outcome = "invalid_health_json" if isinstance(exc, json.JSONDecodeError) else "endpoint_error"
                diagnostic = {"outcome": outcome, "error_type": type(exc).__name__}
            self.sleep(min(2, max(0, deadline - self.clock())))
        self._last_health_diagnostic = {
            **diagnostic, "attempts": attempts,
            "expected_package_version": expected_package_version,
        }
        return False

    def _switch(self, target: Path) -> None:
        if self.current.exists() and not self.current.is_symlink(): raise PipelineError("current_pointer_not_symlink")
        rel = os.path.relpath(target, self.root)
        tmp = self.root / (".current-next-" + uuid.uuid4().hex)
        os.symlink(rel, tmp)
        os.replace(tmp, self.current)
        fd = os.open(self.root, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)

    def _restore_db(self, backup_path: Path) -> None:
        # Caller must stop the service and verify it is inactive first.
        result = self._run(["/usr/bin/systemctl", "is-active", self.service], timeout=5)
        if result.stdout.strip() in {"active", "deactivating"}:
            raise PipelineError("database_restore_refused_service_still_active")
        if backup_path.is_symlink() or not backup_path.is_file(): raise PipelineError("database_backup_missing")
        meta_path = backup_path.with_suffix(backup_path.suffix + ".json")
        if meta_path.is_symlink() or not meta_path.is_file(): raise PipelineError("database_backup_metadata_missing_or_symlink")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if (meta.get("sha256") != _sha256(backup_path) or meta.get("integrity_check") != "ok"
                or meta.get("size_bytes") != backup_path.stat().st_size):
            raise PipelineError("database_backup_integrity_failed")
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(self.db_path) + suffix)
            if sidecar.is_symlink(): raise PipelineError("database_sidecar_symlink_rejected")
            sidecar.unlink(missing_ok=True)
        tmp = self.db_path.with_name("." + self.db_path.name + ".rollback-" + uuid.uuid4().hex)
        shutil.copyfile(backup_path, tmp)
        os.chmod(tmp, 0o600)
        with tmp.open("rb+") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        with sqlite3.connect(tmp) as conn:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok": raise PipelineError("restored_database_integrity_failed")
            user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            migration_version = 0
            if "schema_migrations" in tables:
                migration_version = int(conn.execute("SELECT COALESCE(MAX(version),0) FROM schema_migrations").fetchone()[0])
        if (user_version, migration_version) != (meta.get("database_user_version"), meta.get("schema_migration_version")):
            raise PipelineError("restored_database_schema_version_mismatch")
        os.replace(tmp, self.db_path)
        dir_fd = os.open(self.db_path.parent, os.O_RDONLY)
        try: os.fsync(dir_fd)
        finally: os.close(dir_fd)
        os.chown(self.db_path, self._uid("solarminer"), self._gid("solarminer"))
        for suffix in ("-wal", "-shm"):
            Path(str(self.db_path) + suffix).unlink(missing_ok=True)

    @staticmethod
    def _uid(name: str) -> int:
        import pwd
        return pwd.getpwnam(name).pw_uid

    @staticmethod
    def _gid(name: str) -> int:
        import grp
        return grp.getgrnam(name).gr_gid

    def apply(self, op_id: str) -> dict[str, Any]:
        with self._locked():
            try:
                return self._apply_locked(op_id)
            except Exception as exc:
                # Fail closed for errors before the activation/rollback block
                # (e.g. signature, package metadata, or backup creation failure).
                try:
                    state = self._read_state() or {}
                    if state.get("operation_id") == op_id and state.get("state") not in TERMINAL:
                        self._record("FAILED", operation_id=op_id, target_version=state.get("target_version"),
                                     previous_target=state.get("previous_target"), backup_path=state.get("backup_path"),
                                     failure=_failure_code(exc), finished_at_utc=_utc())
                except Exception:
                    pass
                raise

    def _apply_locked(self, op_id: str) -> dict[str, Any]:
        if os.geteuid() != 0: raise PipelineError("root_privileges_required")
        self._last_health_diagnostic = {"outcome": "not_run", "attempts": 0}
        row, details = self._operation(op_id)
        if row["state"] not in {"VERIFIED", "APPLY_QUEUED"}: raise PipelineError("update_operation_not_verified")
        self.preflight()
        package, manifest, digest = self._verified_artifact(op_id, row, details)
        previous_target = os.readlink(self.current)
        previous_path = (self.root / previous_target).resolve()
        if self.releases.resolve() not in previous_path.parents or not previous_path.is_dir(): raise PipelineError("previous_release_target_invalid")
        release_name = str(manifest["version"])
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+~_-]{0,63}", release_name): raise PipelineError("release_version_invalid")
        target = self.releases / release_name
        if target.exists() or target.is_symlink(): raise PipelineError("release_version_already_exists")
        self._record("PRECHECK", operation_id=op_id, target_version=release_name, previous_target=previous_target,
                     package_sha256=digest, health_timeout_seconds=60)
        backup = create_database_backup(self.db_path, self.backups)
        backup_path = Path(backup["backup_path"])
        self._record("BACKUP_CREATED", operation_id=op_id, target_version=release_name, previous_target=previous_target,
                     package_sha256=digest, backup_path=str(backup_path), backup_sha256=backup["sha256"],
                     database_user_version=backup["database_user_version"], schema_migration_version=backup["schema_migration_version"],
                     health_timeout_seconds=60)
        stage = self.releases / (".stage-" + uuid.uuid4().hex)
        stage.mkdir(mode=0o700)
        try:
            self._run(["/usr/bin/dpkg-deb", "--extract", str(package), str(stage)], timeout=60, check=True)
            module_dir = stage / "usr/lib/solarminer-gateway/solarminer_gateway"
            if not module_dir.is_dir() or not (module_dir / "app.py").is_file(): raise PipelineError("release_payload_incomplete")
            pwa_dir = stage / "usr/share/solarminer/pwa"
            if not pwa_dir.is_dir() or not (pwa_dir / "index.html").is_file() or not (pwa_dir / "manifest.webmanifest").is_file():
                raise PipelineError("release_pwa_payload_incomplete")
            for catalog_file in ("catalog.json", "catalog.sig", "catalog.pub"):
                if not (stage / "usr/share/solarminer" / catalog_file).is_file():
                    raise PipelineError("release_catalog_payload_incomplete")
            # Only a verified signed package can be extracted. Stage is same filesystem as releases/current.
            os.chmod(stage, 0o755)
            os.replace(stage, target)
            self._record("STAGED", operation_id=op_id, target_version=release_name, previous_target=previous_target,
                         new_target=os.path.relpath(target, self.root), backup_path=str(backup_path), package_sha256=digest,
                         health_timeout_seconds=60)
            self._switch(target)
            self._record("SWITCHED", operation_id=op_id, target_version=release_name, previous_target=previous_target,
                         new_target=os.path.relpath(target, self.root), backup_path=str(backup_path), package_sha256=digest,
                         health_timeout_seconds=60)
            self._record("SERVICE_RESTARTING", operation_id=op_id, target_version=release_name, previous_target=previous_target,
                         new_target=os.path.relpath(target, self.root), backup_path=str(backup_path), package_sha256=digest,
                         health_timeout_seconds=60)
            self._run(["/usr/bin/systemctl", "restart", self.service], timeout=20, check=True)
            self._record("HEALTH_CHECKING", operation_id=op_id, target_version=release_name, previous_target=previous_target,
                         new_target=os.path.relpath(target, self.root), backup_path=str(backup_path), package_sha256=digest,
                         health_timeout_seconds=60)
            if not self._health(release_name, 60):
                raise PipelineError("new_release_health_check_failed_after_60s")
            self._record("COMMITTED", operation_id=op_id, target_version=release_name, previous_target=previous_target,
                         new_target=os.path.relpath(target, self.root), backup_path=str(backup_path), package_sha256=digest,
                         health_timeout_seconds=60, health_check="passed", finished_at_utc=_utc())
            return {"status": "COMMITTED", "operation_id": op_id, "version": release_name, "backup_path": str(backup_path)}
        except Exception as exc:
            failed_health_diagnostic = dict(self._last_health_diagnostic)
            current_state = self._read_state() or {}
            self._record("ROLLING_BACK", operation_id=op_id, target_version=release_name, previous_target=previous_target,
                         new_target=os.path.relpath(target, self.root) if target.exists() else None,
                         backup_path=str(backup_path), failure=_failure_code(exc), health_timeout_seconds=60,
                         health_diagnostic=dict(self._last_health_diagnostic))
            try:
                self._run(["/usr/bin/systemctl", "stop", self.service], timeout=15, check=True)
                self._switch(previous_path)
                self._restore_db(backup_path)
                self._run(["/usr/bin/systemctl", "start", self.service], timeout=20, check=True)
                if not self._health(str(row["installed_version"]), 60):
                    raise PipelineError("previous_release_health_check_failed_after_60s")
                self._record("ROLLED_BACK", operation_id=op_id, target_version=release_name, previous_target=previous_target,
                             backup_path=str(backup_path), failure=_failure_code(exc),
                             health_diagnostic=failed_health_diagnostic,
                             rollback_health_diagnostic=dict(self._last_health_diagnostic),
                             rollback_health_check="passed", finished_at_utc=_utc())
                return {"status": "ROLLED_BACK", "operation_id": op_id, "reason": type(exc).__name__}
            except Exception as rollback_exc:
                self._record("RECOVERY_BLOCKED", operation_id=op_id, target_version=release_name, previous_target=previous_target,
                             backup_path=str(backup_path), failure=_failure_code(exc), rollback_failure=_failure_code(rollback_exc),
                             health_diagnostic=failed_health_diagnostic,
                             rollback_health_diagnostic=dict(self._last_health_diagnostic), finished_at_utc=_utc())
                raise PipelineError("update_failed_and_rollback_requires_manual_recovery") from rollback_exc

    def recover(self) -> dict[str, Any]:
        # Gateway startup requires the recovery oneshot. During an online
        # update, the apply unit itself restarts Gateway while holding this
        # pipeline lock. Check whether that owner is still active before
        # acquiring the lock; otherwise Gateway startup waits for recovery,
        # while recovery waits for the updater, deadlocking the health check.
        record = self._read_state()
        op_id = record.get("operation_id") if isinstance(record, dict) else None
        if (record and record.get("state") in ACTIVE_STATES
                and isinstance(op_id, str) and UUID_RE.fullmatch(op_id)):
            unit_status = self._run(
                ["/usr/bin/systemctl", "is-active", f"solarminer-update-apply@{op_id}.service"], timeout=5
            )
            if unit_status.stdout.strip() in {"active", "activating", "deactivating"}:
                return {"status": "update_unit_active", "operation_id": op_id,
                        "state": record.get("state")}
        with self._locked():
            return self._recover_locked()

    def rollback_committed(self) -> dict[str, Any]:
        """Revert only the active release to the previously active, signature-validated release."""
        if os.geteuid() != 0:
            raise PipelineError("root_privileges_required")
        with self._locked():
            record = self._read_state()
            if not record or record.get("state") != "COMMITTED":
                return {"status": "skipped", "reason": "no_committed_release_to_rollback"}
            current_target = record.get("new_target")
            previous_target = record.get("previous_target")
            backup_raw = record.get("backup_path")
            if not all(isinstance(value, str) and value for value in (current_target, previous_target, backup_raw)):
                raise PipelineError("committed_rollback_metadata_missing")
            if not self.current.is_symlink() or os.readlink(self.current) != current_target:
                return {"status": "skipped", "reason": "active_release_does_not_match_update"}
            previous = (self.root / previous_target).resolve()
            if self.releases.resolve() not in previous.parents or not previous.is_dir():
                raise PipelineError("recovery_previous_release_invalid")
            previous_version = previous.name
            with sqlite3.connect(f"file:{self.db_path.resolve().as_posix()}?mode=ro", uri=True, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                prior = conn.execute(
                    "SELECT * FROM update_operations WHERE target_version=? AND state='COMMITTED' "
                    "ORDER BY updated_at DESC LIMIT 1", (previous_version,)
                ).fetchone()
            if not prior:
                return {"status": "skipped", "reason": "previous_release_has_no_verified_success_record"}
            prior_row = dict(prior)
            prior_details = json.loads(prior_row.get("details_json") or "{}")
            prior_pipeline = prior_details.get("pipeline") if isinstance(prior_details, dict) else None
            if not isinstance(prior_pipeline, dict) or prior_pipeline.get("health_check") != "passed":
                return {"status": "skipped", "reason": "previous_release_health_was_not_attested"}
            _package, prior_manifest, _digest = self._verified_artifact(prior_row["id"], prior_row, prior_details)
            if prior_manifest.get("version") != previous_version:
                raise PipelineError("previous_release_signature_version_mismatch")
            backup = Path(backup_raw)
            if backup.is_symlink() or self.backups.resolve() not in backup.resolve().parents or not backup.is_file():
                raise PipelineError("recovery_backup_path_invalid")
            self._record("ROLLING_BACK", operation_id=record.get("operation_id"),
                         recovery="watchdog_persistent_local_health_failure",
                         rollback_reason="persistent_local_health_failure")
            return self._recover_locked()

    def _recover_locked(self) -> dict[str, Any]:
        if os.geteuid() != 0: raise PipelineError("root_privileges_required")
        # Preserve recovery of the pre-existing connector release journal as well.
        from .deployment_recovery import DeploymentReleaseSwitch
        connector_recovery = DeploymentReleaseSwitch(self.root).recover_pending()
        record = self._read_state()
        # RECOVERY_BLOCKED is visible as a terminal result to the Owner, but
        # it must remain retryable by the independent recovery service. A
        # transient stop/start or health-check failure must not permanently
        # disable restoration of the validated previous release and DB backup.
        if not record or (record.get("state") in TERMINAL and record.get("state") != "RECOVERY_BLOCKED"):
            if record and isinstance(record.get("operation_id"), str) and record.get("state") in TERMINAL:
                self._db_state(record["operation_id"], record["state"], record)
            return {"status": "clean", "state": record.get("state") if record else None,
                    "connector_recovery": connector_recovery}
        op_id = record.get("operation_id")
        # The Gateway service restart is part of the update transaction. Its
        # Requires= recovery unit runs during that restart, so recovery must
        # not mistake any live apply stage for a process that died. If the
        # apply unit is still active, let it finish its own health check or
        # rollback; the boot/timer recovery will retry after the unit exits.
        if record.get("state") in ACTIVE_STATES and isinstance(op_id, str) and UUID_RE.fullmatch(op_id):
            unit_status = self._run(["/usr/bin/systemctl", "is-active", f"solarminer-update-apply@{op_id}.service"], timeout=5)
            if unit_status.stdout.strip() in {"active", "activating", "deactivating"}:
                return {"status": "update_unit_active", "operation_id": op_id, "state": record.get("state"),
                        "connector_recovery": connector_recovery}
        if not isinstance(op_id, str) or not UUID_RE.fullmatch(op_id): raise PipelineError("recovery_operation_id_invalid")
        backup_raw, previous_raw = record.get("backup_path"), record.get("previous_target")
        if not isinstance(previous_raw, str): raise PipelineError("recovery_previous_target_missing")
        if record.get("state") == "RECOVERY_BLOCKED" and not isinstance(backup_raw, str):
            raise PipelineError("recovery_blocked_database_backup_missing")
        if isinstance(backup_raw, str):
            backup_candidate = Path(backup_raw)
            if backup_candidate.is_symlink() or self.backups.resolve() not in backup_candidate.resolve().parents:
                raise PipelineError("recovery_backup_path_invalid")
        previous = (self.root / previous_raw).resolve()
        if self.releases.resolve() not in previous.parents or not previous.is_dir(): raise PipelineError("recovery_previous_release_invalid")
        self._record("ROLLING_BACK", operation_id=op_id, previous_target=previous_raw,
                     backup_path=backup_raw, recovery="boot_or_timer_recovery")
        active_result = self._run(["/usr/bin/systemctl", "is-active", self.service], timeout=5)
        service_was_active = active_result.returncode == 0 and active_result.stdout.strip() == "active"
        if service_was_active:
            self._run(["/usr/bin/systemctl", "stop", self.service], timeout=15, check=True)
        self._switch(previous)
        if isinstance(backup_raw, str): self._restore_db(Path(backup_raw))
        if service_was_active:
            self._run(["/usr/bin/systemctl", "start", self.service], timeout=20, check=True)
        row, _ = self._operation(op_id)
        if service_was_active and not self._health(str(row["installed_version"]), 60):
            self._record("RECOVERY_BLOCKED", operation_id=op_id, previous_target=previous_raw,
                         backup_path=backup_raw, recovery="previous_release_health_check_failed")
            raise PipelineError("recovery_previous_release_health_check_failed")
        self._record("ROLLED_BACK", operation_id=op_id, previous_target=previous_raw,
                     backup_path=backup_raw, recovery="boot_or_timer_recovery",
                     rollback_health_check="passed" if service_was_active else "pending_systemd_start")
        return {"status": "recovered", "operation_id": op_id, "state": "ROLLED_BACK",
                "connector_recovery": connector_recovery}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="SolarMiner privileged update pipeline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight", action="store_true")
    group.add_argument("--enqueue", metavar="OPERATION_ID")
    group.add_argument("--operation", metavar="OPERATION_ID")
    group.add_argument("--recover", action="store_true")
    group.add_argument("--rollback-committed", action="store_true")
    args = parser.parse_args()
    try:
        pipeline = SystemUpdatePipeline()
        if args.preflight: result = pipeline.preflight()
        elif args.enqueue: result = pipeline.enqueue(args.enqueue)
        elif args.operation: result = pipeline.apply(args.operation)
        elif args.rollback_committed: result = pipeline.rollback_committed()
        else: result = pipeline.recover()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (PipelineError, UpdateValidationError, OSError, ValueError, sqlite3.Error, KeyError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)[:180]}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
