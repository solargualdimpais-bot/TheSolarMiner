# Gateway 0.6.181

- Added an additive SQLite Shelly product-profile catalogue in the existing Gateway database, alongside the shared product catalogue and separate physical-device inventory.
- Seeded documented profiles for Shelly Vintage Gen1 and the Shelly BLU Gateway, including model-specific capabilities, metrics, commands, Settings groups, and source links.
- Added an Owner-only API for reading the catalogue. Seed operations are idempotent and preserve later local edits.
- Embedded the matching PWA with compact Shelly cards, model-specific Settings navigation, and release-to-apply brightness control.

Automated checks use mocked data. No physical Shelly commands are sent by tests.
