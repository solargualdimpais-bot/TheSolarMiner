# SolarMiner Gateway 0.6.18

- Added the Nginx public HTTPS edge while keeping the Gateway API bound to loopback; packaged TCP 80 ACME challenge and TCP 443 reverse proxy.
- Added automatic Let's Encrypt public IPv4 certificate issuance and renewal with a pinned Certbot release, preserving the local certificate for internal health checks and proxy verification.
- Added password-based authentication for a new PWA browser device. The Gateway verifies an Ed25519 proof, Argon2id credentials, active account state and per-IP/per-account rate limits before associating the device and creating a session.
- Added a visible username/password sign-in panel after Gateway reachability checks. Existing browser identities continue using their device-key proof; credentials are cleared from the form after submission.
- Fixed Nginx package-install ordering so the site configuration is installed only after its fallback certificate exists; added Nginx configuration validation before service restart.
- Fixed client-IP attribution for Gateway login and bootstrap throttling behind Nginx.
- Updated the PWA service-worker cache key and synchronized the Gateway-embedded copy.
- Documented public-IP setup, router forwarding, NAT loopback, CGNAT and the remaining external-network checks.

## Verification

The release build still requires the GitHub Actions release-signing secret. Local tests and Debian package assembly must pass before publishing; a physical first-boot and external-network TLS test remain necessary to confirm router/ISP behavior.
