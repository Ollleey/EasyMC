// Minimal service worker: makes the panel installable as a PWA.
// It only caches the static shell; all API calls go straight to the network
// so live data is never stale.
const SHELL = ["/static/style.css", "/static/app.js", "/static/icon-192.png"];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open("mcpanel-shell").then((c) => c.addAll(SHELL).catch(() => {})));
});

self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // Never cache API or dynamic pages — always go to network.
  if (url.pathname.startsWith("/api/") || url.pathname === "/" ||
      url.pathname === "/login") {
    return;
  }
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request))
  );
});
