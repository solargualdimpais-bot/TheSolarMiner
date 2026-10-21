# VALIDATION_REPORT.md — SolarMiner Gateway v0.4.0 / CODE 01

**Validation status: PARTIALLY VALIDATED — DO NOT MARK CODE 01 COMPLETE.**  
**Hardware status: NOT_VALIDATED_ON_HARDWARE.**  
Date: 2026-10-18.

## 1. Initial workspace and repository status

The environment is Debian GNU/Linux 13.3 (Trixie), amd64, Python 3.13.5. No SolarMiner Git repository or `.git` worktree was available in the accessible workspace, and the connected GitHub repository list was empty. Therefore, a repository-wide inspection, original branch/commit capture, and in-place repository change could not be performed. The CODE 01 project was created in a new isolated directory: `/mnt/data/solarminer-code01-work/solarminer-gateway`.

The Prova 0 source archive was inspected without modifying it. It contains `README.md`, `REPORT.md`, `build.sh`, `src/solarminer-prova0/app.py`, packaging scripts and service unit, tests, and evidence files. The original build command is `sh ./build.sh [output-directory]`; by default it writes `dist/solarminer-prova0_0.1.0_amd64.deb` inside the source tree. The CODE 01 build is a separate script and writes only `dist/solarminer-gateway_0.4.0_amd64.deb` under the new project directory.

## 2. Protected Prova 0 artifacts and preservation

| Artifact | SHA-256 before / known initial | SHA-256 after |
|---|---|---|
| `/mnt/data/solarminer-prova0_0.1.0_amd64.deb` | `8716677481e91dd3b95f3de3ca84c9d0076cc708996a21d0211da858edad7fa6` | `8716677481e91dd3b95f3de3ca84c9d0076cc708996a21d0211da858edad7fa6` |
| `/mnt/data/solarminer-prova0-source.zip` | `e40c462bc3ae638ad73ce48218a81079a9da62b1194dfdc87fa70218092ba4bc` | `e40c462bc3ae638ad73ce48218a81079a9da62b1194dfdc87fa70218092ba4bc` |
| `/mnt/data/solarminer-prova0-REPORT.md` | `94a510a941bf831191ee6e025cce6a327ed70fac36ee32755a85c18179617f6e` | `94a510a941bf831191ee6e025cce6a327ed70fac36ee32755a85c18179617f6e` |
| `/mnt/data/solarminer-prova0-FINAL-VALIDATION-2026-10-18-revised.md` | `d8b503d9a54abff492278837849af030d2c9fe10dd94d3608246050e02cd3e0d` | `d8b503d9a54abff492278837849af030d2c9fe10dd94d3608246050e02cd3e0d` |

The source ZIP passed `unzip -t`. No original Prova 0 artifact was overwritten, deleted, or used as CODE 01 output. The new build script contains no write path into the Prova 0 artifact locations.

### Isolated original-build/runtime checks

- The original `build.sh` was run from the extracted source archive with a separate temporary output directory. The rebuilt `.deb` SHA-256 was `b99114a51e4d900b82ed1ec5595cb4be056afd0c43060e60a2b49a0d9d573315`, different from the protected original package hash. Extracted payload files and control files were byte-for-byte identical to the protected package; the archive hash difference is therefore in Debian archive/container metadata, not in the extracted package payload/control contents. This isolated rebuild did not touch the original package.
- The protected package was extracted to a temporary directory and its original application was run against a temporary SQLite database. `GET /health` returned `{"status":"ok","version":"0.1.0"}`; a `POST /test-data` succeeded and a subsequent `GET /test-data` returned the persisted test record. This verifies the extracted Prova 0 application locally, not the systemd-managed installation.
- No package was installed on the host. PID 1 is `supervisord`; `systemctl is-system-running` reports `offline`. Systemd service lifecycle, install/remove/purge, and reboot validation remain unverified.

## 3. CODE 01 implementation summary

Implemented in the isolated new project:

