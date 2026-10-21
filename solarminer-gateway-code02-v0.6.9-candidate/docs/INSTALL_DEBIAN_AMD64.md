# Instalação inicial — Debian amd64

## Destino e pré-requisitos

O pacote CODE02 é `amd64`, adequado ao Intel Core i5-8400. A árvore exige Debian com Python 3.11 ou posterior; Debian 12 (Bookworm) é a primeira versão Debian estável que satisfaz esse requisito, e Debian posterior também pode satisfazê-lo. Confirma no Gateway com:

```sh
cat /etc/os-release
dpkg --print-architecture
python3 --version
```

O resultado de arquitetura tem de ser `amd64`. Não usar pacotes ARM64.

## Instalação inicial através de pen USB

A pen deve conter, na mesma pasta:

- `install-from-usb.sh` (este repositório: `packaging/install-from-usb.sh`);
- exatamente um pacote oficial `solarminer-gateway_*_amd64.deb`;
- `release-pubkey.pem`, a chave pública Ed25519 de release obtida por uma origem confiável;
- a impressão SHA-256 do ficheiro da chave, obtida por um canal independente.

Depois de instalar Debian minimal/netinst e iniciar sessão como `root`, monta a pen e executa o script diretamente como root:

```sh
sh /media/<utilizador>/<PEN>/install-from-usb.sh
```

O script verifica Debian, Python, AMD64, pacote e impressão da chave. Pede o URL GitHub inicial e permite registar outros repositórios aprovados. Esses URLs ficam numa allowlist root-owned; a PWA Owner pode selecionar e guardar apenas uma dessas origens. O script usa `apt-get` para obter dependências Debian. Não é necessário executar o comando `sudo`; o pacote instala a dependência `sudo` usada pelo serviço para invocar somente o helper privilegiado autorizado.

A instalação do pacote configura o serviço e o timer diário de verificação. A verificação usa a origem Owner guardada (ou a primeira origem aprovada no arranque inicial), exige a chave pública provisionada e verifica manifesto Ed25519, hash, tamanho, versão, arquitetura e dependências. Não executa código do repositório. A aplicação de um pacote continua a exigir confirmação Owner pela PWA.

## Instalação sem pen USB

É tecnicamente possível depois de Debian estar instalado e ter acesso à Internet: o Gateway pode obter o pacote de um release público HTTPS. Para o fazer com segurança, é necessário publicar um pacote `.deb` AMD64 e manifesto assinado, provisionar a chave pública por uma origem independente e conhecer a sua impressão SHA-256. O repositório atualmente não tem releases GitHub publicados; por isso não existe ainda um artefacto remoto que este método possa instalar.

Não usar `curl | sh` para executar código não verificado. A instalação remota tem de verificar a assinatura Ed25519 e o hash do pacote antes de chamar `dpkg`; não deve fazer `git pull`, executar scripts do release ou instalar dependências fornecidas pelo repositório.

## Limite da validação

A construção do `.deb` em amd64 e a instalação/arranque em Debian limpo são verificações separadas. Este documento não constitui evidência de que o pacote atual foi instalado num Gateway físico. Registar a versão Debian, `dpkg --print-architecture`, o SHA-256 do `.deb`, o resultado do serviço e do health check durante um ensaio antes de declarar a instalação validada.
