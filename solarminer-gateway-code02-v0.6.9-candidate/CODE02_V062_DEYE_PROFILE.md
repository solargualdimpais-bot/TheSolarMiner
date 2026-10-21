# Experimental Deye Modbus TCP profile

Target candidate: SUN-15K-SG05LP3-EU. The discovered community table is for the SUN-14/15/16/18/20K-SG05LP3-EU-SM2 family. It is a candidate reference, not an official factory register map and not proof of compatibility with a unit lacking the `SM2` suffix or with any particular firmware.

The shipped module preserves FC03-only raw holding-register reads. It deliberately does not decode scales, units, signed power direction, 32-bit word order, SOC, temperatures or energy totals. Candidate addresses from the community source may be stored as CANDIDATE metadata for simulated tests only; they must not be emitted as validated live telemetry or activate production control.

Evidence needed before field-specific corroboration: exact nameplate model and firmware, an applicable manufacturer document where available, raw register response and timestamp, an independent reference instrument or inverter display, expected tolerance and repeatability, safe preconditions and the operator's record. No write function is available. No physical hardware validation has been performed in this build.
