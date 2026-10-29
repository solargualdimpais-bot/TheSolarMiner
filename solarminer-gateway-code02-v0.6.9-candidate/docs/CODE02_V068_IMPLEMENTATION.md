# SolarMiner Gateway CODE02 v0.6.8 — implementação incremental

## Objetivo e origem

Esta entrega é uma implementação incremental sobre o código-fonte CODE02 v0.6.7 parcial e a PWA v0.5.6. Não é uma reescrita cega do projeto: mantém os contratos de autenticação, RBAC, identidade Ed25519, catálogo de conectores, registo de equipamentos e rotas existentes, alterando os pontos necessários para ligar a PWA e melhorar as garantias de recuperação.

- Versão do pacote: `0.6.8`.
- Versão pública de compatibilidade da API: permanece `0.6.0` intencionalmente; não foi alterada para evitar quebra de contrato.
- PWA incorporada: `The Solar Miner v0.5.7`, baseada na v0.5.6.
- O incremento não instala software no Gateway físico, não publica a PWA e não executa comandos sobre dispositivos.

## Alterações implementadas

### 1. PWA e API real de leitura

- A PWA v0.5.7 está incorporada em `web/pwa/` e é servida pela mesma origem do CODE02.
- Depois de autenticação, a PWA consulta apenas endpoints de leitura existentes: `/api/v1/status`, `/api/v1/energy/categories` e `/api/v1/energy/equipment`.
- A lista de equipamentos e as leituras devolvidas pela API substituem os exemplos de energia apenas na sessão autenticada.
- Os estados `LIVE`, `STALE`, `UNKNOWN` e `UNAVAILABLE` são distintos. Só leituras recentes com confiança `LIVE_UNVERIFIED` ou `PHYSICALLY_CORROBORATED` podem produzir estado de dados `LIVE`; leituras sintéticas, documentação e configuração não são tratadas como telemetria.
- Se a consulta falhar, a PWA não troca silenciosamente os dados reais por valores DEMO. Mantém o estado de falha/desatualização identificado.
- Não foi inventado um endpoint de histórico; o gráfico histórico real continua indisponível se o contrato não fornecer uma série temporal.

### 2. Sessões, identidade e convites

- A PWA pode criar uma identidade Ed25519 do dispositivo durante bootstrap local ou resgate de convite.
- A chave privada é reimportada como `CryptoKey` não exportável e guardada em IndexedDB; o token Bearer fica apenas em memória e é descartado no logout/expiração.
- Antes de enviar credenciais no login, a PWA verifica o desafio de identidade do Gateway e compara a fingerprint completa fixada durante o bootstrap/convite.
- O primeiro Owner pode ser criado apenas a partir de um browser local no próprio Gateway; o endpoint CODE02 já rejeita bootstrap remoto. O token local de bootstrap é introduzido manualmente e não é persistido pela PWA. Nesse primeiro bootstrap, a fingerprint é fixada a partir do desafio assinado obtido localmente (TOFU sob controlo local + token de bootstrap); logins e convites posteriores comparam a fingerprint fixada.
- A chave de recuperação do Owner é mostrada uma única vez para cópia/arquivo offline; não é gravada no browser.
- O Owner pode criar, listar e revogar convites de utilização única. O Gateway devolve o código de convite e a fingerprint; a PWA gera localmente o QR/link de ativação, sem dependência QR no Gateway.
- O resgate verifica a assinatura Ed25519 do desafio e a fingerprint completa antes de consumir o convite.
- O MAC continua a ser apenas declarado; não é apresentado como prova física.
- A presença usa o endpoint autenticado existente e é descrita como atividade recente da sessão, nunca como presença física nem como prova de ligação LAN/REMOTO.

### 3. Cache e atualização da PWA

- Cache estático versionado `the-solar-miner-static-v0.5.7`.
- Só recursos estáticos explicitamente allowlisted podem entrar no cache.
- Requests `/api/v1/`, pedidos com query string, `Authorization`, `Cookie`, `Range`, métodos diferentes de GET e pedidos cross-origin ficam fora do cache.
- A aplicação não guarda tokens, convites, respostas de autenticação ou dados pessoais de API no cache offline.
- O fallback offline só devolve o recurso estático correspondente; não serve `index.html` como resposta genérica a qualquer URL.
- A ativação do novo service worker remove caches antigos pertencentes aos prefixos da PWA.

### 4. Backups e restauro SQLite

Novo módulo `solarminer_gateway.database_backup`:

- Cria cópia consistente com `sqlite3.Connection.backup`, incluindo conteúdo confirmado no WAL.
- Valida `PRAGMA integrity_check` na origem, cópia e base restaurada.
- Regista ID de backup, timestamp UTC, `PRAGMA user_version`, versão de `schema_migrations`, tamanho e SHA-256 num sidecar JSON.
- Protege ficheiros com permissões restritivas e troca o ficheiro final atomicamente.
- O restauro exige `offline=True`, sidecar íntegro, hash e tamanho corretos, versões de schema consistentes e ausência de `-wal`/`-shm` no destino. Recusa symlinks.
- O restauro não é executado automaticamente no arranque; deve ser invocado por um procedimento offline depois de parar todos os escritores.

### 5. Recuperação de troca atómica de releases

Novo módulo `solarminer_gateway.deployment_recovery` e wrapper `solarminer-recovery`:

- Regista transações PREPARED/SWITCHED/COMMITTED/ROLLED_BACK num journal com `fsync`.
- Cria symlink temporário e usa `os.replace` para trocar o apontador ativo atomicamente.
- Valida que o destino pertence a `releases/`, não sobrescreve um caminho ativo que não seja symlink e serializa operações com lock de ficheiro.
- Recupera após processo terminado entre preparação, troca e commit; bloqueia journal ou apontadores inconsistentes em vez de adivinhar.
- O pacote inclui unidade systemd independente da API e timer periódico, sem dependência de Internet/Tailscale.

**Limite crítico:** estes são primitivos de backup/recuperação e testes isolados. Ainda não estão integrados num fluxo completo que descarregue/verifique um `.deb`, prepare `/opt/solarminer/new`, migre o banco de dados, faça health check e só então ative uma release. Por isso, `/api/v1/system/update/apply` continua a responder HTTP 503. Não foi declarado que o Gate G esteja aprovado.

## Funcionalidades mantidas explicitamente locais

- Preferências PROFILE e configurações da casa/favoritos continuam persistidas no browser, no espaço de demonstração.
- Automatismos visuais e controlos de cenário continuam locais/DEMO enquanto não existir contrato de comandos e capacidades físicas verificadas.
- Não foram adicionados drivers Modbus, comandos de inversores, baterias, mineradoras, EV ou outros dispositivos.
- A fase E de integração alargada de dispositivos e produção fica para um prompt posterior.
