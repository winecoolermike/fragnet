#!/usr/bin/env python3
"""Build-time, template-based NA match previews (no paid AI/API).

    python writeups.py dist

Reads data.json, teams.json, rank.json and data/esea-s59-matches.json (Season 59
history). Writes dist/writeups.json and dist/writeups.js for upcoming/live ESEA
NA Main, Intermediate and Advanced matches. Each blurb is 2–4 plain sentences
assembled from several templates so they do not all read the same. A clause is
omitted when the supporting data is missing; the text never states a fact the
data does not support.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
DIVS = ("Main", "Intermediate", "Advanced")
MIN_ROUNDS = 20
SAFE_ID = re.compile(r"^[0-9a-z-]{8,48}$", re.I)


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def iso(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def is_ff(m):
    try:
        a, b = int(m.get("s1") or 0), int(m.get("s2") or 0)
    except (TypeError, ValueError):
        return False
    return a + b <= 1 and (int(m.get("bo") or 1) == 1 or bool(m.get("nostats")))


def rec_str(w, l, t=0):
    try:
        w, l, t = int(w or 0), int(l or 0), int(t or 0)
    except (TypeError, ValueError):
        return ""
    return f"{w}-{l}-{t}" if t else f"{w}-{l}"


def ordinal(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    if 10 <= (n % 100) <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def pick(mid, salt, options):
    if not options:
        return None
    h = hashlib.sha1(f"{mid}:{salt}".encode()).hexdigest()
    return options[int(h[:8], 16) % len(options)]


def when_pt(ts):
    d = iso(ts)
    if not d:
        return ""
    local = d.astimezone(PT)
    return local.strftime("%A, %b %-d at %-I:%M %p PT").replace(" 0", " ")


def poss(name):
    name = str(name or "")
    if not name:
        return ""
    return name + ("'" if name[-1] in "sS" else "'s")


def numword(n):
    return {2: "two", 3: "three", 4: "four", 5: "five"}.get(int(n), str(n))


def season_path(dist):
    root = os.path.dirname(os.path.abspath(dist))
    here = os.path.abspath(os.path.dirname(__file__))
    for p in (
        os.path.join(dist, "esea-s59-matches.json"),
        os.path.join(root, "data", "esea-s59-matches.json"),
        os.path.join(here, "data", "esea-s59-matches.json"),
        os.path.join(os.path.dirname(here), "data", "esea-s59-matches.json"),
    ):
        if os.path.isfile(p):
            return p
    return None


def season_matches(path):
    raw = load(path) or {}
    cols = raw.get("cols") or []
    out = []
    for row in raw.get("rows") or []:
        if not cols or len(row) < len(cols):
            continue
        d = dict(zip(cols, row))
        out.append({
            "id": d.get("id"),
            "region": d.get("region"),
            "division": d.get("division"),
            "t": d.get("t"),
            "t1": {"id": d.get("t1"), "name": d.get("n1")},
            "t2": {"id": d.get("t2"), "name": d.get("n2")},
            "s1": d.get("s1"),
            "s2": d.get("s2"),
            "winner": d.get("winner"),
            "bo": d.get("bo") or 1,
            "nostats": d.get("nostats"),
            "maps": d.get("maps") or [],
        })
    return out


def collect_finished(data, teams, season):
    seen, out = set(), []
    buckets = []
    cs = (data or {}).get("cs") or {}
    buckets.append(cs.get("matches") or [])
    buckets.append((teams or {}).get("matches") or [])
    buckets.append(season or [])
    for bucket in buckets:
        for m in bucket:
            mid = m.get("id")
            t1, t2 = m.get("t1") or {}, m.get("t2") or {}
            if not mid or mid in seen or not t1.get("id") or not t2.get("id"):
                continue
            if m.get("winner") not in (1, 2):
                continue
            seen.add(mid)
            out.append(m)
    out.sort(key=lambda m: str(m.get("t") or ""))
    return out


def form_of(finished, tid, before=None):
    rows = []
    for m in finished:
        if before and str(m.get("t") or "") >= str(before):
            continue
        if is_ff(m):
            continue
        side = 1 if (m.get("t1") or {}).get("id") == tid else (2 if (m.get("t2") or {}).get("id") == tid else 0)
        if not side:
            continue
        w = m.get("winner")
        rows.append("W" if w == side else "L")
    return rows


def streak_of(form):
    if not form:
        return None
    last, n = form[-1], 0
    for r in reversed(form):
        if r != last:
            break
        n += 1
    if n < 2:
        return None
    return last, n


def h2h_of(finished, a, b, before=None):
    rows = []
    for m in finished:
        if before and str(m.get("t") or "") >= str(before):
            continue
        if is_ff(m):
            continue
        t1, t2 = (m.get("t1") or {}).get("id"), (m.get("t2") or {}).get("id")
        if {t1, t2} != {a, b}:
            continue
        rows.append(m)
    return rows


def standings_map(data):
    out = {}
    for dv in ((data or {}).get("cs") or {}).get("divisions") or []:
        for t in dv.get("teams") or []:
            if t.get("id"):
                out[t["id"]] = {
                    "rank": t.get("rank"),
                    "w": t.get("w"),
                    "l": t.get("l"),
                    "t": t.get("t") or 0,
                    "pts": t.get("pts"),
                    "conf": t.get("conf"),
                    "name": t.get("name"),
                    "roster": t.get("roster") or [],
                    "region": dv.get("region"),
                    "division": dv.get("division"),
                }
    return out


def esb_map(rank):
    out = {}
    for t in (rank or {}).get("teams") or []:
        if t.get("id"):
            out[t["id"]] = t
    return out


def top_player(players, ratings, tid, region, division, roster_nicks):
    """Best rated player on the team with enough rounds; else top by kills if rating missing."""
    cands = []
    nicks = {str(n).lower() for n in roster_nicks if n}
    for p in players:
        if p.get("team_id") == tid:
            cands.append(p)
        elif not p.get("team_id") and str(p.get("nick") or "").lower() in nicks and p.get("region") == region and p.get("division") == division:
            cands.append(p)
    best = None
    for p in cands:
        nick = p.get("nick")
        if not nick:
            continue
        rounds = int(p.get("rounds") or 0)
        kills = int(p.get("kills") or 0)
        rt = ratings.get(f"{nick}|{region}|{division}")
        if rt is None and rounds < MIN_ROUNDS:
            continue
        item = {"nick": nick, "rating": rt, "rounds": rounds, "kills": kills}
        if best is None:
            best = item
            continue
        # prefer a rating when both have one; otherwise more kills
        if item["rating"] is not None and (best["rating"] is None or (item["rating"], item["rounds"]) > (best["rating"], best["rounds"])):
            best = item
        elif item["rating"] is None and best["rating"] is None and item["kills"] > best["kills"]:
            best = item
    if not best:
        return None
    rated = [p for p in cands if ratings.get(f"{p.get('nick')}|{region}|{division}") is not None and int(p.get("rounds") or 0) >= MIN_ROUNDS]
    best["n_rated"] = len(rated)
    return best


def all_players(data, teams):
    cols = (teams or {}).get("player_cols") or []
    out, seen = [], set()
    for row in (teams or {}).get("players") or []:
        p = dict(zip(cols, row))
        k = (p.get("nick"), p.get("region"), p.get("division"), p.get("team_id"))
        if k not in seen:
            seen.add(k)
            out.append(p)
    for p in ((data or {}).get("cs") or {}).get("players") or ((data or {}).get("cs") or {}).get("top_players") or []:
        k = (p.get("nick"), p.get("region"), p.get("division"), p.get("team_id"))
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def upcoming_na(data, teams):
    seen, out = set(), []
    cs = (data or {}).get("cs") or {}
    for m in (cs.get("live") or []) + (cs.get("upcoming") or []) + ((teams or {}).get("upcoming") or []):
        if not m or not m.get("id") or m["id"] in seen:
            continue
        if m.get("region") != "NA" or m.get("division") not in DIVS:
            continue
        t1, t2 = m.get("t1") or {}, m.get("t2") or {}
        if not t1.get("id") or not t2.get("id") or not t1.get("name") or not t2.get("name"):
            continue
        if not SAFE_ID.match(str(m["id"])):
            continue
        seen.add(m["id"])
        out.append(m)
    out.sort(key=lambda m: str(m.get("t") or ""))
    return out


def facts_for(m, finished, table, esb, pred, players, ratings):
    a, b = m.get("t1") or {}, m.get("t2") or {}
    fa, fb = table.get(a["id"]) or {}, table.get(b["id"]) or {}
    ea, eb = esb.get(a["id"]) or {}, esb.get(b["id"]) or {}
    form_a = form_of(finished, a["id"], m.get("t"))
    form_b = form_of(finished, b["id"], m.get("t"))
    h2h = h2h_of(finished, a["id"], b["id"], m.get("t"))
    pr = (pred.get("matches") or {}).get(m["id"]) if pred else None
    if pred and m.get("region") not in (pred.get("regions") or []):
        pr = None
    if pred and m.get("division") not in (pred.get("divisions") or []):
        pr = None
    ros_a = [r.get("nick") for r in (fa.get("roster") or []) if r.get("nick")]
    ros_b = [r.get("nick") for r in (fb.get("roster") or []) if r.get("nick")]
    return {
        "m": m,
        "id": m["id"],
        "a": a["name"],
        "b": b["name"],
        "aid": a["id"],
        "bid": b["id"],
        "div": f"{m.get('region')} {m.get('division')}".strip(),
        "conf": m.get("conf") or "",
        "round": m.get("round"),
        "bo": int(m.get("bo") or 1),
        "when": when_pt(m.get("t")),
        "sa": fa if fa.get("rank") not in (None, "") else None,
        "sb": fb if fb.get("rank") not in (None, "") else None,
        "ea": ea if ea.get("pts") is not None else None,
        "eb": eb if eb.get("pts") is not None else None,
        "form_a": form_a,
        "form_b": form_b,
        "str_a": streak_of(form_a),
        "str_b": streak_of(form_b),
        "h2h": h2h,
        "pr": pr,
        "pa": top_player(players, ratings, a["id"], m.get("region"), m.get("division"), ros_a),
        "pb": top_player(players, ratings, b["id"], m.get("region"), m.get("division"), ros_b),
    }


def last5(form):
    return "".join(form[-5:]) if form else ""


def s_meeting(f, style):
    a, b, div, when = f["a"], f["b"], f["div"], f["when"]
    extras = []
    if f["bo"] == 3:
        extras.append("best-of-3")
    if f.get("conf"):
        extras.append(f"{f['conf']} conference")
    if f.get("round"):
        try:
            extras.append(f"round {int(f['round'])}")
        except (TypeError, ValueError):
            pass
    mid = ", ".join(extras)
    paren = f" ({mid})" if mid else ""
    when_bit = f" on {when}" if when else ""
    style = style % 4
    if style == 0:
        return f"{a} and {b} meet in {div}{paren}{when_bit}."
    if style == 1:
        return f"{div}'s {a} face {b}{paren}{when_bit}."
    if style == 2:
        return f"{a} play {b} in {div}{paren}{when_bit}."
    return f"{a} and {b} are scheduled in {div}{paren}{when_bit}." if div else f"{a} and {b} are scheduled to play{when_bit}."


def s_table(f, style):
    sa, sb = f["sa"], f["sb"]
    if not sa and not sb:
        return ""
    def bit(name, s):
        if not s:
            return ""
        rec = rec_str(s.get("w"), s.get("l"), s.get("t"))
        rk = s.get("rank")
        try:
            rk = int(rk)
        except (TypeError, ValueError):
            rk = None
        if rk and rec:
            return f"{name} sit {ordinal(rk)} in the {f['div']} table at {rec}"
        if rk:
            return f"{name} sit {ordinal(rk)} in the {f['div']} table"
        if rec:
            return f"{name} are {rec} in the {f['div']} table"
        return ""
    ba, bb = bit(f["a"], sa), bit(f["b"], sb)
    if ba and bb:
        if style % 2 == 0:
            return f"{ba}; {bb}."
        return f"{ba}, while {bb}."
    return (ba or bb) + "."


def s_esb(f, style):
    # only if we have points for at least one side; label clearly as ESB ranking
    parts = []
    for name, e in ((f["a"], f["ea"]), (f["b"], f["eb"])):
        if not e or e.get("pts") is None:
            continue
        try:
            pts = round(float(e["pts"]))
        except (TypeError, ValueError):
            continue
        rk = e.get("rank_region")
        if rk:
            parts.append(f"{name} have {pts} ESB ranking points ({ordinal(rk)} in {e.get('region') or 'NA'})")
        else:
            parts.append(f"{name} have {pts} ESB ranking points")
    if not parts:
        return ""
    if len(parts) == 2:
        return parts[0] + "; " + parts[1] + "."
    return parts[0] + "."


def s_form(f, style):
    bits = []
    for name, form, st in ((f["a"], f["form_a"], f["str_a"]), (f["b"], f["form_b"], f["str_b"])):
        if st:
            n = st[1]
            word = {2: "two", 3: "three", 4: "four", 5: "five"}.get(n, str(n))
            if st[0] == "W":
                bits.append(f"{poss(name)} last {word} tracked matches have been wins")
            else:
                bits.append(f"{poss(name)} last {word} tracked matches have been losses")
        elif len(form) >= 3:
            bits.append(f"{poss(name)} last {numword(len(form[-5:]))} tracked results are {last5(form)}")
    if not bits:
        return ""
    if len(bits) == 2:
        return bits[0] + "; " + bits[1] + "."
    return bits[0] + "."


def s_h2h(f, style):
    rows = f["h2h"]
    if not rows:
        return ""
    a, b, aid = f["a"], f["b"], f["aid"]
    aw = bw = 0
    last = rows[-1]
    for m in rows:
        w = m.get("winner")
        t1 = (m.get("t1") or {}).get("id")
        if w == 1:
            aw += 1 if t1 == aid else 0
            bw += 1 if t1 != aid else 0
        elif w == 2:
            aw += 1 if t1 != aid else 0
            bw += 1 if t1 == aid else 0
    def score(m):
        try:
            return f"{int(m.get('s1'))}-{int(m.get('s2'))}"
        except (TypeError, ValueError):
            return ""
    last_sc = score(last)
    last_w = last.get("winner")
    last_t1 = (last.get("t1") or {}).get("id")
    if last_w == 1:
        last_name = f["a"] if last_t1 == aid else f["b"]
    elif last_w == 2:
        last_name = f["b"] if last_t1 == aid else f["a"]
    else:
        last_name = ""
    last_when = ""
    d = iso(last.get("t"))
    if d:
        last_when = d.astimezone(PT).strftime("%b %-d")
    n = len(rows)
    if n == 1:
        if last_name and last_sc and last_when:
            return f"They met once this season in the tracked results, {last_name} winning {last_sc} on {last_when}."
        if last_name and last_sc:
            return f"They met once this season in the tracked results, {last_name} winning {last_sc}."
        return "They have met once this season in the tracked results."
    lead = ""
    if aw > bw:
        lead = f"{a} lead {aw}-{bw}"
    elif bw > aw:
        lead = f"{b} lead {bw}-{aw}"
    else:
        lead = f"they are split {aw}-{aw}"
    if last_name and last_sc and last_when:
        return f"They have met {n} times this season in the tracked results; {lead}, most recently {last_name} {last_sc} on {last_when}."
    return f"They have met {n} times this season in the tracked results; {lead}."


def s_pred(f, style):
    pr = f["pr"]
    if not pr or pr.get("p1") is None:
        return ""
    try:
        p = float(pr["p1"])
    except (TypeError, ValueError):
        return ""
    if not 0 <= p <= 1:
        return ""
    if p > 0.5:
        fav, pct = f["a"], int(round(100 * p))
    elif p < 0.5:
        fav, pct = f["b"], int(round(100 * (1 - p)))
    else:
        variants = [
            f"An experimental estimate based on season results gives each side a 50% chance.",
            f"The experimental model, built from this season's tracked results, has this match even at 50%.",
        ]
        return pick(f["id"], "pred50", variants)
    variants = [
        f"An experimental estimate based on season results gives {fav} a {pct}% chance to win.",
        f"The experimental model, built from this season's tracked results, puts {fav} at {pct}%.",
        f"A {pct}% win probability for {fav} is the experimental estimate from this season's tracked results.",
        f"Season results so far produce an experimental {pct}% estimate for {fav}.",
    ]
    return pick(f["id"], "pred", variants)


def s_players(f, style):
    bits = []
    for name, p in ((f["a"], f["pa"]), (f["b"], f["pb"])):
        if not p or not p.get("nick"):
            continue
        nick = p["nick"]
        if p.get("rating") is not None and p.get("rounds"):
            if p.get("n_rated", 0) >= 2:
                bits.append(f"{nick} leads {poss(name)} rated players at {p['rating']:.2f} over {int(p['rounds'])} rounds")
            else:
                bits.append(f"{nick} has a {p['rating']:.2f} rating over {int(p['rounds'])} tracked rounds for {name}")
        elif p.get("kills"):
            bits.append(f"{nick} has {int(p['kills'])} kills in the tracked season stats for {name}")
    if not bits:
        return ""
    if len(bits) == 2:
        return bits[0] + "; " + bits[1] + "."
    return bits[0] + "."


# Template orders: which sentence slots to try, and in what sequence.
# Meeting + pred (when present) cover the required core; others fill out 2–4 sentences.
ORDERS = [
    ("meeting", "table", "form", "pred"),
    ("meeting", "pred", "h2h", "players"),
    ("meeting", "h2h", "table", "pred"),
    ("meeting", "form", "pred", "esb"),
    ("meeting", "table", "pred", "players"),
    ("meeting", "esb", "pred", "form"),
    ("meeting", "players", "form", "pred"),
    ("meeting", "pred", "form", "table"),
]

SLOTS = {
    "meeting": s_meeting,
    "table": s_table,
    "esb": s_esb,
    "form": s_form,
    "h2h": s_h2h,
    "pred": s_pred,
    "players": s_players,
}


def render(f):
    order = pick(f["id"], "order", ORDERS)
    style = int(hashlib.sha1(f"{f['id']}:style".encode()).hexdigest()[:4], 16)
    used, sentences = set(), []
    for slot in order:
        text = SLOTS[slot](f, style)
        if text:
            sentences.append(text)
            used.add(slot)
    # Fill up to 2 (preferably 3) if the chosen order skipped too much.
    if len(sentences) < 2:
        for slot in ("meeting", "table", "form", "h2h", "pred", "esb", "players"):
            if slot in used:
                continue
            text = SLOTS[slot](f, style)
            if text:
                sentences.append(text)
                used.add(slot)
            if len(sentences) >= 3:
                break
    pred = s_pred(f, style)
    if pred and "pred" not in used:
        if len(sentences) < 4:
            sentences.insert(min(1, len(sentences)), pred)
        else:
            sentences[-1] = pred
        used.add("pred")
    sentences = sentences[:4]
    return " ".join(sentences).strip()


# ---------------------------------------------------------------------------
# v5.17 deep predictions (Predictions page): NA Main / Intermediate / Advanced
# matches involving a division top-10 team, plus every match of the teams in
# ALWAYS_PREDICT_TEAMS. Longer, sectioned write-ups; every line comes from the
# data (standings, tracked season results, ESB ranking / map Elo, ratings).
# ---------------------------------------------------------------------------
TOP_N = 10
# Teams whose every upcoming NA match always gets a deep prediction (matched by
# name, case/punctuation-insensitive). Add more names here.
ALWAYS_PREDICT_TEAMS = ["High Tech Performance"]
# "esb": top 10 of the division by ESB Team Ranking points (ranking.py order);
# "standings": top 10 by the ESEA division table.
TOP_BY = os.environ.get("ESB_TOP_BY", "esb").strip().lower() or "esb"


def norm_name(s):
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


def always_match(name, wanted=None):
    n = norm_name(name)
    if not n:
        return False
    for w in (wanted if wanted is not None else ALWAYS_PREDICT_TEAMS):
        x = norm_name(w)
        if x and (x == n or (len(x) >= 6 and (x in n or n in x))):
            return True
    return False


def division_top(rank, table, region, division, n=TOP_N, by=None):
    """[(team id, place)] for the division's top n, in ranking.py order (ESB points) or standings order."""
    by = by or TOP_BY
    if by == "standings":
        rows = []
        for tid, s in table.items():
            if s.get("region") == region and s.get("division") == division:
                try:
                    rows.append((int(s.get("rank")), tid))
                except (TypeError, ValueError):
                    pass
        rows.sort()
        return [(tid, rk) for rk, tid in rows[:n]]
    rows = [t for t in (rank or {}).get("teams") or [] if t.get("region") == region and t.get("division") == division and t.get("pts") is not None]
    rows.sort(key=lambda t: (-float(t["pts"]), int(t.get("rank") or 9999)))
    return [(t["id"], i + 1) for i, t in enumerate(rows[:n])]


