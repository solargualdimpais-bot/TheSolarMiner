SOLARMINER GATEWAY

PROMPT FINAL DE CONSOLIDAÇÃO TÉCNICA, FUNCIONAL E DE SEGURANÇA

Preparação da versão candidata à instalação física --- CODE02 + PWA

Destinatário: Codex Projeto: SolarMiner Gateway

NOTA DE ESCOPO DESTA REVISÃO Este prompt foi limitado para evitar uma
implementação monolítica: agora executa B+C+D+G e apenas a persistência
SQLite indispensável à segurança de G. A Fase E alargada e os drivers de
dispositivos ficam para trabalho posterior. A falta de ZIP histórico não
bloqueia a execução; os backups e a recuperação têm requisitos
verificáveis explícitos; os testes são executados por grupos e
reportados sem contagens fictícias. Aplicação: The Solar Miner Objetivo:
Consolidar a implementação existente, concluir as funcionalidades
prioritárias, verificar a integração entre o backend e a PWA, fechar as
lacunas de segurança e produzir uma versão candidata à instalação
física, com evidências técnicas verificáveis.

⸻

1.  MANDATO PRINCIPAL

Trabalha sobre o estado real dos ficheiros, código, testes e artefactos
disponíveis no ambiente de trabalho.

O objetivo é aproximar o SolarMiner Gateway da conclusão da
implementação de software, produzindo uma versão candidata coerente,
segura, testada e documentada, que possa ser submetida à auditoria final
antes da instalação num equipamento físico com Debian.

Não te limites a elaborar relatórios, planos, auditorias ou listas de
recomendações. Inspeciona, implementa, integra, testa, corrige e entrega
os artefactos funcionais.

Não declares uma funcionalidade concluída apenas porque: • existe uma
rota de API; • existe uma interface visual; • um teste isolado passou; •
um ficheiro contém o código esperado; • um serviço responde a um health
check; • uma soma SHA-256 corresponde ao ficheiro; • uma atualização foi
copiada para uma pasta; • uma ação aparece como concluída na interface.

Cada declaração de conclusão tem de corresponder ao comportamento
efetivamente implementado e às evidências disponíveis.

A prioridade é entregar uma versão candidata funcional, não criar mais
uma camada de documentação que adie a implementação.

1.1. Resultado final pretendido

No final, quero dispor de: 1. Um CODE02 consolidado, funcional e
testado. 2. Uma PWA consolidada, partindo da versão visual e funcional
mais recente efetivamente disponível. 3. Uma integração real e coerente
entre a PWA e o CODE02. 4. Uma identidade criptográfica do Gateway
verificável e um modelo de confiança explícito. 5. Autenticação,
autorização e gestão de sessões consistentes. 6. Um fluxo completo de
convites, associação de utilizadores e gestão de permissões. 7.
Persistência e recuperação da base de dados testadas. 8. Um mecanismo de
atualização do CODE02 com verificação criptográfica, recuperação e
rollback demonstráveis. 9. Testes organizados por grupos, com resultados
verificáveis. 10. Documentação suficiente para preparar a instalação
física em Debian, sem presumir que esta já foi realizada. 11. Um pacote
de entrega identificável por versão e hashes. 12. Uma matriz final que
mostre exatamente o que está aprovado, o que continua por testar e o que
impede a instalação física.

A versão produzida deve ser uma candidata à instalação, não uma
instalação já aprovada.

⸻

2.  REGRAS DE PRESERVAÇÃO DO PROJETO

Estas regras são obrigatórias.

2.1. Preservar o trabalho existente

Não reescrevas o projeto de raiz.

Não substituas componentes funcionais por implementações simplificadas
apenas para fazer os testes passar.

Não elimines funcionalidades existentes, decisões de arquitetura,
testes, documentação ou artefactos históricos sem uma justificação
técnica concreta.

Não alteres retroativamente decisões de arquitetura já encerradas.

Em particular: • preservar CC-01 a CC-09 e o baseline arquitetural
fechado; • preservar as decisões de arquitetura já aprovadas; • não
reabrir a decisão #74; • não alterar artefactos históricos para os fazer
parecer compatíveis com o código novo; • implementar mudanças
necessárias de forma incremental e rastreável; • não criar CODE 03; •
não criar uma nova linha de implementação paralela que substitua
silenciosamente a linha atual; • não duplicar funcionalidades já
existentes sem primeiro identificar o que está implementado.

Se for necessária uma alteração incompatível, documenta a razão, o
impacto, a migração e a forma de recuperação antes de a executar.

2.2. Não assumir que os artefactos históricos estão disponíveis

Existem referências históricas aos seguintes artefactos:

CODE02 v0.6.6 SHA-256 histórico:
9003e772dbd77b556759c2e8f66a44b0446bd83cda8bfb36f4ef4e1f2ad129fd

PWA autónoma v0.5.4 SHA-256 histórico:
cbaf7f387e5a74906ec3b515633fbaa2528f3a960b1cf0b956dd233b4d9a5837

Também existem referências a versões posteriores de trabalho:

CODE02 v0.6.7 SHA-256 histórico:
7089d053a2e00b2e09b3e9e828d7684c61d37f06ff00b911d3785b22bf8b95a1

PWA v0.5.5 SHA-256 histórico:
72770d788643e9b9e45e894bd7c22dabc896683bf73c16ab14b7fc2d8c079542

Bundle de entrega histórico SHA-256:
65cd576da6795db3de42a68bd639bb3e25fbe161e7d729b61f3c0f59d67ddf14

Manifesto de hashes histórico SHA-256:
7516008e44a7f9890bec2ca7ee32f5037839ee04baceaf3a1ced0771f1a2d847

Estes valores são referências históricas, não prova de que os ficheiros
continuam disponíveis ou de que correspondem ao estado atual do projeto.

Segue este procedimento: 1. Procura os artefactos no workspace, nas
pastas de entrega e nos locais de trabalho disponíveis. 2. Se
encontrares um artefacto, calcula o SHA-256 do ficheiro real. 3. Compara
o resultado com o hash histórico correspondente. 4. Regista se existe
correspondência. 5. Se o ficheiro não existir, regista
ORIGINAL_NOT_FOUND. 6. Se o hash divergir, regista HASH_MISMATCH. 7.
Continua o trabalho com a melhor base de código efetivamente disponível,
desde que seja possível identificar a sua origem e estado. 8. Calcula o
hash da base real utilizada e regista-o na entrega.

REGRA CONDICIONAL --- NÃO BLOQUEAR POR FALTA DE ORIGINAIS

Se os artefactos com os hashes históricos acima não estiverem
disponíveis no workspace, nas pastas de entrega ou nos locais
acessíveis, NÃO falhes a Fase A e NÃO pares a implementação. Regista
literalmente ORIGINAL_NOT_FOUND para cada artefacto ausente e continua
com a cópia de trabalho mais recente que seja efetivamente encontrada e
identificável (por exemplo, PWA v0.5.6 e CODE02 v0.6.7 parcial, apenas
se esses forem os ficheiros reais disponíveis).

Se um ficheiro estiver presente mas o hash divergir, regista
HASH_MISMATCH; não o trates como original verificado. Calcula sempre o
SHA-256 da base efetivamente utilizada e identifica-a como base de
trabalho, não como original histórico. Nunca atribuas a uma cópia um
hash de referência que não lhe corresponda.

Se existirem várias cópias do mesmo projeto, compara-as e identifica a
mais completa e consistente antes de escolher a base.

2.3. Proteger a PWA v0.5.6

A PWA v0.5.6 foi identificada como candidata visual e funcional mais
recente, com melhorias que não podem ser perdidas inadvertidamente.

Se estiver disponível, utiliza-a como base preferencial para a PWA.

Compara-a com a v0.5.5 através de uma comparação recursiva equivalente
a:

diff -r PWA-v055 PWA-v056

Adapta os caminhos à estrutura real do workspace. Executa a comparação
apenas se ambas as árvores estiverem disponíveis; caso contrário,
regista qual delas falta e continua sem bloquear. Guarda ou resume a
saída do diff na documentação da base.

