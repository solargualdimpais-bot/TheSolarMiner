# Gateway 0.6.214

- Corrected the first-install USB bundle to select the package version from the signed release manifest.
- Reused an existing ext4 `SOLARMINER_DATA` volume without formatting it; refused to format an existing data partition with an unexpected filesystem.
- Preserved the active Owner and database when only the Debian system partition is reinstalled. Formatting the data volume still deletes its contents and requires an external backup.
- Disabled the periodic Gateway watchdog timer for this stabilization release, as requested; normal systemd service behavior remains in place.
- Added privacy-safe diagnostics for slow/failed health probes and Deye/Tuya polling, with request durations and aggregate device counts but no device IDs or network addresses.
