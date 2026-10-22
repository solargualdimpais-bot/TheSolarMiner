# SolarMiner Gateway — signed CODE 02 package (API contract v0.6.0)

Standalone Gateway foundation for local identity, bootstrap, authentication, authorization, device identity and audit. This directory is deliberately separate from the archived Prova 0 v0.3.0 artifacts. The current package version is recorded in `packaging/control`; the API-reported version remains `0.6.0` for compatibility. Release workflow builds, tests, signs and publishes the Debian package and USB bundle.

CODE02 v0.6.32 improves Deye Modbus diagnostics and isolates Tuya Cloud errors per device. See [`docs/CHANGELOG_V0632.md`](docs/CHANGELOG_V0632.md), [`docs/HARDWARE_INTEGRATIONS.md`](docs/HARDWARE_INTEGRATIONS.md), and [`docs/UPDATE_AND_ROLLBACK.md`](docs/UPDATE_AND_ROLLBACK.md).

## Build and test

```sh
make test
make deb
```

For the signed install/repair USB workflow, first Owner bootstrap and Tailscale remote access, see [`docs/INSTALL_DEBIAN_AMD64.md`](docs/INSTALL_DEBIAN_AMD64.md), [`docs/OWNER_FIRST_BOOTSTRAP.md`](docs/OWNER_FIRST_BOOTSTRAP.md), [`docs/TAILSCALE_ACCESS.md`](docs/TAILSCALE_ACCESS.md), [`packaging/USB_INSTALL_README.txt`](packaging/USB_INSTALL_README.txt), and [`packaging/USB_REPAIR_README.txt`](packaging/USB_REPAIR_README.txt). The repair tool is for a previously installed Gateway; it is not an unattended USB autorun feature. Release notes are in [`docs/CHANGELOG_V0619.md`](docs/CHANGELOG_V0619.md).

The supported deployment target is Debian 13 (Trixie) or later on `amd64`, with Python 3.13 or later. Runtime dependencies include `dpkg`, `python3-venv`, `nginx`, `python3-pydantic (>= 2)`, `python3-fastapi (>= 0.115.11)`, `python3-uvicorn`, `python3-argon2`, `python3-cryptography`, `python3-qrcode`, `openssl`, `adduser`, `curl`, and `ca-certificates`. Privileged update and Tailscale operations use a restricted systemd socket broker and do not require sudo. The signed first-install bundle installs Tailscale from its official Debian repository; the Gateway needs Owner authorization to join a Tailnet. MagicDNS and HTTPS Certificates enable trusted `*.ts.net` access without router ports or a purchased domain. Direct LAN IP access is served on 8443 but uses a local self-signed certificate that the browser must trust. Review [`docs/TAILSCALE_ACCESS.md`](docs/TAILSCALE_ACCESS.md) and [`docs/REMOTE_ACCESS_AND_TLS.md`](docs/REMOTE_ACCESS_AND_TLS.md).

## Bootstrap

On the initial USB install, the local installer asks for the first Owner password with visible terminal input and stores only a temporary Argon2id verifier. The first PWA device uses that password once to register the Owner and its Ed25519 identity. A new browser can sign in with an active account password over validated HTTPS; the Gateway registers that browser's Ed25519 identity. Later visits authenticate using a fresh device-key signature. The private device key stays non-exportable in the browser. For remote use, authorize the Gateway and the iPhone in the same Tailnet; the Gateway does not register arbitrary first visitors as Owner. See `docs/OWNER_FIRST_BOOTSTRAP.md`, `docs/TAILSCALE_ACCESS.md`, and `docs/API.md`.

## MAC and cryptographic identity

Every account must be linked to an active device. MAC addresses are normalized and stored as `declared`; they are not an authentication factor and the current code deliberately refuses to mark a MAC `verified` because no independent verification process is implemented. Device identity is bound to an Ed25519 public key. Private keys are not stored by the gateway.

## Scope and status