Identifica explicitamente as alterações existentes e preserva, no
mínimo, as seguintes funcionalidades, se estiverem presentes na base
real: • janela de produção com quatro indicadores; • gráfico detalhado
de produção; • preferências de escala tipográfica; • tipografia revista
da secção «A Minha Casa», preservando a edição; • cartões favoritos
redesenhados; • controlos locais DEMO dos favoritos; • testes
existentes; • responsividade para ecrãs móveis.

Não substituas a v0.5.6 pela v0.5.5 silenciosamente.

Se a v0.5.6 não estiver disponível, procura a sua implementação no
workspace, identifica a versão real mais recente e regista
explicitamente a decisão tomada.

Se uma alteração ao backend exigir mudanças na PWA, adapta a PWA
preservando as funcionalidades existentes e acrescenta testes de
regressão.

⸻

3.  ÂMBITO DESTA EXECUÇÃO

O objetivo é fechar as lacunas prioritárias necessárias para preparar a
instalação, sem transformar este incremento numa implementação integral
dos 26 pontos.

ESCOPO DESTE INCREMENTO --- OBRIGATÓRIO

Implementa apenas as Fases B, C, D e G, mais o subconjunto de
persistência SQLite da Fase F que seja estritamente necessário para
demonstrar backup, restauro, migração e recuperação seguros da
atualização.

Inclui neste âmbito: - integração real da PWA com endpoints existentes
do CODE02; - identidade do Gateway, autenticação e autorização; - fluxo
de convites e associação de utilizadores; - favoritos/controlos da PWA
ligados apenas a operações reais já suportadas pelo backend, sem
inventar endpoints de comando; - separação explícita entre LIVE, DEMO,
STALE, UNKNOWN e UNAVAILABLE; - atualização segura da aplicação CODE02,
incluindo backup e recuperação testados; - cache/service worker da PWA,
apenas na medida necessária para evitar servir recursos antigos ou
inconsistentes após uma atualização.

Os indicadores já suportados por endpoints de leitura existentes podem
ser ligados à API durante a Fase B. A implementação alargada da Fase E
--- produção mínima além desses endpoints, histórico energético
adicional, novos modelos de dados ou novas fontes de dados --- fica
EXPLICITAMENTE ADIADA para um prompt posterior, após aprovação das Fases
B, C, D e G.

As integrações específicas de dispositivos e protocolos --- Deye/Modbus,
Tuya LAN, Shelly, MOES/Zigbee, Antminer/CGMiner/BMMiner,
Ctronics/ONVIF/RTSP e Tesla Fleet API --- ficam fora deste incremento.
Não inventes registos Modbus, comandos, endpoints, capacidades nem
respostas de equipamentos.

A execução está dividida em fases, com critérios de aprovação. A Fase A
é uma etapa de identificação e preservação, não uma razão para bloquear
o trabalho quando faltam artefactos históricos.

Fase A --- Identificação e proteção da base de trabalho • Identificar as
versões reais. • Verificar os artefactos disponíveis. • Calcular hashes.
• Criar uma cópia de trabalho segura. • Identificar testes e
funcionalidades já existentes. • Estabelecer a matriz inicial de
lacunas. • Preservar a PWA v0.5.6, se disponível.

Fase B --- Integração funcional entre CODE02 e PWA • Consolidar o
contrato de API. • Ligar as interfaces aos endpoints reais existentes. •
Eliminar dependências indevidas de dados simulados. • Uniformizar os
estados de ligação e de dados. • Garantir tratamento de erros e sessões
expiradas. • Preservar o funcionamento visual existente.

Fase C --- Identidade, autenticação e autorização • Consolidar a
identidade criptográfica do Gateway. • Implementar ou concluir os
mecanismos de autenticação. • Garantir autorização no servidor. •
Impedir falsificação de identidade. • Implementar proteção contra
repetição de pedidos assinados. • Garantir que a interface não substitui
a autorização do backend.

Fase D --- Convites, associação e gestão de utilizadores • Concluir a
emissão de convites. • Concluir a apresentação e utilização de QR codes.
• Concluir a associação de novos utilizadores. • Garantir utilização
única dos convites. • Garantir revogação, expiração e controlo de
permissões. • Concluir a experiência funcional na PWA.

Fase E --- Integração alargada de produção (ADIADA) • Esta fase NÃO deve
ser implementada neste incremento. • Será tratada num prompt posterior,
após aprovação explícita das Fases B, C, D e G. • Apenas a ligação de
indicadores a endpoints de leitura já existentes, necessária à
integração B, pode ser feita agora. • Não acrescentar fontes de dados,
modelos energéticos, históricos ou integrações físicas neste incremento.

Fase F --- Persistência e recuperação (ÂMBITO LIMITADO NESTE INCREMENTO)
• Executar apenas o necessário para garantir a atualização segura:
backup consistente SQLite, verificação de integridade, restauro, versão
do esquema, timestamp e testes de interrupção relevantes. • Não expandir
agora a camada geral de histórico/telemetria para além do estritamente
necessário. • Qualquer trabalho adicional da Fase F fica documentado
para priorização posterior, salvo se for requisito indispensável à
segurança de G.

Fase G --- Atualização segura do CODE02 • Implementar ou concluir a
verificação criptográfica de atualizações. • Implementar staging
isolado. • Garantir ativação segura. • Implementar estado persistente da
atualização. • Implementar recuperação após falha. • Testar rollback. •
Documentar os limites do mecanismo.

Fase H --- Testes, documentação e entrega • Executar os testes por
grupos. • Corrigir regressões. • Produzir um relatório único. • Gerar os
artefactos finais. • Preparar as instruções para a instalação física. •
Apresentar uma matriz final de aprovação.

Exclusões explícitas desta execução

Não implementar agora drivers ou integrações específicas para: •
Deye/Modbus; • Tuya LAN; • MOES/Zigbee; • Shelly; •
Antminer/CGMiner/BMMiner; • Ctronics/ONVIF/RTSP; • Tesla Fleet API; •
novos equipamentos ou protocolos físicos não confirmados.

Estas integrações pertencem a uma fase posterior, salvo se já existir no
projeto uma funcionalidade genérica necessária à integração mínima e que
possa ser consolidada sem desenvolver os drivers em falta.

Não inventes endereços Modbus, registos, credenciais, estados de
equipamentos ou respostas de dispositivos.

Não alteres decisões energéticas nem atribuas ao CODE02 capacidades de
controlo físico que ainda não estejam implementadas e validadas.

⸻

4.  PRINCÍPIOS FUNCIONAIS DO SOLARMINER GATEWAY

O SolarMiner Gateway é o núcleo local do sistema.

A PWA é uma interface de gestão e visualização.

O CODE02 deve ser a autoridade local para: • identidade do Gateway; •
autenticação e autorização; • estado canónico; • persistência; •
permissões; • operações administrativas; • estado de atualização; •
auditoria das operações relevantes.

A PWA não pode ser a autoridade final para decisões de segurança.

Ocultar um botão na PWA não substitui a validação da autorização no
servidor.

O estado apresentado na interface tem de corresponder ao estado
conhecido pelo backend, incluindo a indicação de que esse estado está
indisponível, desatualizado ou não confirmado.

O Gateway deve ser concebido para operação local, sem dependência
permanente da Base44, de serviços externos ou da Internet para as suas
funções locais fundamentais.

A conectividade remota é complementar. Não pode ser usada como
pressuposto para a recuperação local.

⸻

5.  FASE B --- INTEGRAÇÃO REAL ENTRE CODE02 E PWA

5.1. Inventário do contrato de API

Inspeciona o backend e a PWA e produz um inventário dos endpoints
efetivamente implementados.

Para cada endpoint, identifica: • método HTTP; • caminho; • autenticação
exigida; • permissões exigidas; • formato de pedido; • formato de
resposta; • códigos de erro; • efeitos persistentes; • testes
associados; • componentes da PWA que o utilizam.

Não declares um endpoint funcional com base apenas no nome ou na
existência da rota.

Testa o comportamento real.

Cria ou atualiza um contrato de API legível e versionado.

Se existirem incompatibilidades entre frontend e backend, corrige-as de
forma incremental e acrescenta testes de contrato.

5.2. Separação entre DEMO e produção

