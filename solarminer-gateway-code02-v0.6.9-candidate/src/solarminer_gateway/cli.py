"""Local, interactive recovery commands. No recovery secret is accepted as argv/env."""
from __future__ import annotations

import getpass
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from . import recovery

SERVICE_NAME = "solarminer-gateway.service"
GATEWAY_PRIVATE_IDENTITY_PATH = Path("/var/lib/solarminer/gateway-identity.key")
GATEWAY_PUBLIC_IDENTITY_PATH = Path("/etc/solarminer/gateway-identity.pub.pem")


def _require_root() -> None:
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        raise PermissionError("run this local command with real OS administrator privileges (root)")


def _require_tty() -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise recovery.RecoveryError("interactive_terminal_required_secrets_will_not_be_read_from_pipes")


def _require_service_stopped() -> None:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        raise recovery.RecoveryError("cannot_prove_service_is_stopped_systemctl_unavailable")
    result = subprocess.run([systemctl, "is-active", SERVICE_NAME], capture_output=True, text=True, check=False)
    state = result.stdout.strip()
    if result.returncode == 0 or state == "active":
        raise recovery.RecoveryError("stop_solarminer_gateway_service_before_local_recovery")
    if state not in {"inactive", "failed"}:
        raise recovery.RecoveryError("cannot_prove_service_is_stopped")


def _read_pem() -> str:
    print("Paste the Ed25519 public-key PEM. Finish with an empty line:")
    lines: list[str] = []
    while True:
        line = input()
        if not line:
            break
        lines.append(line)
        if len(lines) > 64:
            raise recovery.RecoveryError("public_key_input_too_long")
    pem = "\n".join(lines) + "\n"
    if not pem.strip():
        raise recovery.RecoveryError("public_key_required")
    return pem


def _challenge(purpose: str, owner_id: str, device_id: str | None = None) -> tuple[str, str]:
    challenge = secrets.token_hex(32)
    message = recovery.device_proof_message(purpose, owner_id, challenge, device_id)
    print("\nSign the following exact UTF-8 message with the device's Ed25519 private key.")
    print("The private key must remain on the device and must never be pasted here:")
    print(message.decode("utf-8"))
    signature = input("Device signature (hex): ").strip()
    return challenge, signature


def _new_password() -> str:
    first = getpass.getpass("New owner password (12–1024 characters): ")
    second = getpass.getpass("Repeat new owner password: ")
    if first != second:
        raise recovery.RecoveryError("passwords_do_not_match")
    if not 12 <= len(first) <= 1024:
        raise recovery.RecoveryError("new_password_must_be_12_to_1024_characters")
    return first


def provision_gateway_identity() -> str:
    """Ensure the Gateway identity exists and has service-safe ownership/modes."""
    from .identity import identity_fingerprint, provision_identity
    provision_identity(GATEWAY_PRIVATE_IDENTITY_PATH, GATEWAY_PUBLIC_IDENTITY_PATH)
    shutil.chown(GATEWAY_PRIVATE_IDENTITY_PATH, user="solarminer", group="solarminer")
    os.chmod(GATEWAY_PRIVATE_IDENTITY_PATH, 0o600)
    shutil.chown(GATEWAY_PUBLIC_IDENTITY_PATH, user="root", group="root")
    os.chmod(GATEWAY_PUBLIC_IDENTITY_PATH, 0o644)
    return identity_fingerprint(GATEWAY_PRIVATE_IDENTITY_PATH, GATEWAY_PUBLIC_IDENTITY_PATH)


def _display_recovery_key_once(key: str, completion_lines: tuple[str, ...] = ()) -> None:
    try:
        for line in completion_lines:
            print(line)
        print("\nRECOVERY KEY — DISPLAYED ONCE. STORE IT OFFLINE; IT WILL NOT BE SHOWN AGAIN.")
        print(key)
        print("Do not photograph, email, paste into tickets, or save this output in logs.")
        sys.stdout.flush()
    except (BrokenPipeError, OSError) as exc:
        raise recovery.RecoveryError(
            "operation_committed_but_replacement_key_delivery_failed_use_emergency_reset"
        ) from exc


def run_recovery() -> None:
    _require_root()
    _require_tty()
    _require_service_stopped()
    username = input("Owner username: ").strip()
    owner = recovery.lookup_active_owner(username)
    recovery_key = getpass.getpass("Offline recovery key (input hidden): ")
    recovery.precheck_recovery_key(owner["id"], recovery_key)
    print("This changes the owner password, invalidates old sessions, and revokes old device associations.")
    if input("Type RECOVER-OWNER to continue: ") != "RECOVER-OWNER":
        raise recovery.RecoveryError("owner_recovery_cancelled")
    public_key_pem = _read_pem()
    mac = input("New device MAC metadata (not an identity factor): ").strip()
    challenge, signature = _challenge("recovery", owner["id"])
    new_password = _new_password()
    result = recovery.recover_owner(owner["id"], recovery_key, new_password, public_key_pem, mac, challenge, signature)
    _display_recovery_key_once(result["recovery_key"], (f"Owner recovery completed. New device ID: {result['device_id']}",))


