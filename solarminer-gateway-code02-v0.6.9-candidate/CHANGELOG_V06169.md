Gateway candidate 0.6.169 — Shelly LAN operational integration

- Adds bounded concurrent local reads for registered Shelly devices.
- Keeps Wi-Fi AP onboarding as future work; this candidate does not scan Wi-Fi networks or configure a Shelly/Gateway network.
- Adds authenticated, Owner-only Shelly LAN discovery and read endpoints, plus an authenticated relay command endpoint with one-shot command IDs and read-back confirmation.
- Persists Shelly identity/configuration and command lifecycle metadata in SQLite; no Wi-Fi credentials are stored.
- Network scan enrichment records the Shelly-reported full MAC and identifies its protocol and firmware when the device responds.
- Registration links the Shelly record to the shared MAC-keyed SQLite inventory.
- This is local code only. AP onboarding, asynchronous event subscriptions, encrypted device credentials, Master Energy Engine dispatch, physical validation, release signing and publication are not included/confirmed.