def division_places(rank, region, division):
    rows = [t for t in (rank or {}).get("teams") or [] if t.get("region") == region and t.get("division") == division and t.get("pts") is not None]
    rows.sort(key=lambda t: (-float(t["pts"]), int(t.get("rank") or 9999)))
    return {t["id"]: i + 1 for i, t in enumerate(rows)}


def score_of(m, side):
    try:
        a, b = int(m.get("s1")), int(m.get("s2"))
    except (TypeError, ValueError):
        return ""
    return f"{a}-{b}" if side == 1 else f"{b}-{a}"


def deep_form(finished, tid, before=None, n=5):
    rows = []
    for m in finished:
        if before and str(m.get("t") or "") >= str(before):
            continue
        t1, t2 = m.get("t1") or {}, m.get("t2") or {}
        side = 1 if t1.get("id") == tid else (2 if t2.get("id") == tid else 0)
        if not side:
            continue
        opp = t2 if side == 1 else t1
        d = iso(m.get("t"))
        rows.append({"r": "W" if m.get("winner") == side else "L", "opp": opp.get("name") or "", "score": score_of(m, side),
                     "ff": is_ff(m), "date": d.astimezone(PT).strftime("%b %-d") if d else "", "id": m.get("id")})
    return rows[-n:]


def map_records(finished, tid, before=None):
    rec = {}
    for m in finished:
        if before and str(m.get("t") or "") >= str(before):
            continue
        if is_ff(m):
            continue
        t1, t2 = m.get("t1") or {}, m.get("t2") or {}
        side = 1 if t1.get("id") == tid else (2 if t2.get("id") == tid else 0)
        if not side:
            continue
        maps = m.get("maps") or []
        if maps:
            lst = [(x.get("map"), x.get("s1"), x.get("s2")) if isinstance(x, dict) else tuple((list(x) + [None, None, None])[:3]) for x in maps]
        elif int(m.get("bo") or 1) == 1 and m.get("pick"):
            lst = [(m["pick"][0], m.get("s1"), m.get("s2"))]
        else:
            lst = []
        for name, a, b in lst:
            try:
                a, b = int(a), int(b)
            except (TypeError, ValueError):
                continue
            if not name or a == b:
                continue
            r = rec.setdefault(str(name), {"w": 0, "n": 0})
            r["n"] += 1
            if (a > b) == (side == 1):
                r["w"] += 1
    return rec


