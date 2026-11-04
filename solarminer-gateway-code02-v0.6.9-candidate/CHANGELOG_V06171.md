# Gateway 0.6.171

- Adds Owner-only Tuya Product ID catalog import preview and selective apply endpoints.
- Accepts structured JSON, CSV/TSV, HTML tables and bounded XLSX first-sheet imports; public URL fetching rejects non-public hosts and redirects.
- Persists approved product-scoped DPS references into the Gateway SQLite catalog without enabling DPS writes from imported references.
- Includes Owner PWA 0.5.120 with nested Tuya sections for Cloud account, devices, Product IDs and DPS.
