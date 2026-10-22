# Deye SG05LP3 register map candidate

- Target family: `SUN-14/15/16/18/20K-SG05LP3-EU-SM2` (the downloaded file names the SG05LP3-EU-SM2 family; it does not establish exact firmware compatibility for this inverter/logger).
- Source: https://github.com/mxbode/Deye-SUN-SG05LP3-EU-SM2-Modbus-TSV/blob/main/Deye-SUN-SG05LP3-EU-SM2-Modbus.tsv
- Raw file: https://raw.githubusercontent.com/mxbode/Deye-SUN-SG05LP3-EU-SM2-Modbus-TSV/main/Deye-SUN-SG05LP3-EU-SM2-Modbus.tsv
- Retrieved: 2026-10-22
- SHA-256: `ba9e0b87ed37cc28ed9fc1493a07d9b26d6dc4d15fc95b1786424e85d99b9c48`

This is a community-maintained table, not a Deye-issued register map. It is saved for review only. Do not treat its addresses, data types, scaling, unit IDs, or write permissions as validated for the physical inverter. In particular, the table uses 4xxxx reference addresses; the Modbus PDU address sent on the wire may use zero-based offsets, so every conversion must be checked against a trusted protocol source before implementation.

The official inverter user manual identifies the `SM2` product family and shows the physical Modbus interface, but does not include this register table. The logger firmware (`DYDA_WiBLE_1.7.2`) and its Link 2 settings are separate from the inverter register map.
