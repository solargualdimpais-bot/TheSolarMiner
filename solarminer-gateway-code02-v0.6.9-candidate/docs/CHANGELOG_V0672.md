# SolarMiner Gateway 0.6.72

- Calibrate daily solar forecasts against measured previous days and keep remaining solar, adjusted potential and expected load balance separate.
- Learn panel performance per MPPT, with optional panel orientation and tilt, and give stronger weight to periods when household demand exceeds PV production.
- Estimate battery state of charge only after a stable full-charge anchor and expose usable energy and no-solar autonomy.
- Save and browse daily Engine graph history for measured production, forecast and adjusted potential.
- Add a live Owner terminal over the authenticated Gateway session.
- Run shell commands inside a PTY as the restricted solarminer service account and stream output to the PWA.
- Keep the existing read-only Gateway console for service logs and resource status.
- Bundle Owner PWA 0.5.38.
