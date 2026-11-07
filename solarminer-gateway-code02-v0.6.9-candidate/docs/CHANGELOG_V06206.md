# Gateway 0.6.206

- Keep the Gateway health endpoint responsive by replacing the full SQLite integrity scan on every poll with a small database read.
- Add a regression test to prevent the availability probe from scanning the full database.

Validation covers the route behavior and the Linux release pipeline. The physical Gateway still needs to confirm the endpoint response after updating.
