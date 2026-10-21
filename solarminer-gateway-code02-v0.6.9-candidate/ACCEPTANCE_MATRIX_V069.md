# Matriz de aceitação CODE02 v0.6.9

| Área | Resultado | Evidência/limite |
|---|---|---|
| Manifesto assinado e pacote verificado | PASS em testes de código existentes | A chave real tem de ser provisionada no Gateway de ensaio |
| Máquina de estados persistente e journal | PASS em testes de integração temporários | Não testado em armazenamento físico/queda de energia real |
| Backup SQLite antes da ativação | PASS em testes isolados e integração temporária | Não executado na base física |
| Staging de pacote Debian e validação de payload | PASS em integração temporária | Dependências/arquitetura do host real ainda têm de ser verificadas |
| Symlink atómico e lock | PASS em testes existentes e pipeline | Não substitui teste de reboot real |
| Health-check HTTPS até 60 s | PASS em teste de deadline simulado e integração com health-check injetado | Não foi iniciado um Gateway real para verificar o endpoint durante 60 s |
| Rollback de release após health-check falhado | PASS em integração temporária | Backup e restauro SQLite real em DB temporária; resultado do health-check é simulado; validar em host de ensaio |
| API enfileira em unit independente | PASS em teste API com helper simulado | sudoers e systemd reais não foram ativados neste ambiente |
| Recuperação em boot/timer | Implementada, sintaxe a validar | Não executada em host systemd real/reboot físico |
| PWA v0.5.7 e base visual v0.5.6 | PASS em 72 testes Node | Safari/iPhone e instalação PWA física não validados |
| PROFILE/favoritos multi-dispositivo | NÃO IMPLEMENTADO | Mantém-se local ao browser |
| Comandos físicos e fase E | ADIADOS | Sem comandos/registos inventados |
| Instalação Gateway físico/publicação | NÃO EXECUTADA | Candidata de ensaio apenas; não declarar produção |
