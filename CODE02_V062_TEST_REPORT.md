# CODE 02 v0.6.2 test report

## Results obtained

| Target | Result | Interpretation |
|---|---:|---|
| v0.6.1 source baseline, before changes | 119 passed | Reference regression baseline |
| v0.6.2 source tree | 148 passed | 119 reference tests + 29 new cases |
| Modules extracted from v0.6.2 Debian package | 148 passed | Package module test run |
| Extracted v0.6.2 source ZIP | 148 passed | Archive extracted and tested independently |
| Debian build repeatability | PASS | Two independent builds had identical SHA-256 |
| `dpkg-deb --info` / metadata | PASS | Package is `solarminer-gateway` 0.6.2 amd64 |
| Generated worker unit static syntax | PASS | `systemd-analyze verify` with `/usr/bin/python3`; not runtime enforcement |
| Packaged Gateway unit static syntax | PASS | `systemd-analyze verify` |
| Operational systemd status | BLOCKED | `systemctl is-system-running` returned `offline` |
| Physical equipment validation | NOT RUN | No physical hardware access |

## New test coverage

- IPC request schema, operation allowlist, argument restrictions, bounded frames, peer UID validation and real worker subprocess health exchange.
- Energy categories and equipment profile persistence, reading provenance/trust, invalid trust values, and prevention of direct physical-corroboration claims.
- Physical test proposal/approval/evidence flow, PASS result handling, exact-value matching for field-specific corroboration, no promotion of simulated values, blocking obvious hazardous steps, and result-only-after-observation enforcement.
- Ed25519 signature verification, artifact SHA-256, tamper rejection, required lifecycle evidence and invalid state transitions.
- Authenticated energy API access, reuse of existing RBAC, category navigation contract, profile/readings API and audit records.

## Regression integrity

The three inherited test files (`test_connectors.py`, `test_gateway.py`, `test_recovery.py`) were not modified. The original 119-test suite passed before any modifications and passed again as part of the v0.6.2 suite. No historical artifact was overwritten.

## What these tests do not prove

Local tests do not prove that systemd enforces the generated sandbox, that workers run under separate OS identities in a deployed system, that network restrictions are active, that atomic rollback survives power loss, that the existing PWA is integrated, or that any equipment register map is correct. These items remain blocked/not validated as stated in the implementation report.
