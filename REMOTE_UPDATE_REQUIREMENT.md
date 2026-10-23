# Requisito de atualizações remotas

Preferência do proprietário do SolarMiner:

- Todas as atualizações futuras do software devem ser iniciadas e concluídas remotamente através da PWA.
- O fluxo de atualização deve estar disponível em **Owner → Atualizações → Verificar atualização → Atualizar** (o texto do último comando pode variar conforme a versão). O estado surge durante a verificação e aplicação, sem botão de consulta separado.
- O Gateway ficará sem monitor/ecrã ligado; o processo de atualização não pode depender de interação local no Gateway.
- Preparar o pacote do Gateway e a PWA para que o utilizador possa verificar, confirmar e acompanhar a atualização pela PWA, incluindo o resultado final e eventuais erros. O utilizador espera concluir todo o processo pelo menu Owner, sem acesso físico ao Gateway.
- Tratar esta preferência como requisito para as próximas entregas. Pacotes USB podem existir como recuperação, mas não substituem o fluxo remoto pretendido.

Este requisito descreve o objetivo de entrega; cada versão ainda precisa de validação do fluxo remoto antes de ser apresentada como atualizável pela PWA.
