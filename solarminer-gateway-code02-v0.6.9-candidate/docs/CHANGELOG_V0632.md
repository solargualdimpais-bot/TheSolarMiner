# SolarMiner Gateway 0.6.32

- Deye diagnostics try a read-only, single-register FC03 fallback when FC43/MEI14 is rejected or times out. The raw diagnostic value is discarded; no undocumented metric is exposed.
- Tuya Cloud results are isolated per configured device ID. A failed ID no longer discards successful results from the rest of the configured devices; safe provider error codes are preserved for diagnosis without returning provider messages or secrets.
- Antminer output labels S19K Pro as the Owner-configured model and explicitly marks hardware model identity unverified.
- The Owner PWA explains MOES compatibility through Tuya Cloud and states that Shelly has no driver in this release.
- Updated API, installation, integration and limitation documentation, and included hardware integration guides in the Debian package.
