# SolarMiner Gateway 0.6.155

- Added owner-only, read-only scanning of directly attached private IPv4 networks using TCP probes, ping, and the kernel neighbor table.
- Cross-checks discovered MAC addresses against configured Tuya devices.
- Persists a changed IP only after an explicit UI confirmation and a fresh MAC/IP match.
- Limits scans to 4096 addresses and reports skipped networks; remote subnets and silent hosts cannot be guaranteed.
