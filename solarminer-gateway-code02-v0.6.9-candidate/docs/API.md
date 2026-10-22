# API v1 (CODE 01)

## CODE02 v0.6.42 — perfil partilhado com transparência de fotografia

- `GET /api/v1/site/profile` — nome/fotografia e estrutura de pisos/divisões partilhados com as PWA autenticadas. O perfil inicial chama-se `Solar Energy` e não inclui fotografia.
- `PUT /api/v1/site/profile` — Owner-only; grava nome, fotografia JPEG enviada pelo Owner (base64 validado até 1,8 MB), opacidade visual entre 0 e 1 e até 32 pisos/200 divisões. A API rejeita IDs inválidos ou duplicados. A imagem não é incluída no pacote nem nos logs.
- `POST /api/v1/integrations/tuya/switch` — Owner-only; recebe exatamente `{"device_id":"...","on":true|false}` para um dispositivo Tuya configurado com `switch_code`. O Gateway valida a configuração, executa o comando pela API HTTPS Tuya, tenta ler o estado e regista o resultado na auditoria sem segredos.
- `PUT /api/v1/energy/engine/config` — Owner-only; além da bateria agrega `battery_banks` (até 8), `loads` (até 64) e `automation` (ativação, comissionamento, confirmação do mapa, margem e intervalo mínimo de 300 s).
- `GET /api/v1/energy/engine` — calcula plano de despacho e devolve o último ciclo executado. O serviço verifica a cadência Owner configurada; automatização desligada é o padrão. Amostra Deye ausente, inválida ou com mais de 90 s bloqueia comandos.
- `GET /api/v1/system/console` — Owner-only; devolve até 160 linhas/24 kB das últimas duas horas dos serviços SolarMiner, atualização assinada, Tailscale e Nginx. O helper privilegiado usa `journalctl` com unidades fixas e redação de palavras-passe, tokens, cabeçalhos Bearer e chaves privadas. A PWA pode iniciar uma verificação de release assinada através do fluxo de atualizações existente; a aplicação continua separada e exige confirmação do Owner. Não existe endpoint de shell ou comando arbitrário.
- `GET /api/v1/system/tailscale` — Owner-only; inclui `checks.certificate_valid`, `checks.nginx_config_valid`, `checks.nginx_active` e `checks.gateway_active`. `https_ready` só é verdadeiro se o nome MagicDNS corresponder ao endpoint e todos os checks passarem.

## CODE02 v0.6.38 — histórico e engine energético

- `GET /api/v1/energy/engine?history_hours=24` exige `read`; o período válido é 1–168 horas. Devolve últimas leituras Deye, séries de FV/cargas/bateria/SOC, configuração de capacidade e reserva, energia disponível estimada e tendência solar histórica indicativa.
- `PUT /api/v1/energy/engine/config` exige papel Owner e recebe `battery_capacity_kwh` (número ou `null`), `minimum_soc_percent`, `maximum_soc_percent` e até 8 bancos `{id,name,capacity_kwh,minimum_soc_percent,maximum_soc_percent,active}`. Bancos paralelos com `active:false` não entram na capacidade. O resumo devolve `current.battery_soc_percent` estimado no Gateway a partir de uma âncora persistente de tensão máxima (inicializada com o pico observado nos 30 dias anteriores) e integração de potência assinada. `battery_soc_source` identifica a estimativa, `battery_soc_estimate` explica estado e referência, `battery_energy_available_kwh_above_minimum` dá energia utilizável e `battery_inverter_reported_soc_percent` é apenas diagnóstico. A expiração de amostras históricas não redefine a âncora; uma lacuna superior a dez minutos suspende a estimativa até nova referência de tensão. Sem capacidade, referência ou histórico de potência recente/contínuo, os campos calculados ficam `null`.
- O Gateway recolhe FC03 a cada 30 segundos e a API serve a leitura mais recente em memória; persiste uma amostra por minuto e elimina histórico Deye com mais de 90 dias. A resposta inclui estado/idade da última amostra e ambos os intervalos.
- A projeção usa regressão linear das amostras de FV recentes, sem meteorologia, e não executa comandos físicos. A confiança é baixa e as leituras continuam `LIVE_UNVERIFIED`.

