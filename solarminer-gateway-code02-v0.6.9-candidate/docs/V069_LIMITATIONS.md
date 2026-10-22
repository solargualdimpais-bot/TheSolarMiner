# Limitações conhecidas da candidata atual

- A candidata ainda necessita de instalação e validação funcional no Gateway físico do utilizador.
- O updater depende de chave Ed25519 confiável, allowlist administrativa, certificado TLS, release ativa, base de dados e serviço de recuperação. Qualquer preflight inválido falha fechado.
- Deye: não há mapa de registos confirmado para modelo e firmware exatos; não são expostas métricas nem escritas Modbus.
- Antminer: existe leitura BOSminer CGMiner compatível; a identidade física do modelo e os comandos de potência não são validados nem enviados.
- Tuya: integração Cloud de leitura, dependente de credenciais, região, permissões e associação do dispositivo ao projeto configurado. MOES só funciona se estiver efetivamente exposto por esse projeto.
- Shelly: não há driver nem formulário de configuração.
- Tesla Fleet: leitura do estado de carregamento; não há controlo do veículo nem motor energético X/Y/Z.
- Testes simulados confirmam o comportamento do software, mas não comprovam comunicação com os equipamentos físicos do utilizador.