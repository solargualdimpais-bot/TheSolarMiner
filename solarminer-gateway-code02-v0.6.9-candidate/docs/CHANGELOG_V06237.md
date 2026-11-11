# Gateway 0.6.237

## Installer reliability

- Explicitly records whether the USB installer created a new `SOLARMINER_DATA` partition or reused an existing one.
- Skips the existing-Owner lookup for a partition created during the current installation, so a fresh 64 GB Debian system partition with a separate free-space data partition always follows first-owner setup.
- Verifies and logs the mounted data volume UUID and source device before inspecting any database.
- Refuses to treat a database without its initialization marker as a verified existing Owner.
- Includes the Tailscale and HTTPS endpoint setup and validation from 0.6.236.
