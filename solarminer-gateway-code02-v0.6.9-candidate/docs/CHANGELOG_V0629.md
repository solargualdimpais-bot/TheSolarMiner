# SolarMiner Gateway 0.6.29

- Serve every JavaScript module imported by the Gateway-hosted PWA, with the same-origin Content Security Policy. Previously, several module URLs returned 404, which stopped app initialization and left the interface controls inactive.
- When the PWA is opened directly on the Gateway HTTPS port or its Tailscale HTTPS name, select that same origin automatically and start the normal health, bootstrap, and session check.
- Keep standalone GitHub Pages endpoint selection unchanged.
