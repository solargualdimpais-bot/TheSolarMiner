# SolarMiner Gateway CODE02 v0.6.51

- Fix false Nginx validation failures in Owner diagnostics and Tailscale status. The privileged broker's strict systemd sandbox now permits writes only to the Nginx log directory and runtime directory required by `nginx -t`; it no longer reports sandbox EROFS errors as host configuration failures.
