# SolarMiner Gateway CODE02 v0.6.265

- Add safe, per-request diagnostics for Intelligence conversations from the Owner PWA through the Gateway to the OpenClaude agent.
- Identify permission-denied errors by safe error type and code without exposing paths, prompts, credentials, or raw exception text.
- Preserve local-only Ollama as the default provider and the existing read-only MCP restrictions.
- Bound online update apply/status requests and treat a lost apply response as unconfirmed until the Gateway status is checked.
- Give independent recovery enough systemd runtime to finish the 180-second health check and record its result.
