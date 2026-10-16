import { decideAndDispatch } from "./worker.js";
const mk = (active) => { const calls = []; return { calls, f: async (u, o = {}) => { calls.push((o.method || "GET") + " " + u);
  if (u.endsWith("/dispatches")) return { status: 204, ok: true };
  const s = new URL(u).searchParams.get("status"); return { ok: true, json: async () => ({ total_count: s === active ? 1 : 0 }) }; } }; };
let m = mk(null); console.assert(await decideAndDispatch({ GH_DISPATCH_TOKEN: "x" }, m.f) === "dispatched");
m = mk("in_progress"); const r = await decideAndDispatch({ GH_DISPATCH_TOKEN: "x" }, m.f);
console.assert(r === "skip: run in_progress" && !m.calls.some(c => c.startsWith("POST")), r);
console.assert((await decideAndDispatch({}, m.f)).startsWith("error"));
console.log("PASS cf-cron logic");
