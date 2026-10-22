# Deye Modbus TCP connector — CODE 02 v0.6.1

Status: **read-only Modbus TCP transport implemented; a limited SG05LP3 candidate map returns live values and remains unverified by the manufacturer**.

## Documentation assessment

The manufacturer publishes the `Manual_SUN-14/15/16/18/20K-SG05LP3-EU-SM2_20260319_en` manual for the 14–20 kW `...-SM2` family on its official download page:

- Manufacturer download index: https://www.deyeinverter.com/download/product-manual/
- Manufacturer product family page: https://www.deyeinverter.com/product/three-phase-hybrid-inverter-1/sun14-15-16-18-20ksg05lp3eusm2-1420kw-three-phase-2-mppt-hybrid-inverter-lv-battery-supported.html

The official product manual covers the `...-SM2` family but does not publish its Modbus register table. A community table for the exact `SG05LP3-EU-SM2` family was downloaded to `SG05LP3-register-map-community.tsv`. Its provenance and SHA-256 are recorded in `SG05LP3_REGISTER_MAP_SOURCE.md`. It is not manufacturer-certified. We have now made read-only FC03 requests from this development computer to the configured live logger and received responses for the device type, status, total load power and PV1/PV2 power addresses. This confirms that these candidate addresses respond on this installation; it does not certify all field meanings, models, firmware, scales or write permissions.

For the exact configured model `SUN-15K-SG05LP3-EU-SM2`, the connector reads only a small allowlist of candidate fields: status code, total load power, and PV1/PV2 input power. It converts reference addresses such as 40673 to the zero-based PDU offset (672). It skips FC43 because the DYDA_WiBLE 1.7.2 logger timed out on that optional identification function and the immediate FC03 fallback also timed out, while direct FC03 reads succeeded when sent first. Returned values are marked `LIVE_UNVERIFIED` and identify the community-map source. Other models retain the generic read-only transport and unmapped values. No write function or control is implemented.

## Read-only safety

- Only Modbus function code `0x03` is implemented.
- No write functions (FC05, FC06, FC0F, FC10, FC16, FC17) are implemented or called.
- IP literals must be private/link-local, not loopback, multicast, or unspecified.
- Port, unit ID, timeout, address, and count are validated; at most 125 registers are requested.
- TCP success alone never marks a device operational or identifies a Deye inverter.
- Local protocol tests are `SIMULATED`; no physical inverter is available in this environment.

## Activation gate

This connector is not advertised in the production catalog or enabled in the Connector Manager. No inverter writes are allowed. Expanding telemetry beyond the allowlist requires reviewed field semantics, firmware applicability, and broader hardware validation. The present spot checks are limited to one device/logger on one LAN, and no production/automation claim is made.
