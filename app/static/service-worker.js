const CACHE_NAME = 'voxdoc-cache-v2';
const ASSETS_TO_CACHE = [
    '/',
    '/static/index.html',
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/icon.svg',
    'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap',
    'https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(ASSETS_TO_CACHE))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    // We only want to cache GET requests for static assets
    if (event.request.method !== 'GET') return;

    // API calls bypass cache and go straight to network (handled via app.js retry queue)
    if (event.request.url.includes('/api/')) return;

    // WebSocket bypasses cache
    if (event.request.url.includes('/ws/')) return;

    event.respondWith(
        caches.match(event.request)
            .then((cachedResponse) => {
                if (cachedResponse) {
                    return cachedResponse; // Cache hit
                }

                return fetch(event.request).then((response) => {
                    // Check if valid response
                    if (!response || response.status !== 200 || response.type !== 'basic') {
                        return response;
                    }

                    // Clone response and add to cache
                    const responseToCache = response.clone();
                    caches.open(CACHE_NAME)
                        .then((cache) => {
                            cache.put(event.request, responseToCache);
                        });

                    return response;
                });
            })
            // Fallback for when offline and resource not cached (e.g. initial load without network)
            .catch(() => {
                // If it's a page navigation request, return index.html
                if (event.request.mode === 'navigate') {
                    return caches.match('/static/index.html');
                }
            })
    );
});
