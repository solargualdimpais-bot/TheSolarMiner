# SQLite — backup consistente e restauro offline

## Regras obrigatórias

1. Nunca copiar apenas o ficheiro principal de uma base de dados ativa em modo WAL.
2. Criar backup através de `create_database_backup()`/API `Connection.backup`.
3. Confirmar `integrity_check=ok`, hash, tamanho e versões de schema no sidecar JSON.
4. Antes de restaurar, parar o serviço Gateway e qualquer outro processo que abra a base de dados.
5. O helper recusa destino com `-wal` ou `-shm`, destino/sidecar por symlink e metadados inválidos.
6. Após o restauro, confirmar `PRAGMA integrity_check` e as versões de schema antes de iniciar o serviço.

## Uso Python

```python
from solarminer_gateway.database_backup import (
    create_database_backup,
    restore_database_backup,
)

backup = create_database_backup(
    "/var/lib/solarminer/gateway.db",
    "/var/lib/solarminer/backups",
)
print(backup)  # backup_path, metadata_path, SHA-256, timestamp e versões

# Apenas depois de parar solarminer-gateway.service e confirmar que não há writers:
result = restore_database_backup(
    backup["backup_path"],
    "/var/lib/solarminer/gateway.db",
    offline=True,
)
assert result["integrity_check"] == "ok"
```

O exemplo documenta a API Python. Não deve ser executado contra uma instalação física sem janela de manutenção, cópia adicional e confirmação do operador.

## Limitações

- O helper de restauro é offline e não tenta descobrir se outro processo mantém a base aberta; cabe ao operador parar todos os escritores. Sidecars presentes fazem o helper recusar o restauro.
- A criação de backup ainda não está ligada automaticamente ao arranque/migração da aplicação, porque este incremento não introduz uma nova migração de schema. Um futuro fluxo de atualização deve chamar explicitamente o backup validado antes de qualquer ALTER TABLE.
