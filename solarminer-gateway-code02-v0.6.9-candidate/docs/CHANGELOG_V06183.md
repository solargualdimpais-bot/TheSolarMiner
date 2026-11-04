# Gateway 0.6.183

- On network-device save, refreshes the configured Tuya inventory and tries a bounded, read-only DPS authentication against matching local keys.
- Associates an IP/MAC to a cloud device only after exactly one device key returns a non-empty DPS status; ambiguous results remain unlinked.
- Preserves local keys and DPS overrides across cloud synchronization and never returns local keys to the PWA.
- Returns the automatic association and read status so the PWA can explain whether control is ready.
- Added regression tests for successful and ambiguous key association.
