# SolarMiner Gateway API contract — CODE 02 v0.6.6

The v0.6.5 API contracts remain unchanged. The following routes are added:

- `POST /api/v1/presence/heartbeat` — requires a valid active session and `read` permission. No user ID, device ID, or connection method is accepted from the client. The Gateway derives user/device from the session, generates timestamps, uses a 120-second TTL and throttles persisted refreshes to five seconds.
- `GET /api/v1/presence/me` — returns only the caller's own user/device state: `unknown`, `online`, or `offline`. The method is `unknown` until Gateway-side evidence can safely distinguish LAN/REMOTE.

Presence is not physical occupancy. It is an expiring online signal from an authenticated app/device. No background heartbeat guarantee is made for Safari/iOS.

Security: presence calls use existing session validation and active user-device association; state transitions are audited; logout invalidates the current user/device presence. No other user's presence can be set or queried through these routes.

Not included: cryptographic Gateway identity attestation, QR endpoint identity pinning, remote invitation, presence inference from Wi-Fi, or physical-presence claims.
