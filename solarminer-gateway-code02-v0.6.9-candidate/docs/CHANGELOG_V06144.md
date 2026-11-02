# SolarMiner Gateway 0.6.144 / Owner PWA 0.5.97

- Adds a read-only Huawei model and firmware probe for the staged modem discovery flow.
- Persists confirmed modem identity/version fields with the Huawei configuration and exposes them without credentials.
- Adds the single-action PWA flow: identify, Continue or Stop, then inventory Huawei clients and scan local IP/MAC neighbors.
- Adds regression coverage for model/version extraction, login-required firmware, profile persistence, and the staged UI contract.
