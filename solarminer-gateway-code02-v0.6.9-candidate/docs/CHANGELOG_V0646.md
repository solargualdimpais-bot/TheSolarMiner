# SolarMiner Gateway CODE02 v0.6.46

- Online-bank capacity changes now preserve aggregate SOC and proportionally scale stored available energy. Switching a parallel bank offline removes only that bank's share of the combined energy, based on its configured capacity.
- Battery page explicitly labels “Bateria Deye · conjunto” as a read-only aggregate summary and displays total nominal capacity from online banks.
- Newly added battery banks start offline until the Owner confirms they are physically connected.
- USB Repair includes the signed 0.6.45 package for rollback.
