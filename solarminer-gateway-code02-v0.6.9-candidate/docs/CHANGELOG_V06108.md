# SolarMiner Gateway 0.6.108

- Reconstruct the public Gateway identity key from the existing private key when Debian was reinstalled but the persistent data volume was preserved.
- Preserve the existing private key and continue to fail closed when the private key is missing, invalid, or conflicts with an existing public key.
- Add regression coverage for persistent-identity recovery.