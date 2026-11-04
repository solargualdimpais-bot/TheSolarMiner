# The Solar Miner PWA v0.5.4 — Relatório de implementação

## Causa identificada
1. A navegação inferior mobile tinha cinco botões fixos e não incluía AUTOMATISMOS. No iPhone, a navegação lateral não é mostrada, por isso a área podia ficar escondida no menu desktop/“Mais”.
2. Fotografias eram serializadas como data URLs Base64 dentro de `localStorage`, por vezes em mais de uma chave. Isso podia ultrapassar a quota relativamente pequena do iOS Safari; algumas falhas de escrita eram silenciosas ou a imagem só ficava na memória.
3. Preferências por utilizador mais antigas podiam substituir a lista de menus após a normalização inicial e ocultar AUTOMATISMOS.

## Alterações
- Adicionado botão AUTOMATISMOS à navegação móvel fixa, com seis colunas responsivas e ligação direta a `navigate("automatismos")`.
- Reaplicada migração de navegação depois de carregar as preferências antigas; HOME, PROFILE e AUTOMATISMOS são garantidos e os restantes itens mantêm a ordem existente.
- Introduzido armazenamento separado de imagens via IndexedDB, com referências pequenas no JSON de `localStorage`. Fotografias de casa, divisão e dispositivo seguem a mesma estratégia.
- Implementada recuperação assíncrona das fotografias antes de considerar a restauração terminada; erros de persistência passam a gerar aviso visível.
- Removida a gravação duplicada da fotografia da propriedade em `localStorage`; a chave antiga é apenas lida para migração e depois limpa.
- Atualizado o service worker para cache v0.5.4.

## Segurança e compatibilidade
Sem novas APIs, chamadas de rede, comandos físicos ou alterações ao Gateway. A persistência de imagens é local ao browser/dispositivo; não equivale a sincronização com o Gateway. IndexedDB é suportado por Safari iOS em contexto HTTPS, mas não foi possível concluir um teste visual interativo no Safari/iPhone neste ambiente.
