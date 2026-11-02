# SolarMiner Gateway 0.6.146 / Owner PWA 0.5.98

- Records the authenticated HiLink state accurately after a successful login.
- Returns sanitized model, firmware, login-state, and endpoint-success diagnostics to the Owner PWA.
- Spaces Huawei API requests by 2.5 seconds and extends bounded probe/inventory timeouts for the slower sequence.
- Carries forward the staged modem identification and LAN inventory flow; it does not bypass Huawei firmware permissions.
