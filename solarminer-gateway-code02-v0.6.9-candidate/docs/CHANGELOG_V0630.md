# SolarMiner Gateway 0.6.30

- Correct BOSminer API request framing to the documented newline-terminated JSON format and close the request half of the TCP stream before reading its response.
- Replace the guessed Deye FC03 register-zero connection check with TCP reachability plus the standard FC43/MEI14 Read Device Identification probe.
- Report saved/not-saved configuration and per-device protocol states in the Owner PWA instead of describing an empty, unconfigured result as a successful read.
- Keep hardware access read-only. Deye metrics remain unavailable until an exact model and firmware register map is verified; Antminer power control is not included.
- Keep the standalone PWA source and Gateway-packaged PWA in sync and rotate the static asset cache name.