A aplicação tem de distinguir explicitamente: • LIVE: informação
proveniente de uma fonte real e válida; • DEMO: informação simulada para
demonstração; • STALE: informação anteriormente recebida, mas
desatualizada; • UNKNOWN: não existe informação suficiente para
determinar o estado; • UNAVAILABLE: a fonte está indisponível ou falhou.

Adapta os nomes ao modelo existente, se necessário, mas preserva a
distinção semântica.

Não uses dados DEMO como fallback silencioso quando a ligação ao Gateway
falhar.

Não apresentes valores inventados como produção real.

Não apresentes um estado desconhecido como zero.

Não transformes a ausência de resposta num estado de sucesso.

Se uma funcionalidade estiver em modo DEMO, torna-o inequívoco na
interface.

Os testes devem demonstrar que uma falha de ligação não converte a
interface para valores simulados apresentados como reais.

5.3. Consistência dos pedidos e das respostas

Respeita o modelo canónico e as regras de consistência já existentes.

Quando aplicável, mantém: • identificadores de transação; • versões do
estado; • timestamps; • origem dos dados; • indicação de validade; •
resultado efetivo da operação.

Não cries um segundo modelo de estado concorrente dentro da PWA.

Se uma operação ainda não estiver implementada, a interface deve
indicá-lo claramente, sem fabricar uma resposta de sucesso.

5.4. Tratamento de erros

Implementa tratamento coerente para: • Gateway indisponível; • timeout;
• falha TLS; • identidade não verificada; • sessão expirada; •
utilizador sem permissões; • pedido inválido; • conflito de estado; •
operação ainda em curso; • atualização em curso; • erro de persistência.

A interface deve distinguir uma operação aceite pelo servidor de uma
operação concluída.

Se o resultado final for desconhecido, apresenta-o como desconhecido e
permite consultar o estado novamente.

5.5. Favoritos e controlos ligados ao backend

Inspeciona cada cartão favorito e identifica se existe uma operação
real, autenticada e documentada no CODE02 que corresponda exatamente à
ação apresentada.

Quando existir um endpoint real e suportado, liga o controlo a esse
endpoint e apresenta o resultado efetivo (aceite, concluído, falhado ou
desconhecido), sem assumir sucesso antecipadamente. Quando não existir
uma operação real suportada, não inventes uma rota nem simules um
comando físico: preserva o controlo DEMO claramente identificado ou
apresenta-o como indisponível/não implementado. Não declares controlo
físico funcional enquanto não existir um adaptador e confirmação de
estado reais.

Preserva os cartões favoritos redesenhados da v0.5.6, os respetivos
estados locais DEMO e os testes existentes. Acrescenta testes de
regressão para impedir que estados locais DEMO sejam apresentados como
LIVE.

5.6. Cache e service worker da PWA

Inspeciona o service worker, a estratégia de cache e o processo de
atualização da PWA. Mantém o cache limitado aos recursos estáticos
apropriados; não caches respostas autenticadas, tokens, convites, dados
pessoais nem respostas de API sensíveis.

Garante que uma nova versão não fica presa indefinidamente a
HTML/JavaScript antigos incompatíveis com o backend atualizado. Usa
versionamento/invalidação explícitos do cache e uma estratégia segura de
ativação/refresh, sem apagar dados de utilizador nem apresentar uma
versão antiga como atual. Testa, em ambiente local, atualização de
versão, cache antigo, falha de rede e recuperação após recarregamento.
Distingue os testes de service worker simulados de uma validação real em
Safari/iPhone.

5.7. Regressão visual

Preserva as melhorias da PWA v0.5.6.

Não simplifiques a interface para facilitar a integração.

Valida: • navegação; • formulários; • cartões; • gráficos; •
preferências; • edição da configuração da casa; • estado de ligação; •
erros; • sessões; • convites; • comportamento em ecrãs estreitos.

A validação automática não substitui a validação visual em
Safari/iPhone. Se esta não puder ser executada, regista-a como pendente.

⸻

6.  FASE C --- IDENTIDADE CRIPTOGRÁFICA, AUTENTICAÇÃO E AUTORIZAÇÃO

Esta é uma área crítica para a preparação da instalação física.

6.1. Identidade do Gateway

Inspeciona a implementação de identidade existente.

Se já existir uma identidade Ed25519, determina: • como é gerada; • onde
é armazenada; • como é protegida; • como é carregada; • como é validada;
• como se identifica a sua rotação; • como a PWA aprende a confiar nela;
• como é recuperada se o armazenamento estiver danificado.

Não substituas automaticamente uma identidade existente.

Não geres uma nova identidade a cada reinício.

Não coloques chaves privadas em: • QR codes; • respostas públicas da
API; • logs; • repositórios; • ficheiros estáticos da PWA; • pacotes de
distribuição; • relatórios de teste.

Se a chave privada ainda não existir, implementa um processo de
provisionamento apropriado ao desenho atual, com permissões restritas e
tratamento explícito de falhas.

A criação ou rotação da identidade tem de ser uma operação consciente e
auditável.

6.2. Desafio de identidade

Implementa ou consolida um desafio criptográfico que permita demonstrar
posse da chave privada correspondente à identidade pública anunciada.

O desafio tem de ser: • imprevisível; • temporário; • de utilização
única, quando aplicável; • associado ao Gateway esperado; • validado
pelo backend; • protegido contra repetição; • invalidado após utilização
ou expiração.

Não aceites uma identidade apenas porque um endpoint de saúde responde.

Um health check não é prova de identidade criptográfica.

6.3. Confiança TLS e identidade

Não pressuponhas que Safari/iPhone consegue inspecionar automaticamente
o certificado TLS de um servidor local para estabelecer uma confiança
segura.

O processo de associação deve utilizar um mecanismo efetivamente
implementável no ambiente previsto, coerente com a arquitetura
existente.

O processo deve permitir distinguir: • o Gateway esperado; • um Gateway
ainda não associado; • um Gateway cuja identidade mudou; • um Gateway
com identidade inválida; • um Gateway cuja identidade não pôde ser
verificada.

A impressão digital SHA-256 pode ajudar na identificação, mas não prova,
por si só, que a identidade é autêntica.

O mecanismo de confiança deve associar a impressão digital ou chave
pública a uma verificação criptográfica e a uma decisão explícita de
confiança.

Não contornes erros TLS.

Não desatives a verificação de certificados para fazer a associação
funcionar.

Não aceites automaticamente uma chave nova quando a chave anterior
mudou.

Se o mecanismo de confiança não puder ser concluído com segurança,
bloqueia as operações sensíveis e documenta exatamente o que falta.

6.4. Assinatura dos pedidos

Inspeciona a implementação de assinatura de pedidos.

Se for utilizada assinatura Ed25519, define e implementa uma
representação canónica e inequívoca do pedido.

A assinatura deve abranger, de forma consistente: • método HTTP; •
caminho normalizado; • query string canónica, quando aplicável; •
timestamp; • nonce; • hash do corpo do pedido; • identificador do
utilizador ou chave, quando aplicável; • contexto de sessão ou
associação, quando aplicável.

O cliente e o servidor devem calcular exatamente os mesmos bytes
assinados.

Documenta a codificação, a normalização e a ordem dos campos.

Evita ambiguidades entre: • barras e caminhos equivalentes; •
codificação de caracteres; • query parameters; • corpos vazios; • JSON
com propriedades em ordem diferente; • timestamps; • hashes do corpo.

Implementa proteção contra repetição de pedidos, com uma política
definida para validade temporal e utilização de nonces.

Um pedido válido não pode ser repetido indefinidamente para executar
novamente uma operação sensível.

Os testes devem incluir: • assinatura válida; • assinatura inválida; •
corpo alterado; • caminho alterado; • método alterado; • timestamp
expirado; • nonce repetido; • chave não registada; • utilizador
revogado; • tentativa de acesso a recurso sem permissão.

Não declares esta funcionalidade concluída enquanto cliente e servidor
não tiverem sido testados em conjunto.

6.5. Sessões e permissões

Inspeciona o modelo de utilizadores e os papéis existentes.

Mantém o princípio do menor privilégio.

Os papéis devem corresponder às permissões realmente implementadas. No
mínimo, distingue o proprietário do Gateway dos utilizadores com acesso
limitado.

