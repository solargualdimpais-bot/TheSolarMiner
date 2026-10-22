# PWA v0.5.8

- Adds a live Owner user list backed by the Gateway API, with separately confirmed role and status changes.
- Requires current Owner password for every change; self-changes are disabled in the UI and the Gateway keeps the last-active-Owner invariant and audit records.
- Adds a one-time recovery-key text-file download so the Owner can store the existing recovery secret on a dedicated offline USB drive.
- Adds a PWA recovery form that loads that file and uses the Gateway's existing Ed25519 challenge-based recovery flow; the old key is consumed and replaced.
- Bumps the static service-worker cache to v0.5.8 so installed PWAs retrieve these files.
- Documents that the USB recovery file is a sensitive, revocable bearer secret; it does not contain release signing private keys, bypass TLS, or automatically log in.
