# Gateway 0.6.240

- Add owner-triggered Tuya panel child discovery, per-product Cloud schema retrieval and persistent Zigbee parent/node transport.
- Reuse and serialize the parent LAN session for panel and child traffic; preserve child topology during configuration edits and regular Cloud inventory sync.
- Keep child writes subject to the existing mapped and authorized DPS rules. No MOES panel-screen, scene, Alexa or firmware API is claimed.
- Add mocked topology, isolation, missing-key, child-command, configuration-preservation and PWA contract coverage.
- Physical compatibility with the user's MOES model and firmware remains unverified; see `TUYA_MOES_PHYSICAL_VALIDATION.md`.
