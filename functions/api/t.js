/* Esports Scoreboard time-on-site beacon (Cloudflare Pages Function, POST /api/t). Nov 13, 2026.
   Body (text/plain JSON, <= 512 bytes): {"p": "<route, e.g. team/cs2/...>", "s": <seconds visible>, "v": 1 on the first beacon of a page view else 0, "d": "m"|"d"}
   Privacy: no cookies, nothing set on the visitor, no IP address, no user agent and no country stored - only route,
   section, device class (phone/desktop by screen width) and seconds. Bots/crawlers (by user agent) are ignored.
   Storage: Workers Analytics Engine through the binding ESB_TIME (dataset esb_time_on_site). If the binding is not
   configured on the Pages project the function accepts the beacon and stores nothing. Always answers 204. */
const BOT = /bot|crawl|spider|slurp|preview|headless|lighthouse|pagespeed|curl|wget|python|httpclient|axios|node-fetch|undici|go-http|okhttp|java\/|libwww|facebookexternalhit|embedly|monitor|uptime|pingdom|scan|fetch|archiver|validator/i;
const ROUTE = /^[a-z0-9][a-z0-9._~%\/-]{0,119}$/i;
const SECTIONS = ["home", "cs2", "valorant", "wow", "wow-forever", "news", "team", "player", "match", "guild", "roundup", "search", "forums", "about", "recruiting", "status"];

function done() { return new Response(null, { status: 204, headers: { "Cache-Control": "no-store" } }); }

export async function onRequest(ctx) {
  const { request, env } = ctx;
  if (request.method !== "POST") return new Response(null, { status: 405, headers: { Allow: "POST", "Cache-Control": "no-store" } });
  try {
    const ua = request.headers.get("user-agent") || "";
    if (!ua || BOT.test(ua)) return done();
    const cf = request.cf || {};
    if (cf.botManagement && cf.botManagement.verifiedBot) return done();
    const origin = request.headers.get("origin");
    if (origin && new URL(origin).host !== new URL(request.url).host) return done();   // only beacons from our own pages
    if (+(request.headers.get("content-length") || 0) > 512) return done();
    const body = JSON.parse((await request.text()).slice(0, 512));
    let p = String(body.p || "home").replace(/^[#\/]+/, "").split(/[?#]/)[0];
    if (!ROUTE.test(p)) p = "other";
    const top = p.split("/")[0];
    const section = SECTIONS.indexOf(top) >= 0 ? (top === "team" || top === "player" || top === "match" ? top + "/" + (p.split("/")[1] || "") : top) : "other";
    const s = Math.round(Number(body.s));
    if (!(s >= 1 && s <= 1800)) return done();
    const dev = body.d === "m" ? "phone" : "desktop";
    if (env && env.ESB_TIME && typeof env.ESB_TIME.writeDataPoint === "function") {
      env.ESB_TIME.writeDataPoint({ blobs: [p, section, dev], doubles: [s, body.v === 0 ? 0 : 1], indexes: [section] });
    }
  } catch (e) { /* malformed beacon: ignore */ }
  return done();
}
