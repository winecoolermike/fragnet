/* Esports Scoreboard prediction comments (Cloudflare Pages Function, /api/comments). Nov 20, 2026 (v5.18).
   GET  /api/comments?m=<match id>          -> {enabled, count, items:[{id, name, body, t}]} newest first (max 100)
   GET  /api/comments?counts=<id>,<id>,...  -> {enabled, counts:{id: n}} (max 60 ids)
   POST /api/comments  JSON {m, name, body, website}  (website = honeypot, must stay empty)
   Storage: D1 through the binding ESB_DB (free tier). Without the binding every call answers {enabled:false}
   and the site shows no comment box at all. No sign-in, no email, no cookies. The visitor IP is never stored:
   only an HMAC-SHA-256 of it (keyed with ESB_ADMIN_KEY) is kept for the rate limit (3 a minute, 20 a day).
   Posting is allowed only on matches listed in the current predictions.json or that already have comments.
   Output is plain JSON text; the page escapes every field before showing it. */
const ID = /^[0-9a-z-]{8,48}$/i;
const LINK = /(https?:|www\.|\[url|<a\s|href=|\b[a-z0-9-]{2,}(\.|\s*\(dot\)\s*|\s*\[dot\]\s*)(com|net|org|gg|io|ru|xyz|ly|co|me|tv|info|biz|top|shop|site|online|link|click|app|dev|cn|tk|ml|ga|cf|gq|uk|de|fr|us|ca|bit)\b|discord\.gg|t\.me\/)/i;
const SPAMWORDS = /\b(viagra|casino|crypto ?airdrop|free ?skins?|skin ?giveaway|betting ?tips|onlyfans|telegram|whatsapp|earn \$|make money)\b/i;
let READY = false;

function json(obj, status, extra) {
  return new Response(JSON.stringify(obj), { status: status || 200, headers: Object.assign({
    "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" }, extra || {}) });
}
async function setup(db) {
  if (READY) return;
  await db.batch([
    db.prepare("CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, match TEXT NOT NULL, name TEXT NOT NULL, body TEXT NOT NULL, created INTEGER NOT NULL, iph TEXT NOT NULL)"),
    db.prepare("CREATE INDEX IF NOT EXISTS comments_match ON comments (match, created)"),
    db.prepare("CREATE INDEX IF NOT EXISTS comments_iph ON comments (iph, created)"),
    db.prepare("CREATE TABLE IF NOT EXISTS hits (iph TEXT NOT NULL, created INTEGER NOT NULL)"),
    db.prepare("CREATE INDEX IF NOT EXISTS hits_iph ON hits (iph, created)")
  ]);
  READY = true;
}
function clean(s, max) {
  s = String(s == null ? "" : s).replace(/\r\n?/g, "\n").replace(/[\u0000-\u0009\u000B-\u001F\u007F\u200B-\u200F\u202A-\u202E\u2066-\u2069]/g, "");
  s = s.replace(/\n{3,}/g, "\n\n").replace(/[ \t]{2,}/g, " ").trim();
  return s.length > max ? null : s;
}
async function ipHash(ip, secret) {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret || "esb-comments"), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode("ip:" + ip)));
  return Array.from(sig.slice(0, 16), (b) => b.toString(16).padStart(2, "0")).join("");
}
async function knownMatch(ctx, id) {
  try {
    const r = await ctx.env.ASSETS.fetch(new URL("/predictions.json", ctx.request.url));
    if (!r.ok) return false;
    const p = await r.json();
    return (p.matches || []).some((m) => m.id === id);
  } catch (e) { return false; }
}

