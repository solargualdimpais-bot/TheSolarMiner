"""Queue sanitized Gateway errors and report them to the fixed SolarMiner GitHub repo.

Reports are public GitHub issues. This module intentionally sends structured,
sanitized diagnostics only; raw tracebacks, request data and log files are never
uploaded.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPOSITORY = "solargualdimpais-bot/TheSolarMiner"
ISSUES_URL = f"https://api.github.com/repos/{REPOSITORY}/issues"
TOKEN_PATH = Path(os.environ.get("SOLARMINER_GITHUB_TOKEN_FILE", "/etc/solarminer/github-issues-token"))
QUEUE_PATH = Path(os.environ.get("SOLARMINER_ERROR_QUEUE", "/var/lib/solarminer/error-reports.ndjson"))
MAX_QUEUE_BYTES = 2 * 1024 * 1024
MAX_REPORTS_PER_ISSUE = 100
_LOCK = threading.Lock()

_SECRET_RE = re.compile(
    r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?|(?:access[_ -]?token|refresh[_ -]?token|token|password|passwd|secret|private[_ -]?key|api[_ -]?key)\s*[:=]\s*)[^\s,;]+"
)
_GITHUB_TOKEN_RE = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")
_URL_RE = re.compile(r"https?://[^\s\]\[()<>\"']+", re.IGNORECASE)
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6_RE = re.compile(r"(?i)(?<![0-9a-f:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![0-9a-f:])")
_MAC_RE = re.compile(r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b")
_PATH_RE = re.compile(r"(?:(?:[A-Za-z]:)?[/\\](?:[^\s:/\\]+[/\\])+)[^\s,;]+")
_USERNAME_RE = re.compile(r"(?i)(username|user_id|device_id|account_id)\s*[:=]\s*[^\s,;]+")


def sanitize_message(message: object) -> str:
    """Remove likely credentials, URLs, network/device identifiers and paths."""
    value = str(message)
    value = _SECRET_RE.sub(r"\1[REDACTED]", value)
    value = _GITHUB_TOKEN_RE.sub("[REDACTED]", value)
    value = _URL_RE.sub("[URL]", value)
    value = _MAC_RE.sub("[MAC]", value)
    value = _IPV4_RE.sub("[IP]", value)
    value = _IPV6_RE.sub("[IP]", value)
    value = _USERNAME_RE.sub(r"\1=[REDACTED]", value)
    value = _PATH_RE.sub("[PATH]", value)
    return " ".join(value.split())[:500]


def _safe_record(record: logging.LogRecord) -> dict[str, Any]:
    try:
        message = record.getMessage()
    except Exception:
        message = "log_message_format_error"
    exception_type = None
    if record.exc_info and record.exc_info[0]:
        exception_type = str(record.exc_info[0].__name__)[:80]
    safe_logger = re.sub(r"[^A-Za-z0-9_.-]", "_", record.name)[:100]
    return {
        "id": str(uuid.uuid4()),
        "occurred_at": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
        "level": record.levelname[:16],
        "component": safe_logger,
        "message": sanitize_message(message),
        "exception_type": exception_type,
    }


def enqueue_record(record: logging.LogRecord, path: Path = QUEUE_PATH) -> None:
    """Persist one sanitized ERROR+ diagnostic; never disrupt application logging."""
    try:
        item = _safe_record(record)
        payload = (json.dumps(item, ensure_ascii=True, separators=(",", ":")) + "\n").encode()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with _LOCK:
            if path.exists() and path.stat().st_size + len(payload) > MAX_QUEUE_BYTES:
                # Retain the newest diagnostics when offline for a long period.
                lines = path.read_bytes().splitlines()[-4000:]
                path.write_bytes(b"\n".join(lines) + (b"\n" if lines else b""))
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0), 0o600)
            try:
                os.write(fd, payload)
            finally:
                os.close(fd)
            os.chmod(path, 0o600)
    except Exception:
        # Diagnostics must never cause a request or the Gateway process to fail.
        return


class ErrorQueueHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno >= logging.ERROR:
            enqueue_record(record)


def install_error_queue_handler() -> None:
    root = logging.getLogger()
    if not any(isinstance(handler, ErrorQueueHandler) for handler in root.handlers):
        root.addHandler(ErrorQueueHandler(level=logging.ERROR))


def _load_batch(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    raw = path.read_bytes()
    lines = raw.splitlines(keepends=True)
    batch: list[dict[str, Any]] = []
    consumed = bytearray()
    for raw_line in lines[:MAX_REPORTS_PER_ISSUE]:
        line = raw_line.rstrip(b"\r\n")
        try:
            item = json.loads(line)
            if isinstance(item, dict) and set(item) == {"id", "occurred_at", "level", "component", "message", "exception_type"}:
                batch.append(item)
                consumed.extend(raw_line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Invalid local queue entries are discarded when a valid batch is committed.
            consumed.extend(raw_line)
    return batch, bytes(consumed)


def _create_issue(batch: list[dict[str, Any]], token: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest = hashlib.sha256("".join(item["id"] for item in batch).encode()).hexdigest()[:12]
    title = f"Automated Gateway diagnostics {day} ({len(batch)} errors, {digest})"
    body = [
        "Automated sanitized error report from a SolarMiner Gateway.",
        "\nPrivacy: this report contains no raw log files, tracebacks, HTTP request data, credentials, IP/MAC addresses or user/device IDs.",
        f"\nGateway package version: {sanitize_message(os.environ.get('SOLARMINER_PACKAGE_VERSION', 'unknown'))}.",
        "\nPlease triage and link any fix to this issue. This issue was created by the Gateway error reporter.",
        "\n```json",
        json.dumps(batch, ensure_ascii=True, indent=2),
        "```",
    ]
    request = urllib.request.Request(
        ISSUES_URL,
        data=json.dumps({"title": title, "body": "\n".join(body)}).encode(),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SolarMiner-Gateway-Error-Reporter",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    # The fixed API endpoint must never redirect with an Authorization header.
    opener = urllib.request.build_opener(_NoRedirectHandler())
    with opener.open(request, timeout=15) as response:
        if response.status != 201:
            raise RuntimeError("github_issue_create_failed")
        payload = json.loads(response.read(64 * 1024))
    issue_url = payload.get("html_url")
    if not isinstance(issue_url, str) or not issue_url.startswith(f"https://github.com/{REPOSITORY}/issues/"):
        raise RuntimeError("github_issue_response_invalid")
    return issue_url


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect_rejected", headers, fp)


def flush_reports(path: Path = QUEUE_PATH, token_path: Path = TOKEN_PATH) -> dict[str, Any]:
    """Send one batch to GitHub; retain queued reports on every failure."""
    if not path.exists() or path.stat().st_size == 0:
        return {"status": "empty", "sent": 0}
    if not token_path.exists():
        return {"status": "not_configured", "sent": 0}
    token = token_path.read_text(encoding="utf-8").strip()
    if not token or len(token) > 512 or any(char.isspace() for char in token):
        raise ValueError("github_token_invalid")
    batch, consumed = _load_batch(path)
    if not batch:
        return {"status": "empty", "sent": 0}
    url = _create_issue(batch, token)
    with _LOCK:
        current = path.read_bytes()
        # Remove only the exact prefix that was sent; preserve concurrent errors.
        if current.startswith(consumed):
            remainder = current[len(consumed):]
            temp = path.with_suffix(path.suffix + ".tmp")
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
            try:
                os.write(fd, remainder)
            finally:
                os.close(fd)
            os.replace(temp, path)
    return {"status": "sent", "sent": len(batch), "issue_url": url}


def main() -> int:
    try:
        result = flush_reports()
    except (OSError, ValueError, urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        # Never print the token, request headers, or remote response body.
        print(f"SolarMiner error report not sent: {type(exc).__name__}")
        return 1
    print(f"SolarMiner error reports: {result['status']} ({result['sent']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
