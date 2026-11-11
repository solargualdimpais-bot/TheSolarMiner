# Gateway 0.6.239

- A Tailscale HTTPS probe that is not yet ready no longer rolls back a healthy local Gateway installation.
- The installer retries the endpoint briefly and records curl, Nginx, and Tailscale certificate diagnostics for follow-up.
- The background certificate timer remains responsible for automatic retries after installation.
