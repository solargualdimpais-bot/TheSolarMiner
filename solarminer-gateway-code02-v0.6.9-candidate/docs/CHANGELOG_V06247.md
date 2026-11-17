# SolarMiner Gateway CODE02 v0.6.247

- SolarMiner Intelligence uses local Ollama by default; OpenAI is used only when explicitly selected by the Owner.
- Owner Intelligence console reports agent, Ollama runtime/model and analysis status, and requires confirmation before sending a request to OpenAI.
- Bootstrap installs Ollama and the pinned Qwen model only after Tailscale and HTTPS prerequisites are confirmed.
- Preserve rapid Deye and Tuya telemetry transitions when timestamps collide.
- Make database backup durability and recovery permission handling portable in tests while retaining POSIX directory sync on Debian.
- Preserve signed catalog and plugin hash inputs byte-for-byte on Windows checkouts.
- Keep Linux-only socket, UID/GID and symlink integration tests enabled on Linux CI; report them as skipped only on Windows.
- Release workflow verifies Ollama as the default provider and checks that OpenAI is optional rather than forced at service startup.

Validation in the Windows development environment: Gateway Python suite 682 passed, 35 Linux-specific tests skipped; OpenClaude/MCP Node suite 9 passed; PWA Node suite 198 passed. Linux CI and physical Gateway installation remain the release workflow's required validation steps.
