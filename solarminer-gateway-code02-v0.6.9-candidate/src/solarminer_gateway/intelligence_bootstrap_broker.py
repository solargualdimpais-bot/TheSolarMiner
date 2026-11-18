"""Systemd socket broker exposing only the fixed Intelligence bootstrap action."""
from __future__ import annotations

import json
import subprocess
import sys

MAX_REQUEST = 1024


def handle_request(raw: bytes, runner=subprocess.run) -> dict[str, object]:
    if len(raw) > MAX_REQUEST or not raw.endswith(b"\n"):
        return {"status": "error", "reason": "request_invalid"}
    try:
        request = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return {"status": "error", "reason": "request_invalid"}
    if not isinstance(request, dict) or set(request) != {"action"} or request.get("action") != "start":
        return {"status": "error", "reason": "request_invalid"}
    try:
        result = runner(["/usr/bin/systemctl", "start", "--no-block",
                         "solarminer-intelligence-bootstrap.service"],
                        capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "error", "reason": "intelligence_bootstrap_start_failed"}
    if result.returncode != 0:
        return {"status": "error", "reason": "intelligence_bootstrap_start_failed"}
    return {"status": "ok", "queued": True}


def run() -> int:
    raw = sys.stdin.buffer.readline(MAX_REQUEST + 1)
    response = handle_request(raw)
    sys.stdout.buffer.write(json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()
    return 0 if response.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(run())
