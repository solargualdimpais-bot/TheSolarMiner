# SolarMiner Gateway 0.6.165

- Restores MAC display when direct ARP capture is unavailable by using the Linux neighbor table only for IPs that answered TCP or ICMP during the current scan.
- Labels neighbor-table MACs separately from captured active ARP replies.
- Excludes cached neighbor entries for IPs that did not respond in the current scan, preventing stale IPs from appearing active.
