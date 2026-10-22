# Owner USB and account access

## Recovery key

During first Owner registration, the Gateway generates a one-time recovery key. The Owner PWA v0.6.17 allows downloading it together with the Gateway Ed25519 fingerprint as `solarminer-owner-recovery-key.txt`, which can be copied to a dedicated offline USB drive. The file is plaintext. Anyone who obtains the secret can initiate the Owner recovery flow, so protect the drive physically and replace the file after recovery rotates the key.

The PWA's **Recover Owner with USB** form reads this file, creates a new device identity in the browser, and completes the existing recovery challenge. This recovery key is not the Ed25519 release-signing private key, contains no GitHub credentials, does not validate TLS certificates, and does not bypass normal authentication. Insertion of the USB drive does not silently log into the PWA or grant operating-system root access.

## User and role management

The authenticated Owner PWA reads actual accounts from the Gateway database using `GET /api/v1/users`. Role and status changes use the existing authenticated routes and require the Owner's current password again. The Gateway audits these operations and enforces the last-active-Owner invariant. The current Owner cannot demote or revoke their own active session through this screen. The UI does not promote accounts to Owner; Owner creation and recovery stay in the dedicated flow that issues a recovery key.

Use one-time Gateway invitations to enroll new users and devices. Do not edit the live SQLite database directly on a desktop: copying only `gateway.db` while WAL is active can omit committed data, and raw SQL can violate ownership, audit, or session invariants. Use the PWA for ordinary access changes and the backup/recovery commands for offline repair.
