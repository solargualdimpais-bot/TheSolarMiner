# SolarMiner Gateway CODE02 v0.6.57

- Fixes Tuya Cloud inventory pagination signing by sorting query parameters as required by the Tuya API. This prevents signature rejection on pages after the first when a project has more than 20 devices.
- Adds a regression test covering multi-page inventories and the canonical query order.
