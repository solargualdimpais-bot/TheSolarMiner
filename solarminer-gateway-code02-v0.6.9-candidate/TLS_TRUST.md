# TLS trust and client provisioning

The service refuses to start if its TLS certificate or private key is missing. Package installation creates a self-signed RSA-3072 certificate with SANs for `localhost`, the installation hostname and `127.0.0.1`. A gateway reached by a different DNS name or IP address needs a newly provisioned certificate whose SAN contains the exact name used by the client; do not disable hostname or certificate verification.

The server private key is `/var/lib/solarminer/server.key` (mode `0600`, owned by `solarminer:solarminer`). The public certificate is `/var/lib/solarminer/server.crt`. The certificate is self-signed; it is not a CA and must not be treated as a general-purpose trust anchor for other services.

## Establishing trust

1. Access the gateway through a separately authenticated local administration channel.
2. Obtain the public certificate with local administrative access (for example, `sudo cat /var/lib/solarminer/server.crt`). Do not distribute the private key.
3. Compute the fingerprint locally: `openssl x509 -in server.crt -noout -sha256 -fingerprint`.
4. Verify that fingerprint through an independent trusted channel (for example, an on-site operator reading it from the gateway console). Do not trust a certificate merely because the same untrusted network served it.
5. Install/trust the certificate only on clients where that fingerprint has been verified. Then connect using a DNS name or IP that matches a SAN.
6. Test the endpoint with strict validation, e.g. `curl --cacert server.crt https://gateway-host:8443/api/v1/health --fail`; never use `-k`/`--insecure`.

Because this is a self-signed leaf certificate, client tooling must support explicit trust of that exact certificate. For larger deployments, use a properly managed private CA and issue a leaf certificate with the required SANs. A private CA key must be kept offline or in a dedicated protected signing environment and must never be stored on or served by the gateway API.

A PWA running in a browser cannot override certificate validation and cannot silently trust a newly generated self-signed certificate. The operator must establish trust in the OS/browser trust store or use a certificate issued by a CA trusted by the client. Browser restrictions also mean the PWA cannot read a client's physical MAC address. The API therefore records MACs as `declared`; it does not label them verified without an independent verification process.

## Important limitation

The package bootstrap currently generates a self-signed certificate for the hostname observed during installation plus localhost. It does not discover all future network addresses. Before exposing the service to a LAN, provision and verify a certificate with the actual DNS/IP SANs, then restart the service. TLS certificate rotation and automated CA management are not implemented in CODE 01.
