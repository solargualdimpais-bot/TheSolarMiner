# TLS trust and client provisioning

The local service refuses to start if its TLS certificate or private key is missing. Package installation creates a self-signed RSA-3072 certificate with SANs for `localhost`, the installation hostname and `127.0.0.1`. The service listens only on loopback. Nginx verifies this local certificate when proxying requests. Public browser traffic reaches Nginx on TCP 443, which loads a Let's Encrypt certificate for the Gateway's public IPv4. See `REMOTE_ACCESS_AND_TLS.md` for issuance and network configuration; do not disable hostname or certificate verification.

The server private key is `/var/lib/solarminer/server.key` (mode `0600`, owned by `solarminer:solarminer`). The public certificate is `/var/lib/solarminer/server.crt`. The certificate is self-signed; it is not a CA and must not be treated as a general-purpose trust anchor for other services.

The internal proxy identity is `/var/lib/solarminer/server.crt`; Nginx trusts this exact certificate when it connects to `127.0.0.1:8443`. The public certificate is `/etc/solarminer/public-tls.crt`; its private key is `/etc/solarminer/public-tls.key` and must never be distributed. The public Let's Encrypt certificate is validated by the browser's normal trust store and must match the IPv4 used in the endpoint. Use `https://<public-ip>/api/v1/health` with strict validation; never use `-k`/`--insecure`.

The self-signed certificate is only for the local reverse-proxy connection. It is not served to the browser by the public Nginx endpoint.

A PWA running in a browser cannot override certificate validation or silently trust a new self-signed certificate. This package uses a public CA-issued certificate for the public IPv4 so no per-phone CA installation is needed. Browser restrictions also mean the PWA cannot read a client's physical MAC address. The API records MACs as `declared`; it does not label them verified without an independent verification process.

## Important limitation

IP certificates have a short lifetime and need automatic renewal. The packaged timer retries every 12 hours and the renewal service validates the Nginx configuration before reloading it. The WAN router must forward TCP 80 and 443; CGNAT or ISP filtering can prevent issuance and remote access. See `REMOTE_ACCESS_AND_TLS.md`.
