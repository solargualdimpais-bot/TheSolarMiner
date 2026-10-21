# SolarMiner Gateway 0.6.13

## Correção de instalação e bootstrap Owner

- O executável `solarminer-gateway` define o caminho dos módulos instalados, para que o CLI funcione numa instalação Debian limpa sem depender de uma variável de ambiente da sessão.
- O pacote inclui a rotina local `bootstrap-token`, necessária para criar o primeiro Owner depois da instalação ou de uma recuperação USB.
- O bundle USB inclui uma rotina de reparação para um Gateway existente. Esta valida a assinatura Ed25519 com a chave de release já confiada, o hash/tamanho, versão, origem e arquitetura AMD64 antes de instalar.
- A rotina de reparação cria backup SQLite, ativa a nova árvore de release e exige health check local; em falha, tenta reativar a release anterior e restaurar o backup.
- A instalação mantém-se restrita a Debian 13+ AMD64 e não usa `git pull`, código-fonte remoto ou scripts do repositório.

## Validação

Os testes automatizados e a compilação do pacote são executados pelo workflow de release no GitHub Actions. A execução do script num Gateway físico, incluindo rollback real, continua a exigir validação no dispositivo e não é afirmada por este changelog.