## CODE02 v0.6.36 — telemetria Deye e páginas de energia

`POST /api/v1/integrations/hardware/read` continua exclusivo do Owner autenticado. Para o Deye configurado `SUN-15K-SG05LP3-EU-SM2`, devolve 76 campos FC03 de PV1/PV2, bateria, energias diária/acumulada, limites configurados, rede/CT, saída do inversor e cargas, com endereços, valores brutos, unidades e verificações de coerência. Uma leitura bem-sucedida é gravada no registo canónico de energia (`energy_equipment` e `energy_readings`) como `LIVE_UNVERIFIED`. A Home e as páginas Inversores/Baterias apresentam os dados recolhidos; a página de detalhe mostra todas as leituras. Os acumulados de energia usam pares U32 low-word-first e escala 0,1 kWh. Os limites de corrente são valores configurados lidos, nunca escritos, e não representam a capacidade dinâmica comunicada pelo BMS. Na leitura física registada, o tipo Modbus raw `5` diferiu do tipo publicado `0x0500`, os canais de rede vieram a zero e PV2 mostrou uma divergência entre potência e tensão×corrente. O mapa e o logger ainda não foram certificados pela Deye; não usar as métricas em automações.

O mapa e os ensaios estão documentados em `docs/deye/README.md`, `docs/deye/SG05LP3-register-map-supplement.tsv` e `docs/deye/SG05LP3_REGISTER_MAP_SOURCE.md`. A origem continua apenas FC03, sem comandos de escrita.

## CODE02 v0.6.35 — controlo Owner do Braiins OS

`POST /api/v1/integrations/antminer/control` é exclusivo do Owner autenticado. Aceita apenas `{"action":"set_power_target","watt":N}`, `{"action":"pause"}`, `{"action":"stop"}` ou `{"action":"start"}`. O servidor revalida o papel Owner, chama apenas endpoints fixos da REST API Braiins OS e regista a ação e resultado na auditoria sem palavra-passe nem token. O alvo está limitado a 1–2900 W e a resposta devolve os watts que o firmware confirmou. As credenciais são enviadas na configuração Owner e guardadas no ficheiro privado do Gateway, nunca devolvidas. A ligação ao minerador usa REST HTTP em rede privada; requer Braiins OS 25.07 ou mais recente. A porta CGMiner 4028 continua apenas de leitura.

Para os detalhes do mapa Deye atual, incluindo tensões/correntes por MPPT, bateria, rede e cargas, ver a secção CODE02 v0.6.36 e `docs/deye/README.md`.

## Error reporting (CODE02 0.6.33)

There is no PWA endpoint for log upload. The Gateway queues sanitized application `ERROR` records locally and, when the owner has configured a repository-scoped GitHub token, a systemd timer submits batches as GitHub issues. Configuration and privacy details are in `ERROR_REPORTING.md`.

## CODE02 v0.6.35 — diagnóstico de hardware

`POST /api/v1/integrations/hardware/read` returns per-device diagnostics. For `SUN-15K-SG05LP3-EU-SM2`, Deye reads a limited set of candidate registers using FC03 and skips FC43. Results identify the community map source and remain `LIVE_UNVERIFIED`. Tuya Cloud failures are isolated per configured device ID. Antminer model identity remains unverified by the API response.

## CODE02 v0.6.31 — estado e diagnóstico de recuperação de atualização

`GET /api/v1/system/update/status` inclui o identificador e estado da operação. `details.pipeline` contém `failure`, `rollback_failure`, `recovery` e `finished_at_utc` quando aplicáveis. A PWA Owner apresenta a operação, versões e causas da falha/rollback sem exigir acesso ao terminal.

`RECOVERY_BLOCKED` não volta a aplicar a versão que falhou. O serviço de recuperação pode repetir apenas o rollback para a release anterior e a restauração do backup SQLite validado.

`POST /api/v1/integrations/hardware/read` now returns `configuration` for unsaved fields and per-device connection states for TCP, Modbus, and BOSminer API. Missing configuration is no longer shown as a completed read. Deye uses FC43/MEI14 Read Device Identification instead of guessing an FC03 register. Braiins OS receives JSON newline requests for `summary`, `stats`, and `devs`. The endpoint still sends no control commands.

