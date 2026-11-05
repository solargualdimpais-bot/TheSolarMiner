# Tesla Fleet callback relay

This small HTTPS service runs on the public VM. It receives Tesla's one-time OAuth result and holds the code in memory for at most ten minutes. The private Gateway polls it over outbound HTTPS, exchanges the code with Tesla, stores the rotating refresh token locally, and deletes the relay session. The relay does not receive the Tesla client secret, access token, refresh token, vehicle data, or commands.

## Deployment shape

- Point a domain you control to the VM's public IPv4 address.
- Allow inbound TCP 443 for the callback. Allow TCP 80 only while issuing or renewing a Let's Encrypt certificate with the standalone challenge.
- Run Uvicorn directly with its TLS certificate using `run_relay.py`; do not put a reverse proxy in front of it.
- Use the exact callback `https://<your-domain>/oauth/callback` in Tesla Developer. Tesla acceptance of a particular domain must still be confirmed in its portal.

## Relay environment

Create `/etc/solarminer-tesla-relay.env` with mode `0600`, owned by root. It must contain:

```text
SOLARMINER_RELAY_API_KEY=<random secret of at least 32 characters>
SOLARMINER_RELAY_TLS_CERT=/etc/letsencrypt/live/<your-domain>/fullchain.pem
SOLARMINER_RELAY_TLS_KEY=/etc/letsencrypt/live/<your-domain>/privkey.pem
```

Install the packages from `requirements.txt` in `/opt/solarminer-tesla-relay/.venv`, place `relay.py` and `run_relay.py` in that directory, install `solarminer-tesla-relay.service` into systemd, then start it. The `solarminer-relay` service account needs read access to the certificate and private key. Restart the service after certificate renewal.

## Gateway environment

Create `/etc/solarminer/tesla-relay.env` with mode `0600`, owned by root. Use the same API key, but never copy it into the PWA or Tesla Developer:

```text
SOLARMINER_TESLA_RELAY_URL=https://<your-domain>
SOLARMINER_TESLA_RELAY_API_KEY=<same random secret as the relay>
```

Restart `solarminer-gateway.service` after configuring the file. The PWA then receives the callback URL from the authenticated Gateway configuration endpoint.

Do not commit either environment file or put its secret in support messages. The current integration is only for OAuth and read-only vehicle telemetry; it does not issue vehicle commands.
