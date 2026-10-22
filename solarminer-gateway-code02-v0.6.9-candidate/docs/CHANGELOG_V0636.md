# CODE02 v0.6.36

- Mapeia leitura Deye FC03 para os sinais usados pela PWA: potência/tensão/corrente nos dois MPPTs; SOC, tensão, corrente/potência assinadas e separadas em carga/descarga, temperatura, capacidade e energias diária/acumulada da bateria; limites de corrente de carga/descarga configurados; energia PV diária/acumulada, importação/exportação de rede, consumo diário/acumulado, medições trifásicas de rede/CT e saída; potência das cargas.
- Regista instantâneos Deye bem-sucedidos no registo canónico de energia para aparecerem na Home e nas áreas Inversores/Baterias após leitura Owner.
- A PWA apresenta todas as métricas com unidade e referência Modbus. A leitura principal do inversor usa a potência FV total; a bateria usa SOC.
- Acrescenta avisos de qualidade para código de tipo divergente, campos de rede a zero e incoerência entre potência FV e tensão×corrente.
- Mantém todos os campos `LIVE_UNVERIFIED`; mapa de protocolo/comunidade e compatibilidade exata com DYDA_WiBLE/firmware ainda não foram certificados pela Deye.
- Continua a enviar apenas FC03. Nenhuma escrita Modbus nem comando do inversor é implementado.
- Regista oito janelas FC03 confirmadas por leitura física do endpoint indicado, incluindo os novos contadores de energia e limites. Uma leitura recente devolveu PV diário/acumulado 37,8/1889,0 kWh, bateria carga diária/acumulada 7,4/716,7 kWh e descarga 4,9/647,5 kWh, consumo diário/acumulado 33,7/1613,1 kWh e limites configurados 100/200 A. A leitura foi feita no computador de desenvolvimento, não no Gateway instalado, e não foi comparada com o visor do inversor.
