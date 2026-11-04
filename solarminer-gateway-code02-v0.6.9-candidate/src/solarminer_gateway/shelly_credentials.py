"""Local envelope encryption for optional Shelly HTTP credentials."""
from __future__ import annotations

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def _cipher(data_dir: Path) -> Fernet:
    directory = Path(data_dir)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    key_path = directory / "shelly-credentials.key"
    if key_path.is_symlink():
        raise ValueError("shelly_credential_key_path_unsafe")
    try:
        key = key_path.read_bytes()
    except FileNotFoundError:
        generated = Fernet.generate_key()
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            key = key_path.read_bytes()
        else:
            with os.fdopen(fd, "wb") as handle:
                handle.write(generated)
                handle.flush()
                os.fsync(handle.fileno())
            key = generated
    if not key or len(key) > 256:
        raise ValueError("shelly_credential_key_invalid")
    try:
        return Fernet(key)
    except (TypeError, ValueError) as exc:
        raise ValueError("shelly_credential_key_invalid") from exc


def seal(data_dir: Path, username: str, password: str) -> bytes:
    if not isinstance(username, str) or len(username) > 128:
        raise ValueError("shelly_username_invalid")
    if not isinstance(password, str) or len(password) > 256:
        raise ValueError("shelly_password_invalid")
    if not username and not password:
        return b""
    payload = json.dumps({"username": username, "password": password}, separators=(",", ":")).encode()
    return _cipher(data_dir).encrypt(payload)


def open_credentials(data_dir: Path, ciphertext: bytes | memoryview | None) -> dict[str, str]:
    if not ciphertext:
        return {"username": "", "password": ""}
    try:
        payload = _cipher(data_dir).decrypt(bytes(ciphertext))
        value = json.loads(payload)
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("shelly_credentials_unavailable") from exc
    if not isinstance(value, dict) or set(value) != {"username", "password"}:
        raise ValueError("shelly_credentials_unavailable")
    return {"username": str(value["username"]), "password": str(value["password"])}
