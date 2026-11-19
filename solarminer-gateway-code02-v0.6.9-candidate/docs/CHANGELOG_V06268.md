# SolarMiner Gateway CODE02 v0.6.268

- Put Intelligence request access logging in the generated Tailscale HTTPS virtual host used by the PWA, including OPTIONS and POST correlation by Diagnostic ID.
- Report only whether the Gateway's existing local credential is accepted by OpenClaude; retain Bearer authentication on the trace endpoint and never return either token.
- Preserve the existing Gateway authentication for PWA diagnostic reads; do not expose prompts, credentials or tool payloads in the trace.
- Keep Ollama, Qwen, OpenClaude, MCP, broker, update and rollback architecture and request deadlines unchanged.
