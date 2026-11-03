# SolarMiner Gateway 0.6.164

- Added an owner-managed LAN device inventory keyed by MAC address.
- Added a save endpoint that confirms the MAC in a fresh scan and refuses to update an IP when the MAC maps to multiple addresses.
- Exposed device names from the local inventory in subsequent network scans.
- Preserved explicitly configured Tuya names when a matching MAC is edited from the LAN details dialog.
