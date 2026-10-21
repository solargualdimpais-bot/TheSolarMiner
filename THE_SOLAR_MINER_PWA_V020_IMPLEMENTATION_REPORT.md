# The Solar Miner PWA v0.2.0 — relatório de implementação

## Implementado

- Mantidas as seis áreas e a interface responsiva da v0.1.0.
- Emparelhamento por código de utilização única emitido pelo Gateway para um username ativo, por sessão `owner`/`admin` com `manage_devices`.
- Geração de par Ed25519 com Web Crypto; chave privada não exportável; exportação só da chave pública SPKI; assinatura executada no cliente.
- CryptoKey privada persistida no IndexedDB, com validação para recusar chave privada exportável. O token bearer não é persistido em localStorage, IndexedDB ou Cache API.
- Login assinado compatível com o canonical existente, sessão em memória, leitura autenticada, logout e fluxo para emitir código de emparelhamento a partir de uma sessão administrativa.
- Erros claros para falta de código, chave/algoritmo não suportado, timeout, falha de rede, HTTP 401/403 e sessão expirada.
- Botão explícito para remover a identidade local antes de emparelhar novamente; a remoção local não substitui a revogação administrativa do Gateway.
- Modo `SIMULATED` permanece isolado e não inicia autenticação. Nenhum comando de equipamento foi adicionado.

## Testes

- Baseline v0.1.0: 12 testes aprovados.
- v0.2.0: 19 testes aprovados.
- Testes do backend confirmam interoperabilidade de assinaturas Web Crypto com a validação Ed25519 em Python e um fluxo HTTP completo em loopback.

## Não validado

Não houve ensaio em Safari/iOS, não se confirmou persistência de CryptoKey no IndexedDB do iPhone, nem confiança de certificado, DNS local, Tailscale ou ligação a hardware. A chave não exportável não impede XSS na mesma origem.
