const CACHE_NAME = "kangaroo-pwa-v59";
const ASSETS = [
  "/static/manifest.webmanifest",
  "/static/icons/icon-192.svg",
  "/static/icons/icon-512.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("push", (event) => {
  let payload = { title: "Kangaroo", body: "Есть обновление по шагу", url: "/app" };
  try {
    if (event.data) payload = { ...payload, ...event.data.json() };
  } catch (_err) {
    /* ignore malformed payload */
  }
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: "/static/icons/icon-192.svg",
      badge: "/static/icons/icon-192.svg",
      data: { url: payload.url || "/app" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = event.notification.data?.url || "/app";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ("focus" in client) {
          client.navigate(target);
          return client.focus();
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(target);
      return undefined;
    })
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  const isStatic = url.pathname.startsWith("/static/");

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (isStatic && response.ok && !url.pathname.endsWith(".js") && !url.pathname.endsWith(".css")) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() => {
        if (isStatic) {
          return caches.match(event.request);
        }
        return Response.error();
      })
  );
});
