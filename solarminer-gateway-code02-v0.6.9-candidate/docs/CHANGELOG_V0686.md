# Gateway 0.6.86 / Owner PWA 0.5.51

- The non-disruptive Antminer control test now recognizes Braiins tuner-state field names in camelCase and snake_case.
- It also accepts watt values encoded as numbers or numeric strings, then resends the unchanged positive target and verifies the REST response.
