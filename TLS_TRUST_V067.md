# TLS and Gateway identity trust — v0.6.7

The browser does not read the server TLS certificate directly. `/api/v1/health` and `/api/v1/info` establish reachability/product metadata only, not Gateway identity.

The new identity challenge uses an independently provisioned Ed25519 key pair. The QR carries the full SHA-256 fingerprint of the DER SubjectPublicKeyInfo public key. The client fetches `/api/v1/gateway/identity` with a fresh timestamp and nonce, checks that the returned public key's full SHA-256 equals the QR fingerprint, then verifies the Ed25519 signature over:

`GET\n/api/v1/gateway/identity\n{timestamp}\n{nonce}`

This proves possession of the private key corresponding to the QR fingerprint, assuming the QR itself was received through an Owner-controlled trusted channel. It does not make an untrusted QR trustworthy. If that independent QR/fingerprint channel is unavailable, pairing must stop. Do not accept an unknown TLS certificate silently and do not disable TLS validation.

Provision the private key with restrictive file permissions and the public key independently. The code fails closed if either key is absent, malformed, mismatched, or the private key is group/other accessible. No key is generated automatically. This implementation has not been tested against real Tailscale DNS or Safari/iPhone.
