# Gateway 0.6.210

- Temporarily keep Gateway and proxy health checks and logs while disabling watchdog-triggered Gateway restarts, Nginx reloads, and automatic release rollback.
- The watchdog action pause is controlled by `SOLARMINER_WATCHDOG_ACTIONS_ENABLED` in the systemd unit and can be reversed in a later release.
