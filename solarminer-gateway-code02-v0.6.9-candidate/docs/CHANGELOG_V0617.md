# SolarMiner Gateway 0.6.17

- Bundles the Owner PWA user-management screen backed by the existing Gateway API.
- Adds download of the one-time Owner recovery key to a file for storage on a dedicated offline USB drive.
- Adds the PWA form to load that file and complete the existing Ed25519-proven Owner recovery flow; recovery rotates and consumes the old key.
- Keeps user mutations authenticated, requires current-password reauthentication, preserves audit logging and protects the final active Owner.
- Updates the embedded PWA cache and package version so installed service workers retrieve the changed interface.
- Documents recovery-key handling and the supported workflow for account/database recovery.
