# SolarMiner Gateway CODE02 v0.6.259

## Intelligence readiness and update consistency

- Nginx allows the Intelligence ask route to finish within the Gateway and PWA deadlines, while retaining the shorter default timeout for other routes.
- Online reconciliation now stops already-active package-owned broker sockets before replacing units, reloads systemd, starts each socket, and verifies it is active. Rollback uses the same sequence.
- The Intelligence bootstrap restarts Ollama after applying its systemd drop-in and verifies the running process received the local-only settings.
- Bootstrap completion now requires a successful loopback HTTP health response from the actual OpenClaude process, with the expected Ollama runtime and model configured.
- The installer pins the OpenClaude SDK's Anthropic peer dependency explicitly; the SDK statically imports it even when SolarMiner selects local Ollama. This installs a library only and does not enable or send requests to Anthropic or OpenAI.
- Added focused tests for health readiness, Ollama process configuration, socket reload behavior, and the Nginx request deadline.
- Updated the packaged Owner PWA cache and version.

The health probe verifies that the SDK-backed agent server is running and that Ollama reports the expected model installed. It does not claim a full physical Gateway-to-MCP conversation test; that remains a separate deployment validation.

This release does not format disks or modify the physical Gateway during build. The initial-install USB flow is for Debian 13 already installed on a GPT disk: it preserves the Debian partition and creates/formats a data partition only in the single verified unallocated region on the root disk. It is not bootable media. A real Debian 13 installation and a physical Lenovo conversation remain untested by CI.
