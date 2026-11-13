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
    return 0


if __name__ == "__main__":
    sys.exit(main())
