"""Transactional reconciliation for the package's privileged runtime files.

Online releases are unpacked under /opt and are not installed by dpkg.  The
gateway updater therefore reconciles a deliberately small, package-owned set
of helpers, Python modules, Intelligence assets and systemd units itself.  It
does not touch /etc, credentials, databases, or user data.
"""
from __future__ import annotations

import json
import hashlib
import os
import platform
import re
import subprocess
import shutil
import stat
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Callable


PROTOCOL_VERSION = 1
MANIFEST_NAME = "system-components.json"
SYSTEM_COMPONENT_PREFIXES = (
    "usr/bin/solarminer-",
    "usr/sbin/solarminer-",
    "usr/lib/solarminer-gateway/",
    "usr/share/solarminer/intelligence-agent/",
    "usr/share/solarminer/intelligence-mcp/",
    "lib/systemd/system/solarminer-",
    "usr/lib/systemd/system/solarminer-",
)
REQUIRED_SOCKETS = (
    "solarminer-update-broker.socket",
    "solarminer-intelligence-bootstrap-broker.socket",
    "solarminer-admin-terminal.socket",
)
REQUIRED_COMPONENTS = (
    "usr/bin/solarminer-gateway",
    "usr/bin/solarminer-recovery",
    "usr/bin/solarminer-data-volume-check",
    "usr/bin/solarminer-update-check-daily",
    "usr/sbin/solarminer-update-apply",
    "usr/sbin/solarminer-intelligence-bootstrap",
    "usr/bin/solarminer-update-broker",
    "usr/bin/solarminer-intelligence-bootstrap-broker",
    "usr/lib/solarminer-gateway/solarminer_gateway/system_update_pipeline.py",
    "usr/lib/solarminer-gateway/solarminer_gateway/system_components.py",
    "usr/lib/solarminer-gateway/solarminer_gateway/intelligence_health.py",
    "usr/lib/solarminer-gateway/solarminer_gateway/update_broker.py",
    "usr/lib/solarminer-gateway/solarminer_gateway/intelligence_bootstrap_broker.py",
    "usr/lib/solarminer-gateway/solarminer_gateway/admin_terminal_broker.py",
    "usr/share/solarminer/intelligence-agent/agent-service.mjs",
    "usr/share/solarminer/intelligence-mcp/server.mjs",
    "usr/lib/systemd/system/solarminer-gateway.service",
    "usr/lib/systemd/system/solarminer-recovery.service",
    "usr/lib/systemd/system/solarminer-recovery.timer",
    "usr/lib/systemd/system/solarminer-intelligence-bootstrap.service",
    "usr/lib/systemd/system/solarminer-intelligence-bootstrap.timer",
    "usr/lib/systemd/system/solarminer-intelligence.service",
    "usr/lib/systemd/system/solarminer-update-apply@.service",
    "usr/lib/systemd/system/solarminer-update-broker.socket",
    "usr/lib/systemd/system/solarminer-update-broker@.service",
    "usr/lib/systemd/system/solarminer-intelligence-bootstrap-broker.socket",
    "usr/lib/systemd/system/solarminer-intelligence-bootstrap-broker@.service",
    "usr/lib/systemd/system/solarminer-admin-terminal.socket",
    "usr/lib/systemd/system/solarminer-admin-terminal@.service",
)


class SystemComponentError(RuntimeError):
    """A package/system component could not be safely reconciled."""


def _relative(path: str) -> str:
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        raise SystemComponentError("system_component_path_invalid")
    value = candidate.as_posix()
    if not value.startswith(SYSTEM_COMPONENT_PREFIXES):
        raise SystemComponentError("system_component_path_not_allowlisted")
    return value


