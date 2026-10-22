# SolarMiner Gateway 0.6.31

- Recovery service retries the validated rollback when an earlier attempt entered `RECOVERY_BLOCKED`, instead of treating that state as unrecoverable forever.
- Recovery rejects missing or out-of-scope SQLite backup paths before changing the active release.
- Owner PWA displays the operation ID and recorded update/rollback failure reasons returned by the Gateway.
- No update retry is performed automatically; only restoration of the previous verified release and database backup is retried.
