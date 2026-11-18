# SolarMiner Gateway CODE02 v0.6.257

- Owner Intelligence diagnostics identify session expiration, Owner permission failures, unavailable endpoints, Gateway HTTP errors, bootstrap broker errors, HTTPS/network failures, status request timeouts, OpenClaude unavailability, Ollama runtime/model failures, provider configuration, and request limits.
- The Intelligence status request has a bounded 15-second timeout. If the Gateway cannot be queried, component installation is shown as unknown rather than absent.
- Public Gateway health and information probes separate a Gateway/network outage from a failure limited to the authenticated Intelligence status route.
- PWA static cache and displayed version are advanced to 0.5.187 so clients fetch the diagnostic interface after update.
