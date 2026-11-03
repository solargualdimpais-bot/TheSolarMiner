# SolarMiner Gateway 0.6.159

- Allows AF_NETLINK in the Gateway service sandbox so `ip` can enumerate attached IPv4 interfaces for network discovery.
- Keeps AF_PACKET and CAP_NET_RAW enabled for direct Ethernet ARP scans.