## CODE02 v0.6.29 — atualizações assinadas automáticas

O `solarminer-update-check-daily.timer` verifica a origem GitHub selecionada e permitida e enfileira automaticamente uma atualização apenas se o manifesto e o pacote forem válidos e o preflight independente passar. A API sem privilégios e o serviço diário comunicam com o helper root através do socket Unix privado `solarminer-update-broker.socket`; o broker só aceita `preflight` e `enqueue` com UUID. A aplicação usa o mesmo helper privilegiado, backup SQLite, staging, health check e rollback que o endpoint Owner. `GET /api/v1/system/update/status` expõe o estado e a versão alvo. A verificação manual continua disponível na PWA Owner.

## CODE02 v0.6.26 — integrações de hardware e carregamento EV

- `GET /api/v1/integrations/hardware`, `PUT /api/v1/integrations/hardware` e `POST /api/v1/integrations/hardware/read` são reservados ao Owner autenticado.
- A PWA pode guardar um fornecedor de cada vez com o `PUT` anterior e consulta cada um separadamente através de `POST /api/v1/integrations/hardware/deye/read`, `/antminer/read` ou `/tuya/read`. A leitura Tuya aceita `device_id` opcional. Todos os endpoints individuais voltam a validar o papel Owner e não enviam comandos de controlo.
- Deye Modbus TCP primeiro verifica o transporte e envia FC43/MEI14 Read Device Identification, sem adivinhar um registo FC03. O estado diferencia IP não configurado, TCP inacessível, resposta Modbus de exceção, timeout e resposta de identidade. Ainda não há métricas Deye descodificadas.
- Antminer verifica TCP e envia pedidos JSON BOSminer com newline para `summary`, `stats`, `devs`. O estado distingue porta alcançável de API que não respondeu. Não existe API de escrita ou controlo de potência nesta versão.
- Tuya Cloud usa credenciais Access ID/Secret armazenadas no ficheiro privado do Gateway; os segredos nunca são devolvidos pela API.
- Tesla Fleet para carregamento usa `GET/PUT /api/v1/energy/ev/tesla` e `POST /api/v1/energy/ev/tesla/read`, reservados ao Owner. Devolve apenas campos de carga do veículo escolhido, não inclui localização, climatização ou estado de condução e não envia comandos.
- Endereços LAN exigem IP privado literal. Ver `HARDWARE_INTEGRATIONS.md` para configuração e limites.

O endpoint genérico de leituras de hardware é dedicado a Deye, Antminer e Tuya. Configuração e consulta Tesla pertencem exclusivamente à área Carregador EV.

All network use is intended over TLS. A fresh USB installation sets the initial Owner password locally with `solarminer-gateway owner-password`; the Gateway stores a temporary Argon2id verifier, never the plaintext. `POST /api/v1/bootstrap/owner` accepts the Owner name, that password, a fresh timestamp/nonce and an Ed25519 proof from the first PWA device, then consumes the verifier in the Owner-creation transaction. Only the exact configured HTTPS PWA origin is allowed remotely. Legacy one-time-token bootstrap remains available for older clients. See `OWNER_FIRST_BOOTSTRAP.md` for the end-to-end procedure.

| Method | Path | Access |
|---|---|---|
| GET | `/api/v1/health` | Public, minimal health and bootstrap state |
| GET | `/api/v1/info` | Public, product/version only |
| GET | `/api/v1/bootstrap/status` | Public, state only |
| POST | `/api/v1/bootstrap/owner` | Exact allow-listed HTTPS origin, locally set one-time setup password + Ed25519 proof + timestamp/nonce; legacy token remains supported |
| POST | `/api/v1/auth/device-login` | Associated device Ed25519 signature; issues a temporary session without a password |
| POST | `/api/v1/auth/login` | Legacy password + associated device Ed25519 signature |
| POST | `/api/v1/auth/password-device-login` | Existing active account password + new device Ed25519 proof; registers that browser device and issues a session. Rate limited; password is not logged |
| POST | `/api/v1/auth/logout` | Authenticated session |
| GET | `/api/v1/status` | `read` permission |
| POST | `/api/v1/users` | `manage_users`; owner creation is prohibited here |
| GET | `/api/v1/users` | `manage_users` |
| POST | `/api/v1/users/{id}/revoke` | `owner` only + current password reauthentication; cannot revoke self; kept guarded to prevent bypass |
| PATCH | `/api/v1/users/{id}/role` | `owner` only + current password reauthentication; cannot change own role |
| PATCH | `/api/v1/users/{id}/status` | `owner` only + current password reauthentication; cannot deactivate self |
| POST | `/api/v1/devices/pairing-codes` | `manage_devices`; issues a one-time pairing code for an active username |
| POST | `/api/v1/devices/pair` | One-time pairing code + Ed25519 proof; creates active device association |
| POST | `/api/v1/devices` | `manage_devices`; MAC remains declared metadata |
| POST | `/api/v1/devices/{id}/revoke` | `manage_devices` |
| GET | `/api/v1/audit` | `manage_gateway` |

