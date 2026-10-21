"""Fail-closed release-manifest validation for CODE02 v0.6.9.

This module deliberately separates cryptographic verification from activation.
It never executes a manifest command or invokes dpkg. Activation requires a
separately validated deployment/recovery layout and is disabled by default.
"""
from __future__ import annotations
import hashlib, json, os, re, shutil, stat, tempfile, urllib.parse, urllib.request
from pathlib import Path
from typing import Any
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

MAX_MANIFEST_BYTES = 1024 * 1024
MAX_PACKAGE_BYTES = 1024 * 1024 * 1024
MAX_UPDATE_SOURCES_BYTES = 64 * 1024
DEFAULT_UPDATE_SOURCES_PATH = "/etc/solarminer/update-sources.json"


def normalize_github_repository_url(value: Any) -> str:
    """Accept only a public GitHub repository root, never a file, release, or arbitrary URL."""
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise UpdateValidationError("repository_url_invalid")
    try:
        parsed = urllib.parse.urlsplit(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise UpdateValidationError("repository_url_invalid") from exc
    if (parsed.scheme != "https" or parsed.hostname != "github.com" or port is not None
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise UpdateValidationError("repository_url_not_allowed")
    if not parsed.path.startswith("/") or parsed.path.startswith("//") or parsed.path.endswith("//"):
        raise UpdateValidationError("repository_url_must_be_public_github_repository")
    parts = parsed.path[1:].split("/")
    if parts and parts[-1] == "":
        parts.pop()
    if len(parts) != 2 or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", parts[0]) or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", parts[1]):
        raise UpdateValidationError("repository_url_must_be_public_github_repository")
    return f"https://github.com/{parts[0].lower()}/{parts[1].lower()}"


def normalize_https_origin(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 512:
        raise UpdateValidationError("update_origin_invalid")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise UpdateValidationError("update_origin_invalid") from exc
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise UpdateValidationError("update_origin_must_be_https_origin")
    host = parsed.hostname.lower()
    return f"https://{host}" + (f":{port}" if port and port != 443 else "")


class _AllowedHTTPSRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_origins: set[str]):
        super().__init__()
        self.allowed_origins = allowed_origins

    def redirect_request(self, request, response, code, message, headers, newurl):
        try:
            parsed = urllib.parse.urlsplit(newurl)
            origin = normalize_https_origin(
                f"https://{parsed.hostname}" + (f":{parsed.port}" if parsed.port else "")
            ) if parsed.scheme == "https" and parsed.hostname else ""
        except (ValueError, UpdateValidationError):
            origin = ""
        if origin not in self.allowed_origins:
            raise UpdateValidationError("redirect_origin_not_authorized")
        return super().redirect_request(request, response, code, message, headers, newurl)


def open_allowed_https_url(request: urllib.request.Request, allowed_origins: set[str], timeout: int):
    """Follow redirects only when every next HTTPS origin is explicitly allowed."""
    opener = urllib.request.build_opener(_AllowedHTTPSRedirectHandler(allowed_origins))
    return opener.open(request, timeout=timeout)


def load_update_source(repository_url: str, path: str | Path = DEFAULT_UPDATE_SOURCES_PATH) -> dict[str, Any]:
    """Resolve a user-selected repo only through a root-owned, non-writable allowlist."""
    repository = normalize_github_repository_url(repository_url)
    config_path = Path(path)
    try:
        info = config_path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022
                or info.st_size > MAX_UPDATE_SOURCES_BYTES):
            raise UpdateValidationError("update_source_configuration_unsafe")
        document = json.loads(config_path.read_text(encoding="utf-8"))
    except UpdateValidationError:
        raise
    except (OSError, ValueError, UnicodeError) as exc:
        raise UpdateValidationError("update_source_configuration_unavailable") from exc
    if not isinstance(document, dict) or set(document) != {"repositories"} or not isinstance(document["repositories"], dict):
        raise UpdateValidationError("update_source_configuration_invalid")
    entry = document["repositories"].get(repository)
    if not isinstance(entry, dict) or set(entry) != {"manifest_url", "manifest_origins", "package_origins"}:
        raise UpdateValidationError("repository_not_allowlisted")
    manifest_url = entry["manifest_url"]
    if not isinstance(manifest_url, str) or len(manifest_url) > 2048:
        raise UpdateValidationError("manifest_url_invalid")
    try:
        manifest = urllib.parse.urlsplit(manifest_url)
        manifest_port = manifest.port
    except ValueError as exc:
        raise UpdateValidationError("manifest_url_invalid") from exc
    if manifest.scheme != "https" or not manifest.hostname or manifest.username or manifest.password or manifest.fragment:
        raise UpdateValidationError("manifest_url_not_authorized_https")
    manifest_origin = normalize_https_origin(f"https://{manifest.hostname}" + (f":{manifest_port}" if manifest_port else ""))
    def origins(name: str) -> set[str]:
        values = entry[name]
        if not isinstance(values, list) or not values or len(values) > 8:
            raise UpdateValidationError("update_origins_invalid")
        result = {normalize_https_origin(v) for v in values}
        if len(result) != len(values):
            raise UpdateValidationError("update_origins_invalid")
        return result
    manifest_origins = origins("manifest_origins")
    package_origins = origins("package_origins")
    if manifest_origin not in manifest_origins:
        raise UpdateValidationError("manifest_origin_not_allowlisted")
    return {"repository_url": repository, "manifest_url": manifest_url,
            "manifest_origins": manifest_origins, "package_origins": package_origins}

