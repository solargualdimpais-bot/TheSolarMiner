# SolarMiner Gateway 0.6.15

## Correções de instalação, recuperação e bootstrap Owner

- Corrige o bloqueio do reparador USB: a versão-alvo do pacote Debian usa `TARGET_VERSION`, que não é sobrescrita ao carregar `/etc/os-release`.
- O workflow confirma que a versão de destino do reparador coincide com `packaging/control` e rejeita a antiga variável ambígua.
- O bundle inclui a versão assinada 0.6.14 como origem válida para rollback de uma reparação.
- Mantém o wrapper CLI com `PYTHONPATH` explícito, necessário para `solarminer-gateway bootstrap-token` funcionar após instalação pelo pacote.
- O pacote e o instalador inicial passam a usar a versão 0.6.15; a cópia integrada da PWA recebe cache e rótulo novos.
- Atualiza a orientação de TLS: iOS/Safari exige uma cadeia de confiança e SAN correspondente; a PWA não pode contornar avisos de certificado.

## Causa das falhas observadas

- A atualização 0.6.12 não substituiu a 0.6.10 porque o nome do `.deb` publicado divergia do nome declarado no manifesto assinado. A validação bloqueou a aplicação, como devia; o Gateway permaneceu na versão anterior e o estado de recuperação degradado ficou registado.
- O script de reparação 0.6.14 atribuía a versão do pacote à variável `VERSION` e depois carregava `/etc/os-release`, que define a sua própria variável `VERSION` para Debian. A validação comparava, assim, a versão do `.deb` com o texto da versão Debian e recusava o pacote correto.
- Na 0.6.10 o wrapper do CLI não incluía o caminho dos módulos Python e a CLI ainda não oferecia o comando de emissão do token bootstrap; a correção do wrapper/comando está incluída nas versões posteriores e preservada nesta versão.

## Limites

O instalador exige uma execução explícita como `root`; Debian não executa automaticamente scripts de uma pen USB apenas por esta ser inserida. A instalação limpa e a confiança TLS em cada iPhone têm de ser concluídas no próprio equipamento. A PWA não pode instalar ou confiar silenciosamente num certificado.