Device signatures use Ed25519. Browser pairing signs the exact UTF-8 string `PAIR\n{pairing_code}\n{sha256(public_key_spki_der)}\n{NORMALIZED_MAC}\n{timestamp}\n{nonce}`. Pairing codes are random, single-use, administrator-issued, scoped to one active username, and expire after 60–600 seconds (default 300); only the code digest is persisted. Legacy login signs `LOGIN\n{username}\n{device_id}\n{timestamp}\n{nonce}`. Device login signs `DEVICE-LOGIN\n{user_id}\n{device_id}\n{timestamp}\n{nonce}` (an older single-account device may omit the user ID). New bootstrap signs `BOOTSTRAP\n{username}\n{timestamp}\n{nonce}`; legacy-token bootstrap retains the MAC field in its canonical signature. Timestamps must be within ±300 seconds. Nonces are stored under a uniqueness constraint and inserted in the same SQLite transaction as the protected action. Session bearer tokens are random opaque values; only SHA-256 digests are stored. Password hashes use Argon2id via argon2-cffi with memory=65536 KiB, iterations=3, parallelism=2.

Role permissions:

- `owner`: read, operate, manage users/devices/roles/gateway, recovery.
- `admin`: read, operate, manage users/devices; cannot create/promote an owner.
- `operator`: read and operate.
- `viewer`: read only.

The current API does not expose a general-purpose operation endpoint, password-change endpoint, or independent MAC verification procedure. The PWA signing client uses browser Web Crypto; device enrollment and Gateway operations remain subject to the documented role permissions.


## CODE 01 / A1b user management

`PATCH /api/v1/users/{id}/role` accepts exactly `{"role":"owner|admin|operator|viewer","current_password":"..."}`. `PATCH /api/v1/users/{id}/status` accepts exactly `{"status":"active|revoked","current_password":"..."}`. The legacy `POST /api/v1/users/{id}/revoke` now requires `{"current_password":"..."}` and is subject to the same owner-only, reauthentication, and self-deactivation restrictions to prevent bypassing A1b. The existing database status value `revoked` represents a deactivated account; reactivation uses `active`. Extra fields and non-string values are rejected by request validation.

Both PATCH operations and the legacy `POST /api/v1/users/{id}/revoke` require an authenticated active owner session and verify the owner's current password against the owner account, inside a `BEGIN IMMEDIATE` transaction. The actor's role, status, session revocation/expiry, device state, and credential version are rechecked in the transaction. Passwords are never included in responses, logs, or audit details. Role changes use the A1 `credential_version` trigger to invalidate prior target sessions. Deactivation revokes target sessions and device associations; reactivation restores associations only to active devices and never restores old sessions. The owner's own session remains valid unless its own credentials/session are independently revoked.

Responses: `200` success; `400` invalid role/status values; `401` reauthentication failure or invalidated session; `403` non-owner or forbidden self-change; `404` target not found; `409` last-active-owner invariant conflict; `422` malformed JSON/schema/type validation; `503` database operation unavailable. Unauthenticated requests fail with `401`.


## A2 owner recovery (local only)

