# SolarMiner Gateway 0.6.26

- Move Tesla Fleet configuration and reading from generic hardware integrations to the EV charging area and dedicated Owner API.
- Restricts Tesla API output to charge-state fields for one selected vehicle; location, climate, driving and unrelated vehicle data are excluded.
- Keeps Tesla Fleet read-only. EV strategies remain local because the Gateway energy engine and Tesla command flow are not implemented.
- Preserves existing Tesla credentials in the Gateway's private integration configuration during upgrade.
- Keeps Deye, Antminer S19K Pro and Tuya in the generic hardware integrations panel.
