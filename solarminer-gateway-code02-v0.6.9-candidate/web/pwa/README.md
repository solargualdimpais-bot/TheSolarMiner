# The Solar Miner PWA v0.5.16

PWA de operação ligada ao SolarMiner Gateway CODE02 0.6.43. Em sessão autenticada, as páginas apresentam dados e estado fornecidos pelo Gateway; áreas ainda sem integração mostram disponibilidade explícita e não dados simulados.

Notas da versão: [`CHANGELOG_V0512.md`](CHANGELOG_V0512.md).

## Incremento v0.5.16

Mostra o fluxo da bateria com carga azul e descarga vermelha no menu Energia, e calcula a autonomia até ao SOC de corte com energia utilizável estimada pelo Gateway dividida pelo consumo atual. O cabeçalho partilhado, as opções de fotografia, meteorologia, gráfico interativo e restantes áreas seguem incluídos.

- Home com perfil da casa (nome, localidade e fotografia), meteorologia, produção solar atual e gráfico de histórico/previsão fornecido pelo Gateway.
- Favoritos de equipamentos Tuya configurados, com comandos Owner individuais para interruptores e dispositivos de nível compatíveis.
- Gestão Owner organizada por áreas e operação/configuração independente por equipamento.
- Service worker e cópia embutida no pacote Gateway alinhados com esta versão.

## Limites conhecidos

- Fotografia, nome da casa, transparência, divisões e pisos ficam guardados no Gateway e são partilhados entre PWA autenticadas. Favoritos continuam específicos do browser atual.
- O controlo de nível exige datapoint e escala configurados no Gateway.
- O potencial solar e a meteorologia dependem da localidade e capacidade FV configuradas e da disponibilidade do serviço meteorológico.
- Leituras Deye permanecem identificadas como não validadas fisicamente até ao comissionamento no equipamento.

## Desenvolvimento

Requer Node.js. Executa `npm test`; para pré-visualização estática, executa `npm run serve` e abre `http://127.0.0.1:4173`.

Para publicar em Netlify, publica o conteúdo desta pasta na raiz do site. Consulta `NETLIFY_DEPLOY.md` e `API_CONTRACTS.md`.
## Incremento v0.5.16

Home compares PV production and UPS load with separate filled curves and a highlighted surplus area. Battery pages show configured bank name, capacity and online state, clearly separating inverter telemetry and cumulative counters from physical battery capacity.