No HTTP endpoint accepts a recovery key or performs owner recovery. During `POST /api/v1/bootstrap/owner`, the successful one-time response includes `recovery_key`; the bootstrap client must show it once and must not log or persist it. Bootstrap accepts loopback, same-origin, or the exact HTTPS origin configured in `SOLARMINER_CORS_ORIGINS`, and always requires the local one-time token, a fresh timestamp/nonce and an Ed25519 device proof. The value is generated from 32 CSPRNG bytes, displayed as `SMR1-` plus grouped Base32, and only a domain-separated SHA-256 verifier is persisted. Because the key has 256 bits of entropy, a slow password KDF is not required for this verifier; human-chosen passwords continue to use Argon2id.

Local commands are installed as `/usr/bin/solarminer-gateway`:

- From a root shell, `solarminer-gateway recovery-setup` creates or rotates the key for an active owner who can reauthenticate with the current password and prove possession of an associated active Ed25519 device. Use after upgrading an existing A1b database that predates recovery-key provisioning.
- From a root shell, `solarminer-gateway recovery` consumes the offline key once, changes the owner password, invalidates sessions, revokes the owner's old device associations, registers a new device after a fresh Ed25519 challenge proof, and rotates the recovery key.
- From a root shell, `solarminer-gateway emergency-reset` is an independent OS-root-only path when the recovery key is lost. It requires an explicit confirmation and a protected, integrity-checked SQLite backup before mutation. It preserves the database and unrelated user data; it is not a factory reset.

Each command requires a TTY, root privileges, and a provably stopped `solarminer-gateway.service`. Recovery keys and passwords are read interactively without echo and are never accepted as command-line arguments or environment variables. The challenge message signed by a new device is the exact UTF-8 text printed by the command, beginning `SOLARMINER-GATEWAY-DEVICE-PROOF-V1`, followed by the purpose (`recovery` or `emergency`), owner UUID, and 64-character lowercase hex challenge, each on a separate line. Setup proofs also include the existing device UUID before the challenge.

A successful recovery invalidates all prior owner sessions and increments `credential_version`. A role removal from owner or account deactivation consumes any active recovery key. The new recovery key is displayed only after commit. If the commit succeeds but terminal delivery fails, the plaintext key cannot be reconstructed from the stored verifier; the operator must use the emergency procedure to rotate it again. Audit success events are in the same transaction as the protected mutation; failed attempts are recorded separately without secret material.

## CODE 02 v0.6.18 — login de novo dispositivo

`POST /api/v1/auth/password-device-login` accepts `username`, `password`, PEM Ed25519 `public_key_pem`, a fresh `timestamp`/`nonce` and a device signature. The signature covers UTF-8 `PASSWORD-DEVICE-LOGIN\n{username}\n{timestamp}\n{nonce}\n{sha256(password UTF-8)}\n{sha256(public-key SPKI DER)}`. The Gateway requires a valid active account, verifies the signature and password, then associates the public key with that account and issues a temporary bearer session in one SQLite transaction. Existing keys can be used only when the key is already active and associated with the same account. Authentication failures do not create device rows. Nginx throttles requests per source IP; the app limits attempts by both source IP and a keyed hash of the username, so the account limit is shared across source IPs without storing usernames in the attempt table. Plaintext passwords are neither persisted nor logged; the request must use validated HTTPS.

The app listens on TCP 8443 on the Gateway interfaces so the LAN endpoint `https://<gateway-lan-ip>:8443` works. Nginx listens on TCP 80/443 and proxies the Tailscale HTTPS endpoint to the app. The default service does not require router port forwarding. Direct LAN-IP HTTPS uses the Gateway's local certificate and requires browser trust; Tailscale uses a public certificate for the MagicDNS `*.ts.net` name.

## CODE 02 v0.6.19 — Tailscale Owner access

| Method | Path | Access |
|---|---|---|
| GET | `/api/v1/system/tailscale` | Owner; returns only installed/connected state, Gateway MagicDNS name, detected/configured HTTPS URL, and certificate readiness |
| PUT | `/api/v1/system/tailscale` | Owner; accepts exactly `{"endpoint":"https://host.tailnet.ts.net"}` or `{"endpoint":null}` to clear the manual setting |

The configured URL must be HTTPS on the standard port, have a `*.ts.net` hostname, and contain no credentials, path, query, or fragment. The Gateway stores the Owner's endpoint selection in `system_state`; it never fetches that URL. The privileged status helper invokes only the fixed `tailscale status --json` command and returns a sanitized subset, never auth keys or peer details. `PUT` is allowed by the exact-origin PWA CORS policy.

