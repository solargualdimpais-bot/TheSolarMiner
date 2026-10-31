# SolarMiner Gateway 0.6.116

- Makes Devices tab changes and navigation immediate, and prevents background inventory refreshes from redrawing a different page.
- Avoids unnecessary full Energy refreshes every 10 seconds and indexes device readings for quicker confirmed-device rendering.
- Attaches submit handling directly to the photovoltaic string and AQS dialogs to prevent native form navigation from resetting the PWA.
- Reads the current Gateway energy configuration before changing PV strings and confirms the saved result.
- Includes Owner PWA 0.5.73.
