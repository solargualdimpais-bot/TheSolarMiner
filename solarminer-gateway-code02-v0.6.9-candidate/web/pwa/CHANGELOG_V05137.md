# PWA 0.5.137

- Uses the callback URL supplied by the authenticated Gateway configuration.
- Completes Tesla Fleet OAuth through the public HTTPS relay while the Gateway retrieves and exchanges the one-time code over outbound HTTPS.
- Accepts the relay return only from the registered callback origin and correlates it to the active OAuth state.
- Keeps the Tesla client secret out of browser storage and does not expose authorization or refresh tokens to the PWA.
