# Gateway 0.6.236

- Fix USB first-install Owner verification: read the existing Owner password from the controlling terminal rather than the installer script's heredoc stdin, and keep password entry hidden.
- Preserve an initialized SolarMiner data partition when its database or Owner cannot be verified; stop with a specific diagnostic instead of treating it as fresh data.
- Clarify installer rollback logging when failure occurs before the Gateway package is installed.
- After the local Gateway health check, automatically request the Tailscale HTTPS certificate, configure the MagicDNS Nginx vhost, and validate TLS/SNI plus the health API through the same hostname used by the PWA. If the tailnet has not yet authorized the Gateway, report that authorization is pending rather than claiming HTTPS is ready.
