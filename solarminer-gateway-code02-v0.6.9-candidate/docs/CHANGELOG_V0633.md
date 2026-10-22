# SolarMiner Gateway 0.6.33

- Added an automatic, hourly queue and GitHub issue reporter for sanitized Gateway application errors.
- Kept error reports on the Gateway when GitHub is unreachable or the optional token is not configured.
- Added a root-managed, repository-scoped GitHub token file; the PWA and application logs never receive the token.
- Kept automatic reporting limited to the Python Gateway process. OS, Nginx, installer, and pre-start systemd errors remain in local journal/log files.
