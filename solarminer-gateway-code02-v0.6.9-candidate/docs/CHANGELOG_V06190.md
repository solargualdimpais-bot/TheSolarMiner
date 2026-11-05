# Gateway 0.6.190

- Read Deye telemetry every 3 seconds for live SOC integration and keep a bounded recent sample window in memory.
- Persist representative Deye telemetry every 9 seconds to balance responsive SOC updates with SQLite growth.
- Continue calculating Gateway SOC from battery voltage and signed charge/discharge power; inverter-reported SOC remains diagnostic only.
