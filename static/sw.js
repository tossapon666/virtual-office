const CACHE = 'virtual-office-v13';
const ASSETS = [
  '/static/app.css',
  '/static/login.css',
  '/static/icon.svg',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/manifest.webmanifest',
  '/static/js/core.js',
  '/static/js/views.js',
  '/static/js/dashboard.js',
  '/static/js/modals.js',
  '/static/js/agent.js',
  '/static/js/events.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(ASSETS))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (!url.pathname.startsWith('/static/')) return;

  // network-first: ได้โค้ดใหม่ทันทีเมื่อออนไลน์ และใช้ cache เมื่อออฟไลน์
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req).then((cached) => cached || new Response('offline', { status: 503 })))
  );
});