Não concedas permissões de proprietário através de: • valores enviados
pelo cliente; • parâmetros de URL; • campos de um convite que o cliente
possa alterar; • manipulação do armazenamento local; • alterações de
interface; • pedidos sem autenticação.

O backend deve verificar a autorização em todas as rotas protegidas.

Implementa ou consolida: • expiração de sessão; • revogação; • validação
de permissões em cada pedido; • proteção contra reutilização de sessões
revogadas; • respostas de erro coerentes; • auditoria das operações
administrativas relevantes.

Não guardes tokens sensíveis em locais acessíveis desnecessariamente a
JavaScript, nem em logs.

Se a arquitetura atual utilizar armazenamento no navegador, documenta o
risco e escolhe a opção compatível mais segura com a aplicação e o
modelo de sessão existente.

Não inventes uma promessa de segurança que a arquitetura do navegador
não consegue cumprir.

6.6. Recuperação do proprietário

Verifica como o proprietário recupera o acesso se: • perder o
dispositivo; • revogar uma sessão por engano; • perder o acesso à PWA; •
o Gateway reiniciar; • a identidade criptográfica ficar inacessível.

A recuperação não pode depender de um endpoint público que permita
assumir o controlo do Gateway.

Se a recuperação física ou administrativa ainda não estiver
implementada, identifica-a como bloqueio ou procedimento pendente para a
instalação.

⸻

7.  FASE D --- CONVITES, QR CODES E ASSOCIAÇÃO DE UTILIZADORES

Conclui o fluxo de convites de ponta a ponta.

Não basta implementar os endpoints de criação e revogação. A
funcionalidade tem de poder ser utilizada na PWA.

7.1. Criação de convites

A criação de convites deve: • exigir autenticação; • exigir permissões
administrativas adequadas; • validar o papel atribuído; • definir a
expiração; • gerar um token criptograficamente aleatório; • guardar
apenas uma representação protegida do token, sempre que aplicável; •
permitir revogação; • registar a operação na auditoria.

A duração predefinida deve ser limitada, com possibilidade de
configuração dentro dos limites definidos pelo sistema.

Não permitas que o cliente atribua a si próprio um papel privilegiado.

Não aceites papéis desconhecidos por omissão.

Mantém os papéis estritamente limitados aos que o sistema suporta.

Se existir uma distinção histórica entre guest e viewer, preserva a
compatibilidade apenas se a semântica estiver definida e testada. Não
cries permissões adicionais implicitamente.

7.2. Utilização única e concorrência

A aceitação de um convite tem de ser atómica.

Duas tentativas simultâneas com o mesmo token não podem criar duas
associações válidas.

Utiliza uma transação SQLite e as garantias adequadas de concorrência.

Testa: • convite válido; • convite expirado; • convite revogado; •
convite já utilizado; • token incorreto; • duas utilizações simultâneas;
• falha durante a transação; • reinício durante a operação; • repetição
do pedido após uma resposta perdida.

Se a resposta se perder depois de uma operação ter sido confirmada, o
cliente deve conseguir consultar o estado de forma segura, sem reabrir a
possibilidade de reutilização do convite.

7.3. QR code

O QR code deve transportar apenas os dados estritamente necessários à
associação.

O formato deve ser versionado e documentado.

Pode incluir: • versão do formato; • endereço ou origem do Gateway; •
token do convite; • identificador público ou impressão digital da
identidade esperada; • expiração.

Adapta os campos ao contrato real, sem duplicar informação
desnecessária.

Não incluir: • chave privada; • password; • segredo administrativo; •
token de sessão permanente; • credenciais de equipamentos.

Não trates um QR code como prova de autenticidade do Gateway.

O cliente deve validar o Gateway esperado através do mecanismo de
confiança descrito anteriormente.

7.4. Interface da PWA

Conclui o fluxo funcional, incluindo: • área de gestão de convites para
o proprietário; • criação de convite; • seleção de papel permitido; •
indicação de validade; • apresentação de QR code; • listagem de
convites; • estado de utilização; • revogação; • fluxo «Tenho um
convite» para o utilizador convidado; • leitura de QR code, se suportada
no navegador; • introdução manual como alternativa; • confirmação da
identidade do Gateway; • aceitação do convite; • apresentação do
resultado; • tratamento de expiração, revogação e erros.

Não declares a leitura de QR code funcional se apenas existir uma
biblioteca instalada.

Testa a funcionalidade disponível no ambiente automatizado e documenta
as limitações de permissões de câmara e de Safari/iPhone.

Se for necessária uma alternativa manual, esta deve ser segura e
utilizável.

7.5. Chaves dos utilizadores

Se cada utilizador possuir uma chave própria, associa a chave pública à
identidade autenticada de forma consistente.

Não confies numa chave pública fornecida num pedido sem verificar que o
utilizador tem autorização para a associar.

A chave privada deve permanecer no dispositivo ou contexto seguro do
utilizador, conforme a arquitetura escolhida.

Se a implementação utilizar IndexedDB e chaves não exportáveis, verifica
o comportamento real do navegador e documenta os limites.

Não afirmes que uma chave é não exportável apenas porque a interface
assim o indica.

A perda do dispositivo deve ter um procedimento de revogação e nova
associação.

⸻

8.  FASE E --- DADOS DE PRODUÇÃO E ESTADO CANÓNICO

Esta fase não autoriza a criação de integrações físicas que ainda não
existam.

O objetivo é fazer com que a PWA apresente corretamente o estado
fornecido pelo CODE02.

8.1. Fonte de verdade

Para cada indicador existente, identifica: • fonte; • endpoint; •
unidade; • timestamp; • validade; • estado de qualidade; • comportamento
quando a fonte falha.

Se a fonte real ainda não existir, apresenta o indicador como
indisponível ou não configurado.

Não inventes valores de produção, potência, energia, SOC, temperatura,
estado de equipamento ou consumo.

8.2. Produção e histórico

Consolida a integração dos indicadores de produção já existentes.

Preserva a apresentação visual da PWA v0.5.6.

Quando existirem dados reais, apresenta-os com as unidades corretas e a
respetiva referência temporal.

Quando existirem apenas dados DEMO, mantém o modo DEMO explícito.

Não fabriques histórico persistente com base em valores simulados sem os
identificar como simulados.

8.3. Comandos e confirmação

Qualquer comando futuro dirigido a um equipamento deve distinguir: •
comando preparado; • comando enviado; • comando aceite pelo serviço
intermediário; • estado confirmado pela fonte real; • resultado
desconhecido; • falha.

Não apresentes um comando enviado como prova de que o equipamento
executou a ação.

Esta execução não deve ativar comandos físicos nem inventar um protocolo
de controlo que ainda não esteja implementado.

⸻

9.  FASE F --- SQLITE, PERSISTÊNCIA E RECUPERAÇÃO

A persistência é um requisito de preparação para instalação física.

Inspeciona o modelo de dados, as migrações, as transações e o modo de
funcionamento SQLite existente.

9.1. Integridade da base de dados

Verifica: • criação inicial; • abertura após reinício; • migrações; •
transações; • concorrência; • modo WAL, se utilizado; • chaves
estrangeiras, se aplicáveis; • índices; • restrições; • integridade dos
registos; • compatibilidade entre versões.

Não alteres o esquema sem identificar a versão atual e a estratégia de
migração.

Todas as migrações devem ser reproduzíveis, rastreáveis e testadas.

9.2. Cópias de segurança

Não copies simplesmente o ficheiro principal de uma base de dados SQLite
ativa quando possam existir dados em WAL.

Usa a API de backup SQLite (`sqlite3.Connection.backup`) ou a ferramenta
SQLite `.backup` sobre uma ligação válida à base de dados. Não uses `cp`
do ficheiro principal como método de backup consistente de uma base
ativa. Se o projeto tiver uma alternativa já implementada, só a podes
reutilizar se demonstrares que produz uma cópia consistente também com
WAL.

O processo de backup deve: 1. identificar e registar a versão do
esquema/base de dados; 2. registar timestamp UTC e identificador único
do backup; 3. produzir uma cópia consistente através da API de backup ou
`.backup`; 4. executar `PRAGMA integrity_check` na cópia e exigir
resultado `ok`; 5. confirmar que a cópia pode ser aberta e restaurada;
6. preservar permissões e proteção dos dados; 7. registar caminho,
tamanho e SHA-256 da cópia, sem expor segredos; 8. emitir um resultado
verificável.

