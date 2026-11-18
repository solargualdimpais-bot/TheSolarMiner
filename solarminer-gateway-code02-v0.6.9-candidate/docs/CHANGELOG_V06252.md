# SolarMiner Gateway CODE02 v0.6.252

## Intelligence startup and installation visibility

- Create the OpenClaude service's writable `work` and `home` directories during Debian package configuration, before systemd attempts to create the service mount namespace. This addresses the installation-time condition that can produce a `226/NAMESPACE` failure when a configured writable path is absent.
- Gate the resident service on the generated credentials, bootstrap readiness marker, and writable directories. The bootstrap creates the marker only after preparing the runtime and removes it if startup fails, preventing the agent from entering a restart loop while installation is incomplete.
- Add separate Owner tabs for Ollama/model status, OpenClaude, optional OpenAI, conversation, and reports. The Ollama tab displays bootstrap stage and model download progress and refreshes status while the Intelligence screen is open.
- Keep the local Ollama provider as the default; OpenAI remains explicit and optional.

## Validation note

The package and CI must pass before this candidate is published. This code change cannot confirm the physical Lenovo installation; the Gateway's service status after installation remains to be verified on that machine.
