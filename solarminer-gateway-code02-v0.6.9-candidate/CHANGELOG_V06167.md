# Gateway 0.6.167

- Adds a central MAC-keyed device inventory shared by saved Gateway identities, the LAN scanner, and the Devices pending list.
- Imports configured Tuya devices, supported Gateway devices, and saved LAN labels into the shared inventory.
- A newly named LAN MAC is saved as pending; a unique current IP updates the record, while ambiguous IPs remain unchanged.
- Adds read-only MOES MiniPad and CCP-S01 DPS profiles without issuing DPS writes.
