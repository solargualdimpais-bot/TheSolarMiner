# SolarMiner Gateway CODE02 v0.6.263

- Allow up to three minutes for the new or restored Gateway release to pass direct TLS and Nginx health checks before rolling back.
- Keep the independent update worker alive long enough to finish bounded activation and rollback steps instead of letting systemd terminate the transaction after five minutes.
- Make the PWA report an unconfirmed update outcome after its wait window; it no longer labels a still-running operation as finished or encourages a second apply.
- Retain the 0.6.262 Intelligence timeout, Ollama environment, OpenClaude readiness and Deye diagnostic changes.
- Include the signed 0.6.262 Debian package in the USB rollback bundle.
