# Gateway 0.6.197

- Pass the synchronized Tuya device IDs and local keys to the bundled LAN discovery scanner, so discovery can match existing cloud-synced identities and known MAC addresses.
- Keep LAN discovery passive; do not probe every local address with every synchronized key.
- Log the scanner exception details locally when discovery fails, while keeping the user-facing error free of credentials.
