# Gateway 0.6.138 / PWA 0.5.92

- Adds an owner-only DPS troubleshooting tab to device settings. Opening the tab requests one LAN diagnostic snapshot; each DPS shows its observed value and current suggested meaning.
- Lets the Owner correct a DPS meaning for the exact Product ID. The saved override is reused for later telemetry and compatible controls for devices sharing that Product ID; control writes remain constrained by observed value type or the product's declared writable schema.
- Shows live voltage, current, and power in breaker details from the Gateway's periodic Tuya LAN readings, replacing the misleading daily-consumption placeholder. The open detail updates with the device reading poll without re-rendering the page.
