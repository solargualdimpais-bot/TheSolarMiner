# The Solar Miner PWA v0.5.10

## Ajustes da Home

- O nome da casa usa uma tipografia mais fina e elegante, com tamanho responsivo.
- Os cartões de meteorologia e produção são quadrados, usam a mesma base visual dos cartões de Painéis, Bateria, Mineradora e Veículo, e mantêm os indicadores em tipografia compacta.
- Cache estática renovada para aplicar os estilos na PWA instalada.
- O nome partilhado predefinido é “Solar Energy”; o cabeçalho de propriedade mantém-se em todos os menus.
- A fotografia começa vazia. Só o Owner pode carregar/remover a imagem; o ficheiro JPEG e o nome ficam guardados no Gateway para todas as PWA autenticadas.
- Pisos e divisões da página Casa são guardados no Gateway e editáveis pelo Owner.
- Os favoritos podem ser escolhidos por qualquer PWA autenticada a partir dos equipamentos já registados. Novos dispositivos físicos continuam sujeitos à configuração Owner existente.
- Removido do Home o aviso “Ambiente demonstrativo ativo”; os estados desconectados mantêm os seus rótulos de demonstração para não confundir exemplos com dados reais.

Não foram alteradas as medições nem os drivers dos equipamentos. As preferências dos favoritos permanecem específicas de cada PWA; os dados de propriedade ficam no Gateway.

## Correção seguinte — v0.5.11

- Upload de fotografia tenta sucessivas reduções de qualidade e dimensões até caber no limite JPEG do Gateway; o limite de origem de 12 MB e o limite guardado de 1,8 MB são indicados no formulário.
- O Owner pode ajustar a transparência da fotografia. A opacidade resultante fica guardada no perfil partilhado do Gateway e é reproduzida nas restantes PWA.
- Regras finais de layout mantêm clima e produção em cartões quadrados, lado a lado em telemóvel, sem as regras CSS antigas os tornarem retangulares ou empilhados.
- O nome de cache do Service Worker muda para aplicar o novo estilo em instalações existentes.