def list_update_sources(path: str | Path = DEFAULT_UPDATE_SOURCES_PATH) -> list[dict[str, Any]]:
    """Return only entries that pass the same root-owned allowlist validation as checks."""
    config_path = Path(path)
    try:
        info = config_path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022
                or info.st_size > MAX_UPDATE_SOURCES_BYTES):
            raise UpdateValidationError("update_source_configuration_unsafe")
        document = json.loads(config_path.read_text(encoding="utf-8"))
    except UpdateValidationError:
        raise
    except (OSError, ValueError, UnicodeError) as exc:
        raise UpdateValidationError("update_source_configuration_unavailable") from exc
    if not isinstance(document, dict) or set(document) != {"repositories"} or not isinstance(document["repositories"], dict):
        raise UpdateValidationError("update_source_configuration_invalid")
    result = []
    for repository in document["repositories"]:
        result.append(load_update_source(repository, config_path))
    if not result:
        raise UpdateValidationError("repository_not_allowlisted")
    return result


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
    if len(manifest["version"]) > 128 or not re.fullmatch(r"[0-9][A-Za-z0-9.+:~-]*", manifest["version"]):
        raise UpdateValidationError("manifest_version_invalid")
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

def download_and_verify_package(manifest: dict[str, Any], destination_dir: str | Path, allowed_origins: set[str] | None = None) -> Path:
    """Download to staging; enforce HTTPS, configured origins, exact size, and hash."""
    base = urllib.parse.urlparse(manifest["package_url"])
    if base.scheme != "https" or not base.hostname:
        raise UpdateValidationError("package_url_not_authorized_https")
    origin = normalize_https_origin(f"https://{base.hostname}" + (f":{base.port}" if base.port else ""))
    allowed = allowed_origins or {origin}
    if origin not in allowed:
        raise UpdateValidationError("package_origin_not_authorized")
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
        with os.fdopen(fd, "wb") as out, open_allowed_https_url(request, allowed, timeout=20) as response:
            final = urllib.parse.urlparse(response.geturl())
            final_origin = normalize_https_origin(f"https://{final.hostname}" + (f":{final.port}" if final.port else "")) if final.scheme == "https" and final.hostname else ""
            if final_origin not in allowed:
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
