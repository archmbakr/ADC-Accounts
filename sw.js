/* ADC accounts — offline shell cache. version 20261002104937 */
const CACHE = 'adc-app-20261002104937';
const SHELL = ['./', './index.html', './manifest.webmanifest', './icon-192.png', './icon-512.png', './apple-touch-icon.png', 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.js'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => Promise.all(SHELL.map(u => c.add(new Request(u, { mode: u.startsWith('http') ? 'cors' : 'same-origin' })).catch(() => {})))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith('adc-app-') && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const r = e.request;
  if (r.method !== 'GET') return;
  const u = new URL(r.url);
  if (u.hostname.endsWith('supabase.co') || u.hostname.endsWith('supabase.in')) return; // data: always live
  if (r.mode === 'navigate') {
    const net = fetch(r).then(res => { if (res && res.ok) { const cp = res.clone(); caches.open(CACHE).then(c => c.put('./index.html', cp)); } return res; });
    const fallback = () => caches.match('./index.html', { ignoreSearch: true, ignoreVary: true });
    e.respondWith(new Promise(resolve => {
      let done = false;
      const t = setTimeout(() => { fallback().then(c => { if (c && !done) { done = true; resolve(c); } }); }, 4000);
      net.then(res => { if (!done) { done = true; clearTimeout(t); resolve(res); } })
         .catch(() => fallback().then(c => { if (!done) { done = true; clearTimeout(t); resolve(c || Response.error()); } }));
    }));
    return;
  }
  const same = u.origin === location.origin;
  const cdn = /(^|\.)(jsdelivr\.net|unpkg\.com|fonts\.googleapis\.com|fonts\.gstatic\.com)$/.test(u.hostname);
  if (!same && !cdn) return;
  e.respondWith(caches.match(r, { ignoreVary: true }).then(hit => {
    const net = fetch(r).then(res => { if (res && (res.ok || res.type === 'opaque')) { const cp = res.clone(); caches.open(CACHE).then(c => c.put(r, cp)); } return res; }).catch(() => hit);
    return hit || net;
  }));
});
