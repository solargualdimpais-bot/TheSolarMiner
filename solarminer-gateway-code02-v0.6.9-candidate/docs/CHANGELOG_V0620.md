# SolarMiner Gateway 0.6.20

- Adds an Owner-only PWA action that starts `tailscale up` on the Gateway and returns only a validated Tailscale authorization URL.
- The PWA can open the one-time authorization link; it does not receive command output, credentials, or Tailscale keys.
- Gateway Tailscale enrollment still requires approval in the user's existing Tailscale account. MagicDNS and HTTPS Certificates remain one-time Tailnet settings.
- Keeps automatic certificate issuance and renewal after the Gateway has joined the Tailnet.