- FastAPI-based v0.4.0 service and `/api/v1/health`, `/api/v1/info`, `/api/v1/status` endpoints.
- SQLite schema with migration version 1, foreign keys, transaction use for bootstrap, nonce consumption, session issuance and revocation, plus audit records.
- First-owner bootstrap token generated randomly and stored only in `/var/lib/solarminer/bootstrap.token` with restrictive directory/file modes. The database stores only a SHA-256 token digest and persistent expiry/consumption state. The token is not returned through HTTP or logged. The bootstrap endpoint checks loopback access and requires Ed25519 proof; the first owner can be created only once by this endpoint. Expired bootstrap is not automatically reissued and moves to `RECOVERY_REQUIRED`.
- Argon2id password hashing configured at memory=65536 KiB, iterations=3, parallelism=2.
- Opaque random bearer sessions; only token digests are stored. Sessions have expiry and are revoked on logout, device revocation and user revocation; password-change revocation is not implemented because a password-change endpoint is not implemented.
- Ed25519 device public-key identity; private keys are not stored by the gateway. Login includes a signature, timestamp and nonce. Nonce insertion uses a SQLite uniqueness constraint in the same transaction as session creation.
- Explicit role permission map for owner/admin/operator/viewer, protected API dependencies, and protection of the last active owner from revocation.
- Device/user associations in SQLite. MAC syntax is validated and normalized, but MACs remain `declared`; the API refuses to claim independent MAC verification.
- TLS-only service startup (fails closed if certificate/key are absent), package-time self-signed certificate generation, systemd unit, `docs/TLS_TRUST.md`, and endpoint documentation in `docs/API.md`.
- A separate Debian package build script and Makefile targets `make test` and `make deb`.

## 4. Test results

### `make test`

**PASS: 10 tests.** Command: `PYTHONPATH=src python3 -m pytest -q` via `make test`.

The local tests exercise:

1. Public health/info and bootstrap state.
2. Bootstrap token file mode `0600`, and absence of the token from the tested HTTP response/log capture.
3. End-to-end first-owner creation with a device Ed25519 signature.
4. Password login, session issuance, protected status access, logout and session rejection after logout.
5. Incorrect password and unauthenticated access rejection.
6. One-time bootstrap behavior.
7. MAC syntax rejection, declared MAC metadata, required device association, viewer read permission and rejection of viewer access to user administration.
8. Device revocation invalidating the associated viewer session.
9. Nonce replay and stale timestamp rejection.
10. Expired bootstrap state persists as recovery-required and does not reissue a token.
11. Concurrent bootstrap requests result in exactly one owner creation.
12. A live localhost TLS server accepts a certificate when explicitly trusted and rejects the same certificate when it is not trusted.

Some related assertions are grouped within the nine pytest tests. The suite does **not** cover every requirement listed in CODE 01; passing this suite does not mean CODE 01 is complete.

### `make deb`

**PASS.** The package was built twice independently using the project build command. Both resulting package hashes matched:

`975eda1d05e756a3685697f716b8998fc7bd351122e97c4a04cb36cbcbdb152a  solarminer-gateway_0.4.0_amd64.deb`

The build uses `SOURCE_DATE_EPOCH=0`; two builds in this environment produced identical hashes. `dpkg-deb --info`, `dpkg-deb --contents`, and `systemd-analyze verify packaging/solarminer-gateway.service` succeeded. Package installation scripts were inspected but not executed because the environment does not have an active systemd manager and host installation was avoided.

## 5. Feature classification

