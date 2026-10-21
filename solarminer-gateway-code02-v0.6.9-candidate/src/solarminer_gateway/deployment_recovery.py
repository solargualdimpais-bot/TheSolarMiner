"""Crash-recoverable atomic release pointer switch primitives.

This module is deliberately separate from the public update API. A production
updater must additionally stage/verify a complete release, stop or coordinate
services, back up/migrate SQLite, run health checks and install an independent
recovery unit before activation may be enabled.
"""
from __future__ import annotations
import json
import os
import uuid
import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator


class DeploymentRecoveryError(RuntimeError):
    pass


class DeploymentReleaseSwitch:
    def __init__(self, root: str | Path):
        raw = Path(root)
        if raw.is_symlink():
            raise DeploymentRecoveryError("deployment_root_must_not_be_symlink")
        self.root = raw.resolve()
        self.releases = self.root / "releases"
        self.journal = self.root / "deployment-journal.jsonl"
        self.lock_path = self.root / ".deployment.lock"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o750)
        if self.journal.is_symlink() or self.lock_path.is_symlink():
            raise DeploymentRecoveryError("deployment_journal_and_lock_must_not_be_symlinks")
        self.releases.mkdir(parents=True, exist_ok=True, mode=0o750)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        if self.lock_path.is_symlink():
            raise DeploymentRecoveryError("deployment_lock_must_not_be_symlink")
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _record(self, event: str, **fields: object) -> None:
        record = {"event": event, **fields}
        fd = os.open(self.journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)

    def _safe_release_target(self, relative: str) -> Path:
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise DeploymentRecoveryError("release_target_must_be_relative")
        target = (self.root / relative).resolve()
        if self.releases.resolve() not in target.parents or not target.is_dir():
            raise DeploymentRecoveryError("release_target_outside_releases_or_missing")
        return target

    def switch(self, new_release: str, *, active_name: str = "current",
               health_check: Callable[[Path], bool] = lambda _path: True,
               fault_hook: Callable[[str], None] | None = None) -> dict[str, str]:
        with self._locked():
            return self._switch_locked(new_release, active_name=active_name, health_check=health_check, fault_hook=fault_hook)

    def _switch_locked(self, new_release: str, *, active_name: str,
                       health_check: Callable[[Path], bool],
                       fault_hook: Callable[[str], None] | None) -> dict[str, str]:
        if not active_name or Path(active_name).name != active_name or active_name.startswith("."):
            raise DeploymentRecoveryError("invalid_active_pointer_name")
        new_path = self._safe_release_target(new_release)
        active = self.root / active_name
        if active.exists() and not active.is_symlink():
            raise DeploymentRecoveryError("active_pointer_is_not_symlink")
        previous = os.readlink(active) if active.is_symlink() else None
        if previous:
            resolved_previous = (self.root / previous).resolve()
            if self.releases.resolve() not in resolved_previous.parents or not resolved_previous.is_dir():
                raise DeploymentRecoveryError("previous_release_target_invalid")
        transaction_id = uuid.uuid4().hex
        new_target = os.path.relpath(new_path, self.root)
        temporary = self.root / f".{active_name}.pending-{transaction_id}"
        self._record("PREPARED", transaction_id=transaction_id, active_name=active_name,
                     previous_target=previous, new_target=new_target)
        os.symlink(new_target, temporary)
        if fault_hook:
            fault_hook("before_switch")
        os.replace(temporary, active)
        dir_fd = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        self._record("SWITCHED", transaction_id=transaction_id, active_name=active_name,
                     previous_target=previous, new_target=new_target)
        if fault_hook:
            fault_hook("after_switch")
        if not health_check(new_path):
            self._restore_pointer(active, previous, transaction_id, active_name, new_target)
            self._record("ROLLED_BACK", transaction_id=transaction_id, active_name=active_name,
                         previous_target=previous, new_target=new_target, reason="health_check_failed")
            raise DeploymentRecoveryError("release_health_check_failed_rolled_back")
        self._record("COMMITTED", transaction_id=transaction_id, active_name=active_name,
                     previous_target=previous, new_target=new_target)
        return {"status": "committed", "transaction_id": transaction_id,
                "active_path": str(active), "release_target": new_target}

    def _restore_pointer(self, active: Path, previous: str | None, transaction_id: str, active_name: str, new_target: str) -> None:
        if active.exists() and not active.is_symlink():
            raise DeploymentRecoveryError("active_pointer_changed_to_non_symlink")
        current = os.readlink(active) if active.is_symlink() else None
        if current != new_target:
            raise DeploymentRecoveryError("active_pointer_changed_during_recovery")
        if previous is None:
            active.unlink(missing_ok=True)
        else:
            old_path = (self.root / previous).resolve()
            if self.releases.resolve() not in old_path.parents or not old_path.is_dir():
                raise DeploymentRecoveryError("previous_release_target_invalid")
            temp = self.root / f".{active_name}.rollback-{transaction_id}"
            os.symlink(previous, temp)
            os.replace(temp, active)
        dir_fd = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    def recover_pending(self) -> dict[str, object]:
        with self._locked():
            return self._recover_pending_locked()

    def _recover_pending_locked(self) -> dict[str, object]:
        if not self.journal.exists():
            return {"status": "clean", "actions": []}
        records = []
        raw_journal = self.journal.read_text(encoding="utf-8")
        lines = raw_journal.splitlines()
        for index, line in enumerate(lines):
            try:
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise DeploymentRecoveryError("deployment_journal_record_invalid")
                records.append(item)
            except json.JSONDecodeError as exc:
                if index == len(lines) - 1 and not raw_journal.endswith("\n"):
                    continue  # Only a torn, incomplete final record may be ignored.
                raise DeploymentRecoveryError("deployment_journal_corrupt") from exc
        prepared: dict[str, dict[str, object]] = {}
        terminal = {"COMMITTED", "ROLLED_BACK", "ROLLBACK_POINTER_RESTORED"}
        for item in records:
            txid = item.get("transaction_id")
            if not isinstance(txid, str): continue
            if item.get("event") == "PREPARED": prepared[txid] = item
            elif item.get("event") in terminal: prepared.pop(txid, None)
        actions: list[dict[str, str]] = []
        for txid, item in prepared.items():
            name = item.get("active_name")
            new_target = item.get("new_target")
            previous = item.get("previous_target")
            if not isinstance(name, str) or Path(name).name != name or not isinstance(new_target, str):
                actions.append({"transaction_id": txid, "action": "BLOCKED_INVALID_JOURNAL"}); continue
            self._safe_release_target(new_target)
            active = self.root / name
            if active.exists() and not active.is_symlink():
                actions.append({"transaction_id": txid, "action": "BLOCKED_NON_SYMLINK_ACTIVE"}); continue
            current = os.readlink(active) if active.is_symlink() else None
            if current == new_target:
                try:
                    self._restore_pointer(active, previous if isinstance(previous, str) else None, txid, name, new_target)
                except DeploymentRecoveryError:
                    actions.append({"transaction_id": txid, "action": "BLOCKED_RESTORE_FAILED"}); continue
                action = "ROLLBACK_POINTER_RESTORED"
                self._record(action, transaction_id=txid, active_name=name, previous_target=previous, new_target=new_target)
                actions.append({"transaction_id": txid, "action": action})
            elif current == previous:
                pending = self.root / f".{name}.pending-{txid}"
                if pending.is_symlink() and os.readlink(pending) == new_target:
                    pending.unlink(missing_ok=True)
                action = "ROLLBACK_NO_SWITCH_NEEDED"
                self._record("ROLLED_BACK", transaction_id=txid, active_name=name, previous_target=previous,
                             new_target=new_target, reason="pointer_never_switched")
                actions.append({"transaction_id": txid, "action": action})
            else:
                actions.append({"transaction_id": txid, "action": "BLOCKED_UNEXPECTED_POINTER"})
        return {"status": "recovered" if actions else "clean", "actions": actions}


def main() -> int:
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Offline SolarMiner atomic release pointer recovery")
    parser.add_argument("--root", default="/opt/solarminer", help="release deployment root")
    args = parser.parse_args()
    root = Path(args.root)
    journal = root / "deployment-journal.jsonl"
    if root.is_symlink() or (journal.exists() and journal.is_symlink()):
        print(json.dumps({"status": "blocked", "reason": "recovery_path_must_not_be_symlink"}))
        return 2
    if not journal.exists():
        print(json.dumps({"status": "clean", "actions": []}))
        return 0
    try:
        result = DeploymentReleaseSwitch(root).recover_pending()
        print(json.dumps(result, sort_keys=True))
        if any(str(item.get("action", "")).startswith("BLOCKED") for item in result.get("actions", [])):
            return 2
        return 0
    except (OSError, DeploymentRecoveryError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "reason": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
