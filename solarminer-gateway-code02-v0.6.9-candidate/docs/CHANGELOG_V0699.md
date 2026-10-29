# Energy surplus manager — Gateway 0.6.99 / PWA 0.5.63

Adds an Energy → Surplus management panel for the forecast-guided dispatch plan. The Owner can enable/disable dispatch, choose the Tesla-home or Tesla-away priority profile, set the minimum forecast surplus and battery reserve, inspect configured loads, and pause/resume automation after manual control.

Dispatch remains fail-closed: forecast potential is only a guide; increases are limited by fresh measured surplus and battery reserve. When the Tesla is considered home, comfort loads take priority and mining is excluded. When away, configured mining loads may be used. Manual Owner actions pause automatic dispatch until resumed.

GitHub Pages includes a local simulation mode that does not contact the Gateway or send commands. Tesla Fleet integration is currently read-only, so Tesla LAN presence detection and remote charging-current changes are not included or implied by this release. Tuya and Braiins controls use only the integrations already configured in the Gateway.
