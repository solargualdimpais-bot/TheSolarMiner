# CODE 02 v0.6.4 — implementação incremental

## Alterações reais nesta versão

- O teste TCP de `tcp-readonly-probe` passou a chamar `tcp_probe` através de `ConnectorWorkerRuntime`; o processo API não abre o socket de destino para este teste.
- A descoberta de rede limitada também usa um worker supervisionado. CIDR, portas e limites são validados no Gateway antes de iniciar a operação. Se o worker falhar, a descoberta falha explicitamente e não devolve um scan parcial como se estivesse completo.
- O worker devolve `TCP_REACHABLE`/`TCP_UNREACHABLE` como evidência de transporte, não identifica protocolo nem capacidades e não envia payload de aplicação.
- `AtomicReleaseStore.recover_interrupted()` foi acrescentado para reconciliar de forma conservadora o ponteiro de release e o journal após reinício do processo. Os testes simulam um ponteiro não confirmado e verificam o rollback para a versão anterior.
- A PWA The Solar Miner é servida na mesma origem HTTPS do Gateway por rotas estáticas explícitas; os endpoints API existentes mantêm a ordem e os comportamentos de autorização/404. O pacote Debian inclui os recursos estáticos em `/usr/share/solarminer/pwa`.
- Os artefactos CODE02 v0.6.3 e todos os artefactos históricos continuam preservados; esta versão foi extraída e alterada num diretório de trabalho separado.

## Limites importantes

- A API de atualização existente continua a reconciliar metadados após atualização confiável do pacote Debian; não descarrega nem executa código. `AtomicReleaseStore` e a recuperação do journal continuam a ser primitivas locais, não uma transação integrada entre ficheiros, SQLite, unidades systemd e health checks dos serviços.
- `recover_interrupted()` deve ser chamado por um orquestrador de atualização futuro; não é executado automaticamente no arranque do Gateway nesta versão.
- O subprocesso do worker é supervisionado, mas em desenvolvimento corre com o mesmo UID do Gateway. Contas dedicadas, ACLs do socket e isolamento systemd efetivo não foram aplicados nem validados num Debian físico.
- A sondagem e descoberta são apenas TCP connect/close. Não identificam equipamento, firmware, protocolo ou capacidades.
- Deye permanece FC03 exclusivamente de leitura. Sem hardware e documentação validada para modelo/firmware concretos, não são declarados valores ou escalas de registos reais validados.

## Classificação

- `IMPLEMENTED_AND_TESTED_LOCALLY`: TCP probe e descoberta executados através do worker; recuperação local do ponteiro/journal; testes de falha e regressão.
- `NOT_VALIDATED_ON_TARGET_HARDWARE`: enforcement systemd, identidade de serviço dedicada, ACLs, limites de recursos/rede e recuperação após falha no Debian-alvo.
- `BLOCKED_NO_TARGET_ENV`: validação operacional no Debian dedicado e validação de equipamentos físicos.
- `NOT_IMPLEMENTED`: orquestração end-to-end de atualização envolvendo API, SQLite, serviços systemd e health checks pós-ativação; autenticação browser-native de emparelhamento inicial para a PWA.

## Testes

A suite preservada de v0.6.3 foi verificada a partir do ZIP original: 158 testes passaram. A suite v0.6.4 acrescenta 5 testes, incluindo política do worker, recuperação de ponteiro após reinício simulado e entrega dos recursos PWA pelo Gateway: 163 testes passaram localmente.

Não foram usadas VMs, não foi feita instalação de produção e não foram enviados comandos a equipamentos físicos.