Executa `PRAGMA integrity_check` na base restaurada depois do restauro e
exige resultado `ok`. Quando apropriado e seguro, executa também a
verificação na origem antes da operação. Documenta claramente qual base
foi verificada e em que momento.

Não consideres um backup válido apenas porque o ficheiro existe ou tem
tamanho superior a zero.

9.3. Teste de restauro

Implementa um teste que: • crie uma base de dados de teste; • insira
dados representativos; • crie um backup; • altere a base de dados
original; • restaure a cópia; • confirme a integridade; • confirme os
dados esperados; • confirme a versão do esquema; • confirme a coerência
das relações e restrições aplicáveis.

O teste deve demonstrar que o restauro recupera efetivamente os dados.

9.4. Interrupções e migrações

Testa interrupções durante: • migração de esquema; • escrita
transacional; • criação de backup; • restauro; • ativação de uma
atualização.

Inclui testes de encerramento forçado do processo, incluindo kill -9 num
ambiente de teste controlado, quando isso for adequado.

Em particular, cria uma base de dados descartável com dados
representativos e testa `kill -9` durante uma migração `ALTER TABLE` (ou
operação equivalente) e durante a troca do ponteiro/symlink de release.
Estes testes têm de correr apenas em ambiente isolado de teste, nunca
sobre dados reais ou a base de dados ativa do utilizador.

Depois de cada interrupção, verifica: • integridade da base de dados; •
versão do esquema; • estado da migração; • capacidade de reiniciar; •
capacidade de continuar ou recuperar sem duplicar operações; •
integridade dos dados.

Não faças testes destrutivos na base de dados real do utilizador.

9.5. Recuperação após reinício

A recuperação deve ser determinística.

Se uma operação tiver ficado incompleta, o sistema deve identificar o
estado e: • concluir a operação com segurança; • reverter a operação; •
ou entrar num estado de recuperação explícito.

Não deixes o Gateway num estado que aparenta estar operacional quando a
base de dados ou o esquema não são utilizáveis.

⸻

10. FASE G --- ATUALIZAÇÃO SEGURA DO CODE02

O mecanismo de atualização deve estar implementado e testado antes de a
instalação física ser considerada pronta.

O âmbito é a atualização da aplicação CODE02.

Não inclui atualização do sistema operativo Debian, firmware de
equipamentos ou firmware do Gateway físico.

10.1. Assinatura criptográfica

Implementa ou conclui um mecanismo de assinatura de releases baseado em
Ed25519, se esta for a tecnologia já adotada no projeto.

A release deve incluir um manifesto assinado que identifique, no mínimo:
• versão; • plataforma e compatibilidade; • versão mínima ou requisitos
de compatibilidade; • hash do pacote; • tamanho esperado; •
identificador da release; • requisitos de migração; • informação
necessária para determinar a estratégia de recuperação.

O formato exato deve ser versionado e documentado.

A assinatura deve cobrir inequivocamente os campos relevantes.

A chave privada de assinatura deve permanecer offline, fora do pacote de
instalação e fora do Gateway.

A chave pública de verificação deve ser provisionada por um mecanismo
independente e protegido.

Uma atualização não pode substituir silenciosamente a chave pública de
confiança utilizada para verificar essa mesma atualização.

Se for necessária rotação de chaves, esta deve seguir um processo
explícito e autenticado, compatível com a arquitetura existente.

10.2. Verificação antes da ativação

Antes de instalar uma release, verifica: • assinatura; • integridade do
manifesto; • hash do pacote; • tamanho; • compatibilidade; • versão; •
espaço disponível; • permissões; • estado atual do serviço; • estado da
base de dados; • existência de backup válido; • ausência de outra
atualização incompatível em curso.

Se qualquer verificação crítica falhar, a atualização deve ser recusada.

Não executes comandos arbitrários recebidos de um servidor remoto.

Não permitas que um manifesto assinado autorize a execução de um script
genérico com privilégios administrativos.

O pacote deve conter uma estrutura conhecida e validada, com uma lista
controlada de ficheiros e operações permitidas.

10.3. Staging e ativação

Inspeciona a estrutura de instalação existente. Reutiliza-a se suportar
releases versionadas, staging isolado e recuperação segura. Caso
contrário, usa e documenta uma estrutura equivalente a: •
/opt/solarminer/current/ --- symlink para a release ativa; •
/opt/solarminer/releases/ --- releases validadas e imutáveis; •
/opt/solarminer/new/ --- staging da próxima release; •
/opt/solarminer/backups/ --- backups verificados.

Prepara a nova versão em `/opt/solarminer/new/` (ou caminho equivalente
justificado), sem apagar nem sobrescrever `current/`. Valida todos os
ficheiros e dependências antes da ativação. A troca do symlink `current`
deve ser atómica no mesmo filesystem, usando um symlink temporário e
`rename` atómico; não implementes a troca como uma sequência em que
`current` fica ausente ou aponta para conteúdo parcial.

O symlink atómico, por si só, não constitui rollback completo. A
recuperação tem de coordenar release de código, estado da base de dados
e estado persistente da atualização.

Antes da ativação: • validar o pacote; • validar a assinatura; • validar
a compatibilidade; • validar a base de dados; • criar e verificar o
backup; • registar o estado da atualização; • confirmar que existe uma
versão anterior recuperável.

A troca atómica de uma ligação simbólica pode fazer parte do mecanismo,
mas não é, por si só, uma estratégia completa de rollback.

10.4. Coordenação entre código e base de dados

Este ponto é obrigatório.

Não assumas que é possível reverter apenas o código se a nova versão
tiver alterado o esquema SQLite.

Define a compatibilidade entre: • versão anterior do código; • versão
nova do código; • versão anterior do esquema; • versão nova do esquema;
• dados persistentes; • estado da atualização; • mecanismo de
recuperação.

Se uma migração for reversível e tiver sido testada, documenta a
estratégia.

Se não for seguro executar a versão anterior com a nova base de dados, o
rollback tem de recuperar o conjunto coerente de código e dados,
utilizando o backup consistente.

Não declares rollback garantido enquanto este cenário não tiver sido
testado.

10.5. Estado persistente da atualização

O processo de atualização deve manter um estado persistente, por
exemplo: • IDLE; • CHECKING; • DOWNLOADING; • VERIFYING; • STAGING; •
BACKING_UP; • ACTIVATING; • HEALTH_CHECK; • COMMITTED; • ROLLBACK; •
RECOVERY_REQUIRED; • FAILED.

Adapta os nomes ao modelo existente, sem perder as distinções
funcionais.

O estado deve sobreviver ao reinício do serviço.

Cada transição tem de ser validada.

Uma interrupção não pode fazer o sistema concluir que uma atualização
falhada foi bem-sucedida.

10.6. Verificação após ativação

Depois da ativação, executa verificações reais durante uma janela de
observação de até 60 segundos, ou utiliza a política já definida no
projeto se esta for mais rigorosa e tecnicamente justificada.

A verificação não pode depender exclusivamente de um endpoint de saúde.

Deve avaliar, conforme aplicável: • processo ativo; • versão ativa; •
capacidade de abrir a base de dados; • integridade do estado
persistente; • capacidade de autenticação; • disponibilidade das rotas
essenciais; • consistência do estado da atualização; • ausência de erros
críticos de arranque.

Se a versão não ficar operacional, executa a recuperação prevista.

Não declares COMMITTED antes de as verificações exigidas passarem.

10.7. Recuperação independente

O mecanismo de recuperação não pode depender exclusivamente: • do
processo CODE02 que acabou de falhar; • da PWA; • do Tailscale; • da
Internet; • do servidor de distribuição da atualização.

Implementa um mecanismo independente do processo principal,
preferencialmente `/usr/local/bin/solarminer-recovery.sh`, executado por
uma unidade systemd e um `systemd timer` separados do serviço CODE02.
Adapta o caminho apenas se existir uma convenção de packaging melhor
justificada; documenta o caminho final e os privilégios mínimos
necessários.