This is a partial CODE 01 implementation, not a hardware-verified release. See `A1B_VALIDATION_REPORT.md` and `docs/A1B_SECURITY.md` for exact test results, security limitations and unimplemented flows. Prova 0 is not rebuilt or modified by this project.


## A2 owner recovery

The first successful, loopback-only owner bootstrap response includes a one-time `recovery_key`. The bootstrap client must display it once to the owner and must not persist it in logs, telemetry, shell history, or support records. Store it offline. The Gateway stores only a domain-separated SHA-256 verifier because the key is generated from 32 random bytes (256 bits of entropy); Argon2 is reserved for human-chosen passwords.

For an existing A1b owner, configure or rotate the key while the owner password and an associated active Ed25519 device are still available: stop the service and run `solarminer-gateway recovery-setup`. To recover using the offline key, stop the service and run `solarminer-gateway recovery`. The command requests the key through hidden interactive input and requires a new device public key plus a signature over a fresh random challenge. The private key never enters the Gateway.

If the offline recovery key is also lost, `solarminer-gateway emergency-reset` is a separate OS-root-only procedure. It requires the service to be stopped, explicit confirmation, a fresh device proof, and a protected SQLite backup under the database directory's `backup/` subdirectory. It preserves users and unrelated data; it does not reset the database. A pre-commit failure rolls back the operation. If a replacement recovery key is committed but cannot be displayed after commit, it cannot be retrieved from storage; use the documented emergency procedure to rotate it again.

All local recovery commands require a real interactive terminal and root privileges, and refuse to proceed if they cannot establish that the systemd service is stopped. No HTTP recovery endpoint was added. Recovery, backup and audit contain no plaintext passwords, recovery keys, bearer tokens, or private device keys; the protected backup necessarily contains sensitive credential verifiers and session hashes and must remain access-controlled.


## CODE 02 — Connector Manager v0.6.0

The Connector Manager adds a signed Ed25519 connector catalog, a built-in read-only TCP reachability probe, bounded private-network discovery, connector lifecycle API endpoints, and persistent audit/operation state. See `docs/CODE02_CONNECTOR_MANAGER.md`. The initial release does not execute third-party connector code, does not send device-control commands, and does not claim protocol or hardware validation.

## CODE 02 v0.6.1 — incremental hardening

This source tree preserves the v0.6.0 CODE 01/A2 and Connector Manager regression suite. The Debian package version is 0.6.1; the inherited Gateway `/api/v1/info` version remains 0.6.0 to preserve the established API contract asserted by the prior tests.

Added in this iteration:

- Hash-verified offline per-connector wheel installation into independent virtual environments (`connector_dependencies.py`).
- A restrictive systemd sandbox policy renderer (`isolated_runtime.py`) with dedicated-user, filesystem, process/resource, and network restrictions.
- A Modbus TCP FC03-only raw read client (`deye_modbus.py`) with strict response validation and explicit unknown scaling/model status.
- Additional tests for protocol framing, malformed/exception responses, timeouts, safe targets, dependency hashes, and sandbox policy.

Important limits: the Deye connector is not yet activated by the signed catalog or dispatched by Connector Manager. The available official manufacturer documents do not establish a register map for the exact requested model/firmware, and the catalog signing key is intentionally absent. No register addresses or conversions have been guessed. The sandbox policy is rendered and unit-tested, but systemd/cgroup enforcement is not operationally tested in this container. See `docs/deye/README.md`, `docs/dependencies/README.md`, and `docs/isolated-connectors.md`.

## CODE 02 v0.6.2 — incremental equipment registry and IPC

This package adds an additive Energy equipment API and trust/evidence data model, a standalone allowlisted connector worker with Unix-socket IPC, and a fail-closed signed activation journal. The 119 reference tests are preserved; additional tests cover the new primitives. The worker's local process/IPC tests do not establish systemd/cgroup isolation. The original PWA source is not present in the v0.6.1 source archive, so the existing PWA menu has not been claimed as integrated. The worker activation flow is not yet end-to-end wired into the Connector Manager, and atomic systemd/filesystem rollback remains blocked pending operational Debian VM validation. See `docs/CODE02_V062_ENERGY_AND_WORKERS.md`, `docs/CODE02_V062_PHYSICAL_VALIDATION.md`, and `docs/CODE02_V062_DEYE_PROFILE.md`.