| Feature | Classification | Evidence / limitation |
|---|---|---|
| Separate build output and Prova 0 artifact preservation | `IMPLEMENTED_AND_TESTED_LOCALLY` | Protected hashes unchanged; isolated CODE 01 output; repeated CODE 01 builds match |
| Health/info/status API and basic protected status | `IMPLEMENTED_AND_TESTED_LOCALLY` | TestClient and live local TLS test; status requires read permission |
| Bootstrap happy path, token mode, expiry/no automatic reissue, single-use/concurrency | `IMPLEMENTED_AND_TESTED_LOCALLY` | Local tests; no installed-service run |
| Argon2id password hash and login happy/negative paths | `IMPLEMENTED_AND_TESTED_LOCALLY` | Local API tests; credential-change flow not present |
| Ed25519 identity and signed login/bootstrap request | `IMPLEMENTED_AND_TESTED_LOCALLY` | Local key generation/signature tests; no browser client or physical client integration |
| Session issue/logout/device revocation and basic role enforcement | `IMPLEMENTED_AND_TESTED_LOCALLY` | Local tests; full role matrix and restart persistence not yet covered |
| SQLite baseline schema, transaction and nonce uniqueness | `IMPLEMENTED_AND_TESTED_LOCALLY` | Local tests; upgrade from an earlier production schema not applicable/verified |
| TLS certificate/name validation | `IMPLEMENTED_AND_TESTED_LOCALLY` | Local TLS server with trusted and untrusted client contexts |
| Debian package creation and archive reproducibility | `IMPLEMENTED_AND_TESTED_LOCALLY` | Two identical build hashes and structural checks |
| Prova 0 extracted app health and SQLite write/read | `IMPLEMENTED_AND_TESTED_LOCALLY` | Temporary DB and local HTTP requests, not systemd install |
| Independent MAC verification | `BLOCKED` | MAC is deliberately marked `declared`; no independent verifier exists |
| Local owner recovery procedure/CLI and audit-confirmed recovery | `BLOCKED` | State `RECOVERY_REQUIRED` exists, but secure recovery workflow is not implemented |
| Password change, role changes, complete multi-device association management, full admin/operator/viewer matrix | `BLOCKED` | Required endpoints/workflows/tests remain incomplete |
| Complete PWA signing/client enrollment workflow | `BLOCKED` | No browser client code supplied or implemented; browser MAC access is not assumed |
| Installed systemd lifecycle, install/remove/purge, reboot persistence | `NOT_VALIDATED_ON_HARDWARE` | No active systemd manager; package was not installed |
| Final TLS SANs and trust on the actual Gateway LAN address | `NOT_VALIDATED_ON_HARDWARE` | Package cert covers install hostname, localhost and 127.0.0.1 only; real LAN identity needs provisioning |
| Physical equipment/device integration | `NOT_VALIDATED_ON_HARDWARE` | No hardware was available |

## 6. Known gaps and security cautions

CODE 01 is **not complete**. The following critical requirements remain:

- Implement and test a secure local recovery procedure with explicit confirmation and audit records. Until then, an expired bootstrap intentionally leaves the service in `RECOVERY_REQUIRED` without automatic reissue.
- Implement password change and credential-version increment/session invalidation, user role changes with anti-escalation rules, complete device-association management, and the full permission matrix.
- Implement a usable client-side device-key enrollment/signing flow appropriate to the actual PWA/browser constraints.
- Expand tests for process-restart session persistence, all roles, failure injection around bootstrap persistence, nonce concurrency across independent clients, migration upgrade behavior, error/log redaction across all endpoints, and package install/remove/purge lifecycle.
- Verify package dependencies and postinst behavior on a clean Debian 13 installation with active systemd; run the service under systemd, test its health and restart behavior, and test removal while confirming data preservation.
- Provision a certificate whose SANs match the real Gateway network DNS/IP and verify trust on supported clients. Do not disable TLS verification.
- Audit the loopback-only bootstrap rule in the intended network topology; do not publish or reverse-proxy the bootstrap endpoint in a way that makes remote clients appear as loopback peers.

No HMAC protocol is implemented; request replay defense currently applies to signed bootstrap and login operations using timestamps and nonces. No integrations for Deye, Antminer, Tesla, Tuya, MOES, Shelly, ONVIF/RTSP, energy engine or signed updates are claimed.

## 7. Commands used

```sh
sha256sum /mnt/data/solarminer-prova0_0.1.0_amd64.deb /mnt/data/solarminer-prova0-source.zip
unzip -t /mnt/data/solarminer-prova0-source.zip
sh ./build.sh /mnt/data/solarminer-code01-work/prova0-rebuild-check
make test
make deb
sha256sum dist/solarminer-gateway_0.4.0_amd64.deb
dpkg-deb --info dist/solarminer-gateway_0.4.0_amd64.deb
dpkg-deb --contents dist/solarminer-gateway_0.4.0_amd64.deb
systemd-analyze verify packaging/solarminer-gateway.service
```

## 8. Final decision

**CODE 01: PARTIALLY VALIDATED; not ready to declare complete.** The new service foundation, local authentication/bootstrap tests, live TLS trust test, isolated Debian build and Prova 0 preservation checks produced useful evidence. Critical recovery, complete authorization workflows, browser client integration and actual systemd/hardware validation remain open. Do not start CODE 02 until these results have been reviewed and the remaining CODE 01 requirements have been addressed.
