# Gateway 0.6.204

- Preserve Shelly JSON-RPC error codes and bounded device messages for BLU scan diagnostics.
- Report the bridge's actual BLE scanner state, whether the scan request was skipped or accepted, and advertisement counts in the Gateway log and PWA result.
- Keep the existing scanner start/skip behavior unchanged while collecting diagnostics, so the next device result identifies the current failure without mixing in a behavioral fix.
- Show the detailed Shelly BLU scan result in Owner PWA 0.5.151.
