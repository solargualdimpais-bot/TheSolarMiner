# SolarMiner Gateway 0.6.107

- Allow the Tailscale certificate service to run Nginx configuration checks using the runtime PID path under /run.
- Start Nginx when inactive after a valid Tailscale vhost is installed; otherwise reload it.
- Surface the full Nginx validation diagnostic in the service journal and persistent log.
