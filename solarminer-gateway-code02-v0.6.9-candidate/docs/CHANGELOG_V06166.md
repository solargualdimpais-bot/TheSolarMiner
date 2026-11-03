# SolarMiner Gateway 0.6.166

- On a failed Tuya LAN status read, refresh the local IP by exact MAC and persist only one unambiguous private IP match.
- If the MAC is not found, the refresh fails, or the MAC appears at multiple IPs, leave the device offline and do not save an IP.
- Persist Tuya availability transitions from the background observer and expose automatic IP refresh in the read-only LAN diagnostic.
