const CACHE_NAME = "illy-coffee-static-v23-cash-eod-cache";
const STATIC_ASSETS = [
  "/",
  "/static/partials/chrome.html",
  "/static/partials/views.html",
  "/css/themes/theme-shared.css?v=20260915-theme-files-10",
  "/css/themes/soft-dark.css?v=20260915-theme-files-6",
  "/css/themes/deep-dark.css?v=20260915-theme-files-6",
  "/css/themes/midnight-glass.css?v=20260915-theme-files-6",
  "/css/themes/warm-cream.css?v=20260915-ice-cream-contrast-1",
  "/css/themes/warm-green.css?v=20260915-theme-files-7",
  "/css/themes/cool-graphite.css?v=20260915-theme-files-6",
  "/css/themes/light.css?v=20260915-theme-files-6",
  "/static/manifest.json",
  "/static/offline.html",
  "/css/styles.css?v=20260915-font-size-1",
  "/static/js/app.js?v=20260917-cash-eod-1",
  "/static/js/barista.js?v=20260917-cash-delivery-confirm-2",
  "/static/js/admin.js?v=20260917-eod-report-2",
  "/static/js/developer.js?v=20260915-inventory-staff-i18n-1",
  "/static/js/i18n.js?v=20260917-cash-eod-1",
  "/static/images/illy-logo.svg",
  "/static/images/illy-cart-logo-2x.svg",
  "/static/images/icons/illy-wide-cup-10x.svg",
  "/static/images/avatar-user.svg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(event.request).catch(() =>
        caches.match(event.request).then((response) => response || new Response(
          JSON.stringify({ error: "Offline rejimdə serverə qoşulmaq mümkün deyil." }),
          { status: 503, headers: { "Content-Type": "application/json" } }
        ))
      )
    );
    return;
  }
  event.respondWith(
    caches.match(event.request).then((cached) =>
      cached || fetch(event.request).then((response) => {
        if (response.ok && url.origin === self.location.origin) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        }
        return response;
      }).catch(() => caches.match("/static/offline.html"))
    )
  );
});
