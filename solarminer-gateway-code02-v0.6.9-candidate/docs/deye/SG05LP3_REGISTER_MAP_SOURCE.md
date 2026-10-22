# Deye SG05LP3 telemetry map: source and validation record

## Target configuration

- Inverter configured in the PWA: `SUN-15K-SG05LP3-EU-SM2`.
- Manufacturer product family: `SUN-14/15/16/18/20K-SG05LP3-EU-SM2`, three-phase low-voltage, two MPPTs.
- Tested endpoint: logger `DYDA_WiBLE_1.7.2`, reported serial `D25B290037D0`, `192.168.8.10:502`, Unit ID 1.
- Implementation reads FC03 only and does not implement Modbus writes.

## Sources compared

1. Deye product-family datasheet/page confirms the `SM2` family and two MPPTs: https://www.deyeinverter.com/product/three-phase-hybrid-inverter-1/sun14-15-16-18-20ksg05lp3eusm2-1420kw-three-phase-2-mppt-hybrid-inverter-lv-battery-supported.html
2. Public copy of Deye's three-phase energy-storage Modbus protocol: https://badenergy.dk/wp-content/uploads/2025/01/Deye_3p_modbus_address_list.pdf. The table describes FC03 read-only ranges 0–59 and 500–2000, battery/PV/grid/inverter/load fields, units, signed values and scale factors.
3. Public read-only SG04/SG05 LP3 implementation: https://github.com/Developer089/deye-modbus-ha/blob/main/custom_components/deye_modbus/maps/sun_3ph_hybrid.yaml. Its README says the map derives from Deye's three-phase energy-storage protocol. Its major PV, battery, inverter and load register offsets/scales agree with the protocol copy for the mapped fields.
4. Previously saved community map: https://github.com/mxbode/Deye-SUN-SG05LP3-EU-SM2-Modbus-TSV/blob/main/Deye-SUN-SG05LP3-EU-SM2-Modbus.tsv; raw copy SHA-256 `ba9e0b87ed37cc28ed9fc1493a07d9b26d6dc4d15fc95b1786424e85d99b9c48`.

The official product literature does not certify the logger's register bridge or this inverter's exact firmware revision. The address table used by the Gateway is therefore an evidence-backed candidate map, not a Deye support statement.

## Physical FC03 spot check

Read-only queries to the live endpoint succeeded for PDU windows `0:1`, `108:2`, `500:1`, `514:22`, `586:7`, `598:28`, `627:29` and `672:8`. Sample values from a single pass included:

- PV1: 408.3 V, 4.2 A, 1726 W.
- PV2: 241.2 V, 0.5 A, 173 W.
- Battery: 53.69 V, 100%, −3.02 A, −150 W, temperature and corrected capacity registers returned.
- Inverter output and load total: 1653 W each.
- The apparent battery charging direction was consistent with PV exceeding the load in that sample.

A later pass with the energy-counter blocks returned PV daily/total energy of 37.8/1889.0 kWh; battery daily/total charge of 7.4/716.7 kWh and discharge of 4.9/647.5 kWh; load daily/total energy of 33.7/1613.1 kWh; and configured battery current limits of 100 A charge and 200 A discharge. This model's Deye datasheet lists a 280 A maximum charge/discharge rating, so the observed 100/200 A values are plausible configured setpoints rather than hardware maximums. They are not the live dynamic limits reported by a battery BMS.

These readings were not obtained from the Gateway host, were not compared simultaneously with the inverter display, and were not corroborated with independent instruments. They validate that the logger returned register bytes for the extended windows and that the conversions are plausible on one installation; they do not prove every metric or firmware.

## Explicit unresolved evidence

- Device-type register raw value was `5`; the published protocol table describes `0x0500` for three-phase hybrid. The Gateway records the raw value but does not treat it as a verified identity.
- Grid voltage and frequency registers returned zero in the sample while inverter AC output and load were nonzero. CT/internal/grid channels may depend on hardware/settings or the logger's mapping and remain unconfirmed.
- PV2 power (173 W) did not closely match the product `241.2 V × 0.5 A` (about 121 W) in the same FC03 block. This remains a signal consistency discrepancy and is one reason all output stays `LIVE_UNVERIFIED`.
- Exact firmware, signed manufacturer register map, source-level validation from the Gateway, and repeated cross-checks are not available.

No guessed write values or control permissions are included. Only the read-only fields listed in `README.md` are decoded.