O script/timer deve funcionar localmente e offline, sem Internet,
Tailscale, PWA ou serviço de distribuição de releases. Deve detetar uma
atualização incompleta após reinício, verificar o estado persistente,
validar a release ativa e decidir de forma determinística se mantém,
reverte ou entra em `RECOVERY_REQUIRED`. Não deve iniciar uma nova
atualização nem apagar backups automaticamente.

Testa a recuperação independente em ambiente Debian isolado ou ambiente
de teste equivalente. A presença de um script, unidade ou timer não
constitui prova de funcionamento: demonstra os cenários de interrupção e
o resultado recuperado.

Não introduzas um supervisor excessivamente complexo se existir uma
solução local simples e fiável.

Documenta como recuperar o sistema quando: • o CODE02 não arranca; • a
atualização é interrompida; • a base de dados não abre; • a versão nova
falha o health check; • a máquina reinicia durante a ativação; • a rede
fica indisponível.

A recuperação de um sistema operativo que não arranca pode exigir
recuperação offline por USB. Não afirmes que o mecanismo de atualização
da aplicação resolve, por si só, uma falha de arranque do Debian.

10.8. Endpoint de aplicação

Se o endpoint de aplicação da atualização, incluindo POST
/api/v1/system/update/apply, continuar a devolver HTTP 503, mantém esse
comportamento enquanto a funcionalidade não estiver realmente completa.

Só remove o bloqueio depois de: • implementação; • validação de
autorização; • validação criptográfica; • staging; • backup; • ativação;
• verificação pós-ativação; • rollback; • testes de interrupção; •
testes de recuperação.

Não substituas o 503 por uma resposta de sucesso simulada.

Não exponhas uma funcionalidade de atualização incompleta como se
estivesse pronta para utilização remota.

10.9. Auditoria da atualização

Regista os eventos relevantes: • release solicitada; • verificação
iniciada; • assinatura validada ou rejeitada; • pacote validado ou
rejeitado; • backup criado e verificado; • ativação iniciada; •
verificação pós-ativação; • commit; • rollback; • recuperação
necessária; • motivo da falha.

Os logs não devem conter chaves privadas, tokens, passwords ou outros
segredos.

⸻

11. TESTES E PROVAS DE FUNCIONAMENTO

Os testes são um dos principais critérios de conclusão.

Não basta apresentar uma contagem total sem explicar o que foi
executado.

Existem antecedentes de timeouts em execuções agregadas de pytest. Por
isso, organiza a execução por grupos, sem ocultar falhas ou somar
contagens sobrepostas como se fossem testes distintos.

11.1. Inventário inicial

Antes de alterar o código: 1. identifica todos os conjuntos de testes;
2. identifica os comandos utilizados; 3. identifica os testes lentos; 4.
identifica os testes de recuperação; 5. identifica dependências
externas; 6. identifica os testes que requerem serviços reais; 7.
identifica os testes que podem ser executados offline.

Não elimines testes lentos apenas para acelerar a execução.

11.2. Testes do backend

Executa os testes por grupos coerentes, incluindo: • inicialização e
configuração; • API e contrato; • autenticação; • autorização; •
identidade criptográfica; • assinatura e proteção contra repetição; •
convites; • concorrência; • SQLite e migrações; • backup e restauro; •
atualização; • rollback; • recuperação após interrupção; • regressão.

Executa pytest por grupos documentados, usando caminhos de teste ou
seletores explícitos que correspondam à estrutura real. Não uses uma
única execução agregada como condição única de sucesso, porque já houve
timeout em `pytest -q` agregado.

Como ponto de partida, apenas se corresponder à estrutura real:

`PYTHONPATH=src python3 -m pytest -q --maxfail=1 -k "not slow"`

Executa este comando por grupos coerentes (por exemplo, API/auth,
convites/identidade, SQLite/backup, update/recovery), não como um único
comando global se o tempo limite for excedido. Executa separadamente os
testes lentos e de recuperação com timeout explícito. Se um grupo
exceder o limite, regista `TIMEOUT`, isola-o e continua os grupos
independentes; nunca o marques como aprovado.

Não repitas suites aprovadas sem motivo. Reexecuta testes apenas quando
a alteração posterior afeta o componente, quando existe uma regressão
concreta ou quando os logs históricos são insuficientes para demonstrar
a nova garantia.

Em `TEST_REPORT.md`, regista por grupo o comando exato, duração/timeout,
testes recolhidos, aprovados, falhados, ignorados, erros de configuração
e resultado. Identifica sobreposições entre grupos; não somes contagens
sobrepostas nem fabriques um total deduplicado. Se a deduplicação não
for fiável, reporta somente os resultados por grupo e declara essa
limitação.

11.3. Testes da PWA

Executa os testes existentes, incluindo os testes Node, se esse for o
mecanismo adotado.

Acrescenta testes para: • ligação ao CODE02; • sessão expirada; • falha
de rede; • identidade não verificada; • dados LIVE versus DEMO; • dados
desatualizados; • erros de autorização; • criação e revogação de
convites; • utilização de convites; • validação de respostas; •
regressão das funcionalidades da v0.5.6.

Não uses mocks como prova de integração real.

Os mocks são úteis para testar cenários isolados, mas devem ser
identificados como testes simulados.

11.4. Testes de integração

Cria um ambiente de teste local que permita verificar o percurso
real: 1. iniciar o CODE02; 2. inicializar ou abrir a base de dados; 3.
estabelecer uma associação de teste; 4. autenticar um utilizador; 5.
executar pedidos autorizados; 6. executar pedidos não autorizados; 7.
criar um convite; 8. aceitar um convite; 9. revogar um convite ou
sessão; 10. consultar o estado através da API; 11. verificar o estado
apresentado pela PWA; 12. reiniciar o backend; 13. verificar a
persistência; 14. executar os cenários de atualização e recuperação em
ambiente isolado.

Não uses equipamentos físicos nem dados de produção.

11.5. Timeouts e resultados inconclusivos

Se um grupo exceder o tempo limite: • regista o comando; • regista o
tempo decorrido; • identifica o último ponto observado; • regista
TIMEOUT; • procura isolar o motivo; • executa os restantes grupos
independentes quando possível.

Um timeout não equivale a aprovação.

Uma execução parcial não equivale a aprovação do conjunto.

Uma falha de infraestrutura não equivale automaticamente a um defeito do
código, mas também não pode ser apresentada como sucesso.

11.6. Contagens de testes

O relatório deve mostrar, por grupo: • comando; • duração; • total
executado; • aprovados; • falhados; • ignorados; • erros de
configuração; • timeout; • observações relevantes.

Identifica testes repetidos ou grupos sobrepostos.

Não somes os resultados de grupos sobrepostos como se fossem testes
únicos.

Não inventes totais agregados.

Se não for possível obter uma contagem deduplicada fiável, apresenta as
contagens por grupo e explica a limitação.

11.7. Relatório único

Produz TEST_REPORT.md.

Este relatório deve conter: • ambiente de execução; • versão do Python e
Node, quando aplicável; • dependências relevantes; • comandos exatos; •
resultados por grupo; • resultados da PWA; • resultados de integração; •
testes de segurança; • testes de persistência; • testes de atualização;
• testes de recuperação; • falhas; • timeouts; • testes não executados;
• limitações; • conclusão fundamentada.

Não apresentes uma percentagem global de aprovação sem explicar o
denominador.

⸻

12. PREPARAÇÃO PARA DEBIAN E INSTALAÇÃO FÍSICA

A entrega deve preparar uma instalação futura, mas não executar a
instalação.

12.1. Inspeção da instalação

Inspeciona os scripts, unidades systemd, dependências e documentação
existentes.

Verifica: • configuração; • caminhos; • permissões; • criação das
pastas; • utilizador e grupo de serviço; • arranque automático; •
reinício após falha; • gestão de logs; • diretório de dados; • proteção
de segredos; • certificados; • health check; • atualização; •
recuperação; • desinstalação ou reversão, quando aplicável.

Não presumas que os scripts de instalação existentes são corretos apenas
porque estão presentes.

Testa-os num ambiente de teste adequado sempre que possível.

12.2. Rede

Preserva a arquitetura prevista: • funcionamento local; • acesso pela
LAN; • acesso remoto opcional através de Tailscale; • ausência de portas
públicas desnecessárias.

Não abras portas no router.

Não alteres configurações de rede reais.

