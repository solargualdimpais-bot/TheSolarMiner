# SolarMiner Gateway 0.6.21

- Fix Nginx HTTPS proxying for LAN and Tailscale endpoints by verifying the backend TLS certificate against its provisioned `localhost` DNS SAN.
- Keep backend certificate verification enabled; no TLS verification is disabled and no private key is exposed to the PWA.
- Bump installer, package, API-reported package version, and PWA cache identifiers to 0.6.21.
