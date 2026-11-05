# Gateway 0.6.195

- Preserve the last valid Tuya LAN sample for a 15-second freshness window after a transient failed poll.
- Report the latest poll attempt separately from the still-valid last sample so clients do not blank DPS values on one timeout.
