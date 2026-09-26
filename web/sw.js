// Service worker: makes the app installable and makes the shell load offline.
//
// It caches the shell ONLY -- html, css, js, icon. It must never cache the
// WebSocket or any API response: this app's entire value is live evidence,
// and a stale verdict served from a cache would be worse than no verdict.

const SHELL = "cap-shell-v3";
const FILES = [
  "/",
  "/index.html",
  "/css/tokens.css",
  "/css/app.css",
  "/js/app.js",
  "/js/sound.js",
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
  // `cache: "reload"` bypasses the browser's OWN http cache, not just ours.
  // The static server sends no cache-control, so browsers fall back to
  // heuristic freshness and happily serve yesterday's app.js -- which is
  // exactly what happened: a fix was deleted, pushed and still on screen
  // hours later, on a page whose own service worker was network-first.
  // Network-first is worthless if the network layer is lying to you.
  const fresh = new Request(ev.request, { cache: "reload" });

  ev.respondWith(
    fetch(fresh)
      .then((res) => {
        const copy = res.clone();
        caches.open(SHELL).then((c) => c.put(ev.request, copy));
        return res;
      })
      .catch(() => caches.match(ev.request).then((hit) => hit || caches.match("/")))
  );
});
