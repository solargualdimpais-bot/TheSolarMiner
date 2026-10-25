# Gateway 0.6.91 / Owner PWA 0.5.56

- Usa uma leitura SOC Deye recente e identificada como fallback do estimador integrado, sem usar histórico importado como leitura atual.
- Calcula energia acima da reserva e autonomia quando há SOC atual válido e capacidade configurada; sem capacidade, mantém energia/autonomia indisponíveis em vez de inventar valores.
- Mantém o editor de strings na mesma área, confirma a configuração devolvida pelo Gateway e apresenta falhas sem navegar para o Início.
- Na mineradora, concentra perfil, alvo atual, hashrate, consumo estimado e edição do alvo num único menu; compara o pedido com a resposta Braiins e não consulta o endpoint de leitura de alvo que o firmware pode não suportar.
- Evita a corrida de acesso SQLite que podia recriar uma base vazia se o ficheiro desaparecesse depois da verificação de segurança.
- Acrescenta as versões Gateway 0.6.89 e 0.6.90 aos pacotes de rollback incluídos no instalador USB.
- Sincroniza a PWA independente com a cópia integrada no Gateway.