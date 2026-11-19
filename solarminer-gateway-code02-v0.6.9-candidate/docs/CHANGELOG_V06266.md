# SolarMiner Gateway CODE02 v0.6.266

## Intelligence component integrity and diagnostics

- Verify protected Intelligence component files through the existing root-owned, socket-activated bootstrap broker. The Gateway receives only the component status, version, protocol and a bounded reason; file permissions and service identity remain unchanged.
- Keep the Gateway health endpoint responsive when the privileged verifier is unavailable, and report component status as unknown instead of incorrectly claiming the files are missing or readable.
- Keep the diagnostic view on the same privileged verification result so health and Owner diagnostics cannot disagree about protected component hashes.
- Add regression coverage for broker request validation, response allowlisting, client transport, and health/status integration.

## Validation limits

- Local Windows regression tests cover the broker contract and Gateway route behavior.
- Linux package build and signed USB bundle are validated by the release workflow.
- A real PWA question through OpenClaude, Ollama, Qwen and SolarMiner MCP still requires the Lenovo M720q; no local test result is presented as that physical proof.
