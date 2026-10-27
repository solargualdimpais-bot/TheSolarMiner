# Gateway 0.6.96 / Owner PWA 0.5.60

- Add delayed rollback after six consecutive local health failures following a committed update, within a 24-hour probation window.
- Before rolling back, require Tailscale or GitHub to be reachable, and skip while update or recovery work is active.
- Permit rollback only to the previously active release whose signed package was verified by the Gateway and whose post-install health check was recorded as passed.
- Restore the pre-update database backup with the previous release; keep rollback blocked if the signed artifact, attestation, release directory or backup is missing or invalid.
- Record Tailscale, GitHub and local Gateway/proxy health separately in the watchdog log.
- Keep the two-minute watchdog restart/reload recovery and the immediate post-install health rollback.
- Include Gateway 0.6.95 among the signed USB recovery candidates.
