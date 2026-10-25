# Gateway 0.6.85 / Owner PWA 0.5.51

- Replaced the misleading read-only protocol label with separate CGMiner telemetry and Braiins REST control capabilities.
- Clarified in the Owner interface that the Gateway can start, pause, stop, and set the miner power target through Braiins OS REST.
- Added a non-disruptive Owner control test: read the current Braiins power target, reapply the same value, and report whether the REST API accepted it. No pause or stop command is sent.
