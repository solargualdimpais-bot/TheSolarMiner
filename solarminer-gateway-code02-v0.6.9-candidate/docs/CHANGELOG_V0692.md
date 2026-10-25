# Gateway 0.6.92 / Owner PWA 0.5.57

- Persists the authenticated Braiins tuner readings into the Antminer equipment history, including measured average hashrate, tuner-estimated consumption, active target, and saved profile target.
- Refreshes the PWA equipment readings after a tuner or full miner-state query so the Mineradoras card reflects the latest Braiins data instead of only CGMiner telemetry.
- Adds an Owner-only readback of saved Engine configuration. This fixes PV strings and battery settings disappearing from the PWA after refresh, and prevents the next string edit from replacing the saved list with an empty one.
- Keeps the 0.6.91 Gateway package available in signed USB rollback bundles.
