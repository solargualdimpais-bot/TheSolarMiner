# SolarMiner Gateway 0.6.63

## Tuya LAN

- Report the saved local IP, Tuya device ID, and whether a local key is configured in the read-only response-time report. Local keys are never returned.
- Keep a broadcast-discovery failure from blocking MAC lookup in the Gateway's local neighbor cache. The result identifies when that fallback was used.
- Surface the scanner exception class in the failure code without including network payloads or secrets.
- Confirm an edited local IP against the Gateway's saved configuration before closing the device editor.

## Energy equipment

- Keep inverter phase output and UPS output readings under Inverters; Panels now contains only MPPT and photovoltaic production readings.
- Persist Owner-defined photovoltaic strings by MPPT, with nominal power and an explicitly configured online/offline state. Individual string telemetry is not inferred from MPPT aggregate readings.
- Add AQS equipment records with manufacturer, tank volume, nominal power, and optional Tuya breaker/channel association.
- Extend the release workflow's verified rollback bundle through Gateway 0.6.62.

## PWA

- Owner-only add, edit, and remove dialogs for photovoltaic strings and AQS equipment.
- Device response diagnostics now show the exact local address used for each Tuya ID and flag shared IP addresses for review.
- Preserve the horizontal energy-area tab scroll position when navigating between equipment areas.
