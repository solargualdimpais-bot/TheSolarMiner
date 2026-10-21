"""Hash-pinned, offline-only per-connector Python dependency management."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .isolated_runtime import validate_connector_id

PACKAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.!+_-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest(manifest: dict[str, Any], wheelhouse: Path) -> list[dict[str, str]]:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("dependency_manifest_schema_invalid")
    entries = manifest.get("dependencies")
    if not isinstance(entries, list):
        raise ValueError("dependency_manifest_entries_invalid")
    validated: list[dict[str, str]] = []
    seen: set[str] = set()
    seen_packages: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("dependency_entry_invalid")
        name, version, filename, digest, source = (item.get(k) for k in ("name", "version", "filename", "sha256", "source"))
        if not all(isinstance(x, str) and x for x in (name, version, filename, digest, source)):
            raise ValueError("dependency_metadata_missing")
        if not PACKAGE_RE.fullmatch(name) or not VERSION_RE.fullmatch(version) or not SHA256_RE.fullmatch(digest):
            raise ValueError("dependency_metadata_invalid")
        if Path(filename).name != filename or filename in seen or not filename.endswith(".whl"):
            raise ValueError("dependency_wheel_filename_invalid")
        normalized_name = re.sub(r"[-_.]+", "-", name).lower()
        if normalized_name in seen_packages:
            raise ValueError("duplicate_dependency_package")
        if not source.startswith(("https://", "file://", "debian:")):
            raise ValueError("dependency_source_untrusted")
        wheel = wheelhouse / filename
        if not wheel.is_file() or sha256_file(wheel) != digest:
            raise ValueError("dependency_wheel_hash_mismatch")
        seen.add(filename)
        seen_packages.add(normalized_name)
        validated.append({"name": name, "version": version, "filename": filename, "sha256": digest, "source": source})
    return validated


def install_offline(connector_id: str, manifest_path: Path, wheelhouse: Path,
                    base_python: str, connectors_root: Path,
                    run=subprocess.run) -> dict[str, str | int]:
    """Create a dedicated venv and install only preverified wheels without network."""
    connector_id = validate_connector_id(connector_id)
    if not connectors_root.is_absolute() or not manifest_path.is_absolute() or not wheelhouse.is_absolute():
        raise ValueError("absolute_paths_required")
    if not Path(base_python).is_absolute() or not os.path.isfile(base_python):
        raise ValueError("base_python_not_found")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("dependency_manifest_unreadable") from exc
    entries = validate_manifest(manifest, wheelhouse)
    root = connectors_root / connector_id
    venv_path = root / "venv"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if venv_path.exists():
        raise FileExistsError("connector_venv_already_exists; use staged update")
    requirements = root / "requirements-hashed.txt"
    try:
        # Use the explicitly validated target interpreter; do not silently use sys.executable.
        create_result = run([base_python, "-I", "-m", "venv", str(venv_path)],
                            check=False, capture_output=True, text=True, timeout=120)
        if create_result.returncode != 0 or not (venv_path / "bin" / "python").is_file():
            raise RuntimeError("connector_venv_creation_failed")
        lines = [f"{e['name']}=={e['version']} --hash=sha256:{e['sha256']}" for e in entries]
        requirements.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        os.chmod(requirements, 0o600)
        pip = venv_path / "bin" / "python"
        cmd = [str(pip), "-I", "-m", "pip", "install", "--disable-pip-version-check", "--no-index",
               "--find-links", str(wheelhouse), "--require-hashes", "--no-deps", "-r", str(requirements)]
        result = run(cmd, check=False, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError("offline_dependency_install_failed")
    except Exception as exc:
        # Only remove the venv and manifest created by this operation; retain unrelated connector state.
        import shutil
        shutil.rmtree(venv_path, ignore_errors=True)
        requirements.unlink(missing_ok=True)
        if isinstance(exc, RuntimeError) and str(exc) in {"connector_venv_creation_failed", "offline_dependency_install_failed"}:
            raise
        raise RuntimeError("connector_dependency_setup_failed") from exc
    return {"connector_id": connector_id, "venv": str(venv_path), "dependency_count": len(entries),
            "pip_exit_code": int(result.returncode), "network_access": "disabled_by_pip_no_index",
            "manifest_verified": "true", "system_python_modified": "false"}
