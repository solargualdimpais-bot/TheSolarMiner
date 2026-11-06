# PWA 0.5.145

- Opens the secure Gateway connection dialog automatically on first use when no endpoint is saved.
- Opens the connection dialog through an early delegated handler, so unrelated startup errors cannot leave the setup button inert.
- Explains that the first Owner password prompt appears only after the Gateway endpoint is securely tested and confirms bootstrap is pending.
- Updates the service-worker cache version so installed PWAs fetch the new onboarding files.
