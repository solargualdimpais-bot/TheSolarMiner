# Gateway 0.6.208

- Stop overlapping periodic Tuya LAN fleet sweeps; wait five seconds after each completed sweep.
- Use only the saved Tuya LAN protocol for reads. Background telemetry no longer retries alternate protocols or starts MAC-based rediscovery after a failed read.
- Limit background Tuya reads to four concurrent devices.
- Initialize SQLite WAL once at startup instead of reissuing the journal-mode pragma on every database connection.
- Keep the liveness health endpoint independent of SQLite so transient database contention cannot trigger a false Gateway restart.

Validation covers the Tuya read path, polling interval, database-independent health endpoint, and the Gateway Linux release suite. Physical LAN behavior still requires confirmation on the installed Gateway.