## CODE 02 v0.6.4 — worker transport integration and local recovery primitive

This incremental candidate routes TCP connector tests and bounded network discovery through the supervised worker process. It serves the independent The Solar Miner PWA from the Gateway HTTPS origin and packages its static assets under `/usr/share/solarminer/pwa`. It adds a conservative `AtomicReleaseStore.recover_interrupted()` helper for a process restart that leaves an uncommitted active pointer. The helper is not wired into startup or a full update orchestrator; it only reconciles the filesystem pointer/journal and does not coordinate SQLite or systemd. See `docs/CODE02_V064_IMPLEMENTATION.md` and `docs/CODE02_V064_TESTING.md`.


## CODE 02 v0.6.5 — browser pairing and authenticated read-only PWA

Adds an administrator-authorized, single-use pairing code scoped to an active username, Ed25519 proof of possession from the browser, and a non-exportable Web Crypto private key stored as a CryptoKey in IndexedDB. The browser then uses the established `LOGIN` canonical signature format, keeps the 8-hour bearer session in memory only, reads the existing `/api/v1/energy/*` endpoints, and calls the existing logout/revocation API. No refresh token, device-control endpoint, or write operation was added. See `docs/CODE02_V065_AUTH.md` and `web/pwa/README.md`.

The backend's original 163-test regression baseline is retained; new tests cover one-time/expired pairing codes, signature and timestamp failures, read authorization, logout, and Node WebCrypto interoperability with the Python Gateway verifier. The PWA includes automated crypto/auth-client tests. Local integration tests do not validate Safari/iOS, production TLS/DNS, Tailscale, Debian systemd enforcement, or physical equipment.


## CODE 02 v0.6.6 — additive user presence API

This source increment adds `POST /api/v1/presence/heartbeat` and `GET /api/v1/presence/me`, backed by a new SQLite table/migration. Identity is derived from the existing authenticated session and active user-device association; the client cannot declare another user/device or claim LAN/REMOTE. Presence expires after 120 seconds without a successful heartbeat, and logout deletes the current session's user/device presence. Heartbeat writes are throttled to one persisted update per five seconds and transitions are audited.

The Gateway identity attestation endpoint is still not implemented. The presence method therefore remains `unknown`; online is not proof of physical presence at home. This source archive is not installed on a physical Gateway.

## v0.6.9 — pipeline de atualização ponta-a-ponta

A instalação inicial Debian amd64 está documentada em `docs/INSTALL_DEBIAN_AMD64.md`. A rotina de verificação assinada é agendada diariamente após configuração da allowlist; consulta e prepara releases, mas a aplicação requer confirmação do Owner na PWA.

Esta árvore contém a implementação incremental CODE02 v0.6.9 com PWA v0.5.7 incorporada e pipeline de atualização/recuperação. Consultar `docs/CODE02_V069_IMPLEMENTATION.md`, `docs/DATABASE_BACKUP_AND_RESTORE.md`, `docs/UPDATE_AND_ROLLBACK.md`, `docs/ACCEPTANCE_MATRIX_V069.md`, `docs/TEST_REPORT_V069.md` e `docs/V069_LIMITATIONS.md` para âmbito, evidências e limitações.

O endpoint de aplicação só responde HTTP 202 quando a assinatura, o helper root, o symlink de release, a chave pública, o certificado TLS, a base SQLite e o timer de recuperação passam o pré-voo; caso contrário permanece bloqueado com HTTP 503. O pipeline tem testes automatizados com `.deb` descartável, mas ainda requer instalação/upgrade em host Debian de ensaio, reboot e falhas reais antes de aprovar instalação no Gateway físico ou produção.
