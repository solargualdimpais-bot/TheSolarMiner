# Pipeline de atualização e recuperação — CODE02 v0.6.9 candidate

## Origem de release escolhida pelo Owner

A PWA oferece a sessão Owner um campo de URL de repositório e o botão **Verificar atualização**. O Gateway aceita apenas a raiz HTTPS `https://github.com/{owner}/{repository}`, confere uma correspondência exata na allowlist administrativa root-owned e valida o URL também no servidor. Não há `git pull`, checkout, execução de scripts ou instalação de dependências obtidas do repositório.

Configure `/etc/solarminer/update-sources.json` como root (ficheiro regular, root-owned, sem permissão de escrita por grupo/outros, JSON até 64 KiB), por exemplo:

```json
{
  "repositories": {
    "https://github.com/owner/repository": {
      "manifest_url": "https://github.com/owner/repository/releases/latest/download/solarminer-release.json",
      "manifest_origins": ["https://github.com", "https://release-assets.githubusercontent.com"],
      "package_origins": ["https://github.com", "https://release-assets.githubusercontent.com"]
    }
  }
}
```

Ajuste as origens permitidas às origens HTTPS de manifesto/pacote usadas pelo serviço de release; redirecionamentos para qualquer outra origem são recusados. A configuração não contém tokens ou credenciais. Repositórios têm de ser públicos. Sem correspondência administrativa, a verificação termina em rejeição e não altera o sistema.

A instalação inicial pode criar esta allowlist através de `packaging/install-from-usb.sh`, executado como `root`. O script valida Debian 13 (Trixie) ou posterior, Python 3.13+, arquitetura `amd64`, o pacote e a impressão SHA-256 da chave pública Ed25519 fornecida por canal independente. O operador pode aprovar várias raízes GitHub; a PWA Owner pode guardar e escolher apenas URLs exatos dessa allowlist. O URL escolhido é persistido em `system_state`.

`solarminer-update-check-daily.timer` executa uma verificação cinco minutos depois do arranque e, depois, diariamente como a conta de serviço `solarminer`. Usa a escolha guardada ou, antes da primeira sessão Owner, a primeira entrada da allowlist inicial. Se existir uma versão mais recente, valida a assinatura e o pacote, exige que o preflight independente passe e enfileira a aplicação no helper privilegiado. O serviço não aplica pacotes com origem, assinatura, compatibilidade ou preflight inválidos. O helper continua a executar backup SQLite, staging, ativação, health check e rollback. A falha da aplicação automática fica registada no estado persistente e no journal systemd; o Gateway não volta a aplicar automaticamente a mesma versão depois de falha, rollback ou recuperação bloqueada. Se um rollback entrar em `RECOVERY_BLOCKED`, o timer tenta novamente restaurar a release e o backup verificados, sem repetir a versão que falhou. A PWA Owner apresenta a causa e o resultado da recuperação.

As unidades da API e da verificação diária mantêm `NoNewPrivileges=true` e `RestrictSUIDSGID=true`; não dependem de sudo. Os pedidos limitados de atualização e Tailscale passam pelo socket local `/run/solarminer/update-broker.sock`, acessível apenas à conta `solarminer`. O broker root-owned aceita `preflight`, `enqueue` com UUID, `tailscale_status` e `tailscale_connect`. Os helpers validam cada pedido; o broker só executa executáveis fixos e não recebe comandos arbitrários da PWA.

O Gateway verifica Ed25519 com a chave de release provisionada localmente, hash e tamanho do pacote, versão, arquitetura e dependências Debian, espaço disponível e preflight do helper. Apenas um pacote validado é guardado em staging. A verificação manual na PWA mostra a versão e o estado; as verificações agendadas enfileiram automaticamente apenas pacotes já verificados cujo preflight passe. O Owner pode continuar a iniciar uma verificação/aplicação manual pela PWA. Ambos os caminhos percorrem os estados de backup SQLite, staging, ativação, health check e rollback descritos abaixo.

## Modelo de ativação

