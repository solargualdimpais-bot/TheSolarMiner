# SolarMiner Gateway CODE02 v0.6.255

- Fixes Intelligence installation recovery after a PWA-only release update: if the newly introduced broker socket has not been provisioned by a Debian package install, the Owner action falls back to the already-installed restricted update broker.
- The fallback accepts only the fixed Intelligence bootstrap systemd unit; no arbitrary command, path, or unit can be supplied.
- Keeps the 0.6.254 non-blocking release-recovery dependency and dedicated broker for installations that have provisioned it.
