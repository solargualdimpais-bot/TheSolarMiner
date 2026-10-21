# Guia local — The Solar Miner PWA v0.5.2

```sh
npm test
npm run serve
```

Abre `http://127.0.0.1:4173`.

- HOME: editar identidade da casa; os favoritos são pessoais e locais.
- CASA: escolher Todos os pisos ou um piso; abrir uma divisão/dispositivo com clique; manter premido 2 segundos para editar. Movimento/scroll cancela o gesto. `Shift+F10` ou menu de contexto fornece uma alternativa de teclado/contextual.
- DEVICES: barra horizontal de divisões e lista compacta; clique para detalhe, pressão de 2 segundos para editar.
- ENERGY: sete abas horizontais.

As alterações são guardadas no `localStorage` do browser. Não há sincronização com o Gateway nem com o servidor Netlify. Não existem comandos físicos nesta demonstração. Safari/iPhone real não foi validado nesta execução.
