# SolarMiner Intelligence — Especificação funcional

## Estado e origem

Este documento regista os requisitos comunicados pelo proprietário para o SolarMiner Intelligence. Os equipamentos, modelos, valores e sintomas abaixo são contexto fornecido pelo proprietário; não foram confirmados por leitura direta do Gateway físico. Medições e resultados citados como exemplos são ilustrativos até serem observados nos dados reais.

## Objetivo

Executar OpenClaude como agente técnico residente no Gateway, usando OpenAI API como fornecedor configurável de raciocínio. O Intelligence deve acompanhar dados e diagnósticos do SolarMiner, investigar causas, desenvolver correções e melhorias, executar validações e encaminhar alterações pelo workflow de release existente. Não é um motor energético ou de dispositivos alternativo: deve reutilizar os motores, conectores, APIs, armazenamento e atualizador do SolarMiner.

O funcionamento essencial dos motores energéticos e das proteções deve continuar local e disponível sem Internet ou OpenAI. A memória técnica persistente deve registar problemas, evidências, investigações, propostas, ficheiros alterados, testes e resultados de release.

## Capacidades funcionais pretendidas

### 1. Diagnóstico de baterias e energia

- Acompanhar as leituras disponíveis das baterias JK-BMS, inversores Deye, painéis solares, cargas e restantes equipamentos conhecidos pelo Gateway.
- Exemplo comunicado: dois bancos LiFePO4, 16 células e 320 Ah por banco, com duas BMS JK-PB16S30A. O número e a configuração exatos carecem de confirmação no Gateway.
- Comparar tensões das 16 células, corrente, temperatura e estado de carga entre células, entre bancos e ao longo do histórico.
- Distinguir desequilíbrios persistentes de diferenças momentâneas; identificar a célula afetada, fundamentar a confiança e acompanhar a tendência.
- Comparar leituras incompatíveis entre Deye e JK-BMS e investigar origem, qualidade, comunicação, configuração ou interpretação pelo software antes de propor uma correção.
- Avaliar previsões existentes de produção solar e consumo contra medições históricas comparáveis; identificar erro, tendência, confiança e oportunidades de melhoria sem criar uma segunda previsão paralela.

### 2. Tuya, DPS e comunicação local

- Avaliar equipamentos Tuya conhecidos, IDs de produto, DPS catalogados ou desconhecidos, valores, tipos de dados, confirmação de comandos, latência e erros.
- Para um DPS desconhecido, investigar capacidades declaradas pelo fabricante/serviço Tuya e dados já disponíveis localmente; comparar estados observados antes e depois de uma operação autorizada e usar documentação/protocolos para sustentar a interpretação.
- Nunca inventar o significado ou a unidade de um DPS. Marcar mapeamentos desconhecidos ou conflitantes como incertos.
- Sintoma de exemplo comunicado: `Tuya LAN command rejected DPS` / ausência de confirmação DPS. Investigar, entre outros pontos, se o DPS existe, se o tipo/valor enviado é compatível, se houve confirmação e se o conector local interpreta corretamente o protocolo.
- Analisar latência, polling excessivo, consultas repetidas e aproveitamento de leituras locais no Device Engine existente; não criar um segundo motor Tuya.
- Criar ou propor novas integrações e entradas de catálogo com base em identidade e evidência verificáveis.

### 3. Shelly e Bluetooth

- Diagnosticar integração Shelly com estado conhecido, disponibilidade, RPC, erros e tempos de resposta.
- Exemplo comunicado: Shelly Vintage SK Dim 1 intermitente. Distinguir indisponibilidade do equipamento de defeito do conector, com base nos dados disponíveis.
- Investigar descoberta Bluetooth através do Shelly Blu Gateway e capacidades/RPC efetivamente suportados, sem depender do Bluetooth do iPhone ou navegador PWA.
- Melhorar o Device Engine existente sem duplicar o canal de comunicação.

### 4. Descoberta de rede e identidade de equipamento

- Acompanhar mudanças de endereço IP e associações DHCP, cruzando MAC conhecido, IP atual e identidade do equipamento.
- Exemplo comunicado: um router Huawei, cujo modelo foi ditado como “B6 36 ... 16 6” e precisa de confirmação, pode alterar endereços DHCP.
- Reconhecer equipamento por MAC sempre que possível, atualizar o inventário apenas com evidência suficiente e voltar a validar a comunicação do protocolo correspondente, como Modbus TCP.
- Distinguir inventário em cache de descoberta ativa. Qualquer varrimento ou escrita na rede tem de usar um mecanismo já existente, autorizado e auditado; uma análise do Intelligence não deve iniciar polling ou scans implícitos.

