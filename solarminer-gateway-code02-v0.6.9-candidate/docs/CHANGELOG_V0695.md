# Gateway 0.6.95 / Owner PWA 0.5.60

- Add Owner-only configuration for a fine-grained GitHub token used only to create reports in the private diagnostics repository.
- Store the token in the Gateway data directory with restrictive permissions; never return it to the PWA or include it in reports.
- Send sanitized application errors together with a bounded snapshot of allowlisted Gateway, updater, recovery, Nginx and Tailscale logs.
- Detect and report new allowlisted system failures on the hourly timer even when the Gateway app has no queued error, with a fingerprint to suppress duplicate reports.
- Preserve the local report queue when the network, broker or GitHub is unavailable.
- Include Gateway recovery release 0.6.94 in the next signed USB bundle as the immediate rollback candidate.
- Add coverage for token validation/storage/removal, Owner-only access and diagnostic redaction.
