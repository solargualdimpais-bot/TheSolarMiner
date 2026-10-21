# CODE 02 v0.6.3 test report

## Test totals (unique functional test suite)

| Target | Result | Meaning |
|---|---:|---|
| v0.6.2 baseline before modifications | 148 passed | Regression baseline, run against a separate extraction |
| v0.6.3 source tree after modifications | 158 passed | 148 inherited tests + 10 additional test cases (parameterized cases expand collection) |
| v0.6.3 Debian-extracted modules | 158 passed | Same test suite imported against modules extracted from the built package |
| v0.6.3 ZIP-extracted source | 158 passed | Same test suite against a fresh extraction of the final ZIP |
| Independent Debian rebuild | PASS | Two builds byte-identical SHA-256 |
| Gateway systemd unit static syntax | PASS | `systemd-analyze verify`; not runtime enforcement |
| Generated worker unit static syntax | PASS | `systemd-analyze verify`; not runtime enforcement |
| Physical Debian target checks | BLOCKED_NO_TARGET_ENV | No target system changed or installed |
| Physical equipment tests | NOT RUN | No equipment connected; no physical operations performed |

## New v0.6.3 tests

- Real subprocess startup, health IPC, connector identity, liveness and termination.
- Invalid worker ID/timeout rejection.
- Signed ZIP activation, hash recheck, staged validation, active pointer commit and previous-release preservation.
- Rollback after post-switch fault and preservation of active pointer on staging/validation/pre-switch failures.
- Artifact tampering, unsealed manifest rejection and ZIP traversal rejection.

## Important limitations

The test counts across source, Debian extraction and ZIP extraction are repeatability targets, not three independent sets of 158 unique scenarios. The update transaction is tested as a local filesystem component, not integrated with the Gateway database/systemd transaction. The worker health exchange is integrated into connector installation preflight, but the existing TCP probe still executes in-process. Static systemd syntax checks do not prove kernel/systemd isolation enforcement. All protocol/physical workflow tests remain simulated. The original PWA source was not available, so no PWA integration tests could be run.

## Reproduction

From the source root:

```sh
PYTHONPATH=src python3 -m pytest -q
```

For the Debian target, extract with `dpkg-deb -x solarminer-gateway_0.6.3_amd64.deb /tmp/sm-deb-extract` and run `PYTHONPATH=/tmp/sm-deb-extract/usr/lib/solarminer-gateway python3 -m pytest -q` from the source root. For ZIP, extract to a clean directory and run the source command there.
