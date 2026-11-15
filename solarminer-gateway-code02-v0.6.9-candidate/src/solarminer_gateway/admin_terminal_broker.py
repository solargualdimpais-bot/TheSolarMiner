"""Owner-authenticated root PTY broker for the separately isolated admin terminal."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("SOLARMINER_DB_PATH", "/var/lib/solarminer/gateway.db"))
MAX_FRAME = 16_384
SESSION_CHECK_SECONDS = 15
MAX_SESSION_SECONDS = 2 * 60 * 60


def _send(message: dict) -> None:
    sys.stdout.buffer.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
    sys.stdout.buffer.flush()


def _read_owner(token: str) -> str | None:
    if not token or len(token) > 512:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    try:
        uri = DB_PATH.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=3)) as conn:
            row = conn.execute("""SELECT s.user_id,s.credential_version,s.expires_at,s.revoked_at,
                    u.role,u.status,u.credential_version,d.status,
                    EXISTS(SELECT 1 FROM user_devices ud WHERE ud.user_id=u.id
                           AND ud.device_id=d.id AND ud.status='active')
                FROM sessions s JOIN users u ON u.id=s.user_id JOIN devices d ON d.id=s.device_id
                WHERE s.token_sha256=?""", (digest,)).fetchone()
        if not row:
            return None
        user_id, session_version, expires_at, revoked_at, role, user_status, user_version, device_status, associated = row
        if (revoked_at is not None or int(expires_at) < int(time.time()) or role != "owner"
                or user_status != "active" or device_status != "active" or not associated
                or int(session_version) != int(user_version)):
            return None
        return str(user_id)
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return None


def _audit(actor: str, action: str, outcome: str) -> None:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with closing(sqlite3.connect(DB_PATH, timeout=3)) as conn:
            with conn:
                conn.execute("INSERT INTO audit(occurred_at,actor_user_id,action,target,outcome,details_json) VALUES(?,?,?,?,?,?)",
                             (stamp, actor, action, "owner_root_shell", outcome, "{}"))
    except sqlite3.Error:
        # If an audit record cannot be written, privileged execution must fail closed.
        raise


def _read_frame(buffer: bytearray) -> dict | None:
    while b"\n" not in buffer:
        import select
        ready, _, _ = select.select([sys.stdin.fileno()], [], [], 1)
        if not ready:
            return None
        chunk = os.read(sys.stdin.fileno(), 4096)
        if not chunk:
            raise EOFError
        buffer.extend(chunk)
        if len(buffer) > MAX_FRAME:
            raise ValueError("frame_too_large")
    line, _, remainder = buffer.partition(b"\n")
    buffer[:] = remainder
    if len(line) > MAX_FRAME:
        raise ValueError("frame_too_large")
    value = json.loads(line.decode("utf-8"))
    return value if isinstance(value, dict) else None


def _read_initial() -> tuple[dict, bytearray]:
    buffer = bytearray()
    while b"\n" not in buffer:
        chunk = os.read(sys.stdin.fileno(), 4096)
        if not chunk:
            raise EOFError
        buffer.extend(chunk)
        if len(buffer) > MAX_FRAME:
            raise ValueError("frame_too_large")
    line, _, remainder = buffer.partition(b"\n")
    value = json.loads(line.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("invalid_auth_frame")
    return value, bytearray(remainder)


def run() -> int:
    import fcntl
    import pty
    import select
    import signal
    import struct
    import termios

    actor = None
    child = master = None
    audit_started = False
    try:
        auth, incoming = _read_initial()
        if not isinstance(auth, dict) or auth.get("type") != "authenticate":
            _send({"type": "error", "data": "Autenticação Owner obrigatória."})
            return 1
        token = auth.get("token")
        actor = _read_owner(token) if isinstance(token, str) else None
        if not actor:
            _send({"type": "error", "data": "Sessão Owner inválida, expirada ou revogada."})
            return 1
        _audit(actor, "system.admin_terminal.started", "success")
        audit_started = True
        master, slave = pty.openpty()
        fcntl_size = struct.pack("HHHH", 24, 100, 0, 0)
        try:
            fcntl.ioctl(slave, termios.TIOCSWINSZ, fcntl_size)
        except OSError:
            pass
        child = os.fork()
        if child == 0:
            try:
                os.close(master)
                os.setsid()
                fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
                for fd in (0, 1, 2):
                    os.dup2(slave, fd)
                if slave > 2:
                    os.close(slave)
                os.chdir("/root")
                os.environ.clear()
                os.environ.update({"HOME": "/root", "USER": "root", "LOGNAME": "root",
                                   "SHELL": "/bin/bash", "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                                   "TERM": "xterm-256color"})
                os.execv("/bin/bash", ["/bin/bash", "--noprofile", "--norc", "-i"])
            except BaseException:
                os._exit(127)
        os.close(slave)
        _send({"type": "ready", "data": "Terminal administrativo root ativo. A sessão é auditada e termina ao revogar ou expirar o acesso Owner."})
        started = time.monotonic()
        last_check = started
        last_activity = started
        while True:
            now = time.monotonic()
            if now - last_check >= SESSION_CHECK_SECONDS:
                if now - started >= MAX_SESSION_SECONDS or not _read_owner(token):
                    _send({"type": "error", "data": "A autorização Owner terminou; terminal administrativo fechado."})
                    break
                last_check = now
            ready, _, _ = select.select([sys.stdin.fileno(), master], [], [], 1)
            if sys.stdin.fileno() in ready:
                while True:
                    try:
                        message = _read_frame(incoming)
                    except (EOFError, ValueError, json.JSONDecodeError):
                        message = {"type": "close"}
                    if message is None:
                        break
                    kind = message.get("type")
                    if kind == "close":
                        break
                    if kind == "input":
                        data = message.get("data")
                        if not isinstance(data, str) or len(data.encode("utf-8")) > 8192:
                            _send({"type": "error", "data": "Entrada demasiado longa."})
                        else:
                            os.write(master, data.encode("utf-8"))
                            last_activity = now
                    elif kind == "resize":
                        rows = max(8, min(100, int(message.get("rows", 24))))
                        cols = max(20, min(240, int(message.get("cols", 100))))
                        import fcntl
                        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
                if message and message.get("type") == "close":
                    break
            if master in ready:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    chunk = b""
                if not chunk:
                    break
                _send({"type": "output", "data": chunk.decode("utf-8", errors="replace")})
                last_activity = now
            if now - last_activity > 30 * 60:
                _send({"type": "error", "data": "Terminal administrativo fechado por inatividade."})
                break
        _send({"type": "exit", "code": 0})
        return 0
    except (EOFError, BrokenPipeError):
        return 0
    except Exception as exc:
        try:
            _send({"type": "error", "data": f"Terminal administrativo recusado: {type(exc).__name__}."})
        except Exception:
            pass
        return 1
    finally:
        if child:
            try:
                os.killpg(child, signal.SIGTERM)
                os.waitpid(child, 0)
            except (OSError, ChildProcessError):
                pass
        if master is not None:
            try:
                os.close(master)
            except OSError:
                pass
        if actor and audit_started:
            try:
                _audit(actor, "system.admin_terminal.closed", "success")
            except sqlite3.Error:
                pass


if __name__ == "__main__":
    raise SystemExit(run())