## CODE 02 v0.6.9 — verificação de atualização por repositório

| Método | Caminho | Acesso |
|---|---|---|
| GET | `/api/v1/system/update/source` | Owner; devolve a origem guardada e as origens exatas da allowlist administrativa |
| POST | `/api/v1/system/update/check` | Sessão autenticada, papel Owner; recebe exatamente `{"repository_url":"https://github.com/owner/repository"}`; guarda a escolha apenas depois da validação da allowlist |
| GET | `/api/v1/system/update/check` | Sessão autenticada com `manage_gateway`; verifica a origem fixa configurada pelo administrador (compatibilidade) |
| GET | `/api/v1/system/update/status` | Sessão autenticada com `read`; estado da operação |
| POST | `/api/v1/system/update/apply` | Owner, confirmação explícita e versão coincidente; inicia preflight/backup/staging/ativação/health check/rollback |

O POST valida URL canónico HTTPS de raiz `github.com/{owner}/{repository}` e procura uma correspondência exata no ficheiro administrativo root-owned `/etc/solarminer/update-sources.json` (ou no caminho definido por `SOLARMINER_UPDATE_SOURCE_ALLOWLIST`). Não aceita credenciais, query, fragmento, subcaminhos, hosts alternativos nem repositórios privados. Depois de uma verificação Owner válida, o URL selecionado fica persistido em `system_state`. A PWA carrega essa seleção e permite mudá-la apenas para outra entrada já aprovada na mesma allowlist root-owned. O serviço `solarminer-update-check-daily.timer` usa a seleção persistida (ou a primeira entrada aprovada durante a instalação inicial) para verificar diariamente; valida manifesto, assinatura, compatibilidade e pacote, mas nunca aplica a atualização. O Owner continua a confirmar a aplicação pela rota `POST /api/v1/system/update/apply`.

O ficheiro tem o formato:

```json
{
  "repositories": {
    "https://github.com/owner/repository": {
      "manifest_url": "https://github.com/owner/repository/releases/latest/download/solarminer-release.json",
      "manifest_origins": ["https://github.com", "https://release-assets.githubusercontent.com"],
      "package_origins": ["https://github.com", "https://release-assets.githubusercontent.com"]
    }
  }
}
```

A lista de origens é configurada pelo administrador, contém apenas origens HTTPS e tem limites de tamanho/quantidade. Redirecionamentos do manifesto e pacote só são seguidos se o destino permanecer numa origem respetiva permitida. O manifesto tem de passar a validação Ed25519 com a chave já provisionada no Gateway; o pacote é validado por hash, tamanho, versão, arquitetura, dependências e preflight antes de ficar `VERIFIED`. Não há clone/pull, execução de scripts do repositório ou instalação de dependências arbitrárias. A PWA não recebe segredos de GitHub. A verificação manual não instala a atualização: exige POST Owner separado e confirmação explícita. O serviço diário pode enfileirar automaticamente apenas depois de todas as validações e do preflight independente passarem. URL/origem/manifesto/assinatura inválidos são rejeitados antes de qualquer alteração do sistema e ficam refletidos no estado/auditoria sem credenciais.

## CODE 02 — Connector Manager v0.6.0

The CODE 02 routes are authenticated with existing Gateway sessions and RBAC. See `CODE02_CONNECTOR_MANAGER.md` for payload examples, signature trust, bounded discovery and limitations.

- `GET /api/v1/connectors/catalog` — returns catalog only after Ed25519 signature and schema verification.
- `GET /api/v1/connectors` — installed connector records.
- `POST /api/v1/connectors/{id}/install` — JSON `{"confirmed": true}`; requires `manage_gateway`.
- `POST /api/v1/connectors/{id}/update` — JSON `{"confirmed":true}`; reconciles metadata after a trusted Debian package upgrade, not a code downloader.
- `PATCH /api/v1/connectors/{id}/config` — JSON `{"config":{"timeout_seconds":1.5}}`; only supported non-secret settings are accepted.
- `POST /api/v1/connectors/{id}/test` — JSON `{"host":"192.168.1.20","port":4028}`; TCP connect/close only, no application payload.
- `DELETE /api/v1/connectors/{id}/remove` — JSON body `{"confirmed": true}`; requires `manage_gateway`.
- `POST /api/v1/devices/discover` — JSON `{"cidr":"192.168.1.0/30","ports":[80,443],"timeout_seconds":0.25}`; private network only, bounded scan, no protocol payload.
- `GET /api/v1/devices/discovered` — discovered TCP endpoints.
- `GET /api/v1/devices/{discovered_id}/capabilities` — only reports transport reachability evidence; does not claim device capabilities.

