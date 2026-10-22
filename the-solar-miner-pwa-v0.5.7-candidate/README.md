# The Solar Miner PWA v0.5.8 (gestão Owner e recuperação offline)

Incremental correction on top of v0.5.3. The prior release remains preserved.

## Base preservada: v0.5.4
- AUTOMATISMOS is now a direct sixth item in the iPhone/mobile bottom navigation.
- Old saved per-user navigation preferences are migrated so AUTOMATISMOS is re-added to the visible navigation and order without resetting the existing order.
- Custom house, room and device photos are stored in IndexedDB rather than inline in localStorage, avoiding common iOS Safari localStorage quota failures. localStorage retains small photo references with the workspace/preferences.
- Legacy property-photo key is cleaned up after migration/save/removal.
- Service-worker cache name is bumped to v0.5.4 to avoid serving stale navigation code.

## Safety / limits
All new automation and user administration remains DEMO-only. No Gateway endpoints or physical commands were added. Images and preferences are local to the browser and do not sync to another device.

## Run locally
Requires Node.js. Run `npm test`; for static preview run `npm run serve` and open `http://127.0.0.1:4173`.

For Netlify, publish the contents of `the-solar-miner-pwa-v0.5.7-deployment.zip` at the site root. See `NETLIFY_DEPLOY.md`.

## Incremento v0.5.8 — acessos Owner e recuperação offline

- Gestão real de utilizadores do Gateway na sessão Owner: listar, alterar papel e ativar/revogar contas, sempre com reautenticação e auditoria no backend.
- Download da chave de recuperação apresentada apenas uma vez, para armazenamento numa pen offline dedicada.
- Detalhes e limites em `OWNER_USB_AND_ACCESS.md`.

## Incremento v0.5.7 — interface

Este incremento preserva o código anterior e refina a interface HOME: o cartão de produção abre um diálogo focado com quatro indicadores e o gráfico detalhado; o seletor de lettering do Profile aplica a escala imediatamente e mantém a gravação através do fluxo existente; o título “A Minha Casa” tem tipografia mais elegante; os favoritos têm melhor legibilidade e controlos locais funcionais. Os controlos dos dispositivos continuam exclusivamente DEMO e não enviam comandos físicos. Os valores de produção continuam sintéticos; Safari/iPhone real não foi validado.
