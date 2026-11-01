# Gateway 0.6.137

- Bundles a pinned community Tuya device/DPS reference catalogue with source provenance and licenses, including 1,778 Product ID configurations and eight generic reference templates.
- Uses community DPS labels and ranges only when the exact Tuya Product ID matches; conflicting references remain unresolved.
- Keeps every community entry read-only. Writable commands still require the device's Tuya schema or an explicit owner mapping.
- Records the owner-provided QCCDZ EV DPS notes without allowing them to override a conflicting exact Product ID/schema reference.
- Includes regression coverage for exact Product ID scoping and the EV DPS 18 conflict.
