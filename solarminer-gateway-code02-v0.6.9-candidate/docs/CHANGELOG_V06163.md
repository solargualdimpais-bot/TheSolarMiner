# SolarMiner Gateway 0.6.163

- Reports a MAC as discovered by active ARP only when a matching Ethernet ARP reply was captured during the current scan.
- Removes the Linux neighbor-table fallback from the live scan because it can retain stale IP-to-MAC mappings.
- When raw ARP is unavailable, TCP, ICMP, SSDP and mDNS results remain labeled by their actual discovery method and do not inherit a cached MAC.
