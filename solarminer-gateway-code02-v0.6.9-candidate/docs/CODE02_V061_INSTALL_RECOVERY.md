# CODE 02 v0.6.1 — build, staged installation and recovery notes

## Current recommendation

Do not install v0.6.1 on the production Gateway yet. The Deye connector is raw-only and not registered in the signed catalog; the systemd policy has not been operationally validated on a real systemd host. Use a disposable Debian test machine/VM first.

## Build and test

```sh
make test
./packaging/build-deb.sh "$PWD/dist"
dpkg-deb --info dist/solarminer-gateway_0.6.1_amd64.deb
dpkg-deb --contents dist/solarminer-gateway_0.6.1_amd64.deb
```

The build environment should record its Debian release, Python version, and `systemd --version`. A successful package build is not proof of service startup or sandbox enforcement.

## Before any staged upgrade

1. Confirm the package SHA-256 against the approved release manifest using a separately trusted copy of the manifest.
2. Record `dpkg-query -W solarminer-gateway`, `systemctl status solarminer-gateway.service`, `systemctl cat solarminer-gateway.service`, and the current service logs.
3. Stop and verify the service before copying the database. Use an access-controlled backup directory; the SQLite database and its WAL/SHM files may contain sensitive authentication state.
4. Verify that the existing TLS key/certificate, database, bootstrap/recovery material, owner identity, and audit records are preserved.
5. Install only on the disposable/staging system; do not use a production host until sandbox and signed-catalog activation are resolved.

## Upgrade and rollback on a staging Debian system

Keep the previously approved v0.6.0 `.deb` and its independently verified SHA-256 outside the target. After taking a verified backup, install the candidate package with `sudo dpkg -i ./solarminer-gateway-code02_0.6.1_amd64.deb`, then inspect `dpkg-query -W`, `systemctl status`, `journalctl -u solarminer-gateway.service`, API health, and the test/audit endpoints. Do not assume the service started merely because `dpkg -i` exited successfully.

If checks fail, stop the service, preserve the failed database and logs for analysis, reinstall the previously approved v0.6.0 package with `sudo dpkg -i ./solarminer-gateway-code02_0.6.0_amd64.deb`, and restore the pre-upgrade database/state backup only if the rollback plan requires it. Do not overwrite newer state blindly; compare timestamps and schema, and preserve audit evidence. Validate the restored service before reconnecting devices.

## Connector install/update/remove/recovery

No third-party connector install/update/remove is enabled by this v0.6.1 release. Do not manually add an unsigned Deye catalog entry, replace `catalog.pub`, or create a service unit as root by hand. The new sandbox and dependency modules are policy/building blocks; they are not yet an end-to-end lifecycle implementation. A future activation must include a root-owned unit, least-privilege account, target-specific network allowlist, signed catalog entry, atomic staging/activation/rollback, and interruption-recovery tests on a real systemd host.
