# SolarMiner Gateway CODE02 v0.6.54

- Allow IPv4 and IPv6 sockets in the restricted update broker so `nginx -t` can validate configured listeners such as `0.0.0.0:80`.
- Keep the broker's address-family restriction limited to Unix, IPv4 and IPv6 sockets; arbitrary shell commands remain unavailable.
- Expose the bundled HEIC/HEIF converter through the Gateway's same-origin PWA asset routes so the photo editor can load it.
- Add Gateway route coverage for the HEIC converter asset.
- Include PWA 0.5.18 with automatic HEIC/HEIF photo conversion.
