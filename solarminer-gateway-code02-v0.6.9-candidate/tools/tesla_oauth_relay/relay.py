"""Minimal public callback handoff for a private SolarMiner Gateway.

The Gateway initiates OAuth and keeps the Tesla client secret. This service
accepts Tesla's browser redirect, retains the short-lived authorization code
in memory, and lets the Gateway retrieve it over an outbound HTTPS request.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field


SESSION_TTL_SECONDS = 600
MAX_SESSIONS = 64
MAX_CODE_LENGTH = 4096
MAX_STATE_LENGTH = 256
MAX_POLL_TOKEN_LENGTH = 256
MAX_ORIGIN_LENGTH = 512


@dataclass
class RelaySession:
    state_hash: str
    poll_token_hash: str
    origin: str
    expires_at: float
    code: str | None = None
    error: str | None = None


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str = Field(min_length=32, max_length=MAX_STATE_LENGTH)
    poll_token: str = Field(min_length=32, max_length=MAX_POLL_TOKEN_LENGTH)
    origin: str = Field(min_length=9, max_length=MAX_ORIGIN_LENGTH)


class SessionResult(BaseModel):
    ready: bool
    code: str | None = None
    error: str | None = None


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _valid_https_origin(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return False
    valid = bool(
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
    )
    if not valid or any(char.isspace() for char in value):
        return False
    try:
        expected = f"https://{parsed.netloc}"
        if value != expected or parsed.hostname.encode("idna").decode("ascii") != parsed.hostname.lower():
            return False
    except (UnicodeError, AttributeError):
        return False
    return True


def create_app(*, api_key: str | None = None) -> FastAPI:
    configured_key = api_key if api_key is not None else os.environ.get("SOLARMINER_RELAY_API_KEY", "")
    if len(configured_key) < 32:
        raise ValueError("SOLARMINER_RELAY_API_KEY must contain at least 32 characters")

    app = FastAPI(title="SolarMiner Tesla OAuth Relay", docs_url=None, redoc_url=None, openapi_url=None)
    lock = threading.Lock()
    sessions: dict[str, RelaySession] = {}

    def cleanup(now: float) -> None:
        expired = [key for key, value in sessions.items() if value.expires_at <= now]
        for key in expired:
            sessions.pop(key, None)

    def require_api_key(value: str | None) -> None:
        if not value or not hmac.compare_digest(value, configured_key):
            raise HTTPException(status_code=401, detail="relay_auth_required")

    @app.get("/v1/health")
    def authenticated_health(authorization: str | None = Header(default=None)) -> dict[str, str]:
        require_api_key(authorization.removeprefix("Bearer ") if authorization else None)
        return {"status": "ok"}

    def require_session(state: str, poll_token: str | None) -> tuple[str, RelaySession]:
        if not state or len(state) > MAX_STATE_LENGTH:
            raise HTTPException(status_code=404, detail="relay_session_not_found")
        state_hash = _digest(state)
        with lock:
            cleanup(time.time())
            session = sessions.get(state_hash)
            if session is None:
                raise HTTPException(status_code=404, detail="relay_session_not_found")
            if not poll_token or not hmac.compare_digest(_digest(poll_token), session.poll_token_hash):
                raise HTTPException(status_code=404, detail="relay_session_not_found")
            return state_hash, session

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/sessions", status_code=201)
    def register_session(
        payload: SessionCreate,
        authorization: str | None = Header(default=None),
    ) -> dict[str, int]:
        require_api_key(authorization.removeprefix("Bearer ") if authorization else None)
        if not all(char.isalnum() or char in "_-" for char in payload.state):
            raise HTTPException(status_code=422, detail="relay_state_invalid")
        if not all(char.isalnum() or char in "_-" for char in payload.poll_token):
            raise HTTPException(status_code=422, detail="relay_poll_token_invalid")
        if not _valid_https_origin(payload.origin):
            raise HTTPException(status_code=422, detail="relay_origin_must_be_https_origin")
        state_hash = _digest(payload.state)
        now = time.time()
        with lock:
            cleanup(now)
            if state_hash in sessions:
                raise HTTPException(status_code=409, detail="relay_state_already_registered")
            if len(sessions) >= MAX_SESSIONS:
                raise HTTPException(status_code=503, detail="relay_session_capacity_reached")
            sessions[state_hash] = RelaySession(
                state_hash=state_hash,
                poll_token_hash=_digest(payload.poll_token),
                origin=payload.origin,
                expires_at=now + SESSION_TTL_SECONDS,
            )
        return {"expires_in": SESSION_TTL_SECONDS}

    @app.get("/oauth/callback", response_class=HTMLResponse)
    def oauth_callback(request: Request) -> HTMLResponse:
        state = request.query_params.get("state", "")
        if not state or len(state) > MAX_STATE_LENGTH:
            raise HTTPException(status_code=400, detail="relay_callback_invalid")
        state_hash = _digest(state)
        now = time.time()
        with lock:
            cleanup(now)
            session = sessions.get(state_hash)
            if session is None or session.code is not None or session.error is not None:
                raise HTTPException(status_code=400, detail="relay_callback_invalid_or_replayed")
            code = request.query_params.get("code")
            oauth_error = request.query_params.get("error")
            if code and len(code) <= MAX_CODE_LENGTH:
                session.code = code
            elif oauth_error:
                # Do not persist or render arbitrary provider-provided text.
                session.error = "access_denied" if oauth_error == "access_denied" else "authorization_failed"
            else:
                raise HTTPException(status_code=400, detail="relay_callback_missing_result")
            origin = session.origin

        safe_origin = json.dumps(origin)
        safe_state = json.dumps(state)
        body = (
            "<!doctype html><html lang=pt><meta charset=utf-8>"
            "<meta name=referrer content=no-referrer><meta name=viewport content='width=device-width'>"
            "<title>SolarMiner · Tesla</title><p>Resposta recebida. Volta ao SolarMiner para concluir.</p>"
            "<script>"
            f"if(window.opener)window.opener.postMessage({{type:'solarminer-tesla-relay',state:{safe_state}}},{safe_origin});"
            "</script></html>"
        )
        return HTMLResponse(
            body,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",
            },
        )

    @app.get("/v1/sessions/{state}", response_model=SessionResult)
    def get_session_result(
        state: str,
        authorization: str | None = Header(default=None),
    ) -> SessionResult:
        poll_token = authorization.removeprefix("Bearer ") if authorization else None
        _, session = require_session(state, poll_token)
        with lock:
            if session.code is None and session.error is None:
                return SessionResult(ready=False)
            return SessionResult(ready=True, code=session.code, error=session.error)

    @app.delete("/v1/sessions/{state}", status_code=204)
    def complete_session(
        state: str,
        authorization: str | None = Header(default=None),
    ) -> None:
        state_hash, _ = require_session(state, authorization.removeprefix("Bearer ") if authorization else None)
        with lock:
            sessions.pop(state_hash, None)
        return None

    return app


app = create_app()
