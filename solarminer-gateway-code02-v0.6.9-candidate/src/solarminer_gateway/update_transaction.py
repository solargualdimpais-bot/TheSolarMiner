"""Fail-closed, filesystem-transactional activation for pre-verified releases.

Signature verification is deliberately delegated to signed_activation; this
module accepts only its VerifiedManifest result. Activation swaps a symlink to
an immutable version directory and retains the previous target for rollback.
The caller must separately verify systemd enforcement and connector health.
"""
from __future__ import annotations
import fcntl, hashlib, json, os, shutil, stat, tempfile, uuid, zipfile
from pathlib import Path
from typing import Callable
from .signed_activation import VerifiedManifest

class UpdateTransactionError(RuntimeError): pass

class AtomicReleaseStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.releases = self.root / "releases"
        self.staging = self.root / "staging"
        self.active = self.root / "active"  # compatibility alias for single-connector tooling
        self.lock_path = self.root / ".update.lock"
        self.journal = self.root / "update-journal.jsonl"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o750)
        self.releases.mkdir(exist_ok=True, mode=0o750)
        self.staging.mkdir(exist_ok=True, mode=0o750)

    def active_path(self, connector_id: str) -> Path:
        if not isinstance(connector_id, str) or not connector_id or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in connector_id):
            raise UpdateTransactionError("invalid_connector_id")
        return self.root / ("active-" + connector_id)

    def _event(self, event: str, **details: object) -> None:
        safe = {k: v for k, v in details.items() if k not in {"secret", "token", "password", "private_key"}}
        fd = os.open(self.journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, (json.dumps({"event": event, **safe}, sort_keys=True) + "\n").encode())
            os.fsync(fd)
        finally: os.close(fd)

    def recover_interrupted(self) -> dict[str, object]:
        """Conservatively reconcile a release-store transaction interrupted by process death.

        This only recovers filesystem pointer/journal state. It does not restart
        systemd services, reconcile the Gateway database, or prove device health.
        """
        events: list[dict[str, object]] = []
        if self.journal.exists():
            for line in self.journal.read_text(encoding="utf-8").splitlines():
                try:
                    event = json.loads(line)
                    if isinstance(event, dict): events.append(event)
                except json.JSONDecodeError:
                    # An incomplete final append is ignored; earlier fsynced lines remain usable.
                    continue
        latest: dict[str, dict[str, object]] = {}
        terminal = {"COMMITTED", "ACTIVATION_FAILED", "ROLLBACK_POINTER_RESTORED"}
        for event in events:
            cid = event.get("connector_id")
            if not isinstance(cid, str): continue
            if event.get("event") == "PREPARED": latest[cid] = event
            elif event.get("event") in terminal:
                prior = latest.get(cid)
                if prior and prior.get("version") == event.get("version"):
                    latest.pop(cid, None)
        actions: list[dict[str, str]] = []
        for cid, prepared in latest.items():
            version = prepared.get("version")
            if not isinstance(version, str): continue
            active = self.active_path(cid)
            if active.exists() and not active.is_symlink():
                actions.append({"connector_id": cid, "action": "BLOCKED_NON_SYMLINK_ACTIVE"})
                continue
            expected = f"releases/{cid}-{version}"
            current = os.readlink(active) if active.is_symlink() else None
            if current == expected:
                previous = prepared.get("previous")
                if previous:
                    previous_path = (self.root / str(previous)).resolve()
                    if self.releases.resolve() not in previous_path.parents or not previous_path.is_dir():
                        actions.append({"connector_id": cid, "action": "BLOCKED_INVALID_PREVIOUS_RELEASE"})
                        continue
                    restore = self.root / (".recover-" + uuid.uuid4().hex)
                    os.symlink(str(previous), restore); os.replace(restore, active)
                else:
                    active.unlink(missing_ok=True)
                dfd = os.open(self.root, os.O_RDONLY); os.fsync(dfd); os.close(dfd)
                self._event("ROLLBACK_POINTER_RESTORED", connector_id=cid, version=version, previous=previous, recovery="process_restart")
                actions.append({"connector_id": cid, "action": "ROLLED_BACK_UNCOMMITTED_POINTER"})
            else:
                self._event("ACTIVATION_FAILED", connector_id=cid, version=version, recovery="no_uncommitted_pointer_detected")
                actions.append({"connector_id": cid, "action": "NO_POINTER_CHANGE"})
        removed = 0
        for child in self.staging.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True); removed += 1
        return {"status": "RECOVERY_COMPLETE", "actions": actions, "staging_directories_removed": removed,
                "scope": "filesystem_pointer_and_journal_only", "service_health_verified": False,
                "database_consistency_verified": False, "power_loss_hardware_tested": False}

    def activate(self, manifest: VerifiedManifest, artifact_path: str | Path,
                 validate: Callable[[Path], bool], fault_at: str | None = None) -> dict[str, object]:
        if not isinstance(manifest, VerifiedManifest) or not manifest.is_verified:
            raise UpdateTransactionError("verified_signed_manifest_required")
        connector_id, version = manifest.get("connector_id"), manifest.get("version")
        if not isinstance(connector_id, str) or not isinstance(version, str) or not connector_id or not version:
            raise UpdateTransactionError("verified_manifest_fields_missing")
        artifact = Path(artifact_path).resolve()
        if not artifact.is_file(): raise UpdateTransactionError("artifact_not_found")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if digest != manifest.get("artifact_sha256"):
            raise UpdateTransactionError("artifact_hash_mismatch")
        release_name = f"{connector_id}-{version}"
        target = self.releases / release_name
        active = self.active_path(connector_id)
        lock_path = self.root / (".update-" + connector_id + ".lock")
        with lock_path.open("a+b") as lock:
            try: fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc: raise UpdateTransactionError("update_already_in_progress") from exc
            if active.exists() and not active.is_symlink():
                raise UpdateTransactionError("active_pointer_not_symlink")
            previous = os.readlink(active) if active.is_symlink() else None
            if previous is not None:
                previous_resolved = (self.root / previous).resolve()
                if self.releases.resolve() not in previous_resolved.parents:
                    raise UpdateTransactionError("active_pointer_outside_release_store")
            stage = Path(tempfile.mkdtemp(prefix="stage-", dir=self.staging))
            self._event("PREPARED", connector_id=connector_id, version=version, artifact_sha256=digest, previous=previous)
            switched = False
            target_created = False
            try:
                payload = stage / "payload"
                payload.mkdir(mode=0o750)
                if not zipfile.is_zipfile(artifact): raise UpdateTransactionError("artifact_must_be_verified_zip")
                with zipfile.ZipFile(artifact) as archive:
                    members = archive.infolist()
                    if not members or len(members) > 10000: raise UpdateTransactionError("archive_member_limit")
                    total_size = sum(item.file_size for item in members)
                    if total_size > 512 * 1024 * 1024: raise UpdateTransactionError("archive_size_limit")
                    for item in members:
                        name = item.filename
                        member = Path(name)
                        mode = (item.external_attr >> 16) & 0xFFFF
                        if member.is_absolute() or ".." in member.parts or not name or "\x00" in name:
                            raise UpdateTransactionError("unsafe_archive_path")
                        if stat.S_ISLNK(mode): raise UpdateTransactionError("archive_symlink_rejected")
                        dest = (payload / member).resolve()
                        if dest != payload.resolve() and payload.resolve() not in dest.parents:
                            raise UpdateTransactionError("archive_path_escape")
                    archive.extractall(payload)
                if fault_at == "staging": raise UpdateTransactionError("injected_staging_failure")
                if validate(payload) is not True:
                    raise UpdateTransactionError("release_validation_failed")
                if fault_at == "validation": raise UpdateTransactionError("injected_validation_failure")
                if target.exists(): raise UpdateTransactionError("release_version_already_exists")
                os.replace(payload, target)
                target_created = True
                dfd = os.open(self.releases, os.O_RDONLY); os.fsync(dfd); os.close(dfd)
                if fault_at == "pre_switch": raise UpdateTransactionError("injected_pre_switch_failure")
                tmp_link = self.root / (".active-" + uuid.uuid4().hex)
                os.symlink(os.path.relpath(target, self.root), tmp_link)
                os.replace(tmp_link, active); switched = True
                dfd = os.open(self.root, os.O_RDONLY); os.fsync(dfd); os.close(dfd)
                self._event("ACTIVATED", connector_id=connector_id, version=version, previous=previous)
                if fault_at == "post_switch": raise UpdateTransactionError("injected_post_switch_failure")
                self._event("COMMITTED", connector_id=connector_id, version=version, previous=previous)
                return {"status": "ACTIVE_POINTER_COMMITTED", "connector_id": connector_id,
                        "version": version, "previous_target": previous,
                        "operational_health_verified": False, "systemd_isolation_verified": False}
            except Exception as exc:
                if switched:
                    if previous:
                        restore = self.root / (".rollback-" + uuid.uuid4().hex)
                        os.symlink(previous, restore); os.replace(restore, active)
                    else:
                        active.unlink(missing_ok=True)
                    dfd = os.open(self.root, os.O_RDONLY); os.fsync(dfd); os.close(dfd)
                    self._event("ROLLBACK_POINTER_RESTORED", connector_id=connector_id, version=version, previous=previous)
                else:
                    self._event("ACTIVATION_FAILED", connector_id=connector_id, version=version, error=type(exc).__name__)
                if target_created and (not active.is_symlink() or active.resolve() != target.resolve()):
                    shutil.rmtree(target, ignore_errors=True)
                    dfd = os.open(self.releases, os.O_RDONLY); os.fsync(dfd); os.close(dfd)
                raise
            finally:
                shutil.rmtree(stage, ignore_errors=True)
