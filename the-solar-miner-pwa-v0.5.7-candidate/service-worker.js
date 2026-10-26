const CACHE_NAME = "the-solar-miner-static-v0.5.58-engine-pv-strings";
const STATIC_ASSETS = [
  "./", "./index.html", "./styles.css", "./app.js", "./gateway-connection.js",
  "./gateway-auth.js", "./app-core.js", "./workspace-ui.js", "./demo-mode.js",
  "./features-v053.js", "./manifest.webmanifest", "./assets/icon.svg",
  "./assets/icon-192.png", "./assets/icon-512.png", "./assets/heic2any-0.0.4.min.js"
];
const STATIC_PATHS = new Set(STATIC_ASSETS.map(path => new URL(path, self.location.href).pathname));
const CACHE_PREFIXES = ["the-solar-miner-static-", "the-solar-miner-demo-static-"];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(key => CACHE_PREFIXES.some(prefix => key.startsWith(prefix)) && key !== CACHE_NAME).map(key => caches.delete(key))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  // API/authenticated traffic (including password-device-login), query strings, non-GET requests and cross-origin
  // requests are deliberately network-only and never enter Cache Storage.
  if (request.method !== "GET" || url.origin !== self.location.origin || url.search ||
      url.pathname.includes("/api/v1/") || request.headers.has("Authorization") ||
      request.headers.has("Cookie") || request.headers.has("Range") || !STATIC_PATHS.has(url.pathname)) return;
  event.respondWith(fetch(request).then(async response => {
    const cacheControl = response.headers.get("Cache-Control") || "";
    if (response.ok && !/no-store|private/i.test(cacheControl) && !response.headers.has("Set-Cookie")) {
      const cache = await caches.open(CACHE_NAME);
      await cache.put(request, response.clone());
    }
    return response;
  }).catch(async () => {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response("Recurso indisponível offline. Reconecta e recarrega a aplicação.", {
      status: 503, headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" }
    });
  }));
});
