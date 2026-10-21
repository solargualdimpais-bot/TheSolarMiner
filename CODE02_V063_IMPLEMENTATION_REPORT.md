# SOLARMINER GATEWAY — CODE 02 v0.6.3 implementation report

## Executive summary

v0.6.3 is an incremental development candidate derived from the locally available v0.6.2 source ZIP. The source and Debian package are built; the preserved regression suite passed before changes (148/148) and the expanded suite passed after changes (158/158). No VM was created or used. No production installation or physical operation was performed.

## Preservation and baseline

Before edits, the v0.6.2 artifacts were inventoried and hashed. Their local hashes matched the local v0.6.2 manifest. The v0.6.2 source ZIP was extracted to a separate temporary baseline directory and tested before any v0.6.3 changes: 148 passed. The working tree was copied to `solarminer-gateway-code02-v0.6.3`; the original ZIP, Debian package, reports and manifest were not overwritten.

Historical v0.6.0 ZIP hash discrepancy remains documented in the v0.6.2 manifest: the actual local file and historical manifest end `...99268ac4701`, while the earlier supplied value ended `...99218ac4701`. No silent correction was made.

## Implemented and tested locally

- `ConnectorWorkerRuntime` supervises a worker subprocess, readiness and health IPC, bounded IPC calls, liveness checks, timeout handling and process termination.
- The existing `connectors.install()` flow now starts the worker, validates the returned worker identity/health contract, stops the worker and only then persists the installed status. The previous API and auth/RBAC contract are retained.
- Signed manifest verification now returns a sealed `VerifiedManifest`; direct construction is rejected. Manifest version strings are restricted to a safe path-component character set.
- `AtomicReleaseStore` rechecks the artifact SHA-256, accepts only a verified manifest, rejects ZIP path traversal and symlinks, bounds archive member count/expanded size, serializes updates with a nonblocking file lock, stages and validates content, atomically swaps the active symlink, journals events with fsync, and restores the prior active pointer on post-switch failure. Fault-injection tests cover staging, validation, pre-switch and post-switch failure.
- systemd policy rendering includes unprivileged account names, NoNewPrivileges, PrivateTmp/Devices, ProtectSystem/Home/Kernel*, capability/resource controls, network-deny-by-default and optional single private-IP allowlisting.
- Deye FC03-only read behavior is preserved. No Modbus writes, register decoding, presumed scales or hardware claims were added.
- Reproducible Debian package build: two independent builds were byte-identical.

## Incomplete integration / blocked

- The Connector Manager install path performs a real local worker health IPC exchange, but the existing `test_connection()` TCP reachability operation still calls the in-process probe. Routing all connector operations through the supervisor is therefore **partially implemented**, not complete acceptance.
- `AtomicReleaseStore` is a tested transaction primitive but is **not yet wired into the existing connector update API/DB/systemd lifecycle**. It atomically swaps a filesystem pointer in its own release store; it does not provide a complete multi-resource transaction across the Gateway database, installed units, service health and power-loss recovery. No claim of full operational rollback is made.
- The runtime worker subprocess currently uses the Gateway process UID in local development. `isolated_runtime` renders policy, but no dedicated Unix accounts or root-owned per-connector units were installed. Static systemd verification passed; actual sandbox enforcement is `NOT_VALIDATED_ON_TARGET_HARDWARE`.
- Search of accessible workspace/project directories and the available file library did not find the original The Solar Miner PWA source (`package.json`, Vite/Next config or an identifiable frontend tree). The PWA menu and pages are **BLOCKED**. No parallel disconnected PWA was created.
- No physical Debian target was available in this workspace. The required target-only checks are `BLOCKED_NO_TARGET_ENV`; this is not a VM-related blocker. No VM was created or used.
- No inverter, battery, miner, EV charger, AQS or underfloor-heating equipment was connected. No physical test was performed.

## Status classification

- `IMPLEMENTED_AND_TESTED_LOCALLY`: worker subprocess lifecycle/health IPC; worker integration into install preflight; sealed signed-manifest verification; local release-store transaction and rollback pointer tests; package build and static unit syntax checks; expanded test suite.
- `SIMULATED`: synthetic signed ZIP artifacts, generated test-only Ed25519 keys, fault-injected update failures, and all equipment/protocol tests without hardware.
- `NOT_VALIDATED_ON_TARGET_HARDWARE`: systemd enforcement, dedicated UID/GID and socket ACLs, actual resource/network restrictions, target Debian service lifecycle, crash/power-loss behavior on target filesystem, device communication and all physical corroboration.
- `BLOCKED`: original PWA integration; end-to-end update transaction integration with Connector Manager, DB and systemd; routing TCP probe operations through the worker; fully separate OS identities in a deployed system.
- `BLOCKED_NO_TARGET_ENV`: checks requiring the dedicated physical Debian Gateway are pending until that equipment is available and authorization is given.

## Test results

- v0.6.2 baseline before changes: 148 passed.
- v0.6.3 source tree: 158 passed.
- v0.6.3 package-extracted modules: 158 passed.
- v0.6.3 ZIP-extracted source: 158 passed (see test report).
- Debian package reproducibility: PASS, two independent builds byte-identical.
- `systemd-analyze verify` for packaged Gateway unit and generated worker unit: PASS (static syntax only).

## Physical target procedure — not executed

When the dedicated Debian PC is available and authorized: (1) capture OS/package versions and a restorable backup; (2) install only under a separately approved maintenance plan; (3) verify packaged systemd units; (4) verify worker UID/GID, socket owner/mode, filesystem boundaries and denied network paths; (5) exercise startup, health IPC, timeout, restart and forced termination; (6) validate signed update, interrupted update, rollback and post-reboot journal consistency using a known-good prior release; (7) verify connector removal is limited to that connector's resources. Do not use electrical switching as part of software validation. Any physical Deye validation must be separately supervised, safe, and corroborated with suitable independent measurements.

## Safety

No CODE 03 work, VM creation/use, production installation, physical equipment commands or physical tests were performed.
