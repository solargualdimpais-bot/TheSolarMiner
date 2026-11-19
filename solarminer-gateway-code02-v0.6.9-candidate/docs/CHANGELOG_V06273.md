# SolarMiner Gateway CODE02 v0.6.273

## Atualização e recuperação

- Limpa cópias antigas de releases, snapshots, backups SQLite e pacotes verificados após um commit saudável, preservando a versão ativa, a release anterior e os artefactos de rollback necessários.
- Limpa pacotes verificados obsoletos antes de descarregar uma nova release, preservando os pacotes das duas últimas atualizações concluídas.
- Verifica espaço para extração, snapshot SQLite e reserva operacional antes de parar o Gateway.
- Regista o resultado de retenção e o diagnóstico de espaço de forma limitada e segura.
- Interrompe a substituição de componentes do sistema até os sockets e sessões administrativas terem sido drenados; volta a abrir os sockets depois da reconciliação ou restauro.

## Validação

- Testes focados locais de retenção, verificação de espaço e componentes passaram no Windows.
- Os testes dependentes de Linux/systemd e a construção/assinatura do pacote são validados pelo workflow oficial Debian antes da publicação.
