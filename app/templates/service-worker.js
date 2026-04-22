/* global self */
const BUILD = "{{ build }}";
const CACHE_NAME = `steadra-cache-${BUILD}`;

const CORE_ASSETS = [
  "/",
  "/pwa/manifest.json",
  "/static/css/app.css",
  "/static/js/app.js",
  "/static/icons/favicon-32.png",
  "/static/icons/steadra-192.png",
  "/static/icons/steadra-512.png",
  "/static/icons/steadra-logo.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(CORE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.map((k) => (k.startsWith("steadra-cache-") && k !== CACHE_NAME ? caches.delete(k) : null)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  if (req.method !== "GET") return;

  // Same-origin only
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy)).catch(() => {});
          return res;
        })
        .catch(() => cached || new Response("Нет сети", { status: 503, headers: { "Content-Type": "text/plain" } }));
    })
  );
});