## CODE 02 v0.6.5 browser authentication

The browser client uses Web Crypto Ed25519 with a non-exportable private `CryptoKey`, stores the key in IndexedDB, and keeps bearer sessions only in memory. The exact additive pairing/login flow, endpoint payloads, CORS development allowlist and residual XSS/TLS risks are documented in `CODE02_V065_AUTH.md`. No token refresh endpoint was added; after expiry, login is repeated with the password and associated device signature.


## CODE 02 v0.6.6 — presence (additive)

| Method | Path | Access |
|---|---|---|
| POST | `/api/v1/presence/heartbeat` | Existing authenticated session with `read`; user/device derived from session, request body ignored/not used |
| GET | `/api/v1/presence/me` | Existing authenticated session with `read`; returns only the caller's user/device presence |

`POST /api/v1/presence/heartbeat` creates or refreshes the caller's presence for 120 seconds. Persisted writes are throttled to at most one every five seconds per user/device pair. The Gateway generates `last_seen_at` and `expires_at`. Response states are `online`; `GET /api/v1/presence/me` returns `unknown` when no record exists, `online` before expiry, and `offline` after expiry. `connection_method` is always `unknown` in this increment; the client cannot claim LAN/REMOTE. Presence transitions are audited. Authenticated logout removes the current user/device presence. No API claims physical presence.

## v0.6.23 — correção da allowlist do repositório oficial

- A comparação da allowlist do repositório GitHub usa URLs canónicos sem distinguir maiúsculas/minúsculas, compatível com `TheSolarMiner` guardado pelo instalador.
- Entradas duplicadas que diferem apenas em maiúsculas/minúsculas continuam bloqueadas.

## v0.6.21 — correção do proxy HTTPS para LAN e Tailscale

- O Nginx valida o certificado TLS interno do backend com o nome DNS `localhost`, que está incluído no SAN do certificado provisionado no Gateway.
- A validação TLS entre Nginx e a API permanece ativa nos endpoints LAN e Tailscale.

## v0.6.20 — autorização Tailscale iniciada pela PWA Owner

- `POST /api/v1/system/tailscale/connect` é exclusivo do Owner. Executa o helper fixo `solarminer-tailscale-connect` e devolve apenas um URL de autorização validado `login.tailscale.com` quando a aprovação está pendente.
- A API encaminha a chamada pelo broker root-owned, que só executa o helper fixo de Tailscale e devolve apenas o URL de autorização validado. Não usa sudoers, não devolve a saída bruta do comando e não escreve o URL temporário nos logs nem no registo de auditoria.
- O Owner abre o link e aprova o Gateway na conta Tailscale. A inclusão do dispositivo na conta não pode ser feita silenciosamente pelo Gateway.

## v0.6.8 — integração PWA e convites QR

- `GET /api/v1/status`, `GET /api/v1/energy/categories` e `GET /api/v1/energy/equipment` são usados pela PWA depois de autenticação; não existem novos endpoints de telemetria ou histórico nesta versão.
- `POST /api/v1/invites` continua Owner-only. A resposta inclui `qr_payload` e `qr_svg`; o SVG é gerado localmente e não usa serviço externo. O token de convite é segredo de utilização única.
- `GET /api/v1/invites` não devolve o token nem o hash do token.
- `POST /api/v1/invites/{invite_id}/revoke` revoga apenas convites pendentes.
- `POST /api/v1/presence/heartbeat` e `GET /api/v1/presence/me` exigem sessão autenticada. O estado indica atividade recente da sessão, não presença física nem caminho LAN/REMOTO.
- `POST /api/v1/system/update/apply` permanece HTTP 503 até a ativação de release, recuperação independente, migração e rollback serem integrados e comprovados de ponta a ponta.