def rated_players(players, ratings, tid, region, division, roster_nicks, k=3):
    nicks = {str(n).lower() for n in roster_nicks if n}
    seen, out = set(), []
    for p in players:
        nick = p.get("nick")
        if not nick or nick in seen:
            continue
        mine = p.get("team_id") == tid or (not p.get("team_id") and str(nick).lower() in nicks and p.get("region") == region and p.get("division") == division)
        if not mine:
            continue
        rt = ratings.get(f"{nick}|{region}|{division}")
        rounds = int(p.get("rounds") or 0)
        if rt is None or rounds < MIN_ROUNDS:
            continue
        seen.add(nick)
        kd = p.get("kd")
        out.append({"nick": nick, "rating": float(rt), "rounds": rounds, "kd": kd, "adr": p.get("adr")})
    out.sort(key=lambda x: (-x["rating"], -x["rounds"]))
    return out[:k]


def pct_word(p):
    if p >= 70:
        return "a clear favorite"
    if p >= 60:
        return "the favorite"
    if p >= 53:
        return "a slight favorite"
    return "a narrow pick in a near coin flip"


def deep_record(m, finished, table, esb, pred, players, ratings, rank, places, reasons):
    a, b = m.get("t1") or {}, m.get("t2") or {}
    region, division = m.get("region"), m.get("division")
    f = facts_for(m, finished, table, esb, pred, players, ratings)
    pr = f["pr"]
    if not pr or pr.get("p1") is None:
        return None
    try:
        p1 = float(pr["p1"])
    except (TypeError, ValueError):
        return None
    if not 0 <= p1 <= 1:
        return None
    fav = 1 if p1 >= 0.5 else 2
    pct = int(round(100 * (p1 if fav == 1 else 1 - p1)))
    A, B = a["name"], b["name"]
    F, U = (A, B) if fav == 1 else (B, A)
    ea, eb = f["ea"], f["eb"]
    sa, sb = f["sa"], f["sb"]

    def team(t, s, e):
        out = {"id": t["id"], "name": t["name"]}
        if s:
            out["std"] = s.get("rank")
            out["rec"] = rec_str(s.get("w"), s.get("l"), s.get("t"))
        if e and e.get("pts") is not None:
            out["pts"] = round(float(e["pts"]))
        if places.get(t["id"]):
            out["esb"] = places[t["id"]]
        return out

    secs = []
    # The Pick
    pick = [f"{F} at {pct}%, {U} at {100 - pct}%. That makes {F} {pct_word(pct)}."]
    if f["bo"] == 3 and pr.get("map_p1") is not None:
        mp = float(pr["map_p1"])
        mpf = int(round(100 * (mp if fav == 1 else 1 - mp)))
        pick.append(f"Best of 3: {F} win a single map {mpf}% of the time in the model, which becomes {pct}% over the series.")
    conf = {"high": "High", "medium": "Medium", "low": "Low"}.get(pr.get("conf"), "")
    if conf and pr.get("n1") is not None and pr.get("n2") is not None:
        pick.append(f"Data confidence: {conf} ({A} {int(pr['n1'])} rated maps, {B} {int(pr['n2'])}).")
    secs.append({"k": "pick", "h": "The Pick", "p": pick})

    # Standing (table + ESB ranking)
    st = []
    for t, s, e in ((A, sa, ea), (B, sb, eb)):
        bits = []
        if s:
            rec = rec_str(s.get("w"), s.get("l"), s.get("t"))
            rk = ordinal(s.get("rank")) if s.get("rank") else ""
            if rk and rec:
                bits.append(f"{rk} in the {f['div']} table at {rec}")
            elif rec:
                bits.append(f"{rec} in the {f['div']} table")
        tid = a["id"] if t == A else b["id"]
        if e and e.get("pts") is not None:
            pl = places.get(tid)
            bits.append(f"{round(float(e['pts']))} ESB points" + (f" ({ordinal(pl)} in {f['div']} by ESB Team Ranking)" if pl else ""))
        if bits:
            st.append(f"{t}: " + "; ".join(bits) + ".")
    if st:
        secs.append({"k": "standing", "h": "Where They Stand", "p": st})

    # Recent form
    fa, fb = deep_form(finished, a["id"], m.get("t")), deep_form(finished, b["id"], m.get("t"))
    if fa or fb:
        rows = []
        for t, lst in ((A, fa), (B, fb)):
            if not lst:
                continue
            w = sum(1 for x in lst if x["r"] == "W")
            rows.append({"team": t, "sum": f"{w}-{len(lst) - w} in the last {len(lst)}",
                         "g": [{"r": x["r"], "opp": x["opp"], "score": x["score"], "date": x["date"], "ff": x["ff"]} for x in reversed(lst)]})
        secs.append({"k": "form", "h": "Recent Form", "form": rows, "p": ["Newest first. Forfeits are marked and do not count toward the model."] if any(x["ff"] for r in (fa + fb) for x in [r]) else []})

    # Key players
    ros = lambda s: [r.get("nick") for r in ((s or {}).get("roster") or []) if r.get("nick")]
    pa = rated_players(players, ratings, a["id"], region, division, ros(table.get(a["id"])))
    pb = rated_players(players, ratings, b["id"], region, division, ros(table.get(b["id"])))
    if pa or pb:
        pl = []
        for t, lst in ((A, pa), (B, pb)):
            if lst:
                pl.append(f"{t}: " + ", ".join(f"{x['nick']} {x['rating']:.2f} ({x['rounds']} rounds)" for x in lst) + ".")
        txt = []
        if pa and pb:
            ta, tb = pa[0], pb[0]
            if abs(ta["rating"] - tb["rating"]) >= 0.05:
                hi, lo = (ta, tb) if ta["rating"] > tb["rating"] else (tb, ta)
                hit = A if hi is ta else B
                txt.append(f"The top rated player in this match is {hi['nick']} of {hit} at {hi['rating']:.2f}, ahead of {lo['nick']} at {lo['rating']:.2f}.")
            else:
                txt.append(f"The two top rated players are close: {ta['nick']} {ta['rating']:.2f} and {tb['nick']} {tb['rating']:.2f}.")
        secs.append({"k": "players", "h": "Key Players", "p": pl + txt, "note": "ESB Rating 1.0, this season, players with 20+ tracked rounds."})

    # Maps
    ma, mb = map_records(finished, a["id"], m.get("t")), map_records(finished, b["id"], m.get("t"))
    named = lambda rec: sum(v["n"] for v in rec.values())
    if named(ma) >= 3 or named(mb) >= 3:
        mp = []
        for t, rec in ((A, ma), (B, mb)):
            if named(rec) < 3:
                continue
            most = sorted(rec.items(), key=lambda kv: (-kv[1]["n"], -kv[1]["w"], kv[0]))[:4]
            mp.append(f"{t} ({named(rec)} maps with a known map name): " + ", ".join(f"{k} {v['w']}-{v['n'] - v['w']}" for k, v in most) + ".")
            c = sorted([(k, v) for k, v in rec.items() if v["n"] >= 2], key=lambda kv: (-kv[1]["w"] / kv[1]["n"], -kv[1]["n"], kv[0]))
            if c and c[0][1]["w"] / c[0][1]["n"] >= 0.6:
                k, v = c[0]
                mp.append(f"{poss(t)} best map so far is {k}, won {v['w']} of {v['n']}.")
        both = sorted((k for k in set(ma) & set(mb) if ma[k]["n"] + mb[k]["n"] >= 3), key=lambda k: -(ma[k]["n"] + mb[k]["n"]))
        if both:
            k = both[0]
            mp.append(f"Both have played {k}: {A} {ma[k]['w']}-{ma[k]['n'] - ma[k]['w']}, {B} {mb[k]['w']}-{mb[k]['n'] - mb[k]['w']}.")
        if mp:
            secs.append({"k": "maps", "h": "Maps", "p": mp, "note": "Map wins-losses in the tracked season results. No map veto is predicted."})

    # Head to head (only if they met)
    if f["h2h"]:
        h = s_h2h(f, 0)
        rows = []
        for x in reversed(f["h2h"]):
            side = 1 if (x.get("t1") or {}).get("id") == a["id"] else 2
            d = iso(x.get("t"))
            rows.append(f"{d.astimezone(PT).strftime('%b %-d') if d else ''}: {A} {score_of(x, side)} {B}" + (" (forfeit)" if is_ff(x) else ""))
        secs.append({"k": "h2h", "h": "Head to Head", "p": [h] + rows})

    # Why (the model's reasoning, from the numbers)
    why = []
    if ea and eb:
        pf, pu = (ea, eb) if fav == 1 else (eb, ea)
        rf_, ru_ = round(float(pf["pts"])), round(float(pu["pts"]))
        gap = rf_ - ru_
        exp = 1 / (1 + 10 ** (-(float(pf["pts"]) - float(pu["pts"])) / 400))
        if f["bo"] == 3:
            exp = exp * exp * (3 - 2 * exp)
        same = abs(100 * exp - pct) <= 2
        if gap >= 1:
            why.append(f"The model compares ESB ratings, which move after every map this season. {F} sit at {rf_} and {U} at {ru_}, a gap of {gap} points"
                       + (f", and that gap is what produces the {pct}%." if same else f"; the model's latest run puts {F} at {pct}%."))
        else:
            why.append(f"The model compares ESB ratings, which move after every map this season. {F} ({round(float(pf['pts']))}) and {U} ({round(float(pu['pts']))}) are almost level, so this is close to a coin flip.")
    else:
        why.append(f"The model compares the two teams' ESB ratings from this season's tracked maps and lands on {F} at {pct}%.")
    support, against = [], []
    ff_, uf_ = (fa, fb) if fav == 1 else (fb, fa)
    fw = sum(1 for x in ff_ if x["r"] == "W" and not x["ff"]); fn = sum(1 for x in ff_ if not x["ff"])
    uw = sum(1 for x in uf_ if x["r"] == "W" and not x["ff"]); un = sum(1 for x in uf_ if not x["ff"])
    if fn >= 3 and un >= 3:
        if fw / fn > uw / un:
            support.append(f"{F} have the better recent form ({fw}-{fn - fw} against {uw}-{un - uw} in played matches)")
        elif fw / fn < uw / un:
            against.append(f"{U} come in hotter ({uw}-{un - uw} against {fw}-{fn - fw} in recent played matches)")
    sf, su = (sa, sb) if fav == 1 else (sb, sa)
    try:
        rf, ru = int(sf["rank"]), int(su["rank"])
        if rf < ru:
            support.append(f"{F} are higher in the table ({ordinal(rf)} vs {ordinal(ru)})")
        elif rf > ru:
            against.append(f"{U} are higher in the table ({ordinal(ru)} vs {ordinal(rf)})")
    except (TypeError, ValueError, KeyError):
        pass
    if f["h2h"]:
        fid = a["id"] if fav == 1 else b["id"]
        wf = sum(1 for x in f["h2h"] if not is_ff(x) and ((x.get("t1") or {}).get("id") == fid) == (x.get("winner") == 1))
        nh = sum(1 for x in f["h2h"] if not is_ff(x))
        if nh and wf * 2 > nh:
            support.append(f"{F} won {'the earlier meeting' if nh == 1 else f'{wf} of {nh} earlier meetings'}")
        elif nh and wf * 2 < nh:
            against.append(f"{U} won {'the earlier meeting' if nh == 1 else f'{nh - wf} of {nh} earlier meetings'}")
    pfx, pux = (pa, pb) if fav == 1 else (pb, pa)
    if pfx and pux and abs(pfx[0]["rating"] - pux[0]["rating"]) >= 0.05:
        if pfx[0]["rating"] > pux[0]["rating"]:
            support.append(f"{F} have the top rated player ({pfx[0]['nick']} {pfx[0]['rating']:.2f})")
        else:
            against.append(f"{U} have the top rated player ({pux[0]['nick']} {pux[0]['rating']:.2f})")
    if support:
        why.append("Backing the pick: " + "; ".join(support) + ".")
    if against:
        why.append("Pointing the other way: " + "; ".join(against) + ".")
    if conf == "Low":
        why.append("Few rated maps so far, so treat this one with extra caution.")
    secs.append({"k": "why", "h": "Why", "p": why})

    return {"id": m["id"], "t": m.get("t"), "when": when_pt(m.get("t")), "region": region, "division": division,
            "div": f["div"], "conf": m.get("conf") or "", "round": m.get("round"), "bo": f["bo"],
            "a": team(a, sa, ea), "b": team(b, sb, eb), "p1": round(p1, 3), "fav": fav, "pct": pct,
            "dconf": pr.get("conf") or "", "why_in": reasons, "sections": secs,
            "label": "Experimental estimate based on season results."}


