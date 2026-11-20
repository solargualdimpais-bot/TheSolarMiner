# SolarMiner Gateway CODE02 v0.6.275

- Keep the installed OpenClaude SDK at 0.36.0; do not change the Ollama runtime, model, or configuration.
- Capture sanitized OpenClaude SDK exceptions at the SDK error logger, `result.errors`, and exceptions escaping the query iterator.
- Persist correlated diagnostics to `/var/log/solarminer-intelligence/diagnostics.log` with timestamps, Diagnostic ID, stage, duration, and bounded rotation.
- Make the agent's sanitized SDK error detail visible in the Owner PWA failure diagnosis. Credentials and stack traces remain out of the PWA response.
- Logging is best-effort and does not alter inference results or error handling.
