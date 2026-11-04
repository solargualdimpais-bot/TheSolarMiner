# Gateway 0.6.174

- Keep the miner's user-assigned name and load characteristics in its canonical Energy equipment record.
- Link miner-load configuration to the Gateway device identity by MAC when the identity is available.
- Preserve assigned names and load characteristics during Braiins telemetry updates.
- Resolve selected Tuya controllers to their central inventory identity when a unique MAC is known.
- Keep load control-device association separate from the identity of the miner or other load.
- Update the integrated Owner PWA to 0.5.123.
- Automated validation covers data persistence; no physical equipment commands are sent by tests.

# Owner PWA 0.5.123

- Edit miner name, rated/minimum/maximum power, priority and automation eligibility in one place.
- Propagate the name to the physical inventory identity and Energy equipment record.
- Keep the separate breaker measurement association independent from the miner name.
- Preserve the selected miner subsection and pause periodic whole-page refreshes while editing miner or load configuration.
- Show save confirmation without replacing the active page.
