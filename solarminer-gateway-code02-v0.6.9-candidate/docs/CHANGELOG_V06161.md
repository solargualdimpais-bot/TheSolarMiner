# SolarMiner Gateway 0.6.161

- Fixes the raw ARP scan failure path so an unavailable packet socket is logged and the scanner can continue with its neighbor-table fallback.
- Returns a structured Gateway error for unexpected local network scan failures instead of an unhandled internal exception.
- Keeps direct Ethernet ARP as the primary IP-to-MAC discovery method, with ICMP, TCP, SSDP and mDNS as supplemental signals.
