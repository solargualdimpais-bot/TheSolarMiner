# System component compatibility during online updates

The Gateway runs its application from `/opt/solarminer/current`, while systemd units, fixed privileged wrappers, Python broker modules and Intelligence assets are installed at package paths under `/usr`. Extracting a new `.deb` into a release directory does not update these system paths.

Starting with package 0.6.258, the verified update pipeline uses a closed path allowlist in `system_components.py` to reconcile those package-owned files. It does not run Debian maintainer scripts during an online activation: `postinst` has installation-time effects, including provisioning `/etc` configuration and restarting services outside the update transaction. `/etc`, credentials, identity keys, databases and user data are not eligible for this reconciliation.

The transaction stops the Gateway, snapshots each previous file and the component manifest under `/opt/solarminer/backups/system-components/<operation-id>`, records the snapshot path durably, atomically installs the allowlisted files, reloads systemd, enables the fixed broker sockets, switches the release pointer, and starts the Gateway. Health attestation requires both `package_version` and `system_components_version` to match the target. Failure or boot recovery restores the snapshot, pointer and SQLite backup before restarting the prior release.

The manifest records component protocol version 1 and the package version. It is not a package signature; trust comes from the signed release manifest and package hash validated before extraction. The manifest is a secret-free compatibility marker readable by the unprivileged Gateway process.

### First upgrade from 0.6.257

The old updater is installed under `/usr/lib` and its service sandbox does not permit system-component writes. It cannot safely bootstrap a new updater through its own online path. Existing 0.6.257 installations must first install 0.6.258 using the signed USB repair/upgrade script, which runs the full package manager, preserves the data volume and credentials, and has an existing package/database/release rollback. Do not use the online update button for this one-time updater transition. Later releases use the transactional online reconciliation mechanism.

### Limitations

Unit tests simulate system file replacement and restoration beneath a temporary root. The package workflow must additionally validate the Debian package contents and run on Ubuntu Linux. These tests do not replace installation and power-loss testing on a Debian 13 VM or the physical Gateway.
