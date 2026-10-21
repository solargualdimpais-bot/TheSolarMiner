# SolarMiner Gateway — CODE 02 v0.6.1 implementation report

## Result classification

- **IMPLEMENTED_AND_TESTED_LOCALLY** — regression suite plus new unit tests; hash-pinned offline dependency-manifest validation; Modbus TCP FC03 request/response parsing; systemd sandbox policy rendering and input validation.
- **SIMULATED** — Modbus responses in unit tests are produced by a fake socket; no live inverter or Modbus test server was available.
- **NOT_VALIDATED_ON_HARDWARE** — no physical Deye inverter communication was performed.
- **BLOCKED** — Deye metrics/register-map compatibility, signed-catalog activation, sandbox operational verification, and Connector Manager dispatch of Deye through the sandbox.

## Reference integrity

The v0.6.0 Debian package SHA-256 matches the supplied reference: `3878482ea137ce331fb3e069a728ca64477c1ac936ac528e29f36791d0bbd2a3`. The v0.6.0 implementation report SHA-256 matches the supplied reference: `c60b1e98a13921f8e7e4b077f4b01b1a95bbf600ef581cfbf88f56afb465bd2f`.

The available v0.6.0 source ZIP, Debian package, and implementation report all match the three supplied reference SHA-256 values exactly. The reference values are preserved in `evidence/code02-v061/reference-hashes-actual.txt`; the SHA-256 values for this v0.6.1 delivery are in the external `SOLARMINER_CODE02_ARTIFACT_MANIFEST_v0.6.1.sha256`. Additional byte comparisons confirm that the five core modules (`app.py`, `cli.py`, `recovery.py`, `connectors.py`, `connector_plugins.py`), three existing test modules, and signed catalog JSON/public key/signature were preserved where applicable. The existing CODE 01 original, A1b, A2, Prova 0 and v0.6.0 artifacts were not overwritten. The 79 original tests were not edited.

## Changes

1. `deye_modbus.py`: validates private/link-local IP targets, port/unit/timeouts/address/count, issues only Modbus FC03, validates MBAP and PDU response framing, reports protocol exceptions and timeouts distinctly, and returns raw data with units/scaling unknown. The module has no Modbus write implementation. It refuses to decode metrics until an applicable register map is verified.
2. `isolated_runtime.py`: renders a restrictive systemd service policy using a dedicated unprivileged user, filesystem protections, no-new-privileges, private temp/devices, syscall and namespace restrictions, resource limits, cgroup-wide process termination, and deny-by-default networking with a single private-IP allowance (`/32` for IPv4 and `/128` for IPv6).
3. `connector_dependencies.py`: verifies wheel SHA-256 hashes and manifest metadata, creates a per-connector venv using the explicitly selected `base_python`, rejects duplicate normalized package names, and installs only from a local wheelhouse with pip `--no-index --require-hashes --no-deps`. It does not install into the global Python environment. Partial venv creation and install failures clean up only the operation-created venv and manifest.
4. Documentation records the Deye model/register-map blocker and sandbox operational limitations, plus staged installation/rollback/recovery instructions.

## Deye documentation assessment

The official Deye site publishes a manual for the `SUN-(14-20)K-SG05LP3-EU-SM2` family and a product-family page. The documentation available for this iteration does not establish a register table applicable to the exact reference `SUN-15K-SG05LP3-EU` without `SM2`, including firmware-specific register semantics. Therefore no addresses, scales, units, signedness, word order, or conversions have been added. The module currently provides raw FC03 reads only and labels results `RAW_READ_ONLY_UNMAPPED`, `UNKNOWN`, `NOT_VERIFIED`, and `NOT_VALIDATED_ON_HARDWARE`.

Official sources:
- https://www.deyeinverter.com/download/product-manual/
- https://www.deyeinverter.com/product/three-phase-hybrid-inverter-1/sun14-15-16-18-20ksg05lp3eusm2-1420kw-three-phase-2-mppt-hybrid-inverter-lv-battery-supported.html

## Catalog and activation safety

The original signed catalog and trust anchor were preserved byte-for-byte. The private Ed25519 signing key is absent, as expected. The Deye entry is a separate explicitly unsigned draft (`packaging/catalog-draft-deye-modbus-tcp-v0.6.1.json`) and is not accepted by runtime. It would be unsafe to silently replace the trust anchor or forge a new catalog signature. A model-applicable register map, owner-controlled signing, and a reviewed Connector Manager-to-sandbox dispatch path are required before activation.

## Test results

- Baseline before changes: **79 passed** (`PYTHONPATH=src python3 -m pytest -q`).
- Final source test suite: **119 passed**. This includes all 79 pre-existing tests unchanged and 40 new parametrized/unit cases.
- Modbus tests are simulated using a fake socket. They verify FC03 framing and raw response handling, invalid targets/parameters, malformed MBAP/PDU, exception responses, and timeout handling. They are not physical validation.
- Systemd unit rendering is tested as text/policy, and `systemd-analyze verify` passes on a generated connector service unit. This is not proof that a live systemd/cgroup network sandbox is enforced.
- Target environment: build/test container reports Debian GNU/Linux 13.3 and Python 3.13. The actual target gateway runtime remains unverified.

## Not completed

- No Deye register-map metrics or unit conversion because an applicable verified map was not found.
- Deye not activated in the signed catalog; catalog signing key unavailable.
- No live systemd operational test; current environment has no active systemd system manager.
- No worker IPC/Connector Manager dispatch path has been wired for Deye, and third-party code execution is not enabled.
- No PWA integration; PWA source is not present in this repository.
- No physical device, remote update, production install, or hardware-control validation was performed.

## Conclusion

The Makefile package target was corrected to refer to the v0.6.1 Debian filename. CODE 02 v0.6.1 is a partial incremental hardening release, not full completion of the stated target. It preserves the original regression suite and adds tested read-only Modbus transport primitives, dependency verification, and a sandbox policy renderer. It does not claim operational isolation, Deye model compatibility, register-map validity, or physical-device success.
