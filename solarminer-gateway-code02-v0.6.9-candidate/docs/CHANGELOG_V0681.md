# Gateway 0.6.81 / Owner PWA 0.5.47

- Braiins OS action responses may be JSON booleans; the Gateway now accepts these for start, pause and stop while continuing to require object responses for login and power-target updates.
- Owner feedback distinguishes a miner already in the requested state from a newly accepted command. After “Iniciar”, the PWA performs a fresh telemetry read and reports the observed hashrate separately from network connectivity.
- Antminer status now labels CGMiner-compatible telemetry as read-only while making clear that start, pause, stop and power-target commands use the separate Braiins OS REST API.
- The Energy chart summary beneath the historical forecast now shows only the remaining FV estimate requested for the selected time.
