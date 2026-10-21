# Per-connector Python dependencies

`connector_dependencies.py` implements an offline-only dependency installation path. Each connector gets `/var/lib/solarminer/connectors/{id}/venv`; manifests pin package versions, wheel filenames, source identifiers and SHA-256 hashes. All wheel hashes are verified before `venv` creation. Installation invokes that venv's Python with `-I -m pip install --no-index --find-links ... --require-hashes --no-deps`; it never uses global `pip` and never resolves dependencies online. The manifest must list every transitive dependency explicitly.

The current built-in TCP and Deye raw Modbus connectors use only Python standard-library modules, so their dependency manifests are empty. No third-party connector is activated by this release. Empty manifests do not prove the sandbox works.

The dependency layer is not a security boundary. A separate systemd sandbox is required for connector execution. Wheel source metadata is recorded for audit, but this code validates file hashes and allowed source URI schemes; a release signer must authenticate the manifest itself. Do not put credentials in a manifest or requirements file.

Runtime discovery/build facts for this artifact: the build/test container reports Debian GNU/Linux 13.3 and Python 3.13. It does not prove that the target Lenovo gateway has the same Debian/Python version. The package's existing minimum Debian dependency contract remains Python >= 3.11; the installer must validate the actual target runtime before using a connector venv.
