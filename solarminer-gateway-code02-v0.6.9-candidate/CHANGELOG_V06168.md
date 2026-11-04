Gateway 0.6.168
- Tuya circuit-breaker telemetry now resolves voltage/current/power through the exact Tuya DLQ product schema and applies its declared scale and unit conversions. Daily energy is shown only when the product schema supplies a numeric value with a usable unit/scale.
- Miner status is marked disconnected on failed API reads; Home hides stale hashrate and power.
- Miner controls and breaker association are split into Situation, Braiins OS, Commands, and Configuration tabs; the breaker selector is available in the miner configuration tab.
- LAN recovery, MAC-keyed inventory and immediate Deye retry after a unique MAC/IP match are included.
