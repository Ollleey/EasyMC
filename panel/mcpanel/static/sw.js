// Minimal service worker — only there to make the panel installable as a PWA.
// It caches NOTHING: every request goes to the network, so a panel update can
// never be masked by a stale cached app.js/style.css. On activation it also
// deletes any caches left by older versions of this worker.
self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.map((n) => caches.delete(n)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (e) => {
  e.respondWith(fetch(e.request));   // pure pass-through, no caching
});
