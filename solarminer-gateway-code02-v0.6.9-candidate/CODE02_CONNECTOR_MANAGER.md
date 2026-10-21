# CODE 02 — Connector Manager v0.6.0

## Status and scope

This additive release builds on CODE 01 / A2 v0.5.0. It provides a signed catalog, a single allowlisted built-in connector (`tcp-readonly-probe`), bounded private-network TCP discovery, authenticated API routes, persistent operation records, and audit entries. It does **not** execute arbitrary third-party connector code and does not issue device-control commands.

The TCP probe establishes and closes a TCP connection without sending an application payload. Its only verified capability is `tcp_reachable`. It does not identify Modbus, CGMiner, Tuya, Shelly, ONVIF/RTSP, Tesla Fleet API, or any physical device. Hardware validation status: `NOT_VALIDATED_ON_HARDWARE`.

## Signed catalog trust

The catalog is installed at `/usr/share/solarminer/catalog.json`; its detached Ed25519 signature is `/usr/share/solarminer/catalog.sig`, and the trusted raw Ed25519 public key (hex) is `/usr/share/solarminer/catalog.pub`. The private signing key is not included in source archives or Debian packages. The package files are root-owned and not writable by the service account. A catalog signature authenticates the catalog bytes; the SHA-256 of the built-in plugin is separately checked against the catalog entry. Both checks are required.

The initial signing key is a development release key, not a substitute for a production key ceremony. Before a production deployment, create and safeguard an owner-controlled offline signing key, sign the approved catalog, and install its public key through a trusted administrative process. Do not accept a public key delivered alongside an untrusted catalog as a new trust anchor.

## Python dependency model

- **Layer A:** the Gateway runs on Debian's system Python, using the existing package dependency baseline (Python >= 3.11 as declared by the inherited A2 package metadata).
- **Layer B:** shared runtime dependencies are supplied by Debian packages; no global `pip` install is performed.
- **Layer C:** the catalog's only connector is built into the package and has no connector-specific third-party dependencies, so it does not need a virtual environment. Third-party connectors and per-connector venv creation are intentionally rejected/not implemented in v0.6.0; they must not be treated as installed merely because a catalog entry exists.

## Installation, configuration and operation

1. Install the Debian package in a disposable/test environment using the normal package-management procedure.
2. Confirm the service's installed version and `/api/v1/health`.
3. Authenticate using an existing CODE 01 owner session.
4. Read `GET /api/v1/connectors/catalog`; the response is available only if the catalog signature and schema verify.
5. Install `tcp-readonly-probe` using `POST /api/v1/connectors/tcp-readonly-probe/install` with `{"confirmed": true}`. Only the allowlisted built-in module can be installed in this release.
6. Optionally set `timeout_seconds` via `PATCH /api/v1/connectors/tcp-readonly-probe/config`, with `{"config":{"timeout_seconds":1.5}}`.
7. Test a private/link-local IP literal and explicit port via `POST /api/v1/connectors/tcp-readonly-probe/test`. This performs a TCP connect/close only; it does not send a device protocol request.
8. Discovery is an explicit, bounded TCP-connect scan. `POST /api/v1/devices/discover` requires a private CIDR of at most 256 addresses and explicit ports; total attempts are capped. It does not perform multicast discovery or send application data.

The API uses the existing bearer-session authentication and RBAC. Reading catalog/device records requires `read`; discovery requires `manage_devices`; installing, configuring, testing and removing a connector require `manage_gateway` (owner in the inherited A2 permission map). Successful operations are audited.

## State and recovery

Connector state and operation phases are persisted in SQLite. The schema migration is additive (migration version 4). An interrupted `PREPARING` or `ACTIVATING` operation is marked `RECOVERY_REQUIRED` at startup rather than being guessed successful. This release does not install arbitrary artifacts, create venvs, run APT/pip, or dynamically activate third-party code. Removal marks the built-in connector removed in persistent state; it does not delete the built-in Python module from the Debian package.

SQLite transactions do not make filesystem operations transactional. The current built-in-only lifecycle minimizes that boundary; the operation journal is a basis for future staged third-party installation, not evidence that third-party rollback already exists.

## API endpoints

- `GET /api/v1/connectors/catalog`
- `GET /api/v1/connectors`
- `POST /api/v1/connectors/{id}/install`
- `POST /api/v1/connectors/{id}/update` — confirmation JSON body required; reconciles metadata against the signed catalog after a trusted Debian package upgrade, but does not download/execute code.
- `PATCH /api/v1/connectors/{id}/config`
- `POST /api/v1/connectors/{id}/test`
- `DELETE /api/v1/connectors/{id}/remove` (confirmation JSON body required)
- `POST /api/v1/devices/discover`
- `GET /api/v1/devices/discovered`
- `GET /api/v1/devices/{discovered_id}/capabilities`

Connector code updates are delivered by the trusted Debian package manager; the API update operation only reconciles persisted metadata and is not an artifact downloader or rollback engine.

There is no PWA source in the A2 repository used for this implementation, so these API endpoints are integrated into the Gateway, but no PWA screens were added or visually validated.

## Current limitations

- Only the generic read-only TCP reachability probe is implemented.
- No device-specific protocol parsing, control commands, or device capability verification.
- No third-party connector artifacts, per-connector virtual environments, dependency resolver, or isolated worker process in v0.6.0. The built-in module is allowlisted and runs in the Gateway process; this is not a sandbox for untrusted code.
- No physical device or hardware test was performed.
- No operational VM/systemd installation test is claimed by the local test suite.
- The signed catalog's development public key is packaged for reproducible local verification; production deployments should replace it through a trusted process before accepting externally maintained catalogs.

## Classification

- Catalog signature verification, schema checks, built-in source hash check, API authorization, bounded discovery logic, lifecycle state and unit tests: `IMPLEMENTED_AND_TESTED_LOCALLY` when the associated tests pass.
- TCP reachability using a live loopback/private test socket: `SIMULATED` in automated tests unless an explicitly identified LAN target is supplied.
- Real supported equipment and physical protocol validation: `NOT_VALIDATED_ON_HARDWARE`.
- Third-party connector installation/isolation and PWA screens: `BLOCKED` / not implemented in this release.
