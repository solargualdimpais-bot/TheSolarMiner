# Gateway 0.6.219

- Restores Tuya DPS profiles already stored in the canonical `tuya_product_dps_map` table to the Owner Product ID list and editor, even when the current integration config lacks a `product_schemas` entry.
- Adds regression coverage for a persisted legacy DPS map that must remain visible through `/api/v1/smart-products/catalog`.
- This change is read-only for existing maps; it does not delete or rewrite Tuya DPS rows.
