# Gateway 0.6.218

- Adds owner-only editing for PID-scoped Tuya DPS metadata and shared device-card templates.
- Imports Zigbee2MQTT reference profiles into the same SQLite product catalog as Tuya and Shelly, keyed by manufacturer, protocol, and model.
- Keeps Zigbee properties in protocol-specific profile details; Tuya DPS mappings and command permissions remain unchanged.
- Adds a paginated Zigbee2MQTT catalog endpoint and packages the sourced catalog with its license and attribution.
