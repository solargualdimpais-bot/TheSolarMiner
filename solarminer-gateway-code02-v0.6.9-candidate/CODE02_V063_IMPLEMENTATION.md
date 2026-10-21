# CODE 02 v0.6.3 — integration notes

## Status vocabulary
- `IMPLEMENTED_AND_TESTED_LOCALLY`: code path exercised by the local test suite.
- `SIMULATED`: test uses a synthetic archive, generated Ed25519 key, or local IPC exchange.
- `NOT_VALIDATED_ON_TARGET_HARDWARE`: no validation on the dedicated Debian PC or real energy equipment.
- `BLOCKED`: a concrete source/integration dependency is missing.
- `BLOCKED_NO_TARGET_ENV`: a check requires the physical target and it is not available in this workspace.

## Worker lifecycle
`connectors.install()` now starts a real `solarminer_gateway.connector_worker` subprocess under the Connector Manager's control, performs the allowlisted IPC health exchange, verifies the returned connector identity, and always stops the process before persisting the install. The manager class also exposes bounded IPC calls, process liveness and termination. This is a functional local subprocess integration; it does not establish separate Unix identities or a systemd sandbox. The existing TCP reachability test path remains a direct transport probe in this release and is not yet routed through worker IPC: this is a known incomplete acceptance item, not concealed as complete.

## Atomic release store
`AtomicReleaseStore` accepts only the sealed result of Ed25519 manifest verification, rechecks the artifact SHA-256, safely extracts ZIP payloads (rejecting traversal and symlinks), validates staging, serializes updates with a nonblocking file lock, atomically switches the `active` symlink and restores the previous pointer on a post-switch exception. It fsyncs journal and parent directories. The returned status explicitly says operational health and systemd isolation are not verified. This local transaction does not prove recovery under actual power loss or filesystem-specific crash semantics.

## systemd
`isolated_runtime.render_systemd_unit()` prepares restrictive policy (dedicated UID/GID name, NoNewPrivileges, PrivateTmp, ProtectSystem, resource controls, IPAddressDeny by default and optional single private device IP allow). The unit must be installed root-owned and matching Unix accounts provisioned by an administrator. Static validation is not enforcement evidence. No target machine was changed or installed.

## PWA search
The available workspace and the v0.6.2 source ZIP were searched for the original The Solar Miner PWA source (`package.json`, Vite/Next configuration and likely project names). No original PWA source was found. No parallel PWA was created. The interface integration remains `BLOCKED` until the original source tree is supplied or made accessible.

## Deye
The Deye module remains Modbus FC03 read-only. Community map entries remain candidate metadata; no register decoding, assumed scaling or write operation is added. Hardware and exact model/firmware compatibility remain `NOT_VALIDATED_ON_TARGET_HARDWARE`.

## Physical target procedure (not executed)
When the dedicated Debian PC is available and authorized: (1) capture system/package versions and a restorable backup; (2) install only in a maintenance window; (3) run `systemd-analyze verify` against packaged units; (4) confirm worker UID/GID differs from Gateway, socket ownership/mode, filesystem writes and network deny/allow using harmless test targets; (5) verify restart/timeout/termination; (6) run signed upgrade tests with a known-good previous release and controlled injected failures; (7) verify active symlink, files, journal and service state after reboot/recovery; (8) remove the test connector and confirm only its own resources were removed. Do not run any physical power/electrical test as part of these software checks. Deye telemetry requires separate supervised validation by a qualified person and independent measurement where safe.
