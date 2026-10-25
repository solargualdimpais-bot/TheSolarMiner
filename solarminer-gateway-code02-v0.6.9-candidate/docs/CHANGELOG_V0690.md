# Gateway 0.6.90 / Owner PWA 0.5.55

- Lê o alvo de potência no estado do tuner, em vez de tentar fazer GET ao endpoint Braiins documentado para escrita.
- Mostra as consultas da mineradora em janelas legíveis, agrupadas por estado, desempenho e configuração; JSON completo passa a estar recolhido em detalhes técnicos.
- Apresenta as ventoinhas em cartões com rotação e velocidade definida, e permite editar o alvo de potência a partir do valor atual comunicado pelo tuner.
- Gera os campos de definições avançadas a partir do esquema devolvido pela Braiins OS e envia apenas os valores alterados.
- Permite configurar controlo automático da mineradora diretamente pela API Braiins, sem exigir um relé Tuya. O despacho mantém as condições existentes de telemetria atual, bateria, margem de excedente e limites de potência; a automatização continua desativada por omissão.
- A PWA independente e a cópia integrada no Gateway foram sincronizadas para esta versão.
