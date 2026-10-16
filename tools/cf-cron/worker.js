// Backup refresh trigger: every 30 min, dispatch deploy.yml unless a run is queued/in progress.
// Secret: GH_DISPATCH_TOKEN (fine-grained PAT, only winecoolermike/fragnet, Actions: read & write).
const REPO = "winecoolermike/fragnet", WF = "deploy.yml", REF = "main";
const ACTIVE = ["queued", "in_progress", "waiting", "pending", "requested"];

export async function decideAndDispatch(env, fetchFn = fetch) {
  if (!env.GH_DISPATCH_TOKEN) return "error: GH_DISPATCH_TOKEN missing";
  const h = { Authorization: "Bearer " + env.GH_DISPATCH_TOKEN, Accept: "application/vnd.github+json",
              "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "esb-cf-cron" };
  const base = `https://api.github.com/repos/${REPO}/actions/workflows/${WF}`;
  for (const s of ACTIVE) {
    const r = await fetchFn(`${base}/runs?status=${s}&per_page=1`, { headers: h });
    if (!r.ok) return `error: list ${s} HTTP ${r.status}`;
    const j = await r.json();
    if ((j.total_count || 0) > 0) return `skip: run ${s}`;
  }
  const d = await fetchFn(`${base}/dispatches`, { method: "POST", headers: { ...h, "Content-Type": "application/json" }, body: JSON.stringify({ ref: REF }) });
  return d.status === 204 ? "dispatched" : `error: dispatch HTTP ${d.status}`;
}

export default {
  async scheduled(event, env, ctx) { console.log(await decideAndDispatch(env)); },
  async fetch() { return new Response("ok", { status: 200 }); }   // no public trigger
};
