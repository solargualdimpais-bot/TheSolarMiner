# Gateway 0.6.103 / Owner PWA 0.5.63

- Corrige a leitura do UUID da partição de dados usando as opções compatíveis do `blkid`.
- Reutiliza a partição `SOLARMiner_DATA` ext4 criada pela tentativa anterior; não a volta a formatar.
- Acrescenta teste para confirmar as opções `blkid` e manter a instalação segura com a partição de dados já existente.