def run_recovery_setup() -> None:
    _require_root()
    _require_tty()
    _require_service_stopped()
    username = input("Active owner username: ").strip()
    owner = recovery.lookup_active_owner(username)
    device_id = input("ID of an active device already associated with this owner: ").strip()
    recovery.lookup_active_device(owner["id"], device_id)
    print("This creates or rotates the offline recovery key; any previous key becomes invalid.")
    if input("Type SETUP-OR-ROTATE to continue: ") != "SETUP-OR-ROTATE":
        raise recovery.RecoveryError("recovery_key_setup_cancelled")
    current_password = getpass.getpass("Current owner password (input hidden): ")
    challenge, signature = _challenge("setup", owner["id"], device_id)
    key = recovery.setup_recovery_key(owner["id"], current_password, device_id, challenge, signature)
    _display_recovery_key_once(key, (f"Recovery key configured for owner {owner['username']}.",))


def run_emergency_reset() -> None:
    _require_root()
    _require_tty()
    _require_service_stopped()
    print("EMERGENCY OWNER RECOVERY: preserves existing data but replaces the owner's password and device association.")
    print("A protected database backup will be created before any mutation.")
    confirmation = input("Type EMERGENCY-RESET to continue: ")
    if confirmation != "EMERGENCY-RESET":
        raise recovery.RecoveryError("emergency_recovery_cancelled")
    username = input("Active owner username to recover: ").strip()
    owner = recovery.lookup_active_owner(username)
    public_key_pem = _read_pem()
    mac = input("New device MAC metadata (not an identity factor): ").strip()
    challenge, signature = _challenge("emergency", owner["id"])
    new_password = _new_password()
    result = recovery.emergency_reset(owner["id"], new_password, public_key_pem, mac, challenge, signature)
    _display_recovery_key_once(result["recovery_key"], (
        f"Emergency recovery completed. New device ID: {result['device_id']}",
        f"Protected pre-operation backup: {result['backup_path']}",
    ))


