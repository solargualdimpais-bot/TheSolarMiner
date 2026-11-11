# Validação física posterior: painel Tuya/MOES e filhos Zigbee

O suporte implementado permite ao Gateway pedir à Tuya os filhos de um painel e tentar leituras LAN pela associação `parent`/`node_id`. Os testes de software usam respostas simuladas. Não confirmam o CCP-TY-EU-LN, CCP-TY-EU-LN-MS, qualquer firmware MOES, nem uma escrita num aparelho real.

Quando o painel estiver disponível, validar com um aparelho não crítico:

1. Confirmar o modelo e a versão de firmware indicados nas definições do painel.
2. Na PWA SolarMiner, abrir o equipamento Tuya que corresponde ao painel e tocar em **Procurar dispositivos ligados**. Confirmar que o aparelho aparece com nome e Product ID.
3. Abrir o aparelho e verificar que o estado LAN é recente. Para um sensor a pilhas, acordá-lo com o botão previsto pelo fabricante antes de avaliar a leitura.
4. Alterar o aparelho pela interface MOES e observar se a leitura SolarMiner acompanha o estado.
5. Se o modelo tiver uma função de escrita já mapeada e autorizada, enviar uma ação de baixo risco no SolarMiner e observar o aparelho e o painel. A resposta do comando não substitui a leitura de confirmação.
6. Se for seguro, manter a rede local ativa e desligar temporariamente apenas o acesso à Internet; repetir a leitura para confirmar que o caminho LAN não usa fallback Cloud.
7. Reiniciar o painel e repetir a leitura; confirmar recuperação sem comandos atrasados ou inesperados.

Não experimentar DPS `raw`, cenas, Alexa, escrita de configurações ou comandos do ecrã do painel durante esta validação. A comunicação com o hub e os aparelhos não prova que o SolarMiner consiga executar eventos de toque/cena, desenhar no ecrã MOES, instalar software no painel ou substituir a respetiva interface.
