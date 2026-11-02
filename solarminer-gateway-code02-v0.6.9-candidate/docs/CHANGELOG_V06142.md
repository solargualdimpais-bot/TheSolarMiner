# Gateway 0.6.142 / Owner PWA 0.5.95

- Huawei HiLink inventory refreshes rotating session cookies and request-verification tokens and retries once with a fresh session after a no-rights response.
- Huawei lookup now checks an alternate LAN host endpoint and reports authorization/session failures separately from endpoint or firmware support failures.
- Owner modem lookup performs a bounded active sweep of private IPv4 subnets directly attached to the Gateway, then returns learned IP/MAC pairs with their source.
- Known MACs are labeled from configured Tuya devices; Owner labels for other discovered MACs are stored locally in a dedicated Gateway table.
- Router response timeout is 15 seconds per request and 120 seconds for the inventory call; the PWA allows 160 seconds and remains cancellable.

Active discovery is best effort. It cannot enumerate hosts behind another routed VLAN, client isolation, or devices that do not respond to LAN probing. Huawei clients remain the authoritative router inventory when its firmware permits access.
