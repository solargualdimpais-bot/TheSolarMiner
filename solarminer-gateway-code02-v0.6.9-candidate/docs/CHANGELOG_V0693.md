# Gateway 0.6.93 / Owner PWA 0.5.58

- Fixes persistence of Braiins tuner readings: the API reports successful reads as `read`, and the Gateway now accepts that documented response state instead of waiting for `read_data`.
- The Antminer card now receives measured average hashrate, estimated consumption, active target, and profile target from the tuner query.
- Keeps Gateway 0.6.92 available in signed USB rollback bundles.

- Improves the photovoltaic string save flow: submit is intercepted explicitly, the configuration is re-read from the Gateway before success is shown, and failures keep the current page/form open.
- Reorders navigation to Home, Casa, Energy, Devices, Automatismos, Profile, Owner, and slightly enlarges navigation icons.
