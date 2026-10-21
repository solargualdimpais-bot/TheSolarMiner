# Instalação de ensaio — SolarMiner CODE02 v0.6.9

> **Apenas VM Debian descartável de ensaio. Não executar no Gateway físico nem em produção.** O pacote não foi instalado durante esta execução.

## Requisitos

- VM Debian amd64 com systemd, acesso à rede para dependências Debian e snapshot antes do ensaio.
- Acesso root/sudo na VM.
- Não reutilizar a base de dados nem credenciais do Gateway real.

## Instalação inicial

Copiar `solarminer-gateway_0.6.9_amd64.deb` para a VM e executar:

```sh
sudo apt install ./solarminer-gateway_0.6.9_amd64.deb
sudo systemctl status solarminer-recovery.timer --no-pager
sudo systemctl status solarminer-recovery.service --no-pager
sudo systemctl status solarminer-gateway.service --no-pager
curl --insecure --fail https://127.0.0.1:8443/api/v1/health
curl --insecure --fail https://127.0.0.1:8443/
readlink /opt/solarminer/current
```

`--insecure` é apenas para o primeiro diagnóstico de certificado autoassinado dentro da VM. Não o usar como recomendação para clientes ou acesso remoto.

Confirmar no health endpoint `status: ok`, `package_version: 0.6.9` e `version: 0.6.0` (contrato público preservado). Confirmar que `current` aponta para uma release em `/opt/solarminer/releases/`.

## Ativar o teste de atualização assinado

A ativação permanece bloqueada até provisionar uma chave pública de teste root-owned em `/etc/solarminer/release-pubkey.pem`, configurar `SOLARMINER_RELEASE_MANIFEST_URL` na unidade systemd e disponibilizar um manifesto Ed25519 válido e um `.deb` de teste da mesma origem HTTPS. O manifesto deve declarar a versão atualmente instalada como `min_compatible_version`, coincidir com o campo `Version` do `.deb`, e o pacote deve conter backend, PWA e catálogo completos.

Depois de provisionar o manifesto de teste e o certificado/cadeia HTTPS adequados:

```sh
sudo systemctl daemon-reload
sudo systemctl restart solarminer-gateway.service
curl --insecure --fail https://127.0.0.1:8443/api/v1/system/update/check
```

Autenticar como Owner através da PWA/API, validar `signature_valid: true`, `compatible: true` e `activation_available: true`; só então submeter `POST /api/v1/system/update/apply` com a versão verificada e `confirm: true`. A resposta esperada é `202 APPLY_QUEUED`; acompanhar `GET /api/v1/system/update/status` até `COMMITTED` ou `ROLLED_BACK`.

## Ensaios obrigatórios antes de considerar a candidata aprovada

1. Atualização assinada válida e health-check real dentro de 60 segundos.
2. Serviço novo que não arranca: confirmar rollback do symlink e restauro SQLite, integridade `ok` e recuperação da versão anterior.
3. Interrupção do helper em cada fronteira persistida; reboot da VM após `SWITCHED`.
4. Timer de recuperação ativo após reboot, sem Internet/Tailscale.
5. Conferir owner/permissões de `/opt/solarminer`, releases, helper, sudoers, chave pública, certificado e base de dados.
6. Testar instalação limpa e upgrade a partir da versão realmente instalada; guardar `journalctl`, `systemctl status`, hashes e `TEST_REPORT.md`.

Até concluir estes ensaios, esta entrega é uma **candidata de desenvolvimento para VM**, não uma aprovação de instalação física.
