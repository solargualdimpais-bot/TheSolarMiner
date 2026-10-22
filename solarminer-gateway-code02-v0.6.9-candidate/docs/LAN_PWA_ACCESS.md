# Accessing the PWA on the Gateway LAN address

The Gateway serves the Owner PWA and its API from the same HTTPS origin on port `8443`. Open `https://<Gateway-LAN-IP>:8443/` while connected to the Gateway's LAN. The PWA now selects that origin automatically and starts its regular health/bootstrap/session check. When the first-Owner setup is pending, it opens the existing setup flow. Otherwise it tries the registered device identity and then presents the password login if needed.

The Gateway must serve all JavaScript modules imported by `app.js`. If one module returns 404, the browser stops loading the application and the buttons appear inactive. The Gateway test suite checks every required module route.

This direct LAN endpoint uses the Gateway's local TLS certificate. The browser must already trust that certificate and its subject alternative name must contain the exact LAN IP being opened. If the Gateway's LAN IP changed since its certificate was created, the browser will report a TLS name error; changing PWA code cannot bypass browser TLS validation. The Tailscale HTTPS name uses the separate publicly trusted certificate when Tailscale certificate setup is active.

GitHub Pages remains a separate origin and still requires the Gateway endpoint to be configured there. Browser storage and registered device identities are isolated by origin, so a device first registered on GitHub Pages may need to complete password login once on the LAN origin.
