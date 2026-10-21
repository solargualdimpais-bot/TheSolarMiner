# CODE 02 v0.6.5 — validação local

## Baseline preservada

- CODE02 v0.6.4 original: 163 testes aprovados a partir do ZIP de referência, antes de editar a cópia de trabalho.
- PWA v0.1.0 original: 12 testes aprovados a partir do ZIP de referência, antes de editar a cópia de trabalho.

## v0.6.5

- Backend fonte: `PYTHONPATH=src pytest -q` — 173 testes aprovados no resultado final, incluindo os 163 testes anteriores e 10 novos testes de emparelhamento/interop.
- PWA v0.2.0: `npm test` — 19 testes aprovados, incluindo geração de chave Ed25519 não exportável, assinatura do canonical `PAIR` e `LOGIN`, timeout/erros, sessão e ausência de armazenamento do token.
- Interoperabilidade: Node Web Crypto gera uma chave não exportável e assina a mensagem de emparelhamento que o Gateway Python valida; outro teste verifica a assinatura `LOGIN` gerada via Web Crypto contra o endpoint real. Um teste de integração adicional inicia Uvicorn apenas em loopback e executa browser-client → pairing → login → GET de leitura → logout por HTTP local.
- Pacote Debian: duas compilações independentes byte-idênticas; conteúdo inspecionado sem instalar o pacote.
- ZIP final: verificação de integridade e repetição da suite após extração do ZIP final.
- Debian extraído: suite executada com `PYTHONPATH` apontado aos módulos extraídos do `.deb`, sem instalar o pacote.

## Cobertura de segurança adicionada

- Emissão de código requer sessão autenticada com `manage_devices`; username de destino tem de estar ativo.
- Código aleatório de 256 bits, expiração 60–600 s, uso único, persistência apenas do hash.
- MAC e chave pública são incluídos na assinatura; alteração do corpo causa falha de assinatura.
- Chave inválida, timestamp fora da janela, código expirado/consumido e dispositivo/chave já registados são recusados.
- Criação de dispositivo, associação, nonce, consumo do código e auditoria são uma única transação SQLite.
- Login mantém o canonical anterior `LOGIN\n{username}\n{device_id}\n{timestamp}\n{nonce}` e devolve sessão limitada a 8 horas.
- Leitura sem sessão, logout e restrições RBAC são exercitados.
- Nenhum teste envia comandos físicos ou escreve Modbus.

## Limites

Estes testes são locais, incluindo a integração HTTP de loopback. Não validam Safari/iOS, certificado confiável no iPhone, DNS local, Tailscale, Debian físico, systemd/cgroups ou equipamento real. O servidor de teste HTTP é limitado a `127.0.0.1` e não é uma configuração de produção.
