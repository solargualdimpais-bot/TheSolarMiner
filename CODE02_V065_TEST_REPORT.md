# CODE 02 v0.6.5 — relatório de testes

## Baseline antes de editar

- CODE02 v0.6.4 ZIP original: 163 testes aprovados com `PYTHONPATH=src pytest -q`.
- PWA v0.1.0 ZIP original: 12 testes aprovados com `npm test`.
- Os quatro hashes de referência do utilizador foram recalculados e coincidiram.

## Resultado final v0.6.5 / PWA v0.2.0

| Alvo | Método | Resultado |
|---|---|---:|
| Backend v0.6.5, fonte/ZIP final extraído | 8 ficheiros de teste executados em processos separados | **173 passed no total** |
| PWA v0.2.0 ZIP final extraído | `npm test` | **19 passed, 0 failed** |
| Módulos do Debian extraído, sem instalação | testes focados `test_browser_pairing.py` + `test_code02_v064.py` | **15 passed, 2 warnings** |
| Pacote Debian | duas compilações independentes + `cmp` | byte-idênticas |
| ZIP backend / PWA | `unzip -t` | passou para ambos |

A suite backend foi executada por ficheiro para garantir que cada invocação terminava normalmente. Uma execução monolítica também imprimiu `173 passed`, mas por vezes deixou o processo de teste sem terminar depois do resumo; por rigor, o resultado final contabilizado é a soma das oito execuções independentes, todas aprovadas. A execução completa com módulos extraídos do `.deb` apresentou o mesmo comportamento de encerramento; por isso, só os 15 testes focados são contabilizados como conclusão limpa para esse alvo.

## Testes novos de autenticação

- Emissão de código requer sessão autenticada `manage_devices`; username de destino tem de existir e estar ativo.
- Código aleatório de 256 bits, expiração 60–600 s, uso único, persistência apenas do hash.
- Assinatura Ed25519, timestamp, chave pública e MAC alterados/inválidos são rejeitados.
- Chave inválida e timestamp fora da janela são rejeitados.
- Pairing cria dispositivo e associação; login com a chave associada permite GET de leitura; logout invalida a sessão.
- Node Web Crypto gera chave não exportável e assina `PAIR`; o Gateway Python valida a assinatura. O canonical `LOGIN` assinado via Web Crypto também é validado pelo Gateway.
- Fluxo HTTP de loopback executa pairing → login → GET `/api/v1/energy/equipment` → logout.
- Nenhum teste envia comandos físicos.

## Interpretação das evidências

O teste HTTP completo usa o código cliente JavaScript/Web Crypto em Node contra Uvicorn local limitado a loopback. É evidência de interoperabilidade de protocolo e de fluxo API, mas **não** é um ensaio de interface num browser gráfico nem no Safari/iPhone. Os dois warnings do backend estão associados ao stack Uvicorn/WebSocket de teste; não foram ocultados para alterar o resultado.
