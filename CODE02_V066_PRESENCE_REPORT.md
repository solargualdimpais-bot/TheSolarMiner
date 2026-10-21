# CODE 02 v0.6.6 — additive presence increment

**Status:** implemented in source; new tests pass individually; not installed or validated on a physical Gateway.

## Changes

- Added SQLite `user_presence` table and migration version 5 without replacing migrations 1–4.
- Added `POST /api/v1/presence/heartbeat` and `GET /api/v1/presence/me`.
- Session-derived user/device identity; request payload cannot select a target user/device or claim connection method.
- Gateway-generated last-seen/expiry timestamps, 120-second TTL, five-second persistence throttle, transition audit.
- Logout deletes the active session's user/device presence.
- `unknown` before first heartbeat, `online` before expiry, `offline` after expiry. `connection_method` remains `unknown`.

## Tests

New tests: `tests/test_presence.py` — 7 passed. Existing test modules were run individually: browser pairing 10, CODE02 v0.6.1 40, v0.6.2 29, v0.6.3 10, v0.6.4 5, connectors 9, gateway 42, recovery 28. Every module passed when invoked individually (180 tests total). A single aggregate pytest invocation did not complete in this environment and timed out while running the recovery tests after earlier tests had passed; this is reported as a limitation rather than a clean aggregate-suite pass.

## Limits

- No physical Gateway installation or test.
- Presence means authenticated app/device heartbeat, not physical presence.
- Gateway identity attestation and secure QR endpoint pinning remain unimplemented.
- LAN/REMOTE remains `unknown`; the backend does not trust client-supplied claims.
- PWA v0.5.1 does not yet call these routes because its authenticated session flow has not been integrated.
