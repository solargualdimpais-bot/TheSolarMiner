# Gateway 0.6.189

- Added an Owner-managed Tesla OAuth relay configuration, verified over authenticated HTTPS and stored privately by the Gateway. The shared relay key is never returned to the PWA.
- The public callback relay now provides an authenticated health check used by Owner setup.
- Added an Ubuntu Server installer and Oracle deployment guide for the direct HTTPS callback relay, including certificate renewal, a restricted systemd service and recovery guidance.
- Improved Shelly BLU discovery with a longer BLE listening window, common BLU Gateway model aliases, and short-lived Gateway-side scan evidence so adding a found sensor does not depend on a second advertisement.
- Preserved Tesla's minimal read-only OAuth scopes. Vehicle command scopes and virtual-key setup are not enabled because command signing is not implemented in this release.
