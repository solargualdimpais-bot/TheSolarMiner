# The Solar Miner PWA 0.5.92

- Breaker detail now shows voltage, current, and power from the Gateway's independent Tuya LAN reader and updates the open detail on each 1.5-second inventory poll.
- Adds a DPS troubleshooting tab that reads a single LAN snapshot when opened and lets the Owner save a semantic correction for the exact Tuya Product ID.
- Product-scoped corrections update future telemetry meanings and compatible controls; the Gateway still checks the declared or observed datapoint type before permitting writes.
