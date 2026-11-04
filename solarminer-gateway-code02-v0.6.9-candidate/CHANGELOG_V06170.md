# Gateway 0.6.170

- Fixed Shelly inventory synchronization calling a nonexistent helper; Shelly records now project into the shared MAC-keyed inventory using the existing upsert routine.
- Added a regression test covering the post-registration Shelly inventory synchronization path.
- Includes Owner PWA 0.5.119 with optional Shelly authentication fields in the LAN registration dialog.
