# CODE 02 v0.6.5 — emparelhamento Ed25519 e autenticação da PWA

## Classificação

- `IMPLEMENTED_AND_TESTED_LOCALLY`: emissão de código de emparelhamento por sessão com `manage_devices`; código aleatório de utilização única, validade limitada; criação de dispositivo/associação numa transação SQLite; assinatura Ed25519 no browser; login no formato existente; sessão bearer limitada e mantida apenas em memória pela PWA; leitura autenticada; logout/revogação; testes negativos e interoperabilidade Node WebCrypto ↔ `cryptography` do Gateway.
- `NOT_VALIDATED_ON_TARGET_HARDWARE`: instalação no Debian dedicado, permissões systemd, comportamento de reinício real, acesso por rede doméstica e Tailscale.
- `BLOCKED_NO_TARGET_ENV`: validação no iPhone/Safari físico e certificados/DNS de produção.

## Fluxo de emparelhamento

1. Um utilizador `owner` ou `admin` com sessão válida solicita `POST /api/v1/devices/pairing-codes` para um username ativo.
2. O Gateway gera um código aleatório de 256 bits, devolve-o uma única vez e persiste apenas SHA-256 do código. A validade predefinida é 300 segundos; o intervalo aceite é 60–600 segundos.
3. No browser novo, a PWA gera uma chave Ed25519 via Web Crypto com a chave privada não exportável. Exporta apenas a chave pública SPKI PEM.
4. A PWA assina o texto UTF-8 exato `PAIR\n{pairing_code}\n{sha256(public_key_spki_der)}\n{MAC_UPPERCASE}\n{timestamp}\n{nonce}`. A assinatura é hexadecimal de 128 caracteres.
5. `POST /api/v1/devices/pair` valida timestamp (±300 segundos), nonce, chave Ed25519, assinatura, código ainda válido e utilizador ativo. A criação do dispositivo, associação ao utilizador, consumo do nonce, consumo do código e auditoria são confirmados numa transação SQLite.
6. A PWA inicia sessão com o contrato existente: `POST /api/v1/auth/login`, password e assinatura Ed25519 do texto `LOGIN\n{username}\n{device_id}\n{timestamp}\n{nonce}`. O token é opaco, limitado a 8 horas, armazenado apenas por hash no servidor e apenas em memória na PWA.
7. A PWA consulta `GET /api/v1/health`, `GET /api/v1/energy/categories` e `GET /api/v1/energy/equipment`; os endpoints de leitura protegidos continuam a exigir `read`.
8. Logout invoca `POST /api/v1/auth/logout`; revogação administrativa do dispositivo continua em `POST /api/v1/devices/{device_id}/revoke`.

O código de emparelhamento é uma autorização temporária para associar uma chave a um utilizador específico; não concede um papel novo nem privilégios administrativos. MAC continua como metadado declarado, não verificado fisicamente.

## Endpoints aditivos

| Método | Endpoint | Autorização | Efeito |
|---|---|---|---|
| POST | `/api/v1/devices/pairing-codes` | `manage_devices` | Emite código de utilização única para username ativo; body `{"username":"viewer","expires_in":300}` |
| POST | `/api/v1/devices/pair` | Código temporário + prova Ed25519 | Consome código e associa dispositivo ao utilizador; body inclui `pairing_code`, `mac`, `public_key_pem`, `timestamp`, `nonce`, `signature` |
| POST | `/api/v1/auth/login` | Password + assinatura de dispositivo associado | Sem alteração incompatível; resposta inclui aditivamente `device_id` |

O endpoint de emissão não devolve o código novamente e não regista o valor secreto em logs/auditoria. Os códigos expirados/consumidos são limpos durante a emissão seguinte. Não há endpoint de refresh de sessão; a PWA volta a autenticar-se com password e assinatura Ed25519 após expiração. Não foi introduzido um bearer permanente.

## Chave do browser e riscos residuais

A chave privada é gerada como `CryptoKey` não exportável e persistida por structured clone em IndexedDB; a PWA recusa explicitamente persistir chaves marcadas como exportáveis. O token de sessão nunca é guardado em IndexedDB, localStorage, Cache API ou service worker. O service worker só cacheia recursos estáticos e não intercepta `/api/v1/`.

IndexedDB não é uma fronteira contra JavaScript malicioso na mesma origem. XSS ou comprometimento dos ficheiros servidos pode usar a chave enquanto a origem estiver comprometida. HTTPS com certificado confiável, integridade da origem, CSP/mitigação XSS e atualização segura continuam requisitos operacionais. O código atual não afirma que a chave seja inviolável.

## HTTPS e desenvolvimento

A PWA permite HTTP apenas em loopback (`localhost`/`127.0.0.1`) para desenvolvimento. O CLI de produção do Gateway recusa iniciar sem certificado e chave TLS. A PWA é servida pelo mesmo origin em produção, pelo que CORS não é necessário. Para desenvolvimento cross-origin, definir `SOLARMINER_CORS_ORIGINS` com a lista explícita e exata de origens de desenvolvimento; por omissão não são permitidas origens adicionais. Não usar `*` nem habilitar credenciais CORS.

## Limitações deliberadas

- O login existente assina username, device ID, timestamp e nonce; não foi alterado para não quebrar clientes CODE 01/CODE 02. A password e os dados da sessão dependem de TLS em trânsito.
- Não existe endpoint de refresh. A sessão expira e a PWA pede nova autenticação.
- A chave MAC permanece declarada e a autenticação não demonstra a identidade física do equipamento.
- Não foi implementado controlo de equipamentos. Os endpoints e testes desta fase limitam-se à identidade, autorização e leitura.
- A validação criptográfica foi executada em Node Web Crypto e no backend local. Não equivale a ensaio em Safari/iOS nem a validação de certificado/DNS no equipamento-alvo.

## HTTP response protections

Gateway responses set `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `X-Frame-Options: DENY`. API responses use `Cache-Control: no-store`. PWA resources receive a Content Security Policy that disallows inline scripts, plugins and framing; `style-src 'unsafe-inline'` remains necessary for the current UI's generated style attributes. This CSP is defense in depth, not a substitute for output escaping and XSS review.