def _missing_required_components(files: set[str]) -> list[str]:
    missing = []
    for required in REQUIRED_COMPONENTS:
        legacy_unit_path = required.replace("usr/lib/systemd/system/", "lib/systemd/system/")
        if required not in files and legacy_unit_path not in files:
            missing.append(required)
    return missing


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_components(package_root: Path) -> dict[str, Path]:
    """Return the allowlisted regular files supplied by an extracted package."""
    result: dict[str, Path] = {}
    for prefix in SYSTEM_COMPONENT_PREFIXES:
        root = package_root / prefix.rstrip("/")
        if prefix.endswith("/"):
            if not root.exists():
                continue
            for candidate in root.rglob("*"):
                if candidate.is_dir() and not candidate.is_symlink():
                    continue
                relative = candidate.relative_to(package_root).as_posix()
                relative = _relative(relative)
                metadata = candidate.lstat()
                if not stat.S_ISREG(metadata.st_mode):
                    raise SystemComponentError("system_component_not_regular_file")
                result[relative] = candidate
        else:
            parent = root.parent
            if not parent.exists():
                continue
            for candidate in parent.glob(root.name + "*"):
                relative = _relative(candidate.relative_to(package_root).as_posix())
                metadata = candidate.lstat()
                if not stat.S_ISREG(metadata.st_mode):
                    raise SystemComponentError("system_component_not_regular_file")
                result[relative] = candidate
    missing = _missing_required_components(set(result))
    if missing:
        raise SystemComponentError("system_component_payload_incomplete:" + ",".join(missing))
    return dict(sorted(result.items()))


def _system_path(relative: str, system_root: Path = Path("/")) -> Path:
    relative = _relative(relative)
    parts = PurePosixPath(relative).parts
    # Debian 13 uses the merged-/usr layout where /lib is a symlink. Package
    # paths remain recorded as dpkg names but are applied to their real target.
    if parts[:3] == ("lib", "systemd", "system"):
        parts = ("usr", "lib", "systemd", "system", *parts[3:])
    target = system_root.joinpath(*parts)
    cursor = system_root
    for part in target.relative_to(system_root).parts[:-1]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise SystemComponentError("system_component_parent_symlink")
        if cursor.exists() and not cursor.is_dir():
            raise SystemComponentError("system_component_parent_not_directory")
    if target.is_symlink():
        raise SystemComponentError("system_component_target_symlink")
    return target


def _read_manifest(path: Path) -> dict[str, Any] | None:
    if path.is_symlink():
        raise SystemComponentError("system_component_manifest_symlink")
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemComponentError("system_component_manifest_invalid") from exc
    if (not isinstance(value, dict) or value.get("protocol") != PROTOCOL_VERSION
            or not isinstance(value.get("version"), str) or not isinstance(value.get("files"), list)
            or not isinstance(value.get("sha256"), dict)):
        raise SystemComponentError("system_component_manifest_invalid")
    files = value["files"]
    if any(not isinstance(item, str) for item in files):
        raise SystemComponentError("system_component_manifest_invalid")
    for item in files:
        _relative(item)
        digest = value["sha256"].get(item)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SystemComponentError("system_component_manifest_invalid")
    if set(value["sha256"]) != set(files):
        raise SystemComponentError("system_component_manifest_invalid")
    return value


def _atomic_json(path: Path, value: dict[str, Any], *, mode: int = 0o600) -> None:
    if path.parent.is_symlink():
        raise SystemComponentError("system_component_state_directory_symlink")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    if path.is_symlink():
        raise SystemComponentError("system_component_manifest_symlink")
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        temporary.unlink(missing_ok=True)


