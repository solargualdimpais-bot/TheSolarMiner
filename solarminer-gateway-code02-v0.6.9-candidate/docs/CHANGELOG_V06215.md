# Gateway 0.6.215

- Expands the private diagnostics report with CPU and I/O-wait measurements, top five process names and usage, and the data-volume mount/read-only state. Process arguments and device/network identifiers are not collected.
- Records slow or failed API routes and slow/failed SQLite access with timestamps and duration. These events are correlated with Deye, Tuya, Nginx, watchdog, and browser endpoint events; inferred causes are explicitly marked as correlations.
- Adds privacy-filtered browser endpoint probe events so Chrome/Safari comparisons can identify endpoint category, API route, result class, HTTP status, and latency without uploading raw hostnames, URLs, or addresses.
- Adds an Owner-only manual report button in the Gateway Console. It sends the current snapshot and queued errors to the same private GitHub repository as automatic reports, without a confirmation dialog.
- Adds an Owner-only Watchdog toggle to the Gateway Console. The watchdog remains disabled by default after installation and can be enabled manually.
- Keeps the USB installation path and persistent data partition protections; the existing Owner and database remain available when `SOLARMINER DATA` is left intact.

Diagnostics provide evidence and conservative rule-based triage; temporal correlation does not establish causation. A browser's generic network error cannot by itself distinguish TLS, DNS, browser policy, or a route failure.
