# CODE02 v0.6.7 / PWA v0.5.5 — limitations

This is a partial local engineering increment, not a completed secure remote updater.

- Implemented: additive invite table; Owner-only invite create/list/revoke; one-time hashed invite token; server-side role allow-list (`viewer`, `operator`, with `guest` normalized to `viewer`); public redeem with Ed25519 canonical request signature, freshness, nonce replay defense, rate limit, transactionally created user/device/association/session and audit; Gateway Ed25519 identity challenge with fail-closed provisioning; signed release-manifest validation and verified package staging; persistent operation status.
- Not implemented: complete Owner invite-management PWA screen; QR code image generation/scanning UI wired to the invite APIs; end-to-end activation UI and credential recovery; independent update recovery systemd service/timer; atomic release activation; automatic health-check/rollback; migration runner and coordinated code/database restoration; package signature enforcement at actual installation; remote updater's final commit path.
- The standalone PWA's `gateway-connection.js` now contains invite QR parsing, Gateway challenge verification and canonical invite signing helpers, but these helpers are not yet connected to a complete invite UI/workflow.
- No `.deb` was produced: the current packaging layout builds Debian packages, but its deployment model does not provide the isolated atomic activation and independent recovery guarantees required to call remote update safe. The updater's apply endpoint remains disabled.
- No real Gateway, production services, Tailscale, or Safari/iPhone was contacted or tested.
- Existing API health/info version `0.6.0` is deliberately preserved for compatibility; package/release metadata is `0.6.7`.
