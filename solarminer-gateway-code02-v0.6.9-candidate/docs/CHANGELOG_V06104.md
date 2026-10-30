# Gateway 0.6.104 / Owner PWA 0.5.63

- Lê o UUID da partição com as opções compatíveis do `blkid`.
- Reutiliza uma partição `SOLARMINER_DATA` ext4 independentemente do tamanho.
- Se a partição rotulada existir noutro formato, verifica que não está montada e prepara-a como ext4; nunca formata outra partição por causa desse rótulo.
- Se não houver partição com o rótulo, mantém a criação apenas numa única área livre suficientemente grande do disco Debian.
- Acrescenta testes para reutilização por rótulo, formatação condicionada, montagem noutro local, UUID e partições duplicadas.
