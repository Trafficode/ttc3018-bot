// Offline fallback contains no controller UI, status, credentials or job data.
const CACHE = 'bark-beetle-offline-v1';
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(['/offline.html','/offline.css'])));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('bark-beetle-offline-') && key !== CACHE).map(key => caches.delete(key)))));
});
self.addEventListener('fetch', event => {
  // All API, camera, file and action requests remain network-only. No retries,
  // background sync, cached application JS or queued machine commands.
  if (event.request.method !== 'GET') return;
  if (new URL(event.request.url).origin !== self.location.origin) return;
  if (new URL(event.request.url).pathname === '/offline.css') {
    event.respondWith(fetch(event.request).catch(() => caches.open(CACHE).then(cache => cache.match('/offline.css'))));
    return;
  }
  if (event.request.mode !== 'navigate') return;
  event.respondWith(fetch(event.request).then(response => {
    if (response.status >= 500) throw new Error('Station unavailable');
    return response;
  }).catch(() => caches.open(CACHE).then(cache => cache.match('/offline.html'))));
});
