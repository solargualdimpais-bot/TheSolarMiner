"""Root-owned, socket-activated broker for the narrow update helper interface."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import uuid

HELPER = "/usr/sbin/solarminer-update-apply"
UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def handle_request(raw: bytes, runner=subprocess.run) -> dict[str, object]:
    if len(raw) > 4096 or not raw.endswith(b"\n"):
        return {"status": "error", "reason": "request_invalid"}
    try:
        request = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return {"status": "error", "reason": "request_invalid"}
    if not isinstance(request, dict) or request.get("action") not in {"preflight", "enqueue"}:
        return {"status": "error", "reason": "request_invalid"}
    action = request["action"]
    if action == "preflight":
        if set(request) != {"action"}:
            return {"status": "error", "reason": "request_invalid"}
        args = [HELPER, "--preflight"]
    else:
        if set(request) != {"action", "operation_id"} or not isinstance(request.get("operation_id"), str):
            return {"status": "error", "reason": "request_invalid"}
        operation_id = request["operation_id"]
        if not UUID_PATTERN.fullmatch(operation_id):
            return {"status": "error", "reason": "operation_id_invalid"}
        try:
            if str(uuid.UUID(operation_id)) != operation_id:
                return {"status": "error", "reason": "operation_id_invalid"}
        except ValueError:
            return {"status": "error", "reason": "operation_id_invalid"}
        args = [HELPER, "--enqueue", operation_id]
    try:
        result = runner(args, capture_output=True, text=True, timeout=12, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "error", "reason": "update_helper_unavailable_or_timed_out"}
    raw_result = result.stdout if result.returncode == 0 else result.stderr
    try:
        payload = json.loads(raw_result or "")
    except (ValueError, TypeError):
        return {"status": "error", "reason": "update_helper_response_invalid"}
    if not isinstance(payload, dict):
        return {"status": "error", "reason": "update_helper_response_invalid"}
    if result.returncode != 0 or payload.get("status") == "error":
        reason = payload.get("reason")
        if not isinstance(reason, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,180}", reason):
            reason = "update_pipeline_failed"
        return {"status": "error", "reason": reason}
    allowed = {"status", "operation_id", "target_version", "health_check_seconds", "current_target", "recovery_timer"}
    return {key: value for key, value in payload.items() if key in allowed}


def main() -> int:
    request = sys.stdin.buffer.readline(4097)
    response = handle_request(request)
    sys.stdout.write(json.dumps(response, sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0 if response.get("status") != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
