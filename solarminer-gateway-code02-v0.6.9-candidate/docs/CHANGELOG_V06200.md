# Gateway 0.6.200

- Capture Tuya's raw Product field and cache a Portuguese label per device; online translation failure leaves the source label intact and does not interrupt inventory sync.
- Persist the Tuya product identity in SQLite and scope owner DPS mappings by Product ID, raw Product, cloud category, and automatically detected equipment kind.
- Replicate an owner DPS map only to devices with the exact same identity; preserve legacy Product-ID-only maps only when that ID has a single complete identity.
- Automatically derive the functional equipment type and DPS interpretation profile in the Gateway. The PWA no longer exposes manual type or DPS-profile selectors in the Tuya device editor.
- Display the translated Tuya Product label and functional equipment type in the device settings.
