# API contract CODE02 v0.6.7 — incremental / partial

## Addendum: first Owner local-password setup and device login

- During first USB installation, `solarminer-gateway owner-password` takes a locally entered password (8–128 chars; terminal echo is enabled), hashes it with Argon2id, and stores only that temporary verifier in the `bootstrap` row. The setup script does not put the plaintext value in its log.
- `POST /api/v1/bootstrap/owner` accepts `username`, `password`, `public_key_pem`, `signature`, `timestamp`, and `nonce` for the new setup flow. The signature covers `BOOTSTRAP`, username, timestamp, and nonce on separate lines. The request must arrive from an allowed origin over trusted HTTPS. The password must match the local verifier. The transaction consumes that verifier and creates the first Owner and its device exactly once. The name may contain spaces. MAC metadata is marked unknown for this flow.
- Legacy installations can still use the optional one-time `bootstrap_token` and MAC payload while they are being migrated.
- `POST /api/v1/auth/device-login` accepts `device_id`, `timestamp`, `nonce`, and `signature`. The Ed25519 signature covers `DEVICE-LOGIN`, device ID, timestamp, and nonce on separate lines. An active, already-associated device receives an eight-hour session; no account password is sent on subsequent PWA visits.
- The PWA stores the private `CryptoKey` as non-exportable IndexedDB data and keeps bearer sessions in memory. Clearing browser data removes the device identity; account recovery/administrative re-enrollment is then required.

## Compatibility

The established `/api/v1/health` and `/api/v1/info` API version remains `0.6.0` for compatibility. The package/release version is `0.6.7`. Existing authentication, session, RBAC, device pairing, presence and audit routes are retained.

## Invites

- `POST /api/v1/invites` — owner only. JSON `{ "role": "viewer|operator|guest", "label": "..." }`. `guest` is normalized server-side to `viewer`. Returns the raw token only in this initial response and a QR payload `{v,url,token,fp,exp}`. Creation fails closed unless `SOLARMINER_PUBLIC_URL` is HTTPS and a matching Gateway Ed25519 identity is provisioned.
- `GET /api/v1/invites` — owner only. Lists status without raw token or token hash.
- `POST /api/v1/invites/{id}/revoke` — owner only, pending invitations only.
- `POST /api/v1/invites/redeem` — public, rate limited. Additional required fields for complete account activation: `username`, `password`, `mac`; plus `invite_token`, `client_pubkey_pem`, `signature`, `timestamp`, `nonce`. The Ed25519 signature covers newline-separated `POST`, path, timestamp, nonce, SHA-256(token), username, SHA-256(password), normalized MAC, and SHA-256(DER public key). The nonce and invite consumption, user/device/association/session creation, and audit are committed in one SQLite transaction.
- `GET /api/v1/gateway/identity?timestamp=...&nonce=...` — signs the method, path, timestamp and nonce using the provisioned Gateway Ed25519 identity. Client must check the full public-key fingerprint against the invite QR and verify the signature. A successful `/health` response is not identity proof.

Provisioning variables:
- `SOLARMINER_GATEWAY_IDENTITY_PRIVATE_KEY` (default `/var/lib/solarminer/gateway-identity.key`, POSIX permissions must not expose group/other access)
- `SOLARMINER_GATEWAY_IDENTITY_PUBLIC_KEY` (default `/etc/solarminer/gateway-identity.pub.pem`)
- `SOLARMINER_PUBLIC_URL` (must be HTTPS)
- `SOLARMINER_INVITE_TTL_SECONDS` (300–604800, default 43200)

The public/private key pair must be provisioned out-of-band and its fingerprint delivered to the Owner through a trusted channel. This source increment does not generate or silently rotate identity keys.

## Remote update

- `GET /api/v1/system/update/check` — authenticated `read`; if configured, retrieves an HTTPS manifest, verifies Ed25519 over canonical sorted compact JSON excluding `signature`, checks required fields, compatibility, package size/hash, available disk space, downloads package to a non-active staging directory and verifies exact size/SHA-256.
- `GET /api/v1/system/update/status` — authenticated `read`; reports the most recent persistent operation.
- `POST /api/v1/system/update/apply` — Owner-only authorization is revalidated, but returns `503 update_activation_disabled_until_independent_recovery_deployment_is_installed`. It intentionally does not activate or run a package.

Release source configuration:
- `SOLARMINER_RELEASE_MANIFEST_URL` (HTTPS; no redirect to a different origin)
- `SOLARMINER_RELEASE_PUBLIC_KEY` (default `/etc/solarminer/release-pubkey.pem`, provisioned independently of updated package)

The updater is intentionally incomplete: staging/cryptographic verification is implemented, but activation, migration orchestration, independent recovery service/timer, health observation and automatic rollback are not. Do not interpret a verified staged package as an applied release.
