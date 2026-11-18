# SolarMiner Gateway CODE02 v0.6.262

- Increased the local Intelligence inference budget to five minutes and aligned the Gateway, Nginx, and Owner PWA deadlines so slow CPU inference is not cut off at 120 seconds.
- Return a clear HTTP 504 diagnostic when the OpenClaude SDK aborts inference at its deadline.
- Use the OpenClaude health response to confirm Node and SDK readiness instead of probing paths protected from the Gateway service account.
- Added regression tests for inference timeout propagation, the full timeout budget, and protected Intelligence paths.
- Added an isolated, diagnostic-only Deye register probe for candidate battery-pack count 40513; unsupported registers do not interrupt other telemetry.
- Include the signed 0.6.261 package in the rollback bundle.
