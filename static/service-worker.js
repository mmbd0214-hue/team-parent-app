
const CACHE_NAME = "qingshan-team-app-11";
const APP_SHELL = [
  "/",
  "/static/style.css",
  "/static/app.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/apple-touch-icon.png"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const req = event.request;
  const url = new URL(req.url);

  if (req.method !== "GET") return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/line/")) return;

  // HTML/JS/CSS 永遠取最新版，避免 PWA 舊快取造成畫面功能沒更新。
  if (url.pathname === "/" || url.pathname === "/admin" ||
      url.pathname.endsWith(".js") || url.pathname.endsWith(".css") ||
      url.pathname === "/service-worker.js") {
    event.respondWith(fetch(req, {cache: "no-store"}));
    return;
  }

  if (url.origin === self.location.origin) {
    event.respondWith(
      caches.match(req).then(cached => cached || fetch(req).then(res => {
        const copy=res.clone();
        caches.open(CACHE_NAME).then(cache=>cache.put(req,copy));
        return res;
      }))
    );
  }
});
