# Gateway 0.6.178

- Identifica as leituras locais Deye pelo MAC único do inventário quando disponível, mantendo a mesma identidade após uma mudança de IP.
- Reassocia histórico legado baseado em IP apenas quando MAC, modelo e endereço Modbus correspondem sem ambiguidade; mantém os registos antigos como referências arquivadas.
- Mantém o histórico da Deye Cloud associado ao `stationId`; o motor junta-o automaticamente ao histórico local apenas quando existe uma única estação cloud e um único Deye local. Com vários inversores, os dados da estação ficam separados.
- Inclui testes para identidade estável entre IPs, migração do histórico e preservação do comportamento sem MAC.
- Mantém a PWA integrada 0.5.126; não foram necessárias alterações de interface.
