/* Esports Scoreboard service worker (R10): network-first for everything same-origin, so online
   visitors always get fresh files; the last good copy is used only when the network fails.
   The page itself shows the data age (fetched_at / STALE badges) and an "Offline" note. No background sync. */
var CACHE = "esb-v1";
var SHELL = ["./", "index.html", "app.js", "style.css", "favicon.svg", "data.json", "manifest.webmanifest", "icon-192.png"];
self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) { return Promise.all(SHELL.map(function (u) { return c.add(u).catch(function () {}); })); }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (ks) { return Promise.all(ks.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); })); }).then(function () { return self.clients.claim(); }));
});
self.addEventListener("fetch", function (e) {
  var r = e.request, u = new URL(r.url);
  if (r.method !== "GET" || u.origin !== self.location.origin || /\/og\//.test(u.pathname)) return;
  e.respondWith(fetch(r).then(function (res) {
    if (res && res.ok && res.type === "basic") { var copy = res.clone(); caches.open(CACHE).then(function (c) { c.put(r, copy); }); }
    return res;
  }).catch(function () {
    return caches.match(r, { ignoreSearch: true }).then(function (hit) {
      return hit || (r.mode === "navigate" ? caches.match("index.html") : undefined) || Response.error();
    });
  }));
});
