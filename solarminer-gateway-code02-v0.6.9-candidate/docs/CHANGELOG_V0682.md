# Gateway 0.6.82 / Owner PWA 0.5.48

- Simplified Antminer control authentication to match the password-only Braiins OS login screen: the Owner form requests only the password and the Gateway authenticates internally as `root`.
- The password remains stored only in Gateway hardware configuration and is never returned to the PWA.
