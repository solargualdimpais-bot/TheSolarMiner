# CODE 02 v0.6.5 — relatório de implementação

## Resumo

Foi criada uma versão incremental real a partir do código-fonte v0.6.4 verificado. A API v1 continua a reportar `0.6.0` por compatibilidade; a versão do pacote Debian e da árvore fonte é `0.6.5`.

## Implementado

- Endpoint aditivo `POST /api/v1/devices/pairing-codes`, protegido por `manage_devices`, que só emite código para um username ativo e exige sessão válida.
- Código aleatório de 256 bits, uso único, TTL configurável entre 60 e 600 segundos (predefinição 300). Só o SHA-256 é persistido; o segredo é devolvido uma vez.
- Endpoint aditivo `POST /api/v1/devices`, sem alterações incompatíveis, continua disponível para provisionamento administrativo antigo.
- Endpoint aditivo `POST /api/v1/devices/pair`: valida chave pública Ed25519, assinatura, timestamp ±300 s, nonce, código ainda válido e utilizador ativo. Cria dispositivo, associação, nonce, consumo do código e evento de auditoria na mesma transação SQLite.
- O canonical de emparelhamento é `PAIR\n{pairing_code}\n{sha256(public_key_spki_der)}\n{NORMALIZED_MAC}\n{timestamp}\n{nonce}`.
- O login existente conserva o canonical `LOGIN\n{username}\n{device_id}\n{timestamp}\n{nonce}`. A resposta acrescenta `device_id` sem retirar campos anteriores. A sessão permanece limitada a 8 horas, armazenada por hash no Gateway e revogável via logout ou revogação do dispositivo.
- PWA v0.2.0 usa Web Crypto Ed25519, chave privada não exportável, IndexedDB para a CryptoKey, token de sessão apenas em memória, login e logout reais e leitura dos endpoints existentes.
- A PWA permite ao utilizador `owner`/`admin` autenticado emitir código e ao novo browser consumi-lo. A identidade local pode ser removida explicitamente para voltar a emparelhar; isso não revoga o dispositivo no servidor.
- O service worker continua a cachear apenas recursos estáticos e ignora `/api/v1/`. As respostas API recebem `Cache-Control: no-store`. Foram adicionados headers CSP e proteções básicas aos recursos estáticos; o CSP permite estilos inline porque a UI atual ainda gera alguns atributos `style`.
- CORS de desenvolvimento é opt-in e por origens exatas através de `SOLARMINER_CORS_ORIGINS`; não há wildcard e `allow_credentials` é falso.

## Compatibilidade e limites

- Sem endpoint de refresh; após 8 horas a PWA volta a autenticar com password e assinatura da chave associada.
- A assinatura de login não inclui a password no canonical por compatibilidade com clientes existentes; TLS é obrigatório para proteger credenciais em trânsito.
- MAC continua declarado, não verificado fisicamente.
- Nenhum endpoint de controlo foi adicionado; não foram feitas escritas Modbus nem comandos físicos.
- A chave não exportável e IndexedDB não defendem contra XSS/JavaScript malicioso na mesma origem. A origem HTTPS, integridade do código e proteção contra XSS são requisitos.

## Classificação

- `IMPLEMENTED_AND_TESTED_LOCALLY`: emparelhamento, login assinado, sessão, leitura e logout, incluindo interoperabilidade Node Web Crypto ↔ backend Python e fluxo HTTP completo em loopback.
- `NOT_VALIDATED_ON_TARGET_HARDWARE`: instalação e operação no Debian dedicado, systemd, TLS, DNS local e Tailscale.
- `BLOCKED_NO_TARGET_ENV`: Safari/iOS real e validação no iPhone; equipamento físico não disponível/ensaiado.