def reconcile(package_root: Path, deployment_root: Path, version: str,
              *, legacy_files: list[str] | None = None, operation_id: str,
              on_snapshot_ready: Callable[[Path], None] | None = None,
              system_root: Path = Path("/")) -> Path:
    """Apply package-owned privileged files and return a complete rollback snapshot.

    Caller must stop the Gateway before this function and reload/restart the
    affected systemd sockets before restarting it.
    """
    deployment_root.mkdir(parents=True, exist_ok=True, mode=0o750)
    if deployment_root.is_symlink():
        raise SystemComponentError("system_component_deployment_root_symlink")
    for directory in (deployment_root / "backups", deployment_root / "backups" / "system-components"):
        if directory.is_symlink():
            raise SystemComponentError("system_component_backup_directory_symlink")
    manifest_path = deployment_root / MANIFEST_NAME
    previous = _read_manifest(manifest_path)
    incoming = package_components(package_root)
    old_files = set(previous["files"]) if previous else set()
    if previous is None and legacy_files:
        old_files = {_relative(item) for item in legacy_files if item.startswith(SYSTEM_COMPONENT_PREFIXES)}
    if not operation_id or any(char not in "0123456789abcdef-" for char in operation_id):
        raise SystemComponentError("system_component_operation_id_invalid")
    snapshot_root = deployment_root / "backups" / "system-components" / operation_id
    snapshot_root.mkdir(parents=True, exist_ok=False, mode=0o700)
    snapshot: list[dict[str, Any]] = []
    previous_manifest_bytes = manifest_path.read_bytes() if manifest_path.is_file() else None
    try:
        affected = old_files | set(incoming)
        for relative in sorted(affected):
            target = _system_path(relative, system_root)
            backup = snapshot_root / "files" / relative
            if target.exists():
                metadata = target.lstat()
                if not stat.S_ISREG(metadata.st_mode):
                    raise SystemComponentError("system_component_target_not_regular_file")
                backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copy2(target, backup, follow_symlinks=False)
                snapshot.append({"path": relative, "existed": True, "backup": str(backup.relative_to(snapshot_root))})
            else:
                snapshot.append({"path": relative, "existed": False})
        metadata = {"protocol": PROTOCOL_VERSION, "version": version,
                    "files": sorted(incoming), "snapshot": snapshot,
                    "previous_manifest": previous_manifest_bytes.decode("utf-8") if previous_manifest_bytes is not None else None}
        _atomic_json(snapshot_root / "snapshot.json", metadata)
        if on_snapshot_ready is not None:
            on_snapshot_ready(snapshot_root)
        for relative, source in incoming.items():
            target = _system_path(relative, system_root)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            if target.parent.is_symlink():
                raise SystemComponentError("system_component_parent_symlink")
            temporary = target.with_name("." + target.name + ".solarminer-" + uuid.uuid4().hex)
            shutil.copy2(source, temporary, follow_symlinks=False)
            os.replace(temporary, target)
        for relative in old_files - set(incoming):
            target = _system_path(relative, system_root)
            target.unlink(missing_ok=True)
        _atomic_json(manifest_path, {"protocol": PROTOCOL_VERSION, "version": version,
                                     "files": sorted(incoming),
                                     "sha256": {relative: _digest(source) for relative, source in incoming.items()}}, mode=0o644)
        return snapshot_root
    except Exception:
        if (snapshot_root / "snapshot.json").is_file():
            restore(snapshot_root, deployment_root)
        raise


