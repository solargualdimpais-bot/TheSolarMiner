# Gateway 0.6.98 / Owner PWA 0.5.62

- Invite QR activation now uses only the Gateway's ready Tailscale MagicDNS HTTPS endpoint. The PWA refuses to generate a QR until that endpoint and its trusted certificate are ready, with clear guidance if setup is incomplete.
- New invitees manually connect their phone to the existing Tailnet, then scan the QR, choose a username and password, and are registered/authenticated automatically. No certificate installation or TLS bypass is used.