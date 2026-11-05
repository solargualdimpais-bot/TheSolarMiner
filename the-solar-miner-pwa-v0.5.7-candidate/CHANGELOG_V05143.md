# PWA 0.5.143

- Keep command feedback out of Home's document flow so it cannot push the page.
- Merge competing Tuya refreshes by observation time, preserving newer LAN state over older snapshots.
- Keep an unconfirmed requested state visibly unknown instead of reverting to an old on/off value.

- Keep Tuya breaker measurements visible for up to five seconds after a missed sample, then label them stale instead of unmapped.
- Refresh only the open device detail fields on each Tuya poll, without redrawing the page.

- A transport failure now leaves the command outcome pending until LAN confirms it, instead of reverting immediately.
