# Tuya DPS registry and device profiles

## Scope

This change adds a versioned, confidence-aware DPS reference registry to the existing Gateway. It preserves raw DPS values and the Gateway's existing connector, persistence, trust, and entity flows. Registry matches are suggestions; they do not authorize a LAN write. Writes continue to require the product's declared function mapping or an explicit local DPS mapping.

## Presets

| Profile | Scope | Mapped data | Safety state |
| --- | --- | --- | --- |
| Energy-monitoring switch / water heater | Owner-selected | DP1 switch; DP9 countdown; DP17 accumulated energy (unit and scale unknown); DP18 current (÷1000 A); DP19 active power (÷10 W); DP20 voltage (÷10 V). | Owner-confirmed meanings from the supplied proposal; DP17 remains raw because its unit/scale is unknown. |
| Six-channel hybrid switch / curtain controller | Owner-selected | DP1–6 Boolean channels; DP107 switch-type setting; DP113–115 pair modes; DP118 equipment identifier. | Emits two switches for a `switch` pair and a non-controllable cover placeholder for a `curtain` pair. No curtain movement/position commands are inferred. DP13 remains inferred and non-writable; DP14 remains unknown. |
| Single switch / borehole cabinet | Owner-selected | DP1 switch; DP9 countdown; DP41 child lock. | Owner-confirmed meanings; DP38/40/42/66 remain candidates or unknown. |
| QCCDZ EV charger | Exact Tuya category `QCCDZ` | DP18 switch status/control mapping. | Restricted to QCCDZ; it does not apply to QLD or unrelated products. Actual command still requires local key, endpoint, declared/explicit mapping, and Gateway command validation. |

The registry also contains community-reported curtain and lighting templates. They remain candidate references with writes disabled. Conflicting DP numbers are not treated as globally meaningful; the selected product profile determines interpretation.

## Recognition and owner configuration

The Gateway compares observed DPS IDs and product schema with versioned profiles, reports compatibility scores and suggestions, and preserves unknown raw values. The device editor now allows an Owner to select and persist one of the supported profiles. A signature match alone does not activate a profile. Product functions and explicit `dpId` values take precedence over channel-name suffixes. For the official `KG` smart-switch category, the documented 1–6 fallback is used only when all six Boolean `switch_1`…`switch_6` functions are declared.

## Energy and SOC

The Energy engine can use timestamped Deye Cloud voltage and signed-power history to find a full-charge anchor and integrate from it. It does not use the inverter-reported SOC percentage as the estimate. Stale history and gaps over the configured continuity limit still fail closed, so a dash can remain when there is no valid anchor or coverage.

## Files changed

- `src/solarminer_gateway/tuya_dps_registry.py` — new registry and confidence-scored profile suggestions.
- `src/solarminer_gateway/integrations.py` — profile persistence/projection, scoped QCCDZ handling, and safer declared-DPS mapping.
- `src/solarminer_gateway/energy_engine.py` — raw DPS telemetry interpretation and voltage/power-based SOC anchor.
- `tests/test_hardware_integrations.py`, `tests/test_energy_engine.py` — registry, local mapping, and SOC regression coverage.
- `the-solar-miner-pwa-v0.5.7-candidate/app.js` — profile selection and DPS inspection in the Owner editor; SOC reason display.
- `the-solar-miner-pwa-v0.5.7-candidate/tests/*` — PWA behavior contracts.
- `web/pwa/*` — embedded PWA synchronized with the standalone PWA.

## Validation status

- Standalone PWA JavaScript syntax check: passed.
- Standalone PWA tests: 149 passed, 0 failed after adding the profile-selector contract test.
- `git diff --check`: passed after the latest edits.
- Gateway Python suite: not run locally because Python 3.13 is not installed in this Windows environment. The Linux release workflow must pass before the Gateway package is considered publishable.
- Real Tuya device behavior and the actual Gateway battery SOC display have not been exercised from this workstation.

## References

- [Tuya Smart Switch Product Function Definition](https://developer.tuya.com/en/docs/iot/smart-switch-product-function-definition?id=K9r7gh4lbe886)
- [Tuya Device Function Point / DPS overview](https://developer.tuya.com/en/docs/iot/device-function-point?id=Ka6y8bi672n1s)
- [Tuya Equipment Related API](https://developer.tuya.com/en/docs/iot/equipment-related-interface?id=K9m1dlii6zkf7)
- User-supplied proposal: `Texto colado.txt` (owner observations and community templates).

The Tuya documentation defines functions and state codes at the product level. The numeric DPS identifier is not a universal semantic identifier across unrelated devices; the QCCDZ DP18 mapping is therefore intentionally limited to the owner-identified QCCDZ category.
