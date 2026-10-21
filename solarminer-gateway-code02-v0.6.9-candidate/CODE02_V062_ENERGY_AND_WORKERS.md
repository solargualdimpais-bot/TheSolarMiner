# CODE 02 v0.6.2 — worker IPC, equipment registry and validation workflow

## Status and scope

This increment adds a separate worker entry point, Unix-domain JSON IPC with Linux peer-credential checking, an additive equipment/reading/physical-test schema, API endpoints, and a fail-closed signed lifecycle journal. It preserves the existing identity, session, RBAC, audit and connector catalog code. It does not run an installation or control physical equipment.

**Operational status:** worker IPC has a local subprocess test. The service's dedicated Unix account, socket ownership/group ACL, systemd/cgroup enforcement, network filter, CPU/memory limits and root-owned service lifecycle have **not** been verified on a Debian VM with operational systemd. The worker module is not yet an end-to-end replacement for the existing Connector Manager's install/update/remove flow. The signed lifecycle journal is a fail-closed primitive, not an atomic filesystem/systemd rollback implementation. Do not treat these items as production-ready.

The v0.6.1 ZIP contains no source for the existing The Solar Miner PWA. The new energy API is additive; it does not claim that the existing PWA menu has been wired to it. Integrate the endpoints into the original PWA source when that source is available. No second app is shipped as a substitute.

## Worker and IPC

Run `python -m solarminer_gateway.connector_worker --socket ABSOLUTE_SOCKET_PATH --gateway-uid UID` only in a supervised test environment. Operations are allowlisted (`health`, `tcp_probe`, `deye_fc03_read`); no shell, arbitrary module, arbitrary function, SQL or Modbus write operation is exposed. Messages are bounded JSON frames, carry protocol version and request ID, reject unknown keys and validate the Linux `SO_PEERCRED` UID. The worker sends only exception class names on failure, avoiding exception text and arguments in responses.

A production unit must be generated and installed by a privileged administrator, use a distinct Unix account per connector, expose the socket only to the Gateway identity, and prove systemd/cgroup/network enforcement. A Python venv is not a security boundary. The local test using the same UID validates process/IPC behavior only, not isolation.

## Signed lifecycle

` signed_activation.py` verifies an Ed25519 signature over the exact manifest bytes and SHA-256 of the artifact. Its trust public key is supplied by the administrator; no key is self-generated or auto-trusted. Lifecycle transitions fail closed unless dependency hashes, operational isolation, worker health and interface contract checks are explicitly evidenced. A successful journal transition is not proof that a service was activated by systemd; that operational integration remains blocked.

## Equipment API

- `GET /api/v1/energy/categories`
- `GET /api/v1/energy/equipment?category=inversores`
- `POST /api/v1/energy/equipment`
- `GET /api/v1/energy/equipment/{equipment_id}`
- `POST /api/v1/energy/equipment/{equipment_id}/readings`
- `POST /api/v1/energy/equipment/{equipment_id}/physical-tests`
- `GET /api/v1/energy/physical-tests/{test_id}`
- `POST /api/v1/energy/physical-tests/{test_id}/approve`
- `POST /api/v1/energy/physical-tests/{test_id}/evidence`

Writes reuse existing `manage_gateway` permission and append to the existing audit table. The initial categories are Inversores, Baterias, Mineradoras, EV, AQS and Soalho Radiante. The data model separates declared, implemented and verified capabilities, raw readings, source, units, timestamps, trust classes, limitations, tests and evidence. Direct insertion of `PHYSICALLY_CORROBORATED` readings is rejected; a passing test can promote only a corresponding `LIVE_UNVERIFIED` field, never simulated data. That promotion is field-specific; it does not validate future readings.

The physical test API records a proposal and operator confirmation; it never performs a physical action. Obvious hazardous manual steps are blocked. The text-based blocklist is a defensive guard, not a substitute for competent electrical risk assessment. Tests involving PV DC, batteries, electrical panels or energized conductors require manufacturer procedure and a qualified professional; when safety is unclear, use passive observation only.

## Deye Modbus profile

`deye_modbus.py` remains FC03-only and returns raw registers. No candidate register map is activated, decoded, or included in the signed catalog. The community SG05LP3-EU-SM2 map is not confirmation for a SUN-15K-SG05LP3-EU without that suffix or for the installed firmware. No Modbus write function is added. Raw register reads must remain `LIVE_UNVERIFIED` until the exact model/firmware and field interpretation are independently corroborated.

## API version compatibility

The package version is 0.6.2. The legacy `/api/v1/info` and health response version remain `0.6.0` in this increment because existing tests and clients treat that field as the established API contract. Package version and API contract version are intentionally distinct until a separately reviewed API-version migration.
