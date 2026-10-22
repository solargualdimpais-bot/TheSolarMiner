# SolarMiner Gateway 0.6.16

## First Owner onboarding and device sessions

- The first-install USB script now asks locally for an Owner password with visible terminal input, confirms it, and stores only a temporary Argon2id verifier.
- The PWA shows a first-Owner registration popup only when the Gateway reports that no Owner exists. It asks for an Owner name and the locally selected password; it no longer asks for a bootstrap token, MAC address, or manually copied Gateway fingerprint.
- The Gateway consumes the setup verifier in the transaction that creates the first Owner and its Ed25519 device identity. Bootstrap requests are origin-restricted, signed, replay-protected, single-use and rate-limited.
- The PWA stores the device private key as a non-exportable CryptoKey and reconnects with a fresh Ed25519 device-login proof. The Owner password is not requested again on that registered device.
- The endpoint-only connection UI and first-Owner popup are synchronized between GitHub Pages and the Gateway-packaged PWA.
- Added API, installation and recovery documentation and tests for the console password, first-Owner bootstrap and password-free device login.
