# Relatório de testes — CODE02 v0.6.7 parcial

## Base e isolamento

- SHA-256 CODE02 v0.6.6 recebido: `9003e772dbd77b556759c2e8f66a44b0446bd83cda8bfb36f4ef4e1f2ad129fd` — confirmado antes das alterações.
- SHA-256 PWA v0.5.4 recebido: `cbaf7f387e5a74906ec3b515633fbaa2528f3a960b1cf0b956dd233b4d9a5837` — confirmado antes das alterações.
- Testes locais usam TestClient, SQLite temporário e chaves Ed25519 geradas para testes.
- Nenhum Gateway físico, serviço de produção ou Tailscale real foi contactado.

## Resultados backend

- `python3 -m py_compile src/solarminer_gateway/app.py src/solarminer_gateway/updates.py`: aprovado.
- Grupo principal (browser pairing, CODE02 v0.6.1–v0.6.4, connectors, gateway, presence e novos testes v0.6.7): **160 passed**.
- `tests/test_recovery.py`, executado separadamente: **28 passed**.
- Total dos grupos executados separadamente: **188 passed**, sem duplicação entre os dois grupos.
- Uma execução agregada `PYTHONPATH=src python3 -m pytest -q` excedeu o limite de execução e não foi registada como sucesso agregado. Por isso, os resultados são apresentados por grupos, não como um único comando global aprovado.

Novos testes cobrem criação/listagem/revogação de convites, resgate de utilização única, criação de utilizador/dispositivo/sessão, role allow-list, falha segura quando identidade do Gateway não está configurada, assinatura do desafio Gateway e validação de manifesto assinado/adulterado.

## Resultados PWA

- `node --test tests/*.test.js`: **65 passed, 0 failed**. O subconjunto `gateway-connection.test.js` teve **29 passed, 0 failed**.
- Os testes são Node.js locais. Não são testes de Safari/iPhone.

## Simulado / não testado

- Testes de falhas da atualização são testes de validação de funções; não demonstram instalação/ativação real.
- Não foi executado `kill -9` de uma atualização em ativação, pois a ativação e o mecanismo independente de recuperação não foram implementados.
- Não foram testados manifestos/pacotes num repositório remoto real.
- Não foi criado nem inspecionado um `.deb` de v0.6.7.
- Safari/iPhone, Tailscale real e Gateway físico: `NÃO_VALIDADO`.
