// Minimal service worker: makes the panel installable as a PWA.
// Network-first for everything, with a cache fallback only when offline — so a
// panel update is always picked up immediately (no stale app.js/style.css),
// while the shell still loads without a connection.
const CACHE = "mcpanel-v2";
const SHELL = ["/static/style.css", "/static/app.js", "/static/icon-192.png"];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => {})));
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    // Drop old caches so a previous version's assets can't be served.
    const names = await caches.keys();
    await Promise.all(names.filter((n) => n !== CACHE).map((n) => caches.delete(n)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return;   // never touch API calls
  e.respondWith(
    fetch(e.request)
      .then((resp) => {
        // Refresh the cached copy of same-origin GETs for offline use.
        if (e.request.method === "GET" && url.origin === location.origin) {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
        }
        return resp;
      })
      .catch(() => caches.match(e.request))
  );
});
