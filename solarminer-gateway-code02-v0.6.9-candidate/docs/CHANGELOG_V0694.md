# Gateway 0.6.94 / Owner PWA 0.5.59

- Add an independent local health watchdog that checks the Gateway HTTPS health endpoint and the Nginx-to-Gateway path every two minutes.
- After three consecutive failures, restart the Gateway service or reload/start Nginx only when its configuration test passes; skip intervention while an update/rollback unit is active.
- Record watchdog actions in the system journal and include watchdog timer status in the Owner diagnostics console.
- Preserve the exact safe preflight failure reason in update status and the Owner update dialog.
- Keep the signed-package, rollback, and recovery preflight requirements unchanged.
