# SolarMiner Gateway 0.6.22

- Fix allowlist lookup for the official GitHub repository when its stored URL uses mixed case (`TheSolarMiner`). Repository URLs are compared using the same canonical form as user-entered URLs.
- Reject ambiguous allowlists containing duplicate repository entries that differ only by letter case.
- Carry forward the 0.6.21 Nginx TLS identity fix and reconfiguration of existing Tailscale virtual hosts.
