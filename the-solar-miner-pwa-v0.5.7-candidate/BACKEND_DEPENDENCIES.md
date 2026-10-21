# Dependências pendentes do Gateway — PWA v0.5.4

1. **RBAC de produção:** identidade de sessão e papéis Owner/Admin devolvidos pelo Gateway; verificação no servidor para toda a gestão de utilizadores e configuração.
2. **Gestão de utilizadores:** API autenticada para listar/criar/associar/desativar utilizadores, convites/QR quando suportados, auditoria e autorização.
3. **Preferências pessoais:** API autenticada GET/PUT por utilizador, separada da configuração global da propriedade.
4. **Automatismos:** API de regras, schema de capacidades, avaliação/executor central, agendamento, cooldown, logs e razões; tratamento fail-closed de dados desconhecidos, desatualizados e equipamentos offline.
5. **Fontes de condições:** telemetria de dispositivos com unidades/timestamp/qualidade; meteorologia real; presença autorizada; localização/fuso horário e horários solares.
6. **Previsão solar:** histórico real de produção e previsão central calculada no Gateway, com potencial diário/restante, timestamp, fonte e confiança.
7. **Operação segura:** testes RBAC, auditoria, prevenção de ciclos e comandos repetidos, timeouts, validação de dados e testes de integração/hardware em ambiente controlado antes de produção.

O CODE 02 v0.6.5 não foi alterado nem instalado. A PWA não chama endpoints que não existam no contrato inspecionado.
