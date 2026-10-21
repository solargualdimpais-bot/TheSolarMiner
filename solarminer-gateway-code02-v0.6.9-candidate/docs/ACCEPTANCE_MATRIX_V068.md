# Matriz de aceitação v0.6.8

| Área | Resultado nesta entrega | Evidência/limite |
|---|---|---|
| Base PWA v0.5.6 preservada | PASS | PWA v0.5.7 derivada da árvore v0.5.6; comparação v0.5.5/v0.5.6 registada no relatório |
| Leitura autenticada de status/categorias/equipamentos | PASS em testes de código | Só endpoints existentes; não implica telemetria física |
| Estado LIVE/STALE/UNKNOWN/UNAVAILABLE | PASS em lógica e testes estáticos | LIVE exige leitura recente com trust de telemetria; não foi feita validação Safari/iPhone |
| Login Ed25519, chave não exportável e token só em memória | PASS em testes de código | Persistência CryptoKey via IndexedDB depende de suporte do browser real |
| Bootstrap inicial do Owner | Implementado com restrição local | Requer browser no próprio Gateway, token local e identidade Gateway provisionada |
| Criar/listar/revogar convites | PASS backend + UI | Só Owner; API devolve QR SVG gerado localmente; depende de `python3-qrcode` |
| Fingerprint e assinatura Ed25519 do Gateway | PASS em testes de API/código | A instalação física da chave de identidade não foi realizada/validada |
| Presença | PASS em integração de sessão | Indica atividade de sessão, não presença física nem método LAN/REMOTO |
| PROFILE/favoritos persistidos | PASS local | Persistência browser-local; não é sincronização multi-dispositivo no backend |
| Automatismos/controles físicos | DEFERRED / DEMO | Sem comandos físicos ou drivers novos |
| Backup SQLite consistente e metadados | PASS em testes isolados | Não executado na base de dados física |
| Restauro offline + integrity_check | PASS em testes isolados | Exige parar writers; não executado em instalação real |
| SIGKILL durante ALTER TABLE | PASS em base temporária | Não é uma migração real da instalação física |
| SIGKILL durante troca de symlink | PASS em diretório temporário | Primitivo não está integrado ao endpoint de update apply |
| Recuperação independente | PARCIAL | Script e units incluídos; ativação end-to-end ainda não integrada/provada |
| `POST /api/v1/system/update/apply` | BLOQUEADO (503) | Intencional até cumprir todos os gates de ativação/recuperação |
| Fase E — integrações físicas/produção | ADIADA | Novo prompt separado; não foram inventados registos, comandos ou drivers |
| Instalação no Gateway / publicação | NÃO EXECUTADA | Sem acesso/consentimento para alterar equipamento físico ou publicar |
