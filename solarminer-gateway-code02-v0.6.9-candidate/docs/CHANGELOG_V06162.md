# SolarMiner Gateway 0.6.162

- Uses fresh active ARP replies without merging stale neighbor-cache entries after a successful sweep.
- Shows a repeated MAC once with its conflicting IP candidates and never saves an ambiguous mapping.
- Updates a Tuya local IP only when its MAC identifies exactly one live IP and exactly one configured device.
