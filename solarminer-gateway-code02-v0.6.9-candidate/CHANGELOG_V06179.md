# Gateway 0.6.179 / Owner PWA 0.5.127

- Adds Shelly BLU sensor discovery through registered Shelly BLE bridges from the unified LAN scan.
- Registers a discovered sensor only after the bridge observes its MAC again, then stores it in the shared device inventory with its bridge association.
- Reads registered BTHome sensor values through the bridge and exposes only capabilities present in the advertisement.
- Shelly light cards expose the power control only when the device reports its state; dimming and color controls remain capability-based.
- Automated checks use mocked bridge RPC responses and do not send commands to physical equipment. Physical validation with the registered BLU Gateway and sensors remains necessary.
