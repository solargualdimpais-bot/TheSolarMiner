# Supervised physical validation — operator workflow

The Gateway only proposes, approves and records tests. It does not switch, disconnect, energize, de-energize or reconfigure physical equipment.

1. Record current equipment profile, firmware, field values, source, timestamps and trust class.
2. Confirm the hypothesis, applicable manufacturer documentation, safe preconditions, instrument suitability, tolerances and stop conditions.
3. An authorized administrator explicitly approves the proposal. Approval is not a command to the equipment.
4. A qualified professional performs any electrical intervention manually under the manufacturer's procedure. Never disconnect PV strings under load, open electrical panels, touch energized conductors, bypass protection/BMS or automate battery/PV disconnection.
5. Record before/during/after observations with timestamps and operator identity. Include independent instrument values where appropriate.
6. Record PASS, FAIL or INCONCLUSIVE and explain latency, uncertainty, instrument resolution and limitations. Stop if alarms, instability, unexpected heating, smell, noise or unsafe divergence occurs.
7. A passing test corroborates only the listed fields and conditions. Simulated values cannot become physically corroborated; later live readings start as LIVE_UNVERIFIED again.

If safety or interpretation is uncertain, mark BLOCKED and use passive observation only. This record-keeping workflow is not an electrical work instruction and does not replace a qualified professional.