Não estabeleças uma ligação Tailscale real durante esta execução.

Documenta as portas, os serviços e as interfaces de rede necessários,
com base no código efetivamente implementado.

12.3. Segredos e configuração

A configuração deve separar: • configuração não sensível; • segredos; •
identidade criptográfica; • dados persistentes; • dados temporários; •
artefactos de atualização.

Não coloques credenciais reais nos exemplos.

Não reutilizes credenciais que possam ter sido partilhadas anteriormente
em conversas.

Utiliza exemplos fictícios e documenta o processo de configuração
inicial.

12.4. Primeiro arranque

Documenta o fluxo de primeiro arranque necessário à instalação física.

Inclui: • preparação do sistema; • inicialização da configuração; •
identidade do Gateway; • criação ou associação do proprietário; •
configuração da rede; • validação do serviço; • acesso inicial pela PWA;
• verificação de segurança; • backup inicial; • recuperação se o
arranque falhar.

Não inventes que o primeiro arranque já foi testado em hardware real.

12.5. Recuperação offline

Produz instruções para recuperação offline por USB, quando aplicável.

As instruções devem distinguir: • falha da aplicação; • falha da base de
dados; • falha de atualização; • falha de configuração; • falha de
arranque do Debian.

Não afirmes que o procedimento funciona até ter sido testado no ambiente
correspondente.

Se o hardware físico ainda não estiver disponível, identifica a
validação física como pendente.

⸻

13. SEGURANÇA E AUDITORIA

Executa uma revisão de segurança centrada nos componentes alterados e
nas rotas relevantes.

Verifica, no mínimo: • autenticação obrigatória; • autorização por rota;
• exposição de dados; • gestão de tokens; • proteção contra repetição; •
validação de entradas; • controlo de concorrência; • permissões de
ficheiros; • armazenamento de segredos; • logs; • CORS, se aplicável; •
configuração TLS; • limites de pedidos; • tratamento de erros; •
atualização assinada; • recuperação após falha.

Não abras uma vulnerabilidade conhecida para facilitar a integração.

Não desatives TLS, autenticação ou autorização para fazer os testes
passar.

Não substituas verificações criptográficas por comparações informais de
strings.

Não uses a posse de um URL, de um QR code ou de uma impressão digital
isolada como prova suficiente de autorização.

Distingue claramente: • integridade do ficheiro; • autenticidade da
origem; • identidade do Gateway; • identidade do utilizador; •
autorização para executar uma operação.

São propriedades diferentes e exigem verificações próprias.

⸻

14. CRITÉRIOS DE QUALIDADE DO CÓDIGO

Durante a implementação: 1. Respeita as convenções do projeto. 2. Evita
duplicação de lógica de autenticação e autorização. 3. Evita abstrações
desnecessárias. 4. Mantém interfaces internas consistentes. 5. Trata
erros explicitamente. 6. Mantém compatibilidade com a base de dados
existente. 7. Acrescenta testes para todas as correções críticas. 8. Não
elimina testes para esconder regressões. 9. Não introduz dependências
sem necessidade. 10. Não deixa segredos nos artefactos. 11. Não deixa
operações administrativas acessíveis sem autenticação. 12. Não introduz
comportamento de sucesso simulado em rotas de produção. 13. Não deixa
funcionalidades críticas parcialmente implementadas apresentadas como
concluídas. 14. Não cria migrações destrutivas sem uma estratégia de
recuperação testada. 15. Não altera a interface visual sem preservar as
funcionalidades existentes.

Se encontrares um defeito que impeça uma destas garantias, corrige-o
antes de declarar a fase aprovada.

⸻

15. GESTÃO DAS FASES E CRITÉRIOS DE APROVAÇÃO

A execução deve avançar de forma ordenada.

Gate 0 --- Base identificada

Aprovado quando: • a base de trabalho está identificada; • os artefactos
disponíveis foram verificados; • os hashes reais foram calculados; • as
ausências estão documentadas; • existe uma cópia de trabalho; • as
funcionalidades existentes estão inventariadas; • a PWA v0.5.6 foi
preservada, quando disponível.

Gate 1 --- Fases B, C, D e G (incluindo apenas a persistência
indispensável a G)

Aprovado quando: • a PWA v0.5.6 continua a ser a base candidata e as
melhorias existentes estão preservadas; • a PWA comunica com o CODE02
através do contrato de API real para os fluxos incluídos no âmbito; • os
favoritos/controlos ligados à API usam apenas operações realmente
suportadas, sem sucesso simulado; • a distinção
LIVE/DEMO/STALE/UNKNOWN/UNAVAILABLE é correta nos fluxos abrangidos; • a
identidade do Gateway, autenticação, autorização e proteção contra
repetição estão testadas em conjunto; • o fluxo de convites está
completo de ponta a ponta no âmbito suportado; • as transações, a
utilização única e os erros/repetições estão testados; • o backup SQLite
usa API `.backup`/backup API, inclui metadados e passa
`PRAGMA integrity_check`; • o restauro foi demonstrado e os testes
`kill -9` durante migração e troca de symlink foram executados em
ambiente isolado; • a recuperação independente offline está demonstrada;
• o endpoint `POST /api/v1/system/update/apply` só deixa de devolver 503
se todas as garantias de ativação/recuperação estiverem realmente
implementadas e aprovadas; caso contrário, o 503 permanece; • não
existem regressões críticas conhecidas; • os testes e a documentação são
coerentes com a implementação.

A Fase E não faz parte deste incremento e não deve começar
automaticamente após este gate. Deve ser objeto de um prompt posterior.
Não avances para uma declaração de prontidão física enquanto houver
lacunas críticas neste gate.

Gate 2 --- Qualificação da versão candidata

Aprovado quando: • todos os testes obrigatórios executáveis foram
executados; • os resultados são reproduzíveis; • as falhas e os timeouts
estão documentados; • os artefactos de entrega estão completos; • os
hashes correspondem aos ficheiros efetivamente entregues; • o
procedimento de instalação está documentado; • o procedimento de
recuperação está documentado; • as limitações de hardware e navegador
estão explícitas; • a matriz final não contém aprovações sem evidência.

Um teste que não pôde ser executado deve aparecer como NÃO TESTADO,
nunca como APROVADO.

Gate 3 --- Preparação para instalação física

Este gate não significa autorização para instalar.

Significa apenas que a versão candidata está suficientemente documentada
para ser submetida à decisão do proprietário.

A instalação física continua dependente de: • auditoria final; •
confirmação do hardware; • preparação do meio de instalação; •
verificação das instruções; • disponibilidade de um procedimento de
recuperação; • autorização explícita do proprietário.

⸻

16. ARTEFACTOS OBRIGATÓRIOS DE ENTREGA

Entrega os ficheiros reais, não apenas referências a eles.

Adapta os nomes e a estrutura às convenções existentes, mas inclui os
seguintes elementos.

16.1. Código • ZIP do CODE02 candidato; • ZIP da PWA candidata,
preservando a base v0.5.6 quando disponível; • scripts necessários para
executar e testar; • ficheiros de configuração de exemplo, sem segredos;
• migrations e código de persistência relevantes; • unidades systemd, se
fizerem parte da entrega.

Se não for possível produzir um pacote de instalação genuíno, não
inventes um .deb.

Um ZIP de código-fonte não deve ser apresentado como pacote de
instalação.

16.2. Integridade

Produz um manifesto SHA-256 dos artefactos entregues.

O manifesto deve incluir: • nome; • versão; • tamanho; • SHA-256; • data
de criação; • relação com a base utilizada.

Calcula os hashes depois de os ficheiros finais estarem concluídos.

Se um ficheiro for alterado posteriormente, recalcula o hash.

Não uses os hashes de versões antigas para identificar versões novas.

16.3. Documentação

Entrega, no mínimo: • README.md atualizado; • API_CONTRACT.md; •
TEST_REPORT.md; • SECURITY_REVIEW.md; • UPDATE_AND_ROLLBACK.md; •
DATABASE_BACKUP_AND_RESTORE.md; • INSTALLATION_PREPARATION.md; •
RECOVERY_OFFLINE.md, se aplicável; • LIMITATIONS.md; •
RELEASE_MANIFEST.sha256 ou nome equivalente; • ACCEPTANCE_MATRIX.md.