export async function onRequest(ctx) {
  const { request, env } = ctx;
  const db = env && env.ESB_DB;
  const url = new URL(request.url);
  if (request.method !== "GET" && request.method !== "POST") return json({ error: "method" }, 405, { Allow: "GET, POST" });
  if (!db || typeof db.prepare !== "function") return json({ enabled: false });
  try { await setup(db); } catch (e) { return json({ enabled: false }); }

  if (request.method === "GET") {
    const counts = url.searchParams.get("counts");
    if (counts != null) {
      const ids = counts.split(",").filter((x) => ID.test(x)).slice(0, 60);
      const out = {};
      if (ids.length) {
        const rs = await db.prepare("SELECT match, COUNT(*) AS n FROM comments WHERE match IN (" + ids.map(() => "?").join(",") + ") GROUP BY match").bind(...ids).all();
        (rs.results || []).forEach((r) => { out[r.match] = r.n; });
      }
      return json({ enabled: true, counts: out });
    }
    const m = url.searchParams.get("m") || "";
    if (!ID.test(m)) return json({ error: "bad match" }, 400);
    const rs = await db.prepare("SELECT id, name, body, created FROM comments WHERE match = ? ORDER BY created DESC, id DESC LIMIT 100").bind(m).all();
    const cnt = await db.prepare("SELECT COUNT(*) AS n FROM comments WHERE match = ?").bind(m).first();
    return json({ enabled: true, count: (cnt && cnt.n) || 0, items: (rs.results || []).map((r) => ({ id: r.id, name: r.name, body: r.body, t: r.created })) });
  }

  // POST
  const origin = request.headers.get("origin");
  try { if (!origin || new URL(origin).host !== url.host) return json({ error: "Posting is only allowed from this site." }, 403); } catch (e) { return json({ error: "Posting is only allowed from this site." }, 403); }
  if (+(request.headers.get("content-length") || 0) > 4096) return json({ error: "Too long." }, 413);
  let body;
  try { body = JSON.parse((await request.text()).slice(0, 4096)); } catch (e) { return json({ error: "Bad request." }, 400); }
  if (body.website) return json({ ok: true, held: true });   // honeypot: pretend it worked
  const m = String(body.m || "");
  if (!ID.test(m)) return json({ error: "Unknown match." }, 400);
  const name = clean(body.name, 30), text = clean(body.body, 500);
  if (name === null) return json({ error: "Name: 30 characters at most." }, 400);
  if (text === null) return json({ error: "Comment: 500 characters at most." }, 400);
  if (name.length < 2) return json({ error: "Please add a name (2 to 30 characters)." }, 400);
  if (text.length < 2) return json({ error: "Please write a comment." }, 400);
  if (LINK.test(name) || LINK.test(text)) return json({ error: "Links and web addresses are not allowed in comments." }, 400);
  if (SPAMWORDS.test(name + " " + text) || /(.)\1{14,}/.test(text) || (text.match(/@/g) || []).length > 3) return json({ error: "That looks like spam, so it was not posted." }, 400);
  const ip = request.headers.get("cf-connecting-ip") || "0.0.0.0";
  const iph = await ipHash(ip, env.ESB_ADMIN_KEY);
  const now = Date.now();
  const lim = await db.prepare("SELECT SUM(CASE WHEN created > ? THEN 1 ELSE 0 END) AS min1, COUNT(*) AS day FROM hits WHERE iph = ? AND created > ?").bind(now - 60000, iph, now - 86400000).first();
  if (lim && (lim.min1 || 0) >= 3) return json({ error: "Slow down a little: 3 comments a minute at most." }, 429);
  if (lim && (lim.day || 0) >= 20) return json({ error: "Daily limit reached (20 comments a day)." }, 429);
  const dup = await db.prepare("SELECT 1 AS x FROM comments WHERE iph = ? AND body = ? AND created > ? LIMIT 1").bind(iph, text, now - 86400000).first();
  if (dup) return json({ error: "You already posted that comment." }, 409);
  const has = await db.prepare("SELECT 1 AS x FROM comments WHERE match = ? LIMIT 1").bind(m).first();
  if (!has && !(await knownMatch(ctx, m))) return json({ error: "Comments are open on the current predictions only." }, 400);
  await db.batch([
    db.prepare("INSERT INTO hits (iph, created) VALUES (?, ?)").bind(iph, now),
    db.prepare("INSERT INTO comments (match, name, body, created, iph) VALUES (?, ?, ?, ?, ?)").bind(m, name, text, now, iph),
    db.prepare("DELETE FROM hits WHERE created < ?").bind(now - 2 * 86400000)
  ]);
  const row = await db.prepare("SELECT id FROM comments WHERE iph = ? AND created = ? ORDER BY id DESC LIMIT 1").bind(iph, now).first();
  return json({ ok: true, id: row && row.id, item: { id: row && row.id, name: name, body: text, t: now } }, 201);
}
