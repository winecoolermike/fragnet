#!/usr/bin/env python3
"""v5.2 spotlights + weekly roundups (Esports Scoreboard), computed only from tracked data.

Writes dist/spot.json + dist/spot.js (window.ESB_SPOT). Template text only, no invented facts.
- Upset: winner was OUTSIDE the top 5 and the loser INSIDE the top 5 of their division/conference
  table built from the results tracked here before that match (3 points per win; ties share a rank;
  both teams must have played before). Biggest rank gap first.
- Top fragger: most kills per division in matches with FACEIT scoreboards (tiebreak K/D).
- Hottest streak: longest current CS2 win streak in tracked results (3+ wins).
- WoW kills: Mythic boss kills dated in the period by the tracked US/EU top guilds (Raider.IO).
Weeks are ISO weeks (Mon-Sun) in Pacific Time. A week is listed only if tracked results cover it
fully (oldest tracked result is before the week began), plus the current week marked "so far".

Usage: python spotlight.py dist
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
MIN_PLAYED = 3
UPSET_RULE = ("Upset = a team outside the top 5 beats a top-5 team, by the division table built from the results tracked here "
              "before that match (3 points per win, ties share a rank). Both teams must have played at least 3 matches; "
              "forfeits and 13:0 results without FACEIT match stats never count.")


def ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def cs_results(data, teams):
    seen, out = set(), []
    for m in ((data.get("cs") or {}).get("matches") or []) + ((teams or {}).get("matches") or []):
        if not m or m.get("id") in seen or m.get("winner") not in (1, 2) or not ts(m.get("t")):
            continue
        seen.add(m["id"])
        out.append(m)
    return sorted(out, key=lambda m: m["t"])


def div_key(m):
    return (m.get("region"), m.get("division"), m.get("conf"))


def upsets(results, start, end):
    pts, played, out = {}, {}, []
    for m in results:
        k, t = div_key(m), ts(m["t"])
        a, b = m["t1"]["id"], m["t2"]["id"]
        table = pts.setdefault(k, {})
        if start <= t < end:
            w, l = (m["t1"], m["t2"]) if m["winner"] == 1 else (m["t2"], m["t1"])
            s1, s2 = int(m.get("s1") or 0), int(m.get("s2") or 0)
            ff = s1 + s2 <= 1 or m.get("nostats") or (min(s1, s2) == 0 and not m.get("maps"))
            if played.get(w["id"], 0) >= MIN_PLAYED and played.get(l["id"], 0) >= MIN_PLAYED and not ff:
                rank = lambda tid: 1 + sum(1 for v in table.values() if v > table.get(tid, 0))
                rw, rl = rank(w["id"]), rank(l["id"])
                if rl <= 5 and rw > 5:
                    out.append({"id": m["id"], "region": m["region"], "division": m["division"], "conf": m.get("conf"), "t": m["t"],
                                "winner": {"id": w["id"], "name": w["name"], "rank": rw}, "loser": {"id": l["id"], "name": l["name"], "rank": rl},
                                "score": f"{m.get('s1')}:{m.get('s2')}" if m["winner"] == 1 else f"{m.get('s2')}:{m.get('s1')}"})
        for tid in (a, b):
            table.setdefault(tid, 0)
            played[tid] = played.get(tid, 0) + 1
        table[m["t1"]["id"] if m["winner"] == 1 else m["t2"]["id"]] += 3
    return sorted(out, key=lambda u: (u["winner"]["rank"] - u["loser"]["rank"]), reverse=True)


def fraggers(results, start, end):
    per = {}
    for m in results:
        t = ts(m["t"])
        if not (start <= t < end) or not m.get("maps"):
            continue
        d = f"{m['region']} {m['division']}"
        for mp in m["maps"]:
            for side, team in (("p1", m["t1"]), ("p2", m["t2"])):
                for row in mp.get(side) or []:
                    if not row or len(row) < 3:
                        continue
                    p = per.setdefault(d, {}).setdefault(row[0], {"nick": row[0], "team": team["name"], "team_id": team["id"], "kills": 0, "deaths": 0, "maps": 0, "best": None, "best_k": -1})
                    p["kills"] += int(row[1] or 0); p["deaths"] += int(row[2] or 0); p["maps"] += 1
                    if int(row[1] or 0) > p["best_k"]:
                        p["best_k"], p["best"] = int(row[1] or 0), m["id"]
    out = []
    for d, ps in sorted(per.items()):
        top = max(ps.values(), key=lambda p: (p["kills"], p["kills"] / max(1, p["deaths"])))
        out.append({"div": d, "nick": top["nick"], "team": top["team"], "team_id": top["team_id"], "kills": top["kills"], "deaths": top["deaths"], "maps": top["maps"], "match": top["best"]})
    return out


def streaks(results, upto, n=5):
    last = {}
    for m in results:
        if ts(m["t"]) >= upto:
            continue
        for side, tm in ((1, m["t1"]), (2, m["t2"])):
            s = last.setdefault(tm["id"], {"id": tm["id"], "name": tm["name"], "div": f"{m['region']} {m['division']}", "n": 0, "last": None})
            s["n"] = s["n"] + 1 if m["winner"] == side else 0
            s["last"] = m["id"]
    top = sorted((s for s in last.values() if s["n"] >= 3), key=lambda s: (-s["n"], s["name"].lower()))
    return top[:n]


def wow_kills(data, start, end):
    raid = (data.get("wow") or {}).get("raid") or {}
    bosses = raid.get("bosses") or []
    out, total = [], 0
    for reg, rows in ((data.get("wow") or {}).get("rankings") or {}).items():
        for g in rows or []:
            ks = [(i, ts(d)) for i, d in enumerate(g.get("kill_dates") or [])]
            ks = [(i, t) for i, t in ks if t and start <= t < end]
            if not ks:
                continue
            total += len(ks)
            out.append({"guild": g.get("guild"), "region": reg, "realm_slug": g.get("realm_slug"), "realm": g.get("realm"), "url": g.get("url"), "progress": g.get("progress"),
                        "kills": len(ks), "bosses": [bosses[i] for i, _ in sorted(ks, key=lambda x: x[1]) if i < len(bosses)], "last": max(t for _, t in ks).isoformat()})
    out.sort(key=lambda g: (-g["kills"], g["last"]))
    return {"raid": raid.get("name"), "kills": total, "guilds": out[:8]}


def block(data, results, start, end):
    inp = [m for m in results if start <= ts(m["t"]) < end]
    return {"start": start.isoformat(), "end": end.isoformat(), "cs_matches": len(inp), "cs_with_scoreboards": sum(1 for m in inp if m.get("maps")),
            "upsets": upsets(results, start, end)[:5], "fraggers": fraggers(results, start, end), "streaks": streaks(results, end), "wow": wow_kills(data, start, end)}


def week_start(dt):
    lp = dt.astimezone(PT)
    d0 = (lp - timedelta(days=lp.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return d0


def build(data, teams, now=None):
    now = now or datetime.now(timezone.utc)
    res = cs_results(data, teams)
    out = {"generated": now.isoformat(timespec="seconds"), "upset_rule": UPSET_RULE, "last7": block(data, res, now - timedelta(days=7), now), "weeks": []}
    if not res:
        return out
    oldest = ts(res[0]["t"])
    ws = week_start(now)
    while True:
        we = ws + timedelta(days=7)
        cur = we > now
        if not cur and ws.astimezone(timezone.utc) < oldest:
            break
        iso = ws.isocalendar()
        b = block(data, res, ws.astimezone(timezone.utc), min(we.astimezone(timezone.utc), now))
        if b["cs_matches"] or b["wow"]["kills"]:
            out["weeks"].append({"id": f"{iso[0]}-w{iso[1]:02d}", "label": f"{ws:%b} {ws.day} - {(we - timedelta(days=1)):%b} {(we - timedelta(days=1)).day}, {(we - timedelta(days=1)).year}",
                                 "current": cur, **b})
        ws -= timedelta(days=7)
        if len(out["weeks"]) >= 26:
            break
    return out


def merge_archive(sp, archive_dir, write=True):
    """Completed weeks are frozen in archive_dir/YYYY-wNN.json (committed by Actions, append-only):
    an archived week always wins over a recomputed one, and weeks that rolled out of the tracked data stay listed.
    Returns the ids of newly archived weeks."""
    import re as _re
    old = {}
    if os.path.isdir(archive_dir):
        for f in sorted(os.listdir(archive_dir)):
            if _re.match(r"^\d{4}-w\d{2}\.json$", f):
                try:
                    w = json.load(open(os.path.join(archive_dir, f), encoding="utf-8"))
                    if w.get("id") == f[:-5]:
                        old[w["id"]] = w
                except (OSError, ValueError):
                    pass
    new = []
    for w in sp["weeks"]:
        if not w.get("current") and w["id"] not in old:
            old[w["id"]] = w
            new.append(w["id"])
            if write:
                os.makedirs(archive_dir, exist_ok=True)
                with open(os.path.join(archive_dir, w["id"] + ".json"), "w", encoding="utf-8") as fh:
                    json.dump(w, fh, ensure_ascii=False, indent=1, sort_keys=True)
                    fh.write("\n")
    cur = [w for w in sp["weeks"] if w.get("current")]
    sp["weeks"] = cur + sorted(old.values(), key=lambda w: w["id"], reverse=True)
    return new


def main(argv=None):
    argv = argv or sys.argv[1:]
    archive = None
    if "--archive" in argv:
        i = argv.index("--archive"); archive = argv[i + 1]; argv = argv[:i] + argv[i + 2:]
    dist = argv[0] if argv else "dist"
    data = json.load(open(os.path.join(dist, "data.json"), encoding="utf-8"))
    try:
        teams = json.load(open(os.path.join(dist, "teams.json"), encoding="utf-8"))
    except Exception:
        teams = None
    sp = build(data, teams)
    new = merge_archive(sp, archive) if archive else []
    if new:
        print(f"[spotlight] archived new weeks: {', '.join(new)}")
    blob = json.dumps(sp, ensure_ascii=False, separators=(",", ":"))
    open(os.path.join(dist, "spot.json"), "w", encoding="utf-8").write(blob)
    open(os.path.join(dist, "spot.js"), "w", encoding="utf-8").write("window.ESB_SPOT = " + blob.replace("</", "<\\/") + ";\n")
    l7 = sp["last7"]
    print(f"[spotlight] last 7 days: {l7['cs_matches']} CS results, {len(l7['upsets'])} upsets, {len(l7['fraggers'])} division fraggers, "
          f"{len(l7['streaks'])} streaks, {l7['wow']['kills']} WoW kills; {len(sp['weeks'])} roundup weeks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
