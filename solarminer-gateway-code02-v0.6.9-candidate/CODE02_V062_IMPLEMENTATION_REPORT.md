# SOLARMINER GATEWAY — CODE 02 v0.6.2 implementation report

## Summary

This is an incremental candidate based on the verified v0.6.1 source ZIP. The historical artifacts remain unchanged. The 119-test reference suite passed before modifications; the resulting source tree and the modules extracted from the built Debian package each pass 148 tests (119 reference + 29 added test cases).

## Implemented and tested locally

- Additive SQLite equipment registry for Inversores, Baterias, Mineradoras, EV, AQS and Soalho Radiante; declared, implemented and verified capabilities remain distinct.
- Authenticated energy API endpoints using the existing session/RBAC checks and the existing audit table; no second authentication system was added.
- Per-reading source, units, timestamp, trust class and evidence metadata.
- Physical-test proposal, explicit administrator approval, before/during/after evidence, PASS/FAIL/INCONCLUSIVE states, and defensive blocking for obvious dangerous manual actions. No physical command is executed.
- Direct insertion of PHYSICALLY_CORROBORATED readings is refused. A passing test only promotes a LIVE_UNVERIFIED field if the exact value in the recorded AFTER observation matches the latest corresponding live reading; simulated readings are never promoted. Future readings are not automatically corroborated.
- Separate connector worker process with allowlisted health/TCP-probe/Deye-FC03 operations, bounded JSON IPC, request IDs, protocol version, Linux peer UID checking, timeout, and no shell or arbitrary operation.
- Signed artifact manifest verifier (Ed25519 + SHA-256) and persistent fail-closed lifecycle journal with PREPARED, VENV_READY, ACTIVATED, ACTIVE, FAILED and ABANDONED states. The verifier requires an externally provisioned trust public key; tests use ephemeral keys only in the test fixture.
- Package metadata and build script updated to 0.6.2; reproducible Debian build comparison passed.
- Deye Modbus module preserved as FC03-only raw reads; no register decoding or write operation was added.

## Important limits — not complete acceptance

- **Worker/Connector Manager integration is incomplete.** The worker process and IPC primitives are implemented and subprocess-tested, but the existing Connector Manager's install/update/remove flow does not yet provision per-connector Unix users, socket ACLs, per-connector venvs, root-owned systemd units, enforce resource/network restrictions at runtime, or supervise worker lifecycle end-to-end.
- **Signed activation and recovery are incomplete operationally.** The signature/hash verifier and lifecycle journal are tested primitives. The complete atomic deployment transaction, filesystem/service rollback, interruption recovery and safe removal are not implemented end-to-end. The lifecycle journal does not claim to change systemd or files.
- **PWA integration is blocked by missing source.** The verified v0.6.1 archive has no source for the existing The Solar Miner PWA. The API/category contract is provided, but the existing PWA menu and individual pages are not claimed as completed or integrated. No separate prototype is presented as the real PWA.
- **Operational systemd isolation is not validated.** `systemctl is-system-running` reports `offline` in this environment. Static syntax verification of the generated worker unit and packaged Gateway unit passed with an available executable path; this is not proof of cgroup, filesystem, network, UID or resource enforcement.
- **No operational Debian VM with a restorable snapshot was available.** Production install was not performed.
- **No physical hardware was tested.** No Deye inverter, BMS, miner, EV charger, AQS or underfloor heating equipment was connected. All protocol and physical workflow tests are local/simulated.
- **Deye remains experimental.** Community register addresses are not activated in the signed catalog, not decoded into engineering units and not treated as verified for the exact model/firmware. FC03 only; no Modbus writes.

## Status classification

- `IMPLEMENTED_AND_TESTED_LOCALLY`: equipment data model/API, trust classification, supervised test record workflow, IPC schema/peer check, worker subprocess health path, Ed25519/hash verifier, lifecycle state-transition primitives, and local test suites.
- `SIMULATED`: synthetic readings, fake socket/protocol responses, generated test signing keys, and all tests that do not communicate with actual equipment.
- `NOT_VALIDATED_ON_HARDWARE`: all equipment identity, firmware compatibility, register map interpretation, field scaling, sign convention, telemetry accuracy, control capability and physical corroboration.
- `BLOCKED`: integration of worker lifecycle into Connector Manager; root-managed dedicated users/socket permissions and actual sandbox enforcement; atomic rollback/recovery; existing PWA integration.
- `BLOCKED_NO_OPERATIONAL_VM`: live systemd/cgroup/network enforcement and staged install/rollback verification on Debian with a restorable snapshot.

## Compatibility

The Debian package version is 0.6.2. The existing `/api/v1/info` and health API version field remains `0.6.0` to preserve the established API contract asserted by the inherited tests; it is intentionally not presented as the package version.

## Safety statement

No production installation, physical equipment command, Modbus write, CODE 03 work or live device validation was performed.
