# Owner PWA 0.5.62

- Invite QR creation now requires the Gateway's ready Tailscale MagicDNS HTTPS endpoint and embeds only that endpoint. This avoids sending invitees to a self-signed LAN certificate that their browser cannot trust automatically.
- Clear recovery guidance is shown if the Gateway's Tailscale HTTPS certificate or endpoint is not ready.
- The existing one-time activation link still opens the PWA, verifies the Gateway identity, creates the invited account, associates the device key and signs the new user into the PWA.