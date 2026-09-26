// Service worker: makes the app installable and makes the shell load offline.
//
// It caches the shell ONLY -- html, css, js, icon. It must never cache the
// WebSocket or any API response: this app's entire value is live evidence,
// and a stale verdict served from a cache would be worse than no verdict.

const SHELL = "cap-shell-v1";
const FILES = [
  "/",
  "/index.html",
  "/css/scaffold.css",
  "/js/app.js",
  "/js/ws.js",
  "/js/state.js",
  "/js/render.js",
  "/js/audio.js",
  "/js/pcm-worklet.js",
  "/manifest.json",
  "/icon.svg",
];

self.addEventListener("install", (ev) => {
  // addAll rejects the whole install if any one file 404s, which is the
  // behaviour we want: a half-cached shell is worse than none.
  ev.waitUntil(caches.open(SHELL).then((c) => c.addAll(FILES)));
  self.skipWaiting();
});

self.addEventListener("activate", (ev) => {
  ev.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (ev) => {
  const url = new URL(ev.request.url);

  // Never touch anything live.
  if (ev.request.method !== "GET") return;
  if (url.pathname === "/ws" || url.pathname.startsWith("/health")) return;

  // Network first, cache as the fallback. The other way round would serve a
  // stale app after a deploy, which during a hackathon is a nightmare you
  // cannot debug because your own browser is lying to you.
  ev.respondWith(
    fetch(ev.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(SHELL).then((c) => c.put(ev.request, copy));
        return res;
      })
      .catch(() => caches.match(ev.request).then((hit) => hit || caches.match("/")))
  );
});
