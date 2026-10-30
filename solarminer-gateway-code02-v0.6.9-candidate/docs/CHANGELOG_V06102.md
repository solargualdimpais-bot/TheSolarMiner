# Gateway 0.6.102 / Owner PWA 0.5.61

- Corrige a deteção de áreas livres para a partição de dados persistentes, com uma segunda leitura independente do GNU Parted quando o formato de máquina não é reconhecido.
- Mantém a regra de segurança: só cria a partição em espaço livre do disco que contém o Debian e aborta se não conseguir identificar exatamente uma área adequada.
- Acrescenta cobertura para linhas do Parted com campos vazios extra, unidades diferentes, vírgula decimal e intervalos pequenos de alinhamento.
