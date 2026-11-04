PWA candidate 0.5.118 — Shelly Devices

- Adds a Shelly Devices view with Gateway LAN discovery, manual IP registration, fresh state reads and read-back-confirmed relay controls.
- Shelly registration stores the exact device-reported MAC in the Gateway shared inventory.
- Uses authenticated Gateway APIs; the PWA does not directly call a Shelly AP.
- Shelly Wi-Fi AP onboarding remains future work. No automatic Wi-Fi network switching or AP provisioning is included.
