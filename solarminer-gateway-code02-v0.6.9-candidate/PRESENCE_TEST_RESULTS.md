# CODE 02 v0.6.6 presence — test results

## Presence tests

`PYTHONPATH=src python3 -m pytest -q tests/test_presence.py`

Result: **7 passed**.

Coverage: unauthenticated denial; session-derived identity; 120-second TTL; unknown/online/offline semantics; five-second throttling; logout invalidation; client cannot claim LAN/REMOTE or target another user; audit of online transition.

## Existing test modules, executed individually

| Module | Result |
|---|---:|
| `test_browser_pairing.py` | 10 passed |
| `test_code02_v061.py` | 40 passed |
| `test_code02_v062.py` | 29 passed |
| `test_code02_v063.py` | 10 passed |
| `test_code02_v064.py` | 5 passed |
| `test_connectors.py` | 9 passed |
| `test_gateway.py` | 42 passed |
| `test_presence.py` | 7 passed |
| `test_recovery.py` | 28 passed |
| **Total across individual module runs** | **180 passed** |

Each module passed when run as its own pytest invocation. A single combined invocation timed out in this environment during the recovery module after earlier tests had passed; therefore no aggregate-suite PASS is claimed. The old CODE 02 v0.6.5 archive remains intact.

## Package checks

- Debian package build succeeded.
- Two independent Debian builds produced the same SHA-256.
- `dpkg-deb --info` and `dpkg-deb --contents` passed.
- No package installation or service start was performed.

## Limits

These are local software tests. They do not validate deployment permissions, real iOS heartbeat timing, physical presence, LAN/REMOTE classification, Gateway cryptographic identity attestation, or physical Gateway operation.
