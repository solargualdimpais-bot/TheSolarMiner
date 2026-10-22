# SolarMiner Gateway 0.6.35

## Deye Modbus TCP read-only mapping

- Added an exact-model read-only path for `SUN-15K-SG05LP3-EU-SM2` using a limited allowlist from a community register map.
- Converted 4xxxx references to zero-based Modbus PDU offsets and skipped FC43 for the tested `DYDA_WiBLE_1.7.2` endpoint.
- Returned device type, status code, total load power, and PV1/PV2 power with community-map provenance and `LIVE_UNVERIFIED` trust.
- No Modbus write functions or control commands were added.
- Tested live FC03 reads from the development computer at `192.168.8.10:502`, Unit ID 1. The device type, status, load power, and both PV power registers returned valid Modbus responses. These spot checks confirm endpoint/address behavior for this installation only; they do not certify the full map or field semantics.
- Added regression coverage for map offsets, mapped readout, and skipping FC43.
- Updated the Owner PWA connection summary and the Gateway-embedded PWA copy.

The map provenance and limitations are recorded in `docs/deye/SG05LP3_REGISTER_MAP_SOURCE.md` and `docs/deye/README.md`.
