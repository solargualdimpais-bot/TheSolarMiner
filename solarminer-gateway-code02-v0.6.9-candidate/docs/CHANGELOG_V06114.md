# SolarMiner Gateway 0.6.114

- Bundles Owner PWA 0.5.71 with Home and Devices cards using the same compact square layout.
- Preserves the most recent explicit, device-specific LAN diagnostic across cached configuration refreshes so old cloud/config snapshots cannot overwrite a newly observed switch state.
- Keeps single-click details separate from double-click editing on the device information area; a one-second background poll no longer drives the cards.
- Uses the existing read-only LAN diagnostic for the selected device and displays only recognized power/voltage values without assuming telemetry fields exist.
- Includes Gateway 0.6.113 among verified USB rollback packages.

