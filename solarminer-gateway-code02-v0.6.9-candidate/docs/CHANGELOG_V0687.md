# Gateway 0.6.87 / Owner PWA 0.5.52

- Update the Antminer test to use one button for telemetry and non-disruptive Braiins control verification.
- Keep the control probe safe: it only resends the currently confirmed positive target; if that target cannot be read, no command is sent.
- Accept Braiins tuner-state field naming and numeric/string watt values for the probe.
