# SolarMiner Gateway 0.6.147 / Owner PWA 0.5.99

- Adds a per-miner Tuya breaker association for switch state and measured electrical telemetry.
- Uses fresh, schema-recognized Tuya power readings for miner consumption; labels Braiins power as an estimate when no valid fresh meter reading is available.
- Marks a shared breaker reading as aggregate and blocks dispatch from attributing aggregate power to each miner individually.
- Keeps the hosted PWA and Gateway-embedded PWA synchronized with a new cache version.