def run_bootstrap_token() -> None:
    """Rotate and display a fresh one-time token for first Owner setup."""
    _require_root()
    _require_tty()
    _require_service_stopped()
    from . import app as gateway_app
    gateway_app.initialize()
    with sqlite3.connect(gateway_app.DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        owner = conn.execute("SELECT 1 FROM users WHERE role='owner' AND status='active' LIMIT 1").fetchone()
        if owner:
            raise recovery.RecoveryError("an_active_owner_already_exists")
        row = conn.execute("SELECT consumed_at FROM bootstrap WHERE id=1").fetchone()
        if row and row["consumed_at"] is not None:
            raise recovery.RecoveryError("bootstrap_was_already_consumed; owner recovery is required")
        if input("Type ISSUE-OWNER-BOOTSTRAP-TOKEN to rotate and display a one-time token: ") != "ISSUE-OWNER-BOOTSTRAP-TOKEN":
            raise recovery.RecoveryError("bootstrap_token_rotation_cancelled")
        # Signed package updates activate an extracted release tree and do not
        # execute dpkg maintainer scripts. Provision the identity here as well
        # so an upgraded Gateway can complete remote Owner bootstrap safely.
        fingerprint = provision_gateway_identity()
        raw = secrets.token_urlsafe(32)
        now = int(time.time())
        expires = now + gateway_app.BOOTSTRAP_TTL
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT OR REPLACE INTO bootstrap(id,token_sha256,expires_at,consumed_at,state) VALUES(1,?,?,NULL,'pending')",
                     (gateway_app.token_hash(raw), expires))
        conn.execute("UPDATE system_state SET value='BOOTSTRAP_PENDING' WHERE key='bootstrap_state'")
        conn.commit()
    gateway_app.BOOTSTRAP_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(gateway_app.BOOTSTRAP_PATH, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(raw + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(gateway_app.BOOTSTRAP_PATH, 0o600)
    print("Use este token uma única vez na PWA oficial. Expira em 15 minutos; não o partilhes nem o guardes em logs:")
    print(raw)
    print(f"Gateway identity SHA-256: {fingerprint}")


def run_owner_password() -> None:
    """Set the one-time first-owner password locally; input is intentionally visible."""
    _require_root()
    _require_tty()
    from . import app as gateway_app
    gateway_app.initialize()
    print("Define a palavra-passe inicial do Owner. O texto aparece enquanto escreves.")
    first = input("Palavra-passe inicial (8 a 128 caracteres): ")
    second = input("Repete a palavra-passe: ")
    if first != second:
        raise recovery.RecoveryError("passwords_do_not_match")
    if not 8 <= len(first) <= 128:
        raise recovery.RecoveryError("owner_password_must_be_8_to_128_characters")
    with sqlite3.connect(gateway_app.DB_PATH, timeout=10, isolation_level=None) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        owner = conn.execute("SELECT 1 FROM users WHERE role='owner' AND status='active' LIMIT 1").fetchone()
        row = conn.execute("SELECT consumed_at FROM bootstrap WHERE id=1").fetchone()
        if owner:
            conn.rollback()
            raise recovery.RecoveryError("an_active_owner_already_exists")
        if not row or row["consumed_at"] is not None:
            conn.rollback()
            raise recovery.RecoveryError("initial_owner_setup_is_unavailable")
        password_hash = gateway_app.PASSWORDS.hash(first)
        conn.execute("UPDATE bootstrap SET setup_password_hash=?,state='local_password_ready' WHERE id=1 AND consumed_at IS NULL", (password_hash,))
        conn.execute("UPDATE system_state SET value='BOOTSTRAP_PENDING' WHERE key='bootstrap_state'")
        gateway_app.audit(conn, None, "bootstrap.owner_password_configured", None, "success")
        conn.commit()
    try:
        gateway_app.BOOTSTRAP_PATH.unlink(missing_ok=True)
    except OSError:
        pass
    first = second = ""
    print("Palavra-passe inicial configurada. Abre o PWA, indica o endpoint HTTPS e usa-a uma vez no primeiro registo Owner.")


def run_identity_fingerprint() -> None:
    _require_root()
    from .identity import identity_fingerprint
    print(identity_fingerprint(Path("/var/lib/solarminer/gateway-identity.key"), Path("/etc/solarminer/gateway-identity.pub.pem")))


def run_github_error_token() -> None:
    """Store a narrowly scoped GitHub issue token without echoing it to the terminal."""
    _require_root()
    _require_tty()
    import tempfile
    from .error_reporting import TOKEN_PATH

    first = getpass.getpass("Fine-grained GitHub token (input hidden): ")
    second = getpass.getpass("Repeat GitHub token: ")
    if first != second:
        raise recovery.RecoveryError("github_tokens_do_not_match")
    if not 20 <= len(first) <= 512 or any(char.isspace() for char in first):
        raise recovery.RecoveryError("github_token_format_invalid")
    if TOKEN_PATH.parent != Path("/etc/solarminer"):
        raise recovery.RecoveryError("github_token_path_not_supported")
    if TOKEN_PATH.parent.is_symlink():
        raise recovery.RecoveryError("github_token_directory_must_not_be_symlink")
    TOKEN_PATH.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".github-issues-token.", dir=TOKEN_PATH.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(first + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(temporary, 0, __import__("grp").getgrnam("solarminer").gr_gid)
        os.chmod(temporary, 0o640)
        os.replace(temporary, TOKEN_PATH)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    first = second = ""
    print("Token guardado com permissões root:solarminer 0640. O envio automático começa no próximo ciclo horário.")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="solarminer-gateway", description="Local SolarMiner Gateway recovery tools")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("recovery", help="recover an owner using the offline one-time recovery key")
    subparsers.add_parser("recovery-setup", help="create or rotate a recovery key while owner access still works")
    subparsers.add_parser("emergency-reset", help="recover an owner using OS-root authority and a protected backup")
    subparsers.add_parser("bootstrap-token", help="rotate and display a one-time token for initial Owner setup")
    subparsers.add_parser("owner-password", help="set the visible, one-time first-owner password from the local console")
    subparsers.add_parser("identity-fingerprint", help="display the provisioned Gateway Ed25519 identity fingerprint")
    subparsers.add_parser("github-error-token", help="store the GitHub Issues token for sanitized automatic error reports")
    args = parser.parse_args()
    handlers = {
        "recovery": run_recovery,
        "recovery-setup": run_recovery_setup,
        "emergency-reset": run_emergency_reset,
        "bootstrap-token": run_bootstrap_token,
        "owner-password": run_owner_password,
        "identity-fingerprint": run_identity_fingerprint,
        "github-error-token": run_github_error_token,
    }
    try:
        handlers[args.command]()
    except sqlite3.Error:
        print("Recovery not completed: a database operation failed; no success is claimed.", file=sys.stderr)
        raise SystemExit(2) from None
    except recovery.RecoveryError as exc:
        if "operation_committed_but_replacement_key_delivery_failed" in str(exc):
            print("Recovery committed but the replacement key could not be delivered. Use emergency-reset to rotate it again.", file=sys.stderr)
        else:
            print(f"Recovery not completed: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    except (PermissionError, OSError) as exc:
        print(f"Recovery not completed: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
