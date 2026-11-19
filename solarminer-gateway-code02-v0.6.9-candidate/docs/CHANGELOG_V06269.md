# SolarMiner Gateway CODE02 v0.6.269

- Bound administrative terminal shell cleanup so disconnected interactive Bash sessions cannot indefinitely occupy the two socket-activated session slots.
- Distinguish assistant response text from non-assistant SDK text and expose privacy-safe SDK event/text-block counts plus an upstream HTTP status, when the SDK provides one, in correlated diagnostics.
- Normalize failed browser transport errors into a fresh mutable error so immutable browser exceptions cannot obscure the original Gateway transport failure.
- Keep Ollama, Qwen, OpenClaude, MCP, the provider, and inference deadlines unchanged; diagnostics do not claim that the Ollama HTTP 500 root cause is known.