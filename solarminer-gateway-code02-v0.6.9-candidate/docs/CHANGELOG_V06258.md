# SolarMiner Gateway CODE02 v0.6.258

## Release coherence and recovery

- Online package activation now reconciles a closed allowlist of package-owned privileged helpers, Gateway Python modules, Intelligence assets and systemd units from the signed Debian artifact.
- The Gateway is stopped during reconciliation. A durable per-operation snapshot is recorded before system files change; a failed activation or interrupted operation restores the prior system components, release pointer and database backup.
- Required broker sockets are reloaded and enabled from the signed package. The Owner health path reports the installed system-component version separately from the application version, and release health checks reject mismatches.
- A signed but incomplete package is rejected if fixed brokers, privileged wrappers or systemd units are absent. Installed manifests fail closed when dpkg reports a missing package-owned component, and health checks require component integrity and protocol validation.
- Full Debian package installation records the installed component inventory. `/etc`, secrets, database contents and user data are excluded from online component reconciliation.
- Owner Intelligence status reports Debian/Python, active release, dpkg package version, component integrity, broker/socket unit states, key Intelligence paths and Smart Device Engine retry diagnostics. It never reads or returns credential contents.
- USB repair marks its transaction so `postinst` does not restart Gateway or the Intelligence bootstrap timer between updating privileged files and switching the active release. They resume after activation or rollback.

## Smart Device Engine

- A scheduler cycle whose device definition disappeared is retired safely instead of raising `KeyError`.
- Repeated scheduler-loop failures now log the first traceback and retry with capped exponential backoff; repeated journal messages are rate-limited.

## Recovery route

The 0.6.257 online updater cannot install these new reconciliation rules because it executes the previously installed updater from `/usr`. The first transition to 0.6.258 on an existing 0.6.257 Gateway must therefore use the signed **USB repair/upgrade** flow (it preserves data and does not format the disk). Once 0.6.258 is installed, subsequent signed online updates can reconcile the system components transactionally.

The PWA diagnostic interface advances to 0.5.188 with a new cache identifier.

This release does not claim physical Lenovo validation. Linux CI package and rollback tests do not replace Debian VM or physical Lenovo installation tests.