Se os documentos já existirem, atualiza-os sem apagar informação
histórica relevante.

16.4. Matriz de aceitação

A matriz deve incluir: • requisito; • componente; • estado; • evidência;
• teste associado; • limitação; • ação pendente.

Utiliza apenas estados explícitos, como: • APROVADO; • FALHADO; •
PARCIAL; • NÃO TESTADO; • NÃO VALIDADO NO IPHONE; • NÃO VALIDADO NO
GATEWAY FÍSICO; • NÃO APLICÁVEL; • BLOQUEADO.

Não atribuas APROVADO com base numa intenção ou numa implementação não
executada.

⸻

17. PROIBIÇÕES ABSOLUTAS NESTA EXECUÇÃO

Não: • instales o software no Gateway físico; • alteres o sistema
operativo de qualquer equipamento real; • publiques uma versão em
produção; • estabeleças uma ligação Tailscale real; • alteres
configurações reais de router ou firewall; • contactes equipamentos
físicos; • executes comandos de controlo de equipamentos; • utilizes
credenciais reais em testes; • apagues backups históricos; • substituas
artefactos anteriores sem preservar a cópia original; • declares que a
PWA foi validada em Safari/iPhone sem essa validação; • declares que o
Gateway foi validado fisicamente sem essa validação; • declares rollback
funcional sem executar testes de recuperação; • declares assinatura
válida apenas porque o hash corresponde; • declares identidade
comprovada apenas porque o health check responde; • escondas falhas,
timeouts ou testes não executados; • introduzas chaves privadas nos
pacotes; • desatives TLS para contornar problemas; • transformes dados
DEMO em dados LIVE; • apresentes uma atualização parcial como segura; •
alteres decisões de arquitetura fechadas sem justificação; • interrompas
a execução apenas porque falta um ZIP histórico, se existir uma base
alternativa verificável.

Se surgir uma operação que exija acesso a um equipamento real,
publicação, credenciais de produção ou autorização externa, não a
executes. Prepara a documentação e identifica a autorização necessária.

⸻

18. PROCEDIMENTO DE EXECUÇÃO

Segue esta sequência.

Passo 1 --- Inspeção

Inspeciona o workspace, identifica os artefactos, versões, testes,
dependências e documentação existentes.

Não comeces por reescrever componentes.

Passo 2 --- Base e regressão

Confirma a base real, calcula os hashes e preserva a PWA v0.5.6 quando
disponível.

Executa os testes iniciais para conhecer o estado de partida.

Passo 3 --- Implementação prioritária

Executa apenas as Fases B, C, D e G, por esta ordem sempre que as
dependências o permitam. Dentro de G, executa exclusivamente os
requisitos de persistência/backup/restauro da Fase F indispensáveis à
segurança da atualização.

Não implementes a Fase E alargada neste prompt, mesmo que as fases
prioritárias sejam aprovadas. A Fase E fica para um prompt posterior
(trabalho de produção/dados), após o gate das Fases B, C, D e G ser
APROVADO.

Os indicadores existentes podem usar endpoints de leitura já disponíveis
como parte da integração B; isso não autoriza criar novos modelos
energéticos, drivers, fontes ou funcionalidades da Fase E.

Se for necessária uma alteração de ordem, documenta a dependência
concreta. Não uses a dependência como motivo para alargar o âmbito.

Passo 4 --- Testes por grupos

Executa os testes, corrige defeitos e repete os testes afetados.

Mantém os resultados anteriores para permitir comparação.

Passo 5 --- Regressão do âmbito alterado

Confirma que as funcionalidades preexistentes afetadas foram
preservadas, incluindo os elementos da PWA v0.5.6 e o comportamento do
service worker/cache. Não repitas testes sem relação com as alterações,
salvo quando necessários para demonstrar uma garantia crítica.

Confirma que a PWA continua coerente e utilizável dentro do âmbito
implementado.

Passo 6 --- Qualificação da release

Gera os artefactos finais, hashes, documentação e matriz de aceitação.

Passo 7 --- Relatório final

Apresenta uma conclusão objetiva sobre o estado real do projeto.

Não termines com apenas uma lista de alterações.

A conclusão deve dizer se a versão candidata está aprovada para
auditoria final ou se existem bloqueios que impedem essa recomendação.

⸻

19. FORMATO OBRIGATÓRIO DA RESPOSTA FINAL DO CODEX

No final, apresenta um relatório com estas secções.

A. Resultado executivo

Explica, de forma direta: • o que foi efetivamente concluído; • o que
continua incompleto; • se a versão candidata pode avançar para auditoria
final; • quais são os bloqueios restantes.

B. Versões e origem

Indica: • versão inicial real; • versão final real; • base utilizada
para CODE02; • base utilizada para PWA; • artefactos históricos
encontrados; • artefactos ausentes; • hashes verificados; • alterações
de versão.

C. Implementação

Lista as funcionalidades efetivamente implementadas, indicando os
ficheiros ou componentes relevantes.

Distingue alterações novas de funcionalidades que já existiam.

D. Testes

Apresenta: • comandos; • grupos; • duração; • resultados; • falhas; •
timeouts; • testes ignorados; • testes não executados; • limitações.

Não inventes resultados.

E. Segurança

Indica os resultados da revisão de: • identidade; • autenticação; •
autorização; • assinatura; • convites; • persistência; • atualização; •
recuperação.

Identifica as lacunas que continuam a representar risco.

F. PWA

Confirma: • versão de origem; • funcionalidades da v0.5.6 preservadas; •
integração com o CODE02; • separação LIVE/DEMO; • regressões
encontradas; • testes realizados; • validação visual em Safari/iPhone,
se efetivamente executada.

G. Atualização e recuperação

Explica o mecanismo implementado e os testes executados.

Distingue claramente: • rollback de código; • recuperação da base de
dados; • recuperação após reinício; • recuperação offline do sistema
operativo.

H. Artefactos entregues

Lista cada ficheiro, com: • caminho; • versão; • tamanho; • SHA-256; •
finalidade.

Indica os caminhos concretos para aceder aos artefactos produzidos.

I. Matriz de aceitação

Apresenta o estado de cada gate: • Gate 0; • Gate 1; • Gate 2; • Gate 3.

Cada aprovação deve ter evidência associada.

J. Próximo passo mínimo

Indica se as Fases B, C, D e G passaram os respetivos gates e enumera a
evidência. Declara expressamente que a Fase E e as integrações de
dispositivos excluídas não foram implementadas neste incremento.

Se as fases prioritárias estiverem aprovadas, o próximo passo é preparar
um prompt separado para a Fase E; isso não autoriza instalação física
nem publicação.

Se não estiverem aprovadas, indica apenas os bloqueios concretos que
precisam de ser resolvidos.

Não proponhas uma nova auditoria arquitetural geral se o problema for
uma falha de implementação identificada.

Não avances automaticamente para a instalação física.

⸻

20. CRITÉRIO FINAL DE SUCESSO

Considera este trabalho concluído apenas quando existir uma versão
candidata identificável, coerente, testada e acompanhada de evidências
suficientes para uma auditoria final.

O objetivo não é obter uma declaração artificial de que tudo está
pronto.

O objetivo é chegar ao ponto em que: • o código real está consolidado; •
a PWA utiliza efetivamente o backend; • a segurança é demonstrável; • os
convites funcionam de ponta a ponta; • a persistência e o restauro foram
testados; • a atualização tem um mecanismo de recuperação comprovado; •
os testes têm resultados rastreáveis; • os artefactos estão
identificados por hashes; • a instalação e a recuperação estão
documentadas; • as limitações estão claramente identificadas.

Se algum destes objetivos não puder ser concluído, entrega tudo o que
foi efetivamente concluído e identifica a lacuna exata, a sua causa e a
correção necessária.

Não sacrifiques segurança, integridade dos dados ou funcionalidades
existentes para produzir uma aparência de conclusão.

Não pares num relatório se for possível implementar e testar a correção
no ambiente disponível.

Não instales, não publiques e não alteres o Gateway físico. Aguarda
autorização explícita do proprietário para qualquer operação real.

O resultado esperado é uma versão candidata à auditoria final e à
posterior preparação da instalação física, não uma alegação de validação
física já realizada.
