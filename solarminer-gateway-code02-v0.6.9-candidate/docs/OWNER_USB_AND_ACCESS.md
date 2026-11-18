# Owner USB and account access

## Recovery key

During first Owner registration, the Gateway generates a one-time recovery key. The Owner PWA v0.6.18 allows downloading it together with the Gateway Ed25519 fingerprint as `solarminer-owner-recovery-key.txt`, which can be copied to a dedicated offline USB drive. The file is plaintext. Anyone who obtains the secret can initiate the Owner recovery flow, so protect the drive physically and replace the file after recovery rotates the key.

The recovery key is not accepted by any HTTP endpoint. Owner recovery requires local interactive root access to the Gateway and the service stopped, following `A2_OWNER_RECOVERY.md`. The PWA cannot recover an Owner account.

## User and role management

The authenticated Owner PWA reads actual accounts from the Gateway database using `GET /api/v1/users`. Role and status changes use the existing authenticated routes and require the Owner's current password again. The Gateway audits these operations and enforces the last-active-Owner invariant. The current Owner cannot demote or revoke their own active session through this screen. The UI does not promote accounts to Owner; first-owner creation uses the initial setup flow, and account recovery is local-only.

Use one-time Gateway invitations to enroll new users and devices. Do not edit the live SQLite database directly on a desktop: copying only `gateway.db` while WAL is active can omit committed data, and raw SQL can violate ownership, audit, or session invariants. Use the PWA for ordinary access changes and the backup/recovery commands for offline repair.