def build_deep(dist, data=None, teams=None, rank=None):
    data = data if data is not None else (load(os.path.join(dist, "data.json")) or {})
    teams = teams if teams is not None else (load(os.path.join(dist, "teams.json")) or {})
    rank = rank if rank is not None else (load(os.path.join(dist, "rank.json")) or {})
    season = season_matches(season_path(dist))
    finished = collect_finished(data, teams, season)
    table = standings_map(data)
    esb = esb_map(rank)
    pred = rank.get("pred") or {}
    players = all_players(data, teams)
    ratings = rank.get("ratings") or {}
    divs, matches, always = [], [], {}
    tops = {}
    for dv in DIVS:
        top = division_top(rank, table, "NA", dv)
        tops[dv] = {tid: pl for tid, pl in top}
        names = []
        for tid, pl in top:
            s, e = table.get(tid) or {}, esb.get(tid) or {}
            names.append({"id": tid, "name": e.get("name") or s.get("name") or "", "place": pl,
                          "rec": rec_str(s.get("w"), s.get("l"), s.get("t")) if s else "", "pts": round(float(e["pts"])) if e.get("pts") is not None else None})
        divs.append({"division": dv, "div": "NA " + dv, "top": names})
    for dv in DIVS:
        places = division_places(rank, "NA", dv)
        for m in upcoming_na(data, teams):
            if m.get("division") != dv:
                continue
            a, b = m.get("t1") or {}, m.get("t2") or {}
            reasons = []
            if a["id"] in tops[dv] or b["id"] in tops[dv]:
                reasons.append("top10")
            for t in (a, b):
                if always_match(t.get("name")):
                    reasons.append("always")
                    always.setdefault(t["name"], 0)
                    always[t["name"]] += 1
            if not reasons:
                continue
            rec = deep_record(m, finished, table, esb, pred, players, ratings, rank, places, sorted(set(reasons)))
            if rec:
                matches.append(rec)
    # names in ALWAYS_PREDICT_TEAMS that exist in the NA tables (reported in the build log)
    found = sorted({s.get("name") for s in table.values() if s.get("region") == "NA" and always_match(s.get("name"))})
    matches.sort(key=lambda r: (DIVS.index(r["division"]), str(r.get("t") or "")))
    return {"generated": datetime.now(PT).isoformat(timespec="minutes"), "top_by": TOP_BY, "top_n": TOP_N,
            "divisions": divs, "matches": matches, "always_found": found, "always_counts": always,
            "label": "Experimental estimate based on season results."}


