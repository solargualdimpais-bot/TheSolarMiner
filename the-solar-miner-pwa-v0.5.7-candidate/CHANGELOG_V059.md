# The Solar Miner PWA v0.5.9 (Home Live e navegação por equipamento)

## Incremento v0.5.9

- Áreas autenticadas passam a usar dados do Gateway; vistas sem integração física mostram estados vazios claros em vez de cartões demonstrativos.
- A Home oferece fotografia e configuração da casa (nome e cidade), cartão meteorológico e produção FV com histórico e previsão fornecidos pelo Gateway.
- Favoritos podem apontar para equipamentos Tuya configurados; interruptores e níveis suportados enviam comandos individuais autenticados como Owner.
- A área Owner permanece dividida por secções e cada equipamento mantém configuração e ação próprias.
- Os ficheiros PWA integrados no pacote Debian são sincronizados com esta versão. O service worker recebe uma cache nova.

## Limites

A fotografia e os metadados de favorito são guardados no browser atual. Controlo de nível só funciona quando o datapoint e a escala estão definidos no Gateway. Deye permanece identificado como não validado fisicamente até comissionamento.
