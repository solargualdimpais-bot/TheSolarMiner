# TLS trust and client provisioning

The Gateway's local API listens on TCP 8443 with the self-signed RSA-3072 certificate `/var/lib/solarminer/server.crt` and private key `/var/lib/solarminer/server.key`. The certificate includes the installation hostname and addresses present at package installation. Direct use of `https://<private-LAN-IP>:8443` requires that browser to trust this exact local certificate. A PWA cannot bypass browser TLS validation or silently trust a new certificate.

For remote use without installing a CA on each phone, use the Gateway's Tailscale MagicDNS HTTPS name (`https://<gateway>.<tailnet>.ts.net`). The Gateway's Nginx endpoint on TCP 443 uses a Let's Encrypt certificate obtained through `tailscale cert`. That certificate is publicly trusted and matches the `.ts.net` hostname. Tailscale traffic is end-to-end encrypted and remains restricted by Tailnet membership and access policies; application login and Owner roles still apply.

The Tailscale certificate files are `/etc/solarminer/tailscale.crt` and `/etc/solarminer/tailscale.key`; the key is root-owned mode `0600` and must never be distributed. `solarminer-tailscale-cert.timer` retries issuance/renewal. MagicDNS and HTTPS Certificates must be enabled by the Tailnet administrator. Tailscale publishes machine and Tailnet DNS names in Certificate Transparency logs when a certificate is issued.

The separate public-IP certificate path on ports 80/443 remains available for installations that deliberately configure inbound router access. It is not needed for Tailscale and must not be confused with the `.ts.net` certificate. The API records MAC addresses as `declared`; browser APIs cannot read a client's physical MAC address.
