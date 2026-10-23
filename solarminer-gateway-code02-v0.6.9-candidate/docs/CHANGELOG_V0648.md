# SolarMiner Gateway CODE02 v0.6.48

- Defer offline recovery while the matching online update worker is still active, including during the Gateway's own service restart.
- Select the newest update operation deterministically when multiple records share the same second-level timestamp.
- Include recovery service/timer output in Owner diagnostics and capture the current `nginx -t` result so Tailscale HTTPS failures show their concrete parser error.
- Preserve the previously working Tailscale Nginx configuration if a newly generated configuration fails validation.
- Include the requested refined weather symbol and thinner Home production chart, with the embedded PWA cache/version advanced to 0.5.16.

The available field evidence establishes that Tailscale HTTPS failed because Nginx configuration validation failed. The exact rejected directive/file was not present in the old Gateway console, so this version adds that evidence; it cannot claim the specific historical Nginx cause before the new diagnostics run on the Gateway.

The online update failure is consistent with the recovery service running during the update's own restart and interfering with its health check/rollback. The operation status selector also had a same-second tie bug that could show an old attempt. Both are corrected here, but only a successful update on the user's Gateway can confirm the field result.
