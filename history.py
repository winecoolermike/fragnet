#!/usr/bin/env python3
"""Full-season ESEA match history (Nov 13, 2026): every finished FACEIT match of the tracked divisions, so the
ESB map Elo (ranking.py) accumulates over the whole season instead of the ~100 newest matches per conference
that the live match lists return.

File: data/esea-s<season number>-matches.json (committed, compact, one match per line):
  {"season": {...}, "saved": iso, "backfill": {<championship id>: {"offset": n, "done": bool}}, "cols": [...], "rows": [[...], ...]}
Rows keep only what the ranking needs: ids, names, round, best-of, time, series score, winner and per-map scores
(no player scoreboards). fetch_data.py merges each run's finished matches and pages older ones in (backfill);
it writes the file at most every SAVE_EVERY_H hours unless the backfill moved, so the deploy commits stay rare.
"""
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "data")
SAVE_EVERY_H = 6
COLS = ["id", "region", "division", "conf", "round", "bo", "t", "t1", "n1", "t2", "n2", "s1", "s2", "winner", "maps", "nostats"]


def path_for(season):
    n = (season or {}).get("number")
    return os.path.join(DIR, f"esea-s{int(n)}-matches.json") if n else None


def empty(season):
    return {"season": {k: (season or {}).get(k) for k in ("id", "name", "number", "start", "end")}, "saved": None, "backfill": {}, "cols": COLS, "rows": []}


def load(season=None, path=None):
    path = path or path_for(season)
    try:
        with open(path, encoding="utf-8") as fh:
            h = json.load(fh)
        if season and (h.get("season") or {}).get("id") not in (None, season.get("id")):
            return empty(season)
        return h
    except (OSError, ValueError, TypeError):
        return empty(season)


def load_current(data):
    """History for the season in data.json (or None). Used by ranking.py."""
    season = (data.get("cs") or {}).get("season") or {}
    p = path_for(season)
    if not p or not os.path.exists(p):
        return None
    h = load(season, p)
    return h if (h.get("season") or {}).get("id") == season.get("id") else None


def row(m):
    maps = [[x.get("map") or "", int(x.get("s1") or 0), int(x.get("s2") or 0)] for x in m.get("maps") or []]
    return [m["id"], m.get("region"), m.get("division"), m.get("conf") or "", int(m.get("round") or 0), int(m.get("bo") or 1), m.get("t"),
            m["t1"]["id"], m["t1"].get("name"), m["t2"]["id"], m["t2"].get("name"), int(m.get("s1") or 0), int(m.get("s2") or 0),
            int(m.get("winner") or 0), maps or 0, 1 if m.get("nostats") else 0]


def to_matches(h):
    out = []
    cols = h.get("cols") or COLS
    for r in h.get("rows") or []:
        d = dict(zip(cols, r))
        m = {"id": d["id"], "region": d["region"], "division": d["division"], "conf": d["conf"], "round": d["round"], "bo": d["bo"], "t": d["t"],
             "t1": {"id": d["t1"], "name": d["n1"]}, "t2": {"id": d["t2"], "name": d["n2"]}, "s1": d["s1"], "s2": d["s2"], "winner": d["winner"]}
        if d.get("maps"):
            m["maps"] = [{"map": a, "s1": b, "s2": c} for a, b, c in d["maps"]]
        if d.get("nostats"):
            m["nostats"] = True
        out.append(m)
    return out


def merge(h, matches):
    """Add finished matches (winner 1/2, both teams known). An entry with per-map scores wins over one without.
    Returns how many rows were added or improved."""
    idx = {r[0]: i for i, r in enumerate(h["rows"])}
    n = 0
    for m in matches or []:
        try:
            if m.get("winner") not in (1, 2) or not m.get("t") or not (m.get("t1") or {}).get("id") or not (m.get("t2") or {}).get("id"):
                continue
            r = row(m)
        except (KeyError, TypeError, ValueError):
            continue
        i = idx.get(r[0])
        if i is None:
            idx[r[0]] = len(h["rows"])
            h["rows"].append(r)
            n += 1
        elif r[14] and not h["rows"][i][14]:
            h["rows"][i] = r
            n += 1
    return n


def save(h, path, force=False, now=None):
    """Write when forced (backfill progress / new file) or when the last save is SAVE_EVERY_H old. Returns True if written."""
    now = now or datetime.now(timezone.utc)
    try:
        last = datetime.fromisoformat(h.get("saved")) if h.get("saved") else None
    except ValueError:
        last = None
    if not force and last and (now - last).total_seconds() < SAVE_EVERY_H * 3600:
        return False
    h["saved"] = now.isoformat(timespec="seconds")
    h["rows"].sort(key=lambda r: (r[6] or "", r[0]))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    head = {k: h[k] for k in ("season", "saved", "backfill", "cols")}
    body = json.dumps(head, ensure_ascii=False, separators=(",", ":"))[:-1]
    text = body + ',"rows":[\n' + ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in h["rows"]) + "\n]}\n"
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return True
