# CODE02 v0.6.7 rollback and recovery — limitation statement

## Current status

The v0.6.7 increment does **not** install or activate remote releases. `POST /api/v1/system/update/apply` deliberately fails closed with HTTP 503 until an independent recovery deployment is installed and tested. Therefore no automatic rollback guarantee is claimed.

## Future deployment requirements before enabling activation

1. Record active package/release identifier and operation ID.
2. Verify the release manifest signature and package SHA-256/size against the independently installed release public key.
3. Keep both prior and candidate artifacts in a local, versioned releases directory.
4. Create a consistent SQLite backup using SQLite backup API and validate `PRAGMA integrity_check`.
5. Prepare candidate code in an isolated directory; do not mutate active code during preparation.
6. Persist every state transition before activation.
7. Use a recovery service/timer independent of the CODE02 process. It must inspect persistent state and restore a matching code/database pair without Internet, PWA or Tailscale.
8. Observe local service, database, auth smoke tests and active version for 60 seconds before commit.
9. On failure, restore code and database together, run integrity checks, restart and verify service, then audit actual outcome.
10. Retain backup until commit and retention policy permit removal.

## Manual incident procedure for this partial build

- Do not call `/api/v1/system/update/apply`; it is intentionally disabled.
- Identify the deployed package and preserve logs/database before intervention.
- Use the existing installation's documented recovery procedure and a known-good, matching package/database backup. Do not restore an arbitrary database against a different schema.
- Verify SQLite integrity and service health after recovery.
- If Debian does not boot, recovery requires local/USB or other out-of-band system recovery; a systemd service inside the failed OS cannot guarantee recovery.

This document is not a claim that rollback automation has been implemented or physically validated.
