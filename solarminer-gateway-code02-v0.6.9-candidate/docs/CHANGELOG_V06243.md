# Gateway 0.6.243

- Preserve the last verified Tuya LAN status through a failed poll while reporting the latest attempt separately.
- Keep successful Tuya response latency separate from failed-attempt duration and expose both to the device status API.
- Refresh Tuya LAN status immediately after a control command and show app-to-Gateway, Gateway-to-device, LAN-read, and total response timings.
- Retain recent measurements with an explicit stale label during brief LAN polling gaps.
- Refresh the Tuya device status view every five seconds without initiating additional device polling from the PWA.
- Update the embedded and standalone PWA cache/version identifiers.
