# Gateway 0.6.97 / Owner PWA 0.5.61

- Gateway invite creation now issues a short-lived single-use code and identity fingerprint; it no longer expects a manually provisioned `SOLARMINER_PUBLIC_URL` or generates an SVG.
- The PWA generates the QR and activation link locally, using LAN and ready Tailscale Gateway endpoints.
- Scanning opens the PWA activation form, which registers a username, password and this browser's device identity with the Gateway.
- Invite redemption remains single-use and role-limited; no Tailscale auth key or tailnet enrollment is embedded in the QR.
- See `docs/INVITE_ACTIVATION.md` for the activation flow and its LAN/Tailscale requirements.
