# SolarMiner Gateway 0.6.109

- Tuya LAN status checks now probe protocol 3.3, then 3.4, then 3.5 using read-only status requests; the first valid response is saved per device.
- A configured MAC can be resolved to a private LAN IP through bounded local discovery when no usable IP is configured.
- Tuya switch and level commands probe and confirm a readable status before sending one physical command; failures never fall back to the Tuya Cloud.
- DPS handling remains device-specific and uses the imported Tuya function/status schema or an explicit Owner mapping; there is no universal DPS index list.
