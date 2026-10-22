# SolarMiner Gateway 0.6.28

- Route Tailscale status and authorization requests through the fixed root-owned helper broker. The Gateway API no longer tries to elevate with `sudo`, which systemd deliberately blocks.
- Validate and sanitize the Tailscale helper response before returning an endpoint or authorization link to the Owner PWA.
- Treat a failed or incomplete `tailscale up` response as an error; the PWA cannot show a false “already connected” state without a confirmed connection or valid authorization URL.
- Report Tailscale helper availability separately from whether the Tailscale client is installed, so an outdated Gateway does not show a false installation diagnosis.
- Leave the public-IP ACME renewal service disabled by default; it is unnecessary for Tailscale and fails behind CGNAT.
- Move Owner-only user, invitation, hardware, Tailscale and update controls into a dedicated Owner page.
- Keep the authenticated Home dashboard focused on energy equipment and display each received reading with its actual field name and unit.
- Synchronize the standalone Owner PWA with the copy packaged in the Gateway and invalidate the static cache.
