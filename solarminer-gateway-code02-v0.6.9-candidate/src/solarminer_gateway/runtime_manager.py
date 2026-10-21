"""Connector Manager-owned worker lifecycle (local development/runtime path).

This supervisor owns worker creation, readiness, bounded IPC, liveness checks and
termination. It does not claim OS isolation: production isolation additionally
requires a root-owned systemd unit and a dedicated Unix account.
"""
from __future__ import annotations
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from typing import Any
from .worker_ipc import request, IPCError

class WorkerRuntimeError(RuntimeError):
    pass

class ConnectorWorkerRuntime:
    def __init__(self, connector_id: str, timeout: float = 3.0, python: str | None = None):
        if not isinstance(connector_id, str) or not connector_id or len(connector_id) > 64 or not all(c.islower() or c.isdigit() or c == '-' for c in connector_id):
            raise ValueError("invalid_connector_id")
        if not 0.1 <= timeout <= 30:
            raise ValueError("invalid_worker_timeout")
        self.connector_id = connector_id
        self.timeout = timeout
        self.python = python or sys.executable
        self._tmp: tempfile.TemporaryDirectory[str] | None = None
        self.socket_path: str | None = None
        self.process: subprocess.Popen[bytes] | None = None

    def start(self) -> dict[str, Any]:
        if self.process and self.process.poll() is None:
            return self.health()
        self._tmp = tempfile.TemporaryDirectory(prefix="smw-")
        self.socket_path = str(Path(self._tmp.name) / "w.sock")
        env = os.environ.copy()
        env["SOLARMINER_CONNECTOR_ID"] = self.connector_id
        # Use the installed package normally; include source path only when running from checkout.
        source_root = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = source_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        self.process = subprocess.Popen(
            [self.python, "-m", "solarminer_gateway.connector_worker", "--socket", self.socket_path,
             "--gateway-uid", str(os.getuid())], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, env=env,
            start_new_session=True,
        )
        deadline = time.monotonic() + self.timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.stop()
                raise WorkerRuntimeError("worker_exited_before_ready")
            try:
                result = self.health()
                return result
            except (OSError, IPCError, WorkerRuntimeError) as exc:
                last_error = exc
                time.sleep(0.02)
        self.stop()
        raise WorkerRuntimeError("worker_readiness_timeout") from last_error

    def call(self, operation: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.process or self.process.poll() is not None or not self.socket_path:
            raise WorkerRuntimeError("worker_not_running")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self.timeout)
                client.connect(self.socket_path)
                return request(client, operation, arguments or {}, timeout=self.timeout)
        except (OSError, IPCError) as exc:
            raise WorkerRuntimeError("worker_ipc_failed") from exc

    def health(self) -> dict[str, Any]:
        return self.call("health", {})

    def is_alive(self) -> bool:
        return bool(self.process and self.process.poll() is None)

    def stop(self) -> None:
        proc, self.process = self.process, None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait(timeout=2)
        if self._tmp:
            self._tmp.cleanup(); self._tmp = None
        self.socket_path = None

    def __enter__(self) -> "ConnectorWorkerRuntime":
        self.start(); return self

    def __exit__(self, *_: object) -> None:
        self.stop()
