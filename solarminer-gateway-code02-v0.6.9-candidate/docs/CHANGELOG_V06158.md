# SolarMiner Gateway 0.6.158

- Replaces UDP-triggered neighbour discovery with direct Ethernet ARP requests and replies on each attached interface.
- Grants the Gateway service only the raw packet capability and address family required for active ARP scanning.
- Keeps ICMP, TCP, SSDP/UPnP, mDNS/DNS-SD, and kernel neighbour-table discovery as complementary methods.
- Reports when active ARP is unavailable so an incomplete scan is not presented as a complete result.