O endpoint `POST /api/v1/system/update/apply` só aceita uma operação `VERIFIED`, com versão de destino coincidente, sessão Owner e helper privilegiado instalado. A API não reinicia o próprio serviço: enfileira a operação numa unidade systemd independente e responde `202 APPLY_QUEUED`. O progresso pode ser consultado em `GET /api/v1/system/update/status`.

O helper `/usr/sbin/solarminer-update-apply` é invocado pela unidade root `solarminer-update-broker@.service`, ativada por um socket Unix com modo `0600` e dono `solarminer`. O broker aceita exclusivamente `preflight` ou `enqueue` com UUID; nunca encaminha comandos ou caminhos fornecidos pelo cliente. A CLI do helper também aceita `--operation UUID` e `--recover`, reservados às unidades root de aplicação e recuperação. Antes da ativação, o helper volta a validar a assinatura Ed25519 do manifesto usando a chave pública root-owned, o hash/tamanho do pacote, a versão Debian e o caminho de staging.

## Máquina de estados persistente

`VERIFIED → APPLY_QUEUED → PRECHECK → BACKUP_CREATED → STAGED → SWITCHED → SERVICE_RESTARTING → HEALTH_CHECKING → COMMITTED`.

Qualquer falha após o backup entra em `ROLLING_BACK`; se o rollback e a verificação da versão anterior passarem, termina em `ROLLED_BACK`. Se não for possível provar a recuperação, termina em `RECOVERY_BLOCKED` e exige intervenção. O estado atual fica em `/opt/solarminer/update-state.json`; cada transição é acrescentada e sincronizada em `update-state.jsonl`, além de refletida em `update_operations` na SQLite. Um lock `flock` serializa ativação e recuperação.

## Backup, ativação e health check

- Backup online via SQLite backup API antes de extrair ou ativar a nova release; metadados incluem UTC, hash, tamanho e versões de schema.
- O pacote é extraído para uma nova diretoria dentro de `/opt/solarminer/releases/`; a versão ativa nunca é sobrescrita.
- O apontador `current` muda por symlink temporário + `os.replace`, seguido de `fsync` da diretoria.
- O serviço é reiniciado pela unidade independente `solarminer-update-apply@UUID.service`.
- O health check consulta `https://127.0.0.1:8443/api/v1/health` por até 60 segundos, exige HTTP 200, integridade SQLite `ok` e `package_version` igual à versão pretendida.
- Em falha, o helper para o serviço, restaura o symlink anterior, repõe o backup SQLite depois de confirmar o serviço parado, reinicia a release anterior e exige health check da versão anterior durante até 60 segundos.

## Recuperação independente

`solarminer-recovery.service` e `.timer` usam o helper fora do processo da API. O serviço é executado na inicialização e periodicamente; trata o journal antigo de conectores e a máquina de estados de atualização. Uma operação não terminal após interrupção é revertida para a release anterior. A recuperação é offline e não requer Internet/Tailscale.

## Pré-requisitos para habilitar

- `current` é um symlink para uma diretoria existente sob `/opt/solarminer/releases/`.
- `solarminer-recovery.timer` está ativo.
- A base SQLite existe e não é symlink.
- `/etc/solarminer/release-pubkey.pem` existe, pertence a root e não é gravável por grupo/outros; a chave deve ser provisionada pelo operador a partir da origem de confiança.
- `solarminer-update-broker.socket` está ativo, com socket Unix `0600` propriedade de `solarminer`; o broker root valida a ação e UUID antes de chamar o helper fixo.
- O pacote tem arquitetura suportada e dependências compatíveis com o host.

Se qualquer pré-requisito falhar, a aplicação permanece bloqueada com HTTP 503. A validação de pacote não implica que ativação esteja disponível.

## Limites de validação

A implementação e os testes em diretórios temporários não substituem uma instalação Debian em host de ensaio. Antes de aprovar a candidata para Gateway físico, executar instalação limpa e upgrade a partir da versão efetivamente instalada, verificar permissões/units systemd e socket, teste de health-check falhado, SIGKILL em cada fronteira de estado, reboot durante `SWITCHED`, recuperação offline, dependências Debian e rollback SQLite real. Não declarar validação física até essa evidência existir.
