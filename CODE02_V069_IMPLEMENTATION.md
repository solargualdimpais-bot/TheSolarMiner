# SolarMiner Gateway CODE02 v0.6.9 — pipeline de atualização

## Objetivo e âmbito

Incremento sobre CODE02 v0.6.8 e PWA v0.5.7. Preserva o contrato público da API `0.6.0`, a base visual da PWA e as integrações existentes. O incremento fecha a implementação de código do pipeline de atualização; não declara instalação física nem publicação.

## Pipeline update ponta-a-ponta

- `GET /api/v1/system/update/check` verifica manifesto Ed25519, compatibilidade, origem HTTPS, tamanho e SHA-256 do pacote. Guarda o manifesto assinado junto do pacote verificado para revalidação independente pelo helper root.
- `POST /api/v1/system/update/apply` exige Owner, operação `VERIFIED` e versão de destino coincidente. Enfileira a atualização numa unidade systemd independente e responde HTTP 202; não reinicia o processo que está a responder ao pedido.
- `/usr/sbin/solarminer-update-apply` aceita apenas modos estritos e identificadores UUID. A regra sudoers permite invocar o helper, não comandos shell arbitrários.
- O helper root revalida assinatura, hash, tamanho, versão Debian, arquitetura e dependências instaladas. Exige chave pública root-owned, symlink `current` válido, base de dados existente e timer de recuperação ativo.
- A máquina de estados é persistida em `/opt/solarminer/update-state.json` e `update-state.jsonl`, com `fsync` em cada transição e lock `flock`. Os estados são refletidos em `update_operations`.
- Antes de extrair/ativar, cria backup SQLite online e regista timestamp UTC, hash, tamanho e versões de schema.
- Extrai o `.deb` verificado para uma release nova e imutável, confirma presença de backend e PWA, e troca `current` com symlink temporário + `os.replace` atómico.
- A unidade `solarminer-update-apply@UUID.service` reinicia o Gateway fora do cgroup da API. O health-check HTTPS de loopback usa o certificado do Gateway, tem prazo máximo de 60 segundos e exige HTTP 200, `status=ok` e `package_version` igual à versão pretendida.
- Se o health-check falhar, o helper para o serviço, restaura o symlink anterior e o backup SQLite, reinicia a versão anterior e valida-a durante até 60 segundos. Se não for possível provar o rollback, persiste `RECOVERY_BLOCKED`.
- A unidade/timer independente executa recuperação em boot e periodicamente, mesmo sem a API, Internet ou Tailscale. O lock evita concorrência entre recuperação e ativação.

## PWA e funcionalidades deliberadamente adiadas

A PWA v0.5.7 e a sua base visual v0.5.6 são preservadas. Favoritos e PROFILE continuam browser-local; não foram adicionados endpoints de comandos físicos. A fase E — Deye/Modbus, Tuya LAN, Shelly, Antminer, MOES, MPPT e produção — continua adiada, sem inventar registos nem comandos.

## Validação e estado

Os testes de integração do pipeline usam um `.deb` descartável, uma chave Ed25519 de teste, SQLite temporária e runner de systemd simulado. Cobrem commit com resultado de health-check injetado, deadline de 60 segundos simulado, bloqueio por preflight, rollback de symlink e restauro SQLite em DB temporária. Não substituem health-check HTTPS real, instalação/upgrade em host Debian de ensaio, reboot real, perda de energia, certificados provisionados ou hardware Gateway.
