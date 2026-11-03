# SolarMiner Gateway 0.6.156

- Replaced TCP/ping-led discovery with active IPv4 neighbor resolution so hosts do not need open TCP ports or ICMP replies.
- Added local SSDP/UPnP and mDNS/DNS-SD discovery for names and device-advertised model/manufacturer details.
- Adds optional offline OUI vendor lookup and explicit interface-discovery diagnostics.
- Keeps the scan limited to directly attached private IPv4 networks; no Huawei DHCP inventory is required.
