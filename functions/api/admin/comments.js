/* Esports Scoreboard comment moderation (Cloudflare Pages Function, /api/admin/comments). Nov 20, 2026 (v5.18).
   Every call needs the header "X-Admin-Key: <ESB_ADMIN_KEY>" (a Pages secret; never in the repo or the page).
   GET    /api/admin/comments            -> newest 200 comments across all matches {items:[{id, m, name, body, t}]}
   DELETE /api/admin/comments?id=<n>     -> removes one comment {ok, deleted}
   Used by the /admin/comments page. Without the D1 binding ESB_DB it answers {enabled:false}. */
function json(obj, status) {
  return new Response(JSON.stringify(obj), { status: status || 200, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex" } });
}
async function same(a, b) {   // constant-time compare through SHA-256 digests
  const enc = new TextEncoder();
  const [x, y] = await Promise.all([crypto.subtle.digest("SHA-256", enc.encode(String(a))), crypto.subtle.digest("SHA-256", enc.encode(String(b)))]);
  const u = new Uint8Array(x), v = new Uint8Array(y);
  let d = 0;
  for (let i = 0; i < u.length; i++) d |= u[i] ^ v[i];
  return d === 0;
}
export async function onRequest(ctx) {
  const { request, env } = ctx;
  if (!env || !env.ESB_ADMIN_KEY) return json({ error: "Admin key is not set up on the server." }, 503);
  const key = request.headers.get("x-admin-key") || "";
  if (!key || !(await same(key, env.ESB_ADMIN_KEY))) {
    await new Promise((r) => setTimeout(r, 800));
    return json({ error: "Wrong admin key." }, 403);
  }
  const db = env.ESB_DB;
  if (!db || typeof db.prepare !== "function") return json({ enabled: false, error: "Comment storage (D1) is not connected yet." });
  try {
    await db.prepare("CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, match TEXT NOT NULL, name TEXT NOT NULL, body TEXT NOT NULL, created INTEGER NOT NULL, iph TEXT NOT NULL)").run();
  } catch (e) { return json({ enabled: false, error: "Comment storage is not reachable." }, 503); }
  const url = new URL(request.url);
  if (request.method === "GET") {
    const rs = await db.prepare("SELECT id, match, name, body, created FROM comments ORDER BY created DESC, id DESC LIMIT 200").all();
    return json({ enabled: true, items: (rs.results || []).map((r) => ({ id: r.id, m: r.match, name: r.name, body: r.body, t: r.created })) });
  }
  if (request.method === "DELETE" || request.method === "POST") {
    const id = parseInt(url.searchParams.get("id") || "", 10);
    if (!(id > 0)) return json({ error: "Missing comment id." }, 400);
    const r = await db.prepare("DELETE FROM comments WHERE id = ?").bind(id).run();
    return json({ ok: true, deleted: (r && r.meta && r.meta.changes) || 0 });
  }
  return json({ error: "method" }, 405);
}
