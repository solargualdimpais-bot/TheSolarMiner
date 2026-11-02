# Gateway 0.6.141 / Owner PWA 0.5.94

- Huawei inventory now tries the LAN host table first, then Wi-Fi host list and DHCP host information, merging returned IP/MAC records.
- Huawei XML parsing tolerates firmware casing and field-name differences and keeps valid IP-only records.
- Huawei queries have a bounded 75-second overall deadline and 10-second per-request timeout. The Owner UI allows 100 seconds and reports which endpoints replied or failed.
- Inventory also merges private IP/MAC pairs already present in the Gateway's local ARP neighbour cache; the dedicated Nginx route allows 100 seconds.
- Added tests for the LAN/Wi-Fi/DHCP fallback sequence, merged clients, API errors, and records without MAC addresses.
