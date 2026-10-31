# The Solar Miner PWA 0.5.70

- Runs the same three-round LAN response test used by diagnostics for one selected device when saving or manually testing it.
- Reads the target switch state before a command and verifies the requested state with a fresh LAN response afterward.
- Preserves each fresh Tuya LAN response instead of replacing it with cached status; shows response count and average latency.
- Keeps Tuya Cloud online status separate from LAN reachability and simplifies the device card layout.
- Distinguishes Tuya Cloud online state from an unresponsive local LAN test.
