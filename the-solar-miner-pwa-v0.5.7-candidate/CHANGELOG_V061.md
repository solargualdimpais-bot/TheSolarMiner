# Owner PWA 0.5.61

- Owner creates a Gateway invitation code; the PWA generates its QR locally.
- QR opens the PWA activation page from GitHub Pages with a one-time secret kept in the URL fragment.
- Activation asks for the new account username and password, verifies the Gateway Ed25519 identity, and redeems the invite.
- The invite carries LAN and ready Tailscale endpoints; activation tries them in order and signs up on the first Gateway that proves the expected identity.
- Bundled the MIT-licensed QR generator; no QR service or Gateway-side QR dependency is required.
