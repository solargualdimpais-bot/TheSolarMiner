# The Solar Miner Owner PWA 0.5.157

- Adds Portuguese labels and an editable, PID-scoped Tuya DPS map while preserving the original Tuya codes and schema.
- Adds the shared Cards editor for Tuya and Shelly templates, linked by protocol and product model.
- Separates protocol identity so Zigbee2MQTT properties cannot be interpreted as Tuya DPS.

## 0.5.157

- Liga os cards, leituras e controlos Tuya ao mapa DPS canónico do PID exato.
- Aplica a associação partilhada a todos os devices com o mesmo PID e impede herança entre produtos diferentes.
- Infere significados óbvios a partir do código Tuya, como tensão, potência e countdown, sem misturar leituras e ordens.
