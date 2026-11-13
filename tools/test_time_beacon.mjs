// Local test of functions/api/t.js with a fake Analytics Engine binding (node tools/test_time_beacon.mjs). Never deployed.
import { onRequest } from "../functions/api/t.js";
const pts = [];
const env = { ESB_TIME: { writeDataPoint: (d) => pts.push(d) } };
const UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";
async function hit(body, ua = UA, extra = {}, method = "POST", e = env) {
  const r = new Request("https://esportsscoreboard.com/api/t", { method, headers: { "user-agent": ua, origin: "https://esportsscoreboard.com", ...extra }, body: method === "POST" ? body : undefined });
  return (await onRequest({ request: r, env: e })).status;
}
const cases = [
  ["human team page", JSON.stringify({ p: "team/cs2/abc-12345678", s: 42, v: 1, d: "m" }), UA, {}, 1],
  ["second beacon same view", JSON.stringify({ p: "team/cs2/abc-12345678", s: 5, v: 0, d: "m" }), UA, {}, 1],
  ["Googlebot ignored", JSON.stringify({ p: "home", s: 10 }), "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", {}, 0],
  ["GPTBot ignored", JSON.stringify({ p: "home", s: 10 }), "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2)", {}, 0],
  ["headless ignored", JSON.stringify({ p: "home", s: 10 }), "Mozilla/5.0 HeadlessChrome/131.0", {}, 0],
  ["no UA ignored", JSON.stringify({ p: "home", s: 10 }), "", {}, 0],
  ["other origin ignored", JSON.stringify({ p: "home", s: 10 }), UA, { origin: "https://evil.example" }, 0],
  ["0 seconds ignored", JSON.stringify({ p: "home", s: 0 }), UA, {}, 0],
  ["too long ignored", JSON.stringify({ p: "home", s: 99999 }), UA, {}, 0],
  ["junk body ignored", "not json", UA, {}, 0],
  ["weird route -> other", JSON.stringify({ p: "<script>", s: 3 }), UA, {}, 1],
];
let fail = 0;
for (const [name, body, ua, extra, want] of cases) {
  const before = pts.length, st = await hit(body, ua, extra);
  const got = pts.length - before, ok = st === 204 && got === want;
  if (!ok) fail++;
  console.log((ok ? "ok  " : "FAIL") + " " + name + " -> " + st + ", " + got + " point(s)");
}
const g = await hit(null, UA, {}, "GET"); console.log((g === 405 ? "ok  " : "FAIL") + " GET -> " + g); if (g !== 405) fail++;
const nb = await hit(JSON.stringify({ p: "home", s: 3 }), UA, {}, "POST", {}); console.log((nb === 204 ? "ok  " : "FAIL") + " no binding -> " + nb + " (stores nothing)");
console.log("stored:", JSON.stringify(pts));
console.log("no IP / UA / country in any stored point:", pts.every((p) => !JSON.stringify(p).match(/Mozilla|\d+\.\d+\.\d+\.\d+/)));
process.exit(fail ? 1 : 0);
