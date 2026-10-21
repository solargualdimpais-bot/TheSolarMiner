# The Solar Miner PWA v0.2.0 — relatório de testes

## Baseline

A PWA v0.1.0 original passou 12 testes antes de alterações.

## Resultado v0.2.0

`npm test`: **19 passed, 0 failed**.

Cobertura:
- seis áreas e fixtures sempre marcados `SIMULATED`;
- estados de leitura ausente/desatualizada e origem dos dados;
- validação HTTPS fora de loopback;
- timeout, erro de rede, 401 e 403 no cliente API;
- service worker não cacheia respostas `/api/v1/` e inclui o módulo `auth-client.js` como recurso estático;
- geração Ed25519 com chave privada não exportável, PEM público SPKI e digest SHA-256;
- assinatura Web Crypto e rejeição de mensagem alterada;
- formato canónico exato de `PAIR` e `LOGIN`;
- emparelhamento sem envio da chave privada;
- validação local de código/MAC antes de rede;
- emissão de código por sessão bearer administrativa;
- logout e recusa de persistência de chave privada exportável.

A suite do backend acrescenta interoperabilidade com o validador Python e o fluxo de loopback HTTP. Isto não é um teste visual no Safari/iPhone nem valida a persistência de CryptoKey no IndexedDB do iOS.

## Limitações

Não houve ensaio em browser gráfico, iPhone/Safari, HTTPS de produção, DNS local, Tailscale, Debian físico ou equipamento real. A chave não exportável não protege contra XSS na mesma origem. Nenhum comando físico está implementado.
