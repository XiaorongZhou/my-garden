const CACHE_NAME = "my-garden-v37";
const APP_SHELL = [
  "/",
  "/manifest.webmanifest",
  "/static/index.html",
  "/static/style.css",
  "/static/app.js",
  "/static/js/api.js",
  "/static/js/helpers.js",
  "/static/js/router.js",
  "/static/js/state.js",
  "/static/js/views/add-view.js",
  "/static/js/views/garden-view.js",
  "/static/js/views/detail-view.js",
  "/static/js/views/chat-view.js",
  "/apple-touch-icon.png",
  "/icon-192.png",
  "/icon-512.png",
  "/maskable-icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);
  const isApi = url.pathname.startsWith("/api/");
  const isUpload = url.pathname.startsWith("/uploads/");

  if (isApi || isUpload) {
    event.respondWith(fetch(request));
    return;
  }

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response && response.status === 200 && response.type === "basic") {
          const cloned = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, cloned));
        }
        return response;
      })
      .catch(async () => {
        const cached = await caches.match(request);
        if (cached) {
          return cached;
        }
        return caches.match("/");
      })
  );
});
