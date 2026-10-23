# SolarMiner Gateway CODE02 v0.6.43

- Importação de inventário Tuya Cloud no Gateway, incluindo dispositivos offline; chaves locais permanecem apenas no Gateway e a PWA recebe apenas dados públicos e capacidades.
- Cartão Energia: potência assinada em convenção consistente (positivo a carregar, negativo a descarregar), azul durante carga e vermelho durante descarga.
- Cartão de autonomia até ao corte na Energia, calculado pelo Gateway a partir da energia estimada acima do SOC mínimo e do consumo atual.
- Mantém a fotografia partilhada e editável do Owner, enquadramento/zoom/transparência/vinheta, cartões compactos, ícone meteorológico, gráfico histórico interativo, navegação Casa, console Gateway e os restantes recursos v0.6.42.
- A autonomia fica indisponível quando falta configuração de capacidade, uma âncora/histórico energético válido ou consumo positivo; não são apresentados valores fabricados.