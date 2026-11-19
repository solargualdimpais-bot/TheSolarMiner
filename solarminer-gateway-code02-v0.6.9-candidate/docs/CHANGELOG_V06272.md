# SolarMiner Gateway CODE02 v0.6.272

## Fixes

- Drain active and stale `solarminer-admin-terminal@*.service` instances in the signed online-update reconciliation path before reopening the administrative terminal socket. The Debian `postinst` cleanup alone did not run during PWA updates.
- Reset failed terminal activation units during online reconciliation so a previous failed activation does not remain in systemd state.
- Add regression coverage for the required stop, daemon reload, drain, reset, and socket-reopen ordering.

The diagnostic state fix from 0.6.271 remains included. No Ollama, Qwen, OpenClaude, or MCP behavior is changed in this release.
