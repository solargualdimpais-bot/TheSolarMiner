"""Client for the narrowly scoped Intelligence bootstrap broker."""
from __future__ import annotations

import json
import os
import socket
from typing import Any

DEFAULT_SOCKET_PATH = "/run/solarminer/intelligence-bootstrap.sock"


def request_start() -> dict[str, Any]:
    path = os.environ.get("SOLARMINER_INTELLIGENCE_BOOTSTRAP_SOCKET", DEFAULT_SOCKET_PATH)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(15)
        client.connect(path)
        client.sendall(b'{"action":"start"}\n')
        client.shutdown(socket.SHUT_WR)
        response = bytearray()
        while len(response) <= 1024:
            chunk = client.recv(1024)
            if not chunk:
                break
            response.extend(chunk)
            if b"\n" in chunk:
                break
    if len(response) > 1024:
        raise RuntimeError("intelligence_bootstrap_response_too_large")
    try:
        result = json.loads(response.decode("utf-8").split("\n", 1)[0])
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("intelligence_bootstrap_response_invalid") from exc
    if not isinstance(result, dict) or result.get("status") != "ok" or result.get("queued") is not True:
        raise RuntimeError("intelligence_bootstrap_start_failed")
    return result
