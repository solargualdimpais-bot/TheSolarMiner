# SolarMiner Gateway 0.6.110

- Tesla local presence can be configured with the vehicle Wi-Fi MAC alone and checked against the Huawei router's connected-client list.
- The energy surplus plan uses a fresh positive or negative MAC match to select the Tesla-home or Tesla-away priority profile; stale or failed router reads remain unknown and use the configured fallback profile.
- The PWA shows the Tesla LAN presence check separately from the read-only Tesla Fleet charge-state connection.
- Huawei client lookup now uses the documented fixed `admin` username consistently, avoiding a lookup of a username field that is not present in the form.
- Includes the consolidated Owner PWA and Gateway energy, device, solar-string, AQS, Tuya, photo, and history-chart changes from the candidate branch.

The official Linux release workflow must pass tests, package verification, rollback verification, and Ed25519 signing before this version is available to install or update automatically.
