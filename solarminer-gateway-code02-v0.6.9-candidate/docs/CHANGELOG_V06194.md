# Gateway 0.6.194

- Includes the Tuya response-by-response telemetry persistence introduced in 0.6.193.

- Retain the last valid Tuya telemetry as fresh for five seconds so a single missed 1.5-second poll does not clear DPS readings.

- Start fixed-cadence Tuya polls every 1.5 seconds, allow at most two overlapping sweeps, and reject older responses that complete late.

