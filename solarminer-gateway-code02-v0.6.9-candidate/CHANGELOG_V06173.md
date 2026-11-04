# Gateway 0.6.173

- Fixes LAN discovery when Shelly devices are already stored by initializing the MAC-to-IP index before inventory reconciliation.
- Adds a manual flexible-load priority profile whose numeric order is honored by dispatch planning.
- Includes Owner PWA 0.5.122 with persistent load creation, miner breaker association, and per-load priority controls.
- Regression coverage includes the Shelly-present LAN scan and manually ordered dispatch.

Automated validation does not perform commands on physical equipment.
