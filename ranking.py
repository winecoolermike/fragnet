#!/usr/bin/env python3
"""v6 ESB Team Ranking + ESB Player Rating 1.0 (Esports Scoreboard), from real ESEA/FACEIT data only.

TEAM RANKING (Elo on maps):
  start = tier prior (Advanced 1600, Main 1450, Intermediate 1300); per map E = 1/(1+10^((Ro-R)/400)),
  R += K*(S-E)*M with K=32, S=1 win/0 loss, M = 1 + min(round diff, 10)/20 (margin cap 1.5x).
  Maps = per-map FACEIT scores; a Bo1 without map stats counts as one map from the series score.
  Forfeits and 13:0 results without stats are skipped. Ranked once a team has 3+ matches.
  Regions never play each other, so NA vs EU order comes only from the tier prior (disclosed).
PLAYER RATING 1.0 (season):
  0.30*KPR/avgKPR + 0.25*avgDPR/DPR + 0.30*ADR/avgADR + 0.10*KD/avgKD + 0.05*HS/avgHS,
  averages = round-weighted over the player's division (region + division), so the division average = 1.00.
  Min 20 rounds. Season Top 20 multiplies by a division-strength factor (Advanced 1.10, Main 1.00,
  Intermediate 0.90) and needs 60+ rounds. Per-map rating uses the same formula with map rounds.
Usage: python ranking.py dist [--archive rankings]
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

PRIOR = {"Advanced": 1600.0, "Main": 1450.0, "Intermediate": 1300.0}
K, MARGIN_CAP_ROUNDS = 32.0, 10
MIN_MATCHES, MIN_ROUNDS, TOP_MIN_ROUNDS = int(os.environ.get("ESB_RANK_MIN_MATCHES_TEST", 3)), 20, 60   # env override for local UI tests only
DIV_FACTOR = {"Advanced": 1.10, "Main": 1.00, "Intermediate": 0.90}
W = {"kpr": 0.30, "dpr": 0.25, "adr": 0.30, "kd": 0.10, "hs": 0.05}
FORMULA_TEAM = ("Elo on maps: start Advanced 1600 / Main 1450 / Intermediate 1300; per map R += 32 x (result - expected) x "
                "(1 + min(round diff, 10)/20); expected = 1/(1+10^((opp - R)/400)); forfeits skipped; ranked after 3 matches.")
FORMULA_PLAYER = ("Rating 1.0 = 0.30 KPR/avg + 0.25 avg/DPR + 0.30 ADR/avg + 0.10 K/D/avg + 0.05 HS%/avg, averages over the player's "
                  "division (so division average = 1.00); min 20 rounds. Season Top 20: x1.10 Advanced, x1.00 Main, x0.90 Intermediate, min 60 rounds.")


def ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def finished(data, teams):
    seen, out = set(), []
    for m in ((data.get("cs") or {}).get("matches") or []) + ((teams or {}).get("matches") or []):
        if m and m.get("id") not in seen and m.get("winner") in (1, 2) and ts(m.get("t")) and m.get("t1") and m.get("t2"):
            seen.add(m["id"]); out.append(m)
    return sorted(out, key=lambda m: m["t"])


def is_skip(m):
    s1, s2 = int(m.get("s1") or 0), int(m.get("s2") or 0)
    return s1 + s2 <= 1 or m.get("nostats") or (min(s1, s2) == 0 and not m.get("maps"))


def maps_of(m):
    if m.get("maps"):
        return [(int(x.get("s1") or 0), int(x.get("s2") or 0)) for x in m["maps"] if int(x.get("s1") or 0) != int(x.get("s2") or 0)]
    if int(m.get("bo") or 1) == 1:
        return [(int(m.get("s1") or 0), int(m.get("s2") or 0))]
    return [(1, 0) if m["winner"] == 1 else (0, 1)]   # series without map stats: one game, no margin


def elo(results, upto=None):
    R, info = {}, {}
    for m in results:
        if upto and ts(m["t"]) >= upto:
            break
        a, b = m["t1"], m["t2"]
        for t in (a, b):
            if t["id"] not in R:
                R[t["id"]] = PRIOR.get(m.get("division"), 1300.0)
                info[t["id"]] = {"id": t["id"], "name": t["name"], "region": m.get("region"), "division": m.get("division"), "matches": 0, "w": 0, "l": 0}
            info[t["id"]]["name"] = t["name"]
        info[a["id"]]["matches"] += 1; info[b["id"]]["matches"] += 1
        info[a["id"]]["w" if m["winner"] == 1 else "l"] += 1; info[b["id"]]["w" if m["winner"] == 2 else "l"] += 1
        if is_skip(m):
            continue
        for s1, s2 in maps_of(m):
            ea = 1 / (1 + 10 ** ((R[b["id"]] - R[a["id"]]) / 400))
            sa = 1.0 if s1 > s2 else 0.0
            mult = 1 + min(abs(s1 - s2), MARGIN_CAP_ROUNDS) / 20 if (s1 > 1 or s2 > 1) else 1.0
            d = K * (sa - ea) * mult
            R[a["id"]] += d; R[b["id"]] -= d
    return R, info


def table(R, info):
    rows = [dict(info[k], pts=round(v, 1)) for k, v in R.items() if info[k]["matches"] >= MIN_MATCHES]
    rows.sort(key=lambda r: (-r["pts"], r["name"].lower()))
    reg = {}
    for i, r in enumerate(rows):
        r["rank"] = i + 1
        reg[r["region"]] = reg.get(r["region"], 0) + 1
        r["rank_region"] = reg[r["region"]]
    return rows


def week_start(now):
    from zoneinfo import ZoneInfo
    lp = now.astimezone(ZoneInfo("America/Los_Angeles"))
    return (lp - timedelta(days=lp.weekday())).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


# ---------------------------------------------------------------- player rating
def players_of(data, teams):
    cols = (teams or {}).get("player_cols") or []
    out = {}
    for row in (teams or {}).get("players") or []:
        p = dict(zip(cols, row))
        out[(p.get("nick"), p.get("region"), p.get("division"))] = p
    for p in ((data.get("cs") or {}).get("players") or (data.get("cs") or {}).get("top_players") or []):
        out.setdefault((p.get("nick"), p.get("region"), p.get("division")), p)
    return list(out.values())


def div_avgs(players):
    acc = {}
    for p in players:
        r = float(p.get("rounds") or 0)
        if r < MIN_ROUNDS:
            continue
        a = acc.setdefault(f"{p.get('region')} {p.get('division')}", {"r": 0, "k": 0, "d": 0, "adr": 0, "kd": 0, "hs": 0, "n": 0})
        a["r"] += r; a["k"] += float(p.get("kills") or 0); a["d"] += float(p.get("deaths") or 0)
        a["adr"] += float(p.get("adr") or 0) * r; a["kd"] += float(p.get("kd") or 0) * r; a["hs"] += float(p.get("hs") or 0) * r; a["n"] += 1
    return {k: {"kpr": a["k"] / a["r"], "dpr": a["d"] / a["r"], "adr": a["adr"] / a["r"], "kd": a["kd"] / a["r"], "hs": a["hs"] / a["r"], "n": a["n"]}
            for k, a in acc.items() if a["r"] > 0 and a["k"] > 0 and a["d"] > 0}


def rating(kills, deaths, rounds, adr, hs, avg):
    if not avg or rounds <= 0:
        return None
    kpr, dpr = kills / rounds, max(deaths, 1) / rounds
    kd = kills / max(deaths, 1)
    v = (W["kpr"] * kpr / avg["kpr"] + W["dpr"] * avg["dpr"] / dpr + W["adr"] * adr / avg["adr"] + W["kd"] * kd / avg["kd"]
         + W["hs"] * (hs / avg["hs"] if avg["hs"] else 1))
    return round(v, 2)


def player_ratings(players, avgs):
    out = []
    for p in players:
        r = float(p.get("rounds") or 0)
        key = f"{p.get('region')} {p.get('division')}"
        if r < MIN_ROUNDS or key not in avgs:
            continue
        rt = rating(float(p.get("kills") or 0), float(p.get("deaths") or 0), r, float(p.get("adr") or 0), float(p.get("hs") or 0), avgs[key])
        if rt is not None:
            out.append({"nick": p.get("nick"), "region": p.get("region"), "division": p.get("division"), "team_id": p.get("team_id"), "team": p.get("team"),
                        "rounds": int(r), "rating": rt, "adj": round(rt * DIV_FACTOR.get(p.get("division"), 1.0), 2)})
    return out


def map_rating(row, map_rounds, avg):
    """row = [nick, K, D, ADR, HS%] from a FACEIT map scoreboard."""
    try:
        return rating(float(row[1]), float(row[2]), float(map_rounds), float(row[3]), float(row[4]), avg)
    except (TypeError, ValueError, IndexError):
        return None


# ---------------------------------------------------------------- weekly picks (used by spotlight.py)
def player_of_week(results, avgs, start, end, min_maps=2):
    per = {}
    for m in results:
        t = ts(m["t"])
        if not (start <= t < end) or not m.get("maps"):
            continue
        avg = avgs.get(f"{m.get('region')} {m.get('division')}")
        if not avg:
            continue
        for mp in m["maps"]:
            rounds = int(mp.get("s1") or 0) + int(mp.get("s2") or 0)
            if rounds < 13:
                continue
            for side, team in (("p1", m["t1"]), ("p2", m["t2"])):
                for row in mp.get(side) or []:
                    r = map_rating(row, rounds, avg)
                    if r is None:
                        continue
                    p = per.setdefault(row[0], {"nick": row[0], "team": team["name"], "team_id": team["id"], "div": f"{m['region']} {m['division']}", "sum": 0.0, "rounds": 0, "maps": 0, "k": 0, "d": 0, "best": m["id"]})
                    p["sum"] += r * rounds; p["rounds"] += rounds; p["maps"] += 1; p["k"] += int(row[1] or 0); p["d"] += int(row[2] or 0)
    c = [dict(p, rating=round(p["sum"] / p["rounds"], 2)) for p in per.values() if p["maps"] >= min_maps]
    if not c:
        return None
    best = max(c, key=lambda p: (p["rating"] * DIV_FACTOR.get(p["div"].split(" ", 1)[1], 1.0), p["rounds"]))
    best.pop("sum", None)
    return best


def team_of_week(results, start, end):
    r0, _ = elo(results, start)
    r1, info = elo(results, end)
    played = {}
    for m in results:
        if start <= ts(m["t"]) < end:
            for t in (m["t1"], m["t2"]):
                played[t["id"]] = played.get(t["id"], 0) + 1
    c = []
    for k, n in played.items():
        if n >= 2 and info.get(k, {}).get("matches", 0) >= MIN_MATCHES:
            c.append(dict(info[k], gain=round(r1[k] - r0.get(k, PRIOR.get(info[k]["division"], 1300.0)), 1), pts=round(r1[k], 1), played=n))
    return max(c, key=lambda x: (x["gain"], x["pts"])) if c else None


# ---------------------------------------------------------------- build
def build(data, teams, now=None):
    now = now or datetime.now(timezone.utc)
    res = finished(data, teams)
    R, info = elo(res)
    cur = table(R, info)
    ws = week_start(now)
    prev = {r["id"]: r for r in table(*elo(res, ws))}
    for r in cur:
        p = prev.get(r["id"])
        r["prev"] = p["rank"] if p else None
        r["prev_pts"] = p["pts"] if p else None
    pl = players_of(data, teams)
    avgs = div_avgs(pl)
    pr = player_ratings(pl, avgs)
    names = {}
    for m in res:
        names[m["t1"]["id"]] = m["t1"]["name"]; names[m["t2"]["id"]] = m["t2"]["name"]
    for p in pr:
        p["team"] = p.get("team") or names.get(p.get("team_id"))
    top = sorted([p for p in pr if p["rounds"] >= TOP_MIN_ROUNDS], key=lambda p: (-p["adj"], -p["rounds"]))[:20]
    season = (data.get("cs") or {}).get("season") or {}
    # v6.3 season awards (only what the data supports: no rookie-team flag, no weapon stats in FACEIT data we fetch)
    br = max(cur, key=lambda r: (r["pts"] - PRIOR.get(r["division"], 1300.0), r["pts"])) if cur else None
    awards = {"mvp": top[0] if top else None, "best_team": cur[0] if cur else None,
              "breakout": dict(br, gain=round(br["pts"] - PRIOR.get(br["division"], 1300.0), 1)) if br else None,
              "omitted": ["Top rookie team: FACEIT data here does not say which teams are new this season.",
                          "Top AWPer: FACEIT match stats here have no per-weapon data."]}
    # v6.4 playoffs: stages/matches marked as playoffs by fetch_data.py (none until FACEIT publishes them)
    cs = data.get("cs") or {}
    po_divs = [d for d in cs.get("divisions") or [] if re.search(r"playoff", str(d.get("stage") or ""), re.I)]
    po_matches = [m for m in (cs.get("matches") or []) + (cs.get("upcoming") or []) if re.search(r"playoff", str(m.get("stage") or ""), re.I)]
    po_done = [m for m in res if re.search(r"playoff", str(m.get("stage") or ""), re.I)]
    mvp = player_of_week(po_done, avgs, datetime(2000, 1, 1, tzinfo=timezone.utc), now + timedelta(days=1), min_maps=3) if po_done else None
    playoffs = {"divisions": [{"region": d.get("region"), "division": d.get("division"), "stage": d.get("stage"), "link": d.get("link")} for d in po_divs],
                "matches": [{k: m.get(k) for k in ("id", "region", "division", "round", "t", "t1", "t2", "s1", "s2", "winner", "bo")} for m in po_matches], "mvp": mvp,
                "links": [{"region": d.get("region"), "division": d.get("division"), "link": d.get("link")} for d in cs.get("divisions") or []]}
    return {"awards": awards, "playoffs": playoffs, "generated": now.isoformat(timespec="seconds"), "week_start": ws.isoformat(), "season": {"name": season.get("name"), "end": season.get("end"), "start": season.get("start")},
            "formula_team": FORMULA_TEAM, "formula_player": FORMULA_PLAYER, "prior": PRIOR, "div_factor": DIV_FACTOR, "weights": W, "min_rounds": MIN_ROUNDS,
            "teams": cur, "avgs": {k: {kk: round(vv, 4) for kk, vv in v.items()} for k, v in avgs.items()},
            "ratings": {p["nick"] + "|" + p["region"] + "|" + p["division"]: p["rating"] for p in pr}, "top20": top}


def archive(rk, folder):
    """Freeze finished weeks: rankings/YYYY-wNN.json = the table as of that week's end (append-only)."""
    os.makedirs(folder, exist_ok=True)
    ws = datetime.fromisoformat(rk["week_start"])
    iso = (ws - timedelta(days=1)).isocalendar()
    wid = f"{iso[0]}-w{iso[1]:02d}"
    path = os.path.join(folder, wid + ".json")
    if os.path.exists(path):
        return None
    rows = [{"id": r["id"], "rank": r["prev"], "pts": r["prev_pts"]} for r in rk["teams"] if r["prev"]]
    if not rows:
        return None
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"week": wid, "teams": sorted(rows, key=lambda r: r["rank"])}, fh, separators=(",", ":"))
        fh.write("\n")
    return wid


def main(argv=None):
    argv = argv or sys.argv[1:]
    arch = None
    if "--archive" in argv:
        i = argv.index("--archive"); arch = argv[i + 1]; argv = argv[:i] + argv[i + 2:]
    dist = argv[0] if argv else "dist"
    data = json.load(open(os.path.join(dist, "data.json"), encoding="utf-8"))
    try:
        teams = json.load(open(os.path.join(dist, "teams.json"), encoding="utf-8"))
    except Exception:
        teams = None
    rk = build(data, teams)
    blob = json.dumps(rk, ensure_ascii=False, separators=(",", ":"))
    open(os.path.join(dist, "rank.json"), "w", encoding="utf-8").write(blob)
    open(os.path.join(dist, "rank.js"), "w", encoding="utf-8").write("window.ESB_RANK = " + blob.replace("</", "<\\/") + ";\n")
    w = archive(rk, arch) if arch else None
    print(f"[ranking] {len(rk['teams'])} ranked teams, {len(rk['ratings'])} rated players, top20 {len(rk['top20'])}" + (f"; archived {w}" if w else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
