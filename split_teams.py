"""Audit 2 A6: split the lazy teams.json into per-region browser files (teams-na.js, teams-eu.js).

teams.json / teams.js stay whole (build steps, last-good cache, older pages). The app loads only the
region a page needs (a team page or a Top Players region); pages that need everything load all parts.
Same data, nothing added: each part has that region's player rows, match lines and team rosters."""
import json, os, sys

def regions_of_teams(data, tx):
    reg = {}
    for d in ((data.get("cs") or {}).get("divisions") or []):
        for t in d.get("teams") or []:
            if t.get("id"):
                reg.setdefault(t["id"], set()).add(d.get("region"))
    for m in (tx.get("matches") or []) + (tx.get("upcoming") or []):
        for k in ("t1", "t2"):
            tid = (m.get(k) or {}).get("id")
            if tid:
                reg.setdefault(tid, set()).add(m.get("region"))
    for p in tx.get("players") or []:
        cols = tx.get("player_cols") or []
        if "team_id" in cols and p[cols.index("team_id")]:
            reg.setdefault(p[cols.index("team_id")], set()).add(p[cols.index("region")])
    return reg

def split(dist):
    tx = json.load(open(os.path.join(dist, "teams.json"), encoding="utf-8"))
    data = json.load(open(os.path.join(dist, "data.json"), encoding="utf-8"))
    cols = tx.get("player_cols") or []
    ri = cols.index("region") if "region" in cols else 1
    reg = regions_of_teams(data, tx)
    regions = sorted({p[ri] for p in tx.get("players") or []} | {m.get("region") for m in tx.get("matches") or []} - {None})
    out = {}
    for r in regions:
        part = {k: v for k, v in tx.items() if k not in ("rosters", "matches", "upcoming", "players")}
        part["region"] = r
        part["players"] = [p for p in tx.get("players") or [] if p[ri] == r]
        part["matches"] = [m for m in tx.get("matches") or [] if m.get("region") == r]
        part["upcoming"] = [m for m in tx.get("upcoming") or [] if m.get("region") == r]
        part["rosters"] = {tid: v for tid, v in (tx.get("rosters") or {}).items() if r in reg.get(tid, {r})}
        blob = json.dumps(part, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        name = "teams-" + r.lower() + ".js"
        open(os.path.join(dist, name), "w", encoding="utf-8").write(
            "(window.FRAGNET_TXP = window.FRAGNET_TXP || {})[" + json.dumps(r) + "] = " + blob + ";\n")
        out[name] = len(blob)
    print("[split_teams] " + ", ".join(f"{k} {v // 1024} KB" for k, v in out.items()))
    return out

if __name__ == "__main__":
    split(sys.argv[1] if len(sys.argv) > 1 else "dist")
