# CODE02 v0.6.41

## Alterações

- Atualiza a PWA integrada do Gateway para 0.5.10, com nome da propriedade editável (predefinição “Solar Energy”), cabeçalho comum e cartões quadrados de meteorologia e produção.
- Guarda nome, fotografia carregada pelo Owner e estrutura de pisos/divisões em `system_state` no Gateway; todas as PWA autenticadas leem o perfil partilhado.
- Aumenta o limite de corpo Nginx LAN/Tailscale para 3 MB, permitindo o JPEG limitado pela API depois da codificação base64.
- Permite a qualquer PWA autenticada escolher equipamentos do registo do Gateway para os seus favoritos. Registo/configuração de novos dispositivos físicos permanece Owner-only; apenas controlos físicos explicitamente suportados são apresentados ao Owner.
- Remove do Home o aviso/banner “Ambiente demonstrativo ativo”; a vista desconectada continua a identificar os cartões simulados como demonstração.
- O service worker invalida a cache estática para que a PWA instalada descarregue os novos estilos.
- Mantém os dados e a configuração da casa, telemetria e comandos existentes na 0.6.40.

## Limites operacionais

Esta alteração não altera drivers nem a interpretação das medições. A fotografia só aparece depois de ser carregada pelo Owner. A PWA servida pelo endereço local continua a mostrar a versão embutida no pacote Gateway instalado; publicar um release não atualiza por si só um Gateway já instalado.
