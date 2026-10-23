# SolarMiner Gateway CODE02 v0.6.52

- Fix Nginx validation under the privileged broker's strict systemd sandbox by allowing only the Nginx log and runtime paths needed by `nginx -t`; this prevents sandbox read-only errors from being mistaken for host filesystem or configuration failures.
- Add offline, in-browser HEIC/HEIF to JPEG conversion for the Owner home photograph upload. The original image remains local; the converted JPEG is previewed, resized, and compressed before the Gateway receives it.
- Include PWA 0.5.18 with an updated static cache so installed PWAs fetch the HEIC converter.
