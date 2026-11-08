# Gateway 0.6.216

- Fixed first-install data partition creation after adding partition-size metadata.
- Safely resumes an interrupted first install when the installer-created `SOLARMINER_DATA` partition is blank and has no detectable signatures.
- Refuses to format the labeled partition if it is mounted elsewhere, contains any signature, or cannot be inspected.
- Added regression coverage for the five-field partition record and interrupted blank-volume recovery.
