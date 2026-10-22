# SolarMiner Gateway CODE02 v0.6.42

- `site-profile` persists Owner-selected property photo opacity alongside the shared house photo and structure. Existing saved profiles receive the default opacity without a database migration.
- The PWA compresses supported photos repeatedly to fit the Gateway's existing 1.8 MB JPEG limit, including browser-decodable HEIC/HEIF images, and gives explicit errors when the file cannot be decoded or compressed.
- The Owner can set photo transparency in the shared property profile; all authenticated PWAs receive the same appearance.
- Home weather and PV production cards use the same compact two-column square layout at phone widths; final CSS specificity prevents older rules from reverting them to stacked rectangles.
- The embedded Gateway PWA is synchronized with the separately published PWA, and the service-worker cache key is advanced.

Validation: 89 PWA Node tests and 14 Gateway profile/API tests passed locally. No build or install on a Debian Gateway was performed as part of this change.