### 5. Veículo elétrico e otimização energética

- Exemplo comunicado: Tesla Model Y Standard de 2024.
- Avaliar o histórico da estratégia descrita: excedente solar suficiente pode justificar aumentar a corrente em 1 A; descarga excessiva das baterias pode justificar reduzi-la em 1 A; reserva mínima pretendida de 95%; reavaliação aproximada a cada 10 minutos.
- Estudar efeitos atrasados, como aumento de corrente seguido de descarga das baterias, e propor melhorias com backtests e dados reais.
- Limites de corrente, reserva mínima e proteções elétricas têm de permanecer determinísticos, locais e fora do poder de alteração do modelo.

### 6. Antminer e eficiência

- Exemplo comunicado: Antminer S19K Pro, objetivo aproximado de 105 TH/s e observação pontual de cerca de 81 TH/s, ambos por confirmar nos dados reais.
- Correlacionar hashrate, frequência, tensão, temperaturas, erros de hashboards e potência para investigar a causa da perda de desempenho.
- Avaliar eficiência entre energia consumida e desempenho. Qualquer alteração de frequência/tensão tem de permanecer sujeita a limites térmicos e elétricos determinísticos.

### 7. Diagnóstico do Gateway e evolução do próprio software

- Acompanhar erros de aplicação, motores, dispositivos, instalação, atualizações, reinícios e rollbacks, com origem, timestamp, versão, fase, comando/serviço quando disponível e resultado.
- Analisar código e testes do repositório para identificar a causa; desenvolver uma correção focada num checkout isolado, acrescentar testes de regressão novos, executar as suites pertinentes e preservar os testes existentes.
- Comparar métricas antes/depois apenas quando existirem períodos e condições comparáveis; não declarar sucesso sem evidência.
- Criar commits/branches e encaminhar alterações automaticamente pelo mecanismo de publicação configurado. O workflow GitHub existente continua a validar, assinar e publicar artefactos; o atualizador SolarMiner existente continua responsável pela instalação, verificação de saúde e recuperação.
- O Intelligence não pode editar critérios de release, mecanismos de assinatura, autenticação, limites elétricos, recuperação ou as próprias regras de permissão para aprovar a sua alteração. A chave privada de assinatura permanece exclusivamente nos GitHub Secrets.
- A atualização do Gateway só deve ocorrer a partir de um artefacto que passou o workflow e as verificações do atualizador; não aplicar alterações diretamente aos motores em execução.

### 8. Acompanhamento e memória na PWA

A consola Owner deve apresentar atividade real e persistida: problema e evidências, fase da investigação, proposta/código alterado, testes e resultados, estado de branch/commit, validação do workflow, publicação e estado da atualização/recuperação. Não apresentar como reais números ou estados que sejam apenas exemplos. Distinguir dados atuais, históricos, em cache, indisponíveis e inferidos.

## Ciclo autónomo pretendido

1. Observar periodicamente dados, eventos, logs e resultados de atualização pelas interfaces existentes.
2. Detetar mudança ou falha e guardar evidências com tempo, versão e fonte.
3. Investigar com dados históricos, código e documentação; assinalar incerteza e dados em falta.
4. Desenvolver uma alteração focada num checkout isolado, sem tocar na instalação ativa.
5. Executar suites fixas e regressões relevantes; comparar medições quando apropriado.
6. Se as validações falharem, guardar erro e continuar a investigação sem publicar.
7. Se passarem, submeter pelo fluxo GitHub existente; deixar o workflow executar os critérios finais e assinatura.
8. O atualizador existente instala o artefacto assinado, verifica saúde e usa rollback se necessário; o Intelligence lê e regista o resultado.
9. A PWA mostra a trilha completa. Nenhum passo pode ser declarado concluído sem a respetiva evidência.

## Estado de implementação conhecido neste checkout

Na data deste registo, o checkout local contém uma ponte de leitura/MCP, uma sessão de desenvolvimento com permissão de editar apenas o checkout isolado, recusa de shell, proteção de testes existentes e eventos de auditoria para edições e validações. O bootstrap prepara um clone do repositório público após verificar Tailscale/TLS. Isto ainda não constitui ciclo autónomo completo: publicação/PR automático, validação ampla executada em ambiente isolado sem segredos, monitorização contínua baseada em eventos, teste Debian e instalação física no Lenovo ainda carecem de implementação e validação.

## Critério de verdade

Código no checkout, testes locais, publicação GitHub e instalação física são estados diferentes. O Intelligence deve indicar qual deles está confirmado. Nenhuma informação deste documento prova que o equipamento ou a versão correspondente esteja atualmente instalado ou ativo no Lenovo.
