# Gateway 0.6.196

- Tuya synchronization stores category reference schemas once in the shared category catalog instead of duplicating them in every device record.
- The cached Tuya schema catalog budget is reduced to leave space for device records and locally stored keys within the Gateway configuration limit.
- Device-specific function/status schemas and local keys remain preserved.
