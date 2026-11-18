# SolarMiner Gateway CODE02 v0.6.261

- Fixed the Gateway HTTP client calls to avoid using `http.client.HTTPConnection` as a context manager; connections are closed explicitly.
- Applied the fix to Ollama version/model checks, OpenClaude health checks, and Intelligence conversation forwarding.
- Added regression coverage using connection objects that do not implement the context manager protocol.
- Preserved TypeError stage reporting at the Gateway-to-agent boundary.
