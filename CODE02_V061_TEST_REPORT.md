# CODE 02 v0.6.1 — test report

## Summary

- Source tree: **119 passed**.
- Tests against modules extracted from the built Debian package: **119 passed**.
- Tests from the final extracted source ZIP: **119 passed**.
- ZIP integrity: `unzip -t` passed with no errors.
- Debian package: built successfully; `dpkg-deb --info` and `dpkg-deb --contents` passed.
- Reproducibility: two independent builds of the Debian package produced the same SHA-256.
- `systemd-analyze verify`: passed for the generated connector policy unit and packaged Gateway unit (static syntax only).
- A direct local smoke test created a venv with the explicitly selected Python interpreter and installed an empty offline manifest successfully.

## Regression preservation

The three prior test files were byte-identical to the available v0.6.0 ZIP:

- `tests/test_connectors.py` SHA-256 `71c075c177a0c3886c46a9fffe70ad214f0b78262b45a8e7f18ae61bb3662769`
- `tests/test_gateway.py` SHA-256 `8a4f302d7204eb4f847d5690c3a740a699f0a7bd5936bb04b549b43ce7f191ed`
- `tests/test_recovery.py` SHA-256 `fea79dbe63b2b8c4cf014e2cf0640fd6aa9cdd23b9ec35fb8ef5cd2a8a578da4`

The 79 original tests were not edited. The new test module contributes 40 cases, including parameterized cases, covering FC03-only Modbus framing, malformed/exception responses, timeouts, unsafe targets, unknown metric-map fail-closed behavior, sandbox policy restrictions including IPv6 `/128` allowlisting, dependency wheel hashes/source metadata, normalized duplicate-package rejection, explicit base-interpreter venv creation, independent venv paths, offline pip flags, and cleanup after venv-creation or install failure.

## Evidence files

- `solarminer-code02-v061-pytest.log`
- `solarminer-code02-v061-pytest-package.log`
- `solarminer-code02-v061-pytest-zip.log`
- `solarminer-code02-v061-final-zip-test.log`
- `solarminer-code02-work/solarminer-gateway-code02-v0.6.1/evidence/code02-v061/`

## Limits

All Modbus protocol tests use simulated responses. No physical Deye inverter, live Modbus test server, production installation, or operational systemd sandbox was available. A successful static unit verification does not prove cgroup, filesystem, or network restrictions are enforced at runtime. The Deye model-specific register map and signed-catalog activation remain blocked. The available v0.6.0 source ZIP, Debian package, and implementation report all match the supplied reference SHA-256 values exactly. The three prior regression test files were byte-identical to the v0.6.0 archive and remain unchanged.
