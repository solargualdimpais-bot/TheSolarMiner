# SolarMiner Gateway CODE02 v0.6.254

- Makes release recovery ordered but non-blocking for the Gateway API and its administrative/update brokers, so a recovery fault cannot take the diagnostic interface offline.
- Decouples the Owner-triggered Intelligence bootstrap action from the general release update broker.
- Keeps the data-volume mount and integrity check before the bootstrap action runs.
- Restricts the new broker to one fixed systemd unit; it accepts no caller-supplied commands, paths, or unit names.
