# SolarMiner Gateway 0.6.27

- Runs the signed GitHub release check five minutes after boot and daily thereafter.
- Automatically queues only newer releases with valid Ed25519 signature, package hash, size, version, architecture, dependencies and a successful independent recovery preflight.
- Uses the existing privileged updater for SQLite backup, staging, activation, health check and rollback.
- Stops automatic retries of a target version after a failed, rolled-back or recovery-blocked attempt so the same release cannot cause a daily restart loop. The Owner can inspect status and decide whether to retry manually.
- Updates the Owner PWA copy bundled in the Gateway to describe the automatic schedule.