def restore(snapshot_root: Path, deployment_root: Path, *, system_root: Path = Path("/")) -> None:
    """Restore exact pre-update files and component manifest from a snapshot."""
    if snapshot_root.is_symlink() or deployment_root.is_symlink():
        raise SystemComponentError("system_component_snapshot_symlink")
    snapshot_file = snapshot_root / "snapshot.json"
    if snapshot_file.is_symlink():
        raise SystemComponentError("system_component_snapshot_invalid")
    try:
        state = json.loads(snapshot_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemComponentError("system_component_snapshot_invalid") from exc
    if state.get("protocol") != PROTOCOL_VERSION or not isinstance(state.get("snapshot"), list):
        raise SystemComponentError("system_component_snapshot_invalid")
    for item in state["snapshot"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise SystemComponentError("system_component_snapshot_invalid")
        target = _system_path(item["path"], system_root)
        if item.get("existed") is True:
            backup_rel = item.get("backup")
            if not isinstance(backup_rel, str) or PurePosixPath(backup_rel).is_absolute() or ".." in PurePosixPath(backup_rel).parts:
                raise SystemComponentError("system_component_snapshot_invalid")
            source = snapshot_root.joinpath(*PurePosixPath(backup_rel).parts)
            if source.is_symlink() or not source.is_file() or any(parent.is_symlink() for parent in source.parents if parent != snapshot_root.parent):
                raise SystemComponentError("system_component_snapshot_invalid")
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            temporary = target.with_name("." + target.name + ".solarminer-restore-" + uuid.uuid4().hex)
            shutil.copy2(source, temporary, follow_symlinks=False)
            os.replace(temporary, target)
        else:
            target.unlink(missing_ok=True)
    manifest = deployment_root / MANIFEST_NAME
    previous = state.get("previous_manifest")
    if previous is None:
        manifest.unlink(missing_ok=True)
    elif isinstance(previous, str):
        try:
            value = json.loads(previous)
        except json.JSONDecodeError as exc:
            raise SystemComponentError("system_component_snapshot_invalid") from exc
        _atomic_json(manifest, value, mode=0o644)
    else:
        raise SystemComponentError("system_component_snapshot_invalid")


def initialize_installed_manifest(version: str, deployment_root: Path = Path("/opt/solarminer"),
                                   *, list_files: Callable[[], list[str]] | None = None,
                                   system_root: Path = Path("/")) -> None:
    """Record the package-owned component set after a full Debian package install."""
    if list_files is None:
        result = subprocess.run(["/usr/bin/dpkg-query", "--listfiles", "solarminer-gateway"],
                                capture_output=True, text=True, timeout=15, check=False)
        if result.returncode != 0:
            raise SystemComponentError("installed_package_file_list_unavailable")
        list_files = lambda: [line.strip().lstrip("/") for line in result.stdout.splitlines() if line.strip().startswith("/")]
    if deployment_root.is_symlink():
        raise SystemComponentError("system_component_deployment_root_symlink")
    normalized = (item.strip().lstrip("/") for item in list_files())
    files: list[str] = []
    for item in normalized:
        if not item.startswith(SYSTEM_COMPONENT_PREFIXES):
            continue
        relative = _relative(item)
        target = _system_path(relative, system_root)
        if not target.exists():
            raise SystemComponentError("installed_system_component_missing")
        metadata = target.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise SystemComponentError("system_component_target_not_regular_file")
        files.append(relative)
    files = sorted(set(files))
    missing = _missing_required_components(set(files))
    if missing:
        raise SystemComponentError("installed_system_component_inventory_incomplete:" + ",".join(missing))
    path = deployment_root / MANIFEST_NAME
    _atomic_json(path, {"protocol": PROTOCOL_VERSION, "version": version, "files": files,
                        "sha256": {relative: _digest(_system_path(relative, system_root)) for relative in files}}, mode=0o644)


def installed_component_status(deployment_root: Path = Path("/opt/solarminer"),
                               *, system_root: Path = Path("/")) -> dict[str, Any]:
    """Return a secret-free, read-only summary for health and Owner diagnostics."""
    try:
        value = _read_manifest(deployment_root / MANIFEST_NAME)
    except SystemComponentError as exc:
        return {"status": "INCOMPATIBLE", "version": None, "protocol": None, "reason": str(exc)}
    if value is None:
        return {"status": "UNAVAILABLE", "version": None, "protocol": None,
                "reason": "system_components_manifest_missing"}
    missing = _missing_required_components(set(value["files"]))
    if missing:
        return {"status": "INCOMPATIBLE", "version": value["version"], "protocol": value["protocol"],
                "reason": "system_component_inventory_incomplete"}
    try:
        for relative in value["files"]:
            target = _system_path(relative, system_root)
            if not target.is_file():
                return {"status": "FAILED", "version": value["version"], "protocol": value["protocol"],
                        "reason": "system_component_file_missing"}
            if _digest(target) != value["sha256"][relative]:
                return {"status": "FAILED", "version": value["version"], "protocol": value["protocol"],
                        "reason": "system_component_hash_mismatch"}
    except SystemComponentError as exc:
        return {"status": "INCOMPATIBLE", "version": value["version"], "protocol": value["protocol"],
                "reason": str(exc)}
    except OSError:
        return {"status": "FAILED", "version": value["version"], "protocol": value["protocol"],
                "reason": "system_component_file_unreadable"}
    return {"status": "OK", "version": value["version"], "protocol": value["protocol"], "reason": None}


def compatibility_status(active_release_version: str, components: dict[str, Any]) -> dict[str, Any]:
    """Compare the running release with the installed privileged component set."""
    if components.get("status") != "OK":
        return {"status": components.get("status", "UNAVAILABLE"),
                "reason": components.get("reason") or "system_components_unavailable"}
    if components.get("protocol") != PROTOCOL_VERSION:
        return {"status": "INCOMPATIBLE", "reason": "system_components_protocol_mismatch"}
    if components.get("version") != active_release_version:
        return {"status": "INCOMPATIBLE", "reason": "system_components_release_version_mismatch"}
    return {"status": "OK", "reason": None}


DIAGNOSTIC_UNITS = {
    "gateway": "solarminer-gateway.service",
    "update_broker": "solarminer-update-broker.socket",
    "intelligence_bootstrap_broker": "solarminer-intelligence-bootstrap-broker.socket",
    "admin_terminal": "solarminer-admin-terminal.socket",
    "intelligence_bootstrap": "solarminer-intelligence-bootstrap.timer",
    "intelligence_agent": "solarminer-intelligence.service",
}
DIAGNOSTIC_PATHS = {
    "intelligence_bootstrap_binary": Path("/usr/sbin/solarminer-intelligence-bootstrap"),
    "intelligence_runtime": Path("/opt/solarminer/intelligence"),
    "intelligence_state": Path("/var/lib/solarminer/intelligence"),
    "intelligence_agent_env": Path("/etc/solarminer/intelligence-agent.env"),
    "admin_terminal_socket": Path("/run/solarminer/admin-terminal.sock"),
    "update_broker_socket": Path("/run/solarminer/update-broker.sock"),
    "intelligence_bootstrap_socket": Path("/run/solarminer/intelligence-bootstrap.sock"),
}


def _path_status(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {"state": "MISSING", "owner_uid": None, "mode": None, "type": None}
    except OSError:
        return {"state": "UNKNOWN", "owner_uid": None, "mode": None, "type": None}
    if stat.S_ISLNK(metadata.st_mode):
        kind = "symlink"
        state = "UNSAFE"
    elif stat.S_ISREG(metadata.st_mode):
        kind = "file"
        state = "PRESENT"
    elif stat.S_ISDIR(metadata.st_mode):
        kind = "directory"
        state = "PRESENT"
    elif stat.S_ISSOCK(metadata.st_mode):
        kind = "socket"
        state = "PRESENT"
    else:
        kind = "other"
        state = "UNSAFE"
    return {"state": state, "owner_uid": metadata.st_uid,
            "mode": format(stat.S_IMODE(metadata.st_mode), "04o"), "type": kind}


def integrated_diagnostics(active_app_version: str, *, deployment_root: Path = Path("/opt/solarminer"),
                           runner=subprocess.run) -> dict[str, Any]:
    """Return bounded, secret-free system coherence diagnostics for the Owner."""
    components = installed_component_status(deployment_root)
    compatibility = compatibility_status(active_app_version, components)
    try:
        os_release = platform.freedesktop_os_release()
        operating_system = {"id": os_release.get("ID", "unknown"),
                            "version": os_release.get("VERSION_ID", "unknown"),
                            "codename": os_release.get("VERSION_CODENAME", "unknown")}
    except (OSError, AttributeError):
        operating_system = {"id": "unknown", "version": "unknown", "codename": "unknown"}
    try:
        result = runner(["/usr/bin/dpkg-query", "-W", "-f=${Version}", "solarminer-gateway"],
                        capture_output=True, text=True, timeout=3, check=False)
        dpkg_version = (result.stdout.strip() if result.returncode == 0 and isinstance(result.stdout, str)
                        and re.fullmatch(r"[A-Za-z0-9.+:~_-]{1,64}", result.stdout.strip()) else None)
    except (OSError, subprocess.TimeoutExpired):
        dpkg_version = None
    try:
        current = deployment_root / "current"
        active_release = current.resolve(strict=True).name if current.is_symlink() else None
    except OSError:
        active_release = None
    units: dict[str, dict[str, str]] = {}
    for key, unit in DIAGNOSTIC_UNITS.items():
        try:
            result = runner(["/usr/bin/systemctl", "is-active", unit],
                            capture_output=True, text=True, timeout=2, check=False)
            value = result.stdout.strip() if isinstance(result.stdout, str) else ""
            state = value if value in {"active", "inactive", "failed", "activating", "deactivating"} else "unknown"
        except (OSError, subprocess.TimeoutExpired):
            state = "unknown"
        units[key] = {"unit": unit, "state": state}
    paths = {key: _path_status(path) for key, path in DIAGNOSTIC_PATHS.items()}
    return {
        "status": compatibility["status"], "reason": compatibility["reason"],
        "operating_system": operating_system, "python_version": platform.python_version(),
        "application_version": active_app_version, "debian_package_version": dpkg_version,
        "active_release": active_release, "system_components": components,
        "units": units, "paths": paths,
    }