def write_deep(dist, blob):
    with open(os.path.join(dist, "predictions.json"), "w", encoding="utf-8") as fh:
        json.dump(blob, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    pub = {k: v for k, v in blob.items() if k not in ("always_found", "always_counts")}
    js = "window.ESB_PREDS = " + json.dumps(pub, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + ";\n"
    with open(os.path.join(dist, "predictions.js"), "w", encoding="utf-8") as fh:
        fh.write(js)


def build(dist):
    data = load(os.path.join(dist, "data.json")) or {}
    teams = load(os.path.join(dist, "teams.json")) or {}
    rank = load(os.path.join(dist, "rank.json")) or {}
    season = season_matches(season_path(dist))
    finished = collect_finished(data, teams, season)
    table = standings_map(data)
    esb = esb_map(rank)
    pred = rank.get("pred") or {}
    players = all_players(data, teams)
    ratings = rank.get("ratings") or {}
    out = {}
    for m in upcoming_na(data, teams):
        text = render(facts_for(m, finished, table, esb, pred, players, ratings))
        if text:
            out[m["id"]] = {"text": text, "a": (m.get("t1") or {}).get("name"), "b": (m.get("t2") or {}).get("name"),
                            "div": f"{m.get('region')} {m.get('division')}", "t": m.get("t")}
    return out


def write(dist, blob):
    path = os.path.join(dist, "writeups.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(blob, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    slim = {k: v["text"] for k, v in blob.items()}
    js = "window.ESB_WRITEUPS = " + json.dumps(slim, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + ";\n"
    with open(os.path.join(dist, "writeups.js"), "w", encoding="utf-8") as fh:
        fh.write(js)
    return path


def main(argv=None):
    argv = argv or sys.argv[1:]
    dist = argv[0] if argv else "dist"
    blob = build(dist)
    write(dist, blob)
    print(f"[writeups] {len(blob)} NA match previews")
    deep = build_deep(dist)
    write_deep(dist, deep)
    per = {dv: sum(1 for r in deep["matches"] if r["division"] == dv) for dv in DIVS}
    print(f"[writeups] deep predictions ({deep['top_by']} top {deep['top_n']}): {per}; always-predict teams found: {deep['always_found']} -> {deep['always_counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
