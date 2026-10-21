# Limitações conhecidas CODE02 v0.6.9 candidate

- O código do pipeline e os testes automatizados foram implementados, mas o pacote não foi instalado num host Debian/systemd real. A candidata necessita de ensaio de instalação limpa e upgrade a partir da versão efetivamente instalada.
- O updater só fica disponível quando `/etc/solarminer/release-pubkey.pem` é provisionada com chave pública confiável, o certificado TLS local existe, `current` aponta para uma release válida, a base de dados existe e `solarminer-recovery.timer` está ativo. Caso contrário, apply falha fechado com HTTP 503.
- A verificação da API e o helper root revalidam a assinatura, mas o provisionamento da chave e a gestão da rotação são responsabilidade operacional a validar no host.
- Os testes de pipeline criam pacotes `.deb` descartáveis e simulam systemd; não validam `sudoers`, unidades reais, reboot, corte de energia nem o comportamento de dpkg no Gateway físico.
- Não foi executada instalação física, validação visual Safari/iPhone, QR nativo, IndexedDB/CryptoKey real ou instalação PWA no ecrã inicial.
- PROFILE e favoritos não sincronizam com o backend; comandos físicos continuam DEMO/local.
- Fase E — Deye Modbus, Tuya LAN, Shelly, Antminer, MOES e produção solar/MPPT — continua adiada. Não foram adicionados drivers, registos Modbus ou comandos físicos.
