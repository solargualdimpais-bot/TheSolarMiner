# SolarMiner — inventário e verificação de artefactos de autenticação

Data da verificação: 2026-10-19. Os artefactos originais não foram modificados; todo o código novo foi trabalhado em `/mnt/data/solarminer-auth-work/`.

## Referências originais verificadas

| Ficheiro | Tamanho | SHA-256 recalculado | Integridade/conteúdo |
|---|---:|---|---|
| `/mnt/data/solarminer-gateway-code02-v0.6.3.zip` | 292 988 bytes | `43dd2361d234b17371210d7e30620308f6a2e394a11b3aa82cb9013a43e5b257` | `unzip -t` passou; 197 entradas; contém fonte, testes, relatórios e pacote interno v0.6.3 |
| `/mnt/data/solarminer-gateway-code02-v0.6.4.zip` | 329 254 bytes | `f06275447035628b79b9e1cea4ce1c355aeaf4d50cf3056aa92734e6b3581ee9` | `unzip -t` passou; 196 entradas; contém fonte, testes, PWA e documentação |
| `/mnt/data/solarminer-gateway-code02_0.6.4_amd64.deb` | 74 212 bytes | `88a9562a3e654fd8570efa273f6faa713d58c4c4a5310d02da4cbd942696d749` | `dpkg-deb --info` e `--contents` passaram; 62 entradas; pacote extraído para inspeção, não instalado |
| `/mnt/data/the-solar-miner-pwa-v0.1.0.zip` | 28 570 bytes | `9a156db2feed5b1c0ddf1a52fa93d03dea64cdb3dee49f8cfbc839c686837b3b` | `unzip -t` passou; 17 entradas; contém fonte da PWA e suite de testes |
| `/mnt/data/SOLARMINER_PHASE1_ARTIFACT_MANIFEST.sha256` | 1 971 bytes | `859e7a49c79762c689cbf0073830b6c33c50df59cffd7701cd98f4f003dc1c67` | `sha256sum -c` passou para todas as 18 entradas enumeradas |

## Inspeção cruzada do v0.6.4 ZIP e Debian

- Todos os 13 módulos Python do `src/solarminer_gateway` no ZIP v0.6.4 têm o mesmo SHA-256 que os módulos correspondentes extraídos do Debian v0.6.4.
- Os 10 recursos PWA runtime (HTML, JavaScript, CSS, manifest, service worker e três ícones) também coincidem byte a byte entre ZIP e Debian.
- O pacote declara `solarminer-gateway` versão `0.6.4`, arquitetura `amd64`, com dependências Python/FastAPI/Uvicorn/Argon2/cryptography e OpenSSL.
- O conteúdo do pacote foi extraído apenas para inspeção/testes. Não foi instalado nem executado como serviço.

## Baselines executadas antes das alterações

- CODE02 v0.6.4, fonte extraída do ZIP: 163 testes aprovados.
- PWA v0.1.0, extraída do ZIP: 12 testes aprovados.

## Preservação

Os hashes acima foram recalculados após o trabalho e continuam iguais. A nova implementação está em diretórios de trabalho separados; não foi iniciado CODE 03, não foi usada máquina virtual e não foram executadas operações físicas.
