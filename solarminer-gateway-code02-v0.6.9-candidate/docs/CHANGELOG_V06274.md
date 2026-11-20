# SolarMiner Gateway CODE02 v0.6.274

## Intelligence / Ollama

- Upgrade the pinned OpenClaude SDK from 0.36.0 to 0.37.0. This upstream version sends `think: false` by default to Ollama hybrid-reasoning models when no explicit reasoning effort is requested. Qwen 3.5 therefore produces the ordinary assistant response without spending the full request on hidden reasoning by default.
- Keep the existing Qwen model, Ollama runtime, MCP server, authentication, and request timeouts unchanged.
- Add a release-pipeline contract test that invokes the installed SDK `query()` against an isolated Ollama-compatible fixture, verifies the native `/api/chat` request includes `think: false`, and verifies assistant text is emitted back to the host. This is an SDK integration contract test, not a real Qwen inference test.

## Validation limits

- The official Linux release pipeline must pass the Gateway, Intelligence/MCP, PWA, SDK contract, Debian packaging, signature, and rollback-artifact checks before this release is considered published.
- A live inference through the Lenovo's Qwen model and PWA still requires confirmation on that device after installing the update.
