# SolarMiner Gateway CODE02 v0.6.276

## Fixes

- Include a positive Debian `Installed-Size` field in the built package. The online update preflight uses this field to estimate activation storage before stopping services.
- Verify the field in the release pipeline so a package missing it cannot be signed and published.
- Preserve the OpenClaude SDK diagnostics introduced in 0.6.275; the SDK remains pinned to 0.36.0.
