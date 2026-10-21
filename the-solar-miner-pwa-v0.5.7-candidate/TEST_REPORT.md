# PWA v0.5.4 — Relatório de testes

## Resultados executados
- `node --check app.js`: aprovado.
- `node --check workspace-ui.js`: aprovado.
- `npm test`: **63 testes aprovados, 0 falhas**. Foram acrescentados testes estáticos para navegação mobile direta, migração de preferências antigas e estratégia de persistência IndexedDB.
- HTTP smoke test local: `index.html` respondeu HTTP 200.
- ZIP de publicação e ZIP de código-fonte validados com `unzip -t`.
- SHA-256 gerado para os dois ZIPs e documentos entregues.

## Limitações
- Os testes de IndexedDB são verificações automatizadas do código/contrato de integração; não simulam um Safari real com quota de armazenamento.
- A tentativa de execução de Chromium headless não terminou dentro do limite do ambiente. Não há validação visual interativa concluída.
- Não foi testado num iPhone/Safari real.
- Não foram testados o Gateway real, utilizadores reais, meteorologia externa nem dispositivos físicos.

Nenhum teste falhou na suite automatizada; isso não deve ser interpretado como certificação de browser ou de integração com o Gateway.
