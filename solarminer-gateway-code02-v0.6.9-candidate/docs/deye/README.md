# Deye Modbus TCP connector — CODE 02 v0.6.1

Status: **raw read-only Modbus transport implemented; model-specific metrics BLOCKED**.

## Documentation assessment

The manufacturer publishes the `Manual_SUN-14/15/16/18/20K-SG05LP3-EU-SM2_20260319_en` manual for the 14–20 kW `...-SM2` family on its official download page:

- Manufacturer download index: https://www.deyeinverter.com/download/product-manual/
- Manufacturer product family page: https://www.deyeinverter.com/product/three-phase-hybrid-inverter-1/sun14-15-16-18-20ksg05lp3eusm2-1420kw-three-phase-2-mppt-hybrid-inverter-lv-battery-supported.html

The available official product manual is evidence for the existence of that product family, but the public material found for this iteration does **not** provide a verifiable, model-applicable Modbus TCP register table for the exact reference `SUN-15K-SG05LP3-EU` (without `SM2`). The family suffix and model/firmware must not be silently treated as interchangeable. A community register list is not accepted as proof of compatibility for this exact model.

Accordingly this release deliberately does not ship guessed register addresses, scale factors, units, signedness, word order, or metric conversions. The module supports a bounded Modbus TCP FC03 (Read Holding Registers) request and validates the MBAP/PDU response, but returns raw register values marked `RAW_READ_ONLY_UNMAPPED`, with units/scaling `UNKNOWN`, model compatibility `NOT_VERIFIED`, and hardware validation `NOT_VALIDATED_ON_HARDWARE`. `documented_metrics()` fails closed.

## Read-only safety

- Only Modbus function code `0x03` is implemented.
- No write functions (FC05, FC06, FC0F, FC10, FC16, FC17) are implemented or called.
- IP literals must be private/link-local, not loopback, multicast, or unspecified.
- Port, unit ID, timeout, address, and count are validated; at most 125 registers are requested.
- TCP success alone never marks a device operational or identifies a Deye inverter.
- Local protocol tests are `SIMULATED`; no physical inverter is available in this environment.

## Activation gate

This connector is not yet advertised in the production catalog or enabled in the Connector Manager. The existing catalog's private signing key is intentionally absent from source/package. Adding an entry without the owner's trusted signing process would weaken the catalog trust boundary. Activation requires: (1) an official or owner-authorized register map applicable to the exact model and firmware, with source/version and field semantics; (2) owner-controlled offline signing of the updated catalog; (3) explicit model confirmation; and (4) validation against a real device before any physical-validation claim.
