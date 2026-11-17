# SolarMiner Gateway CODE02 v0.6.249

## Fixes

- Use only a fresh, valid SOC reading from a Deye source as the current battery SOC. Remove the legacy voltage and power estimator, never project future SOC, and show the reading source in the Owner Energy view.
- Prevent the Intelligence service from entering a restart loop while its bootstrap credential file has not yet been created. Systemd now skips the service until bootstrap provisions that file.
- Record the administrative terminal broker proxy failure class in the Gateway journal while keeping the Owner-facing error free of sensitive runtime details.

## Validation limits

- The physical Lenovo Gateway was not reachable during this build. Its Intelligence bootstrap outcome and administrative broker socket still require runtime verification on the installed Gateway.
