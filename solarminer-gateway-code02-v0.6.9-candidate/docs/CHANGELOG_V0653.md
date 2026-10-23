# SolarMiner Gateway CODE02 v0.6.53

- Allow IPv4 and IPv6 sockets in the restricted update broker so `nginx -t` can validate configured listeners such as `0.0.0.0:80`.
- Keep the broker's address-family restriction limited to Unix, IPv4 and IPv6 sockets; arbitrary shell commands remain unavailable.
- Include signed rollback package support for Gateway 0.6.52 in the USB installer.
- Carry forward PWA 0.5.18, including automatic HEIC/HEIF photo conversion.
