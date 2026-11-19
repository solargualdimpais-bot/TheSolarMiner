# SolarMiner Gateway CODE02 v0.6.267

- Carry one validated Intelligence diagnostic ID from the authenticated PWA request through the Gateway to the local OpenClaude agent.
- Expose bounded, secret-free Gateway and agent stage traces, including SDK output and MCP tool call/result counts.
- Write a dedicated Nginx access record for Intelligence POST and OPTIONS traffic with diagnostic ID, HTTP status and upstream timings; do not log authorization headers or prompts.
- Put the same random Diagnostic ID in the ask URL query as well as its header, so browser OPTIONS preflight records can be correlated before the authenticated POST is sent.
- Preserve the original PWA request error and diagnostic ID when trace lookup fails, and report the trace lookup failure separately.
- Keep the existing Ollama, Qwen, OpenClaude, MCP and broker architecture and request deadlines unchanged.
