# Gateway 0.6.140 / Owner PWA 0.5.93

- Moves all Huawei modem connection and client lookup tools into a dedicated Owner → Modem tab, separate from Tuya / MOES.
- Removes Huawei configuration controls from the Tuya tab while keeping Tuya LAN discovery there.
- Makes the Huawei lookup cancellable and bounds the PWA wait to 25 seconds; reports the number of matched MAC/IP records.
