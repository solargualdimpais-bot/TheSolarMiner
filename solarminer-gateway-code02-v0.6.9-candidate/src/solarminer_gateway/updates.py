"""Fail-closed release-manifest validation for CODE02 v0.6.9.

This module deliberately separates cryptographic verification from activation.
It never executes a manifest command or invokes dpkg. Activation requires a
separately validated deployment/recovery layout and is disabled by default.
"""
from __future__ import annotations
import hashlib, json, os, shutil, tempfile, urllib.parse, urllib.request
from pathlib import Path
from typing import Any
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

MAX_MANIFEST_BYTES = 1024 * 1024
MAX_PACKAGE_BYTES = 1024 * 1024 * 1024

class UpdateValidationError(ValueError):
    pass

def canonical_manifest(manifest: dict[str, Any]) -> bytes:
    unsigned = {k: v for k, v in manifest.items() if k != "signature"}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def load_release_key(path: str | Path) -> Ed25519PublicKey:
    p = Path(path)
    try:
        key = serialization.load_pem_public_key(p.read_bytes())
    except Exception as exc:
        raise UpdateValidationError("release_public_key_missing_or_invalid") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise UpdateValidationError("release_ed25519_key_required")
    return key

def verify_manifest(manifest: dict[str, Any], public_key: Ed25519PublicKey, installed_version: str) -> dict[str, Any]:
    required = {"schema_version", "release_id", "version", "min_compatible_version", "changelog", "package_name", "package_url", "package_size", "sha256", "signature_algorithm", "signature", "compatibility", "migration_requirements"}
    if not isinstance(manifest, dict) or not required.issubset(manifest):
        raise UpdateValidationError("manifest_required_fields_missing")
    if manifest["schema_version"] != 1 or manifest["signature_algorithm"] != "Ed25519":
        raise UpdateValidationError("manifest_schema_or_algorithm_unsupported")
    if not all(isinstance(manifest[k], str) and manifest[k] for k in ("release_id", "version", "min_compatible_version", "package_name", "package_url", "sha256")):
        raise UpdateValidationError("manifest_field_type_invalid")
    if not isinstance(manifest["package_name"], str) or Path(manifest["package_name"]).name != manifest["package_name"] or not manifest["package_name"].endswith(".deb"):
        raise UpdateValidationError("package_name_invalid")
    if not isinstance(manifest["package_size"], int) or not 1 <= manifest["package_size"] <= MAX_PACKAGE_BYTES:
        raise UpdateValidationError("package_size_invalid")
    if not isinstance(manifest["sha256"], str) or len(manifest["sha256"]) != 64 or any(c not in "0123456789abcdefABCDEF" for c in manifest["sha256"]):
        raise UpdateValidationError("package_sha256_invalid")
    if not isinstance(manifest["compatibility"], dict) or not isinstance(manifest["migration_requirements"], list) or not isinstance(manifest["changelog"], list):
        raise UpdateValidationError("manifest_structure_invalid")
    try:
        signature = bytes.fromhex(manifest["signature"])
        public_key.verify(signature, canonical_manifest(manifest))
    except (ValueError, InvalidSignature, TypeError) as exc:
        raise UpdateValidationError("manifest_signature_invalid") from exc
    # Do not compare arbitrary version strings lexically. Require an explicit compatibility assertion.
    if manifest["min_compatible_version"] != installed_version:
        raise UpdateValidationError("installed_version_not_compatible")
    url = urllib.parse.urlparse(manifest["package_url"])
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.fragment:
        raise UpdateValidationError("package_url_not_authorized_https")
    return {"signature_valid": True, "compatible": True, "package_url": manifest["package_url"], "sha256": manifest["sha256"].lower(), "package_size": manifest["package_size"]}

def download_and_verify_package(manifest: dict[str, Any], destination_dir: str | Path) -> Path:
    """Download to a non-active staging directory; enforce same-origin and exact size/hash."""
    base = urllib.parse.urlparse(manifest["package_url"])
    if base.scheme != "https" or not base.hostname:
        raise UpdateValidationError("package_url_not_authorized_https")
    raw_dest = Path(destination_dir)
    if raw_dest.exists() and raw_dest.is_symlink():
        raise UpdateValidationError("staging_directory_symlink_rejected")
    raw_dest.mkdir(mode=0o700, parents=True, exist_ok=True)
    if raw_dest.is_symlink():
        raise UpdateValidationError("staging_directory_symlink_rejected")
    dest = raw_dest.resolve()
    fd, name = tempfile.mkstemp(prefix="release-", suffix=".part", dir=dest)
    path = Path(name)
    digest, size = hashlib.sha256(), 0
    try:
        request = urllib.request.Request(manifest["package_url"], headers={"Accept": "application/octet-stream", "User-Agent": "SolarMiner-CODE02/0.6.9"})
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(request, timeout=20) as response:
            final = urllib.parse.urlparse(response.geturl())
            if final.scheme != "https" or final.hostname != base.hostname or final.port != base.port:
                raise UpdateValidationError("package_redirect_origin_changed")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk: break
                size += len(chunk)
                if size > manifest["package_size"] or size > MAX_PACKAGE_BYTES:
                    raise UpdateValidationError("package_size_exceeded")
                digest.update(chunk); out.write(chunk)
            out.flush(); os.fsync(out.fileno())
        if size != manifest["package_size"]:
            raise UpdateValidationError("package_size_mismatch")
        if digest.hexdigest().lower() != manifest["sha256"].lower():
            raise UpdateValidationError("package_sha256_mismatch")
        final_path = dest / (Path(manifest["package_name"]).name + ".verified")
        if final_path.parent != dest or final_path.is_symlink():
            raise UpdateValidationError("unsafe_package_name")
        os.replace(path, final_path)
        os.chmod(final_path, 0o600)
        return final_path
    except Exception:
        try: path.unlink(missing_ok=True)
        except OSError: pass
        raise
