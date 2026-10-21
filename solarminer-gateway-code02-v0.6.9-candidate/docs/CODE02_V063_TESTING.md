# Reproducing CODE 02 v0.6.3 tests

Requirements: Python 3.11+, pytest, dependencies listed by the package (including cryptography and FastAPI dependencies). No VM is required.

From the extracted source root:

```sh
PYTHONPATH=src python3 -m pytest -q
```

Package target: extract the generated `.deb` with `dpkg-deb -x`, then run the same tests with `PYTHONPATH` pointing at the extracted `/usr/lib/solarminer-gateway` directory. Archive target: extract the delivered source ZIP and run the command above. Compare test totals and preserve the per-target logs in the manifest.

Local tests simulate signed artifacts and release faults. They do not prove systemd enforcement, crash consistency on the target filesystem, PWA integration or physical equipment compatibility.
