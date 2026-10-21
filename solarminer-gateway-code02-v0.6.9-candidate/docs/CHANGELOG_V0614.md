# SolarMiner Gateway 0.6.14

## Reparação USB tolerante a estado de atualização interrompida

- Usa a versão previamente instalada registada no `dpkg` como referência de rollback, mesmo quando o symlink `current` ficou quebrado ou aponta para uma release candidata falhada.
- O bundle contém os pacotes e manifestos assinados 0.6.10–0.6.13; a ferramenta confirma a assinatura e a identidade do pacote originalmente instalado antes de começar.
- Em falha, o rollback reinstala o pacote Debian anterior, repõe a ligação para a release que estava ativa e restaura o backup SQLite.
- A correção do wrapper Python e o bootstrap Owner da 0.6.13 mantêm-se.

## Validação

O workflow de release Linux executa sintaxe, testes automatizados, build Debian, verifica as assinaturas dos pacotes de rollback e publica o bundle. A validação final de instalação e rollback no Gateway físico permanece pendente.
