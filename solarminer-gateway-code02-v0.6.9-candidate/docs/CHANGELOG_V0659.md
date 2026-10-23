# SolarMiner Gateway 0.6.59

- Improve Tuya LAN diagnostics: devices without a valid private target are reported as configuration failures, not zero-millisecond responses.
- Report response latency only for successful LAN replies and expose failure counts/reasons.
- Add Owner-triggered LAN discovery that matches broadcast Tuya IDs and saves discovered private IPs locally; public Cloud IPs are not used as LAN targets.
- Align the embedded PWA with 0.5.25, including the shared Casa photo treatment and actionable Tuya diagnostics.
