#!/usr/bin/env python3
"""v4.5 real path pages, sitemap, robots.txt and share images (Esports Scoreboard).

    python pages.py dist [--site https://winecoolermike.github.io/fragnet/] [--og-cache .ogcache] [--no-og]

Run on dist/ after the data refresh and BEFORE prerender.py (it uses the plain dist/index.html as the
template). For every team / player / match with at least one tracked match, and for the main sections,
it writes <route>/index.html - e.g. team/cs2/<id>/ - with a unique <title>, description, canonical,
Open Graph tags, JSON-LD and a static snapshot of the page (links between snapshots are real paths, so
the pages work without JavaScript). With JavaScript, app.js reads <meta name="fragnet-route"> and renders
the same view; #hash routes keep working everywhere.

Share images (1200x630 PNG, no logos) are drawn with Pillow for teams and matches only. Each image
is keyed by a hash of what it shows; unchanged images are reused from --og-cache, so a normal refresh
only draws the entities whose numbers changed. Never invents data: every value comes from the
data files; anything missing is simply left out.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone

import prerender as pr

# public base URL of the site (canonical, og:url, sitemap, robots, share images). One switch for a custom domain:
# set SITE_URL (env or repository variable) to e.g. https://esportsscoreboard.com/ ; links inside pages are relative.
SITE = (os.environ.get("SITE_URL") or "https://winecoolermike.github.io/fragnet/").strip()
SITE = SITE if SITE.endswith("/") else SITE + "/"
SITE_LABEL = [re.sub(r"^https?://", "", SITE).rstrip("/")]
SAFE_SEG = re.compile(r"^(?!\.+$)[A-Za-z0-9._-]{1,48}$")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
OG_VERSION = "og-2"   # bump to redraw every share image (v4.7 rebrand)
e, ext, pt, std = pr.e, pr.ext, pr.pt, pr.std


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-")


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default if default is not None else {}


def num(x, d=0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


PATH_MAP = {}   # audit B10: hash route -> readable/stable path (team slug-id8, vlr event id)
PATH_RE = re.compile(r'href="(team/cs2/[0-9a-f-]{36}|valorant/event-\d{1,2})/"')


def path_map(site):
    PATH_MAP.clear()
    for p in site.pages:
        r = p["route"]
        m = re.match(r"^team/cs2/([0-9a-f-]{36})$", r)
        if m:
            nm = slug(p["title"].split(" :: ")[0]) or "team"
            PATH_MAP[r] = f"team/cs2/{nm[:40].strip('-')}-{m.group(1)[:8]}"
    evs = ((site.d.get("valorant") or {}).get("events")) or []
    for i, ev in enumerate(evs):
        m = re.search(r"/event/(\d+)/([a-z0-9-]+)", str(ev.get("url") or ""), re.I)
        if m:
            PATH_MAP[f"valorant/event-{i + 1}"] = f"valorant/event-{m.group(1)}-{m.group(2).lower()[:60]}"
    for p in site.pages:
        new = PATH_MAP.get(p["route"])
        if new:
            p["path"] = new
            p["route"] = new   # the SPA resolves both forms (slug-id8 teams, vlr event ids)


def ilink(route, text, cls=""):
    """Link between snapshots: a real path relative to <base href> (works without JavaScript)."""
    return f'<a href="{e(route)}/"{(" class=" + chr(34) + cls + chr(34)) if cls else ""}>{e(text)}</a>'


def kv(rows):
    return ('<div class="rankbox"><table class="tbl kv"><tbody>'
            + "".join(f'<tr><th scope="row">{e(k)}</th><td>{v}</td></tr>' for k, v in rows if v not in (None, ""))
            + "</tbody></table></div>")


def table(head, rows, cls="tbl"):
    if not rows:
        return ""
    return (f'<div class="rankbox"><table class="{cls}"><thead><tr>' + "".join(head) + "</tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>")


PLAYER_CARD_MIN_ROUNDS = 50


class Site:
    def __init__(self, dist, site):
        self.dist, self.site = dist, site
        self.d = load(os.path.join(dist, "data.json"))
        self.tx = load(os.path.join(dist, "teams.json"))
        self.vx = load(os.path.join(dist, "val.json"))
        self.pages = []           # dicts: route, title, desc, body, og, ld, kind
        self.og_jobs = {}         # key -> (title, sub, lines, accent)
        cs = self.d.get("cs") or {}
        self.divs = sorted([dv for dv in cs.get("divisions") or [] if dv.get("teams")], key=lambda dv: 0 if dv.get("region") == "NA" else 1)
        seen, self.fin = set(), []
        for m in (cs.get("matches") or []) + (self.tx.get("matches") or []):
            if m.get("id") and m["id"] not in seen and m.get("t1") and m.get("t2") and SAFE_SEG.match(str(m["id"])):
                seen.add(m["id"])
                self.fin.append(m)
        self.fin.sort(key=lambda m: m.get("t") or "", reverse=True)
        seen = set()
        self.up = []
        for m in (cs.get("upcoming") or []) + (self.tx.get("upcoming") or []):
            if m.get("id") and m["id"] not in seen and m.get("t1") and m.get("t2"):
                seen.add(m["id"])
                self.up.append(m)
        self.up.sort(key=lambda m: m.get("t") or "")
        self.by_team = {}
        for m in self.fin:
            for s in ("t1", "t2"):
                self.by_team.setdefault((m.get(s) or {}).get("id"), []).append(m)
        self.up_team = {}
        for m in self.up:
            for s in ("t1", "t2"):
                self.up_team.setdefault((m.get(s) or {}).get("id"), []).append(m)
        cols = self.tx.get("player_cols") or []
        self.players = {}
        for p in (cs.get("players") or cs.get("top_players") or []) + [dict(zip(cols, r)) for r in self.tx.get("players") or []]:
            k = str(p.get("nick") or "").lower()
            if k and (k not in self.players or num(p.get("rounds")) > num(self.players[k].get("rounds"))):
                self.players[k] = p
        val = self.d.get("valorant") or {}
        self.vres = [m for m in val.get("results") or [] if self.vid(m.get("url"))]
        self.vdet = self.vx.get("matches") if isinstance(self.vx.get("matches"), dict) else {}
        self.vteams_meta = self.vx.get("teams") or {}
        self.team_rank = {}
        for dv in self.divs:
            for t in dv.get("teams") or []:
                if t.get("id"):
                    self.team_rank[t["id"]] = (t, dv)

    @staticmethod
    def vid(u):
        m = re.search(r"vlr\.gg/(\d+)/", u or "")
        return m.group(1) if m else ""

    # ------------------------------------------------------------- helpers
    def div_id(self, dv):
        return slug(f'{dv.get("region")}-{dv.get("division")}')

    def cs_side(self, s):
        s = s or {}
        if s.get("id") and UUID.match(str(s["id"])):
            return ilink(f'team/cs2/{s["id"]}', s.get("name") or "TBD")
        return e(s.get("name") or "TBD")

    def form(self, tid, before=None):
        out = []
        for m in sorted(self.by_team.get(tid, []), key=lambda m: m.get("t") or ""):
            if before and (m.get("t") or "") >= before:
                continue
            side = 1 if (m.get("t1") or {}).get("id") == tid else 2
            w = m.get("winner")
            out.append("W" if w == side else "L" if w in (1, 2) else "D")
        return out[-5:]

    def form_html(self, f):
        if not f:
            return '<span class="dim">&ndash;</span>'
        return '<span class="form">' + "".join(f'<span class="fq {x.lower()}">{x}</span>' for x in f) + "</span>"

    def cs_results(self, ms, limit=10):
        rows = []
        for m in ms[:limit]:
            w = m.get("winner")
            rows.append(f'<tr><td class="dim hide-sm">{e(pt(m.get("t"), "%b %-d"))}</td><td class="n {"win" if w == 1 else "lose"}">{self.cs_side(m.get("t1"))}</td>'
                        f'<td class="score">{ilink("match/cs2/" + m["id"], str(int(num(m.get("s1")))) + ":" + str(int(num(m.get("s2")))))}</td>'
                        f'<td class="{"win" if w == 2 else "lose"}">{self.cs_side(m.get("t2"))}</td><td class="hide-sm">{e((m.get("region") or "") + " " + (m.get("division") or ""))}</td></tr>')
        return table(['<th class="first hide-sm">Date</th>', '<th class="n">Team 1</th>', '<th class="c">Score</th>', "<th>Team 2</th>", '<th class="hide-sm">Division</th>'], rows, "tbl res") \
            or '<div class="empty">No finished matches in the tracked data.</div>'

    def cs_upcoming(self, ms, limit=5):
        rows = [f'<tr><td class="dim">{e(pt(m.get("t"), "%b %-d, %H:%M") or "TBD")}</td><td class="n">{self.cs_side(m.get("t1"))}</td><td class="c">vs</td><td>{self.cs_side(m.get("t2"))}</td></tr>' for m in ms[:limit]]
        return table(['<th class="first">Scheduled (PT)</th>', '<th class="n">Team 1</th>', '<th class="c"></th>', "<th>Team 2</th>"], rows, "tbl res") \
            or '<div class="empty">No upcoming matches listed.</div>'

    def vteam_link(self, name):
        if not hasattr(self, "_vres_slugs"):   # team pages exist only for teams with >=1 tracked result
            self._vres_slugs = {slug(m.get(sd)) for m in self.vres for sd in ("team1", "team2")}
        return ilink("team/val/" + slug(name), name) if slug(name) and slug(name) in self._vres_slugs else e(name)

    def v_results(self, ms, limit=10):
        rows = []
        for m in ms[:limit]:
            w = m.get("winner")
            rows.append(f'<tr><td class="dim hide-sm">{e(pt(m.get("ts"), "%b %-d"))}</td><td class="n {"win" if w == 0 else "lose"}">{self.vteam_link(m.get("team1"))}</td>'
                        f'<td class="score">{ilink("match/val/" + self.vid(m.get("url")), str(m.get("score1")) + ":" + str(m.get("score2")))}</td>'
                        f'<td class="{"win" if w == 1 else "lose"}">{self.vteam_link(m.get("team2"))}</td><td class="hide-sm">{e(m.get("event"))}</td></tr>')
        return table(['<th class="first hide-sm">Date</th>', '<th class="n">Team 1</th>', '<th class="c">Score</th>', "<th>Team 2</th>", '<th class="hide-sm">Event</th>'], rows, "tbl res") \
            or '<div class="empty">No results in the tracked data.</div>'

    def add(self, route, title, desc, body, og=None, ld=None, kind="section"):
        self.pages.append({"route": route, "title": title, "desc": desc[:300], "body": body, "og": og, "ld": ld, "kind": kind})

    # ------------------------------------------------------------- CS2
    def build_cs(self):
        cs = self.d.get("cs") or {}
        season = (cs.get("season") or {}).get("name") or "ESEA League"
        ov = []
        for i, dv in enumerate(self.divs):
            rows = []
            for t in dv.get("teams") or []:
                rows.append(f'<tr><td class="rk"><span>{e(t.get("rank"))}</span></td><td class="team">{self.cs_side(t)}<span class="cc">{e(t.get("country"))}</span></td>'
                            f'<td class="n">{int(num(t.get("w")))}</td><td class="n">{int(num(t.get("l")))}</td><td class="n"><b>{int(num(t.get("pts")))}</b></td><td class="c">{self.form_html(self.form(t.get("id")))}</td></tr>')
            name = f'{dv.get("region")} {dv.get("division")}'
            body = (std(f"Counter-Strike 2 :: {e(name)} Standings", e(season), "")
                    + table(['<th class="first c">#</th>', "<th>Team</th>", '<th class="n">W</th>', '<th class="n">L</th>', '<th class="n">Pts</th>', '<th class="c">Form</th>'], rows)
                    + f'<div class="note">{e(dv.get("stage") or "")} &middot; {ext(dv.get("link"), "full table on FACEIT")}</div>')
            lead = (dv.get("teams") or [{}])[0]
            desc = f"ESEA {season} {name} standings: {len(dv.get('teams') or [])} teams, led by {lead.get('name')} ({int(num(lead.get('w')))}-{int(num(lead.get('l')))}). Form, results and rosters on Esports Scoreboard."
            self.add("cs2/" + self.div_id(dv), f"{name} Standings :: ESEA League CS2", desc, body)
            ov.append(f'<tr><td class="team">{ilink("cs2/" + self.div_id(dv), name)}</td><td>{self.cs_side(lead) if lead.get("name") else "&ndash;"}</td><td class="n">{len(dv.get("teams") or [])}</td></tr>')
        if ov:
            self.add("cs2", "Counter-Strike 2 :: ESEA League", f"ESEA {season} CS2 standings for {len(ov)} divisions in North America and Europe, with leaders, form, results and top players.",
                     std("Counter-Strike 2 :: ESEA League", e(season), table(['<th class="first">Division</th>', "<th>Leader</th>", '<th class="n">Teams</th>'], ov)))
        self.add("cs2/results", "CS2 Match Results :: ESEA League", f"Latest ESEA League ({season}) match results in North America and Europe, with scores, maps and scoreboards.",
                 std("Counter-Strike 2 :: Match Results", "EU + NA", self.cs_results(self.fin, 50)))
        # v4.6: every division, top 25 by K/D (min. 20 rounds) from all players with stats; the live page sorts/filters/pages the rest
        minr = int(num((cs.get("top_players_meta") or {}).get("min_rounds") or 20))
        body, total = "", 0
        for dv in self.divs:
            pool = [p for p in self.players.values() if p.get("region") == dv.get("region") and p.get("division") == dv.get("division") and num(p.get("rounds")) >= minr]
            pool.sort(key=lambda p: (-num(p.get("kd")), -num(p.get("adr")), str(p.get("nick")).lower()))
            total += len(pool)
            rows = [f'<tr><td class="rk"><span>{i + 1}</span></td><td class="team">{self.plink(p.get("nick"))}</td><td class="n hide-sm">{int(num(p.get("rounds")))}</td>'
                    f'<td class="n">{num(p.get("kd")):.2f}</td><td class="n">{num(p.get("adr")):.1f}</td><td class="n hide-sm">{round(num(p.get("hs")))}%</td></tr>' for i, p in enumerate(pool[:25])]
            name = f'{dv.get("region")} {dv.get("division")}'
            body += f'<h2 class="subhead">Top Fraggers :: {e(name)}</h2>' + (table(['<th class="first c">#</th>', "<th>Player</th>", '<th class="n hide-sm">Rnds</th>', '<th class="n">K/D</th>', '<th class="n">ADR</th>', '<th class="n hide-sm">HS%</th>'], rows)
                     + f'<div class="note">Top {len(rows)} of {len(pool)} players with at least {minr} rounds, by K/D.</div>' if rows else f'<div class="empty">No player in {e(name)} has {minr} rounds yet.</div>')
        self.add("cs2/players", "Top Fraggers :: ESEA League CS2", f"ESEA League ({season}) top fraggers in every NA and EU division: {total} players with {minr}+ rounds, by K/D with ADR and headshot rate.",
                 std("Counter-Strike 2 :: Top Fraggers", "every division", body))
        # teams with at least one tracked match
        for tid, (t, dv) in self.team_rank.items():
            ms = self.by_team.get(tid, [])
            ups = self.up_team.get(tid, [])
            if not ms and not ups:
                continue
            name, dn = t.get("name") or "Team", f'{dv.get("region")} {dv.get("division")}'
            ros = t.get("roster")
            if not ros:
                xr = (self.tx.get("rosters") or {}).get(tid) or {}
                ros = [{"nick": a[0], "country": a[1], "sub": bool(a[2]) if len(a) > 2 else False} for a in xr.get("r") or []]
            rrows = []
            for r in ros or []:
                p = self.players.get(str(r.get("nick") or "").lower())
                rrows.append(f'<tr><td class="team">{self.plink(r.get("nick"))}</td><td>{e(r.get("country"))}</td><td>{"Substitute" if r.get("sub") else "Player"}</td>'
                             f'<td class="n">{(f"{num(p.get(chr(107) + chr(100))):.2f}") if p else "&ndash;"}</td></tr>')
            f = self.form(tid)
            info = kv([("Division", ilink("cs2/" + self.div_id(dv), dn)), ("Standing", f'#{e(t.get("rank"))} &middot; {int(num(t.get("w")))}W {int(num(t.get("l")))}L &middot; {int(num(t.get("pts")))} pts'),
                       ("Form", self.form_html(f)), ("Country", e(t.get("country"))), ("FACEIT", ext(pr.team_url(t), "Team page on FACEIT"))])
            body = (std(e(name), "CS2 &middot; ESEA League team", info)
                    + '<h2 class="subhead">Roster</h2>' + (table(['<th class="first">Player</th>', "<th>Country</th>", "<th>Role</th>", '<th class="n">K/D</th>'], rrows) or '<div class="empty">No roster in the public data.</div>')
                    + '<h2 class="subhead">Recent Results</h2>' + self.cs_results(ms) + '<h2 class="subhead">Upcoming Matches</h2>' + self.cs_upcoming(ups))
            rec = f"{int(num(t.get('w')))}-{int(num(t.get('l')))}"
            desc = f"{name}: #{t.get('rank')} in ESEA {dn} ({rec}, {int(num(t.get('pts')))} pts)" + (f", form {' '.join(f)}" if f else "") + ". Roster, results and upcoming matches on Esports Scoreboard."
            ogk = "cs-team-" + tid
            self.og_jobs[ogk] = (name, f"ESEA {dn} · CS2", [("RANK", "#" + str(t.get("rank"))), ("RECORD", rec), ("FORM", " ".join(f) or "-")], (217, 80, 0))
            self.add("team/cs2/" + tid, f"{name} :: ESEA {dn} CS2 team", desc, body, og=ogk, kind="team",
                     ld={"@context": "https://schema.org", "@type": "SportsTeam", "name": name, "sport": "Counter-Strike 2",
                         "memberOf": {"@type": "SportsOrganization", "name": f"ESEA League {dn}"}, "url": self.site + "team/cs2/" + tid + "/"})
        # players with at least one match
        for k, p in self.players.items():
            nick = str(p.get("nick") or "")
            if not SAFE_SEG.match(nick) or num(p.get("matches")) < 1:
                continue
            tid = p.get("team_id")
            team = (ilink("team/cs2/" + tid, p.get("team")) if tid and tid in self.team_rank and (self.by_team.get(tid) or self.up_team.get(tid)) else e(p.get("team") or "-"))
            info = kv([("Team", team), ("Stats group", e((p.get("region") or "") + " " + (p.get("division") or ""))),
                       ("Matches / rounds", f'{int(num(p.get("matches")))} / {int(num(p.get("rounds")))}'),
                       ("K/D", f'<b>{num(p.get("kd")):.2f}</b>'), ("ADR", f'{num(p.get("adr")):.1f}'), ("HS%", f'{round(num(p.get("hs")))}%'),
                       ("Division rank", f'#{int(num(p.get("drank")))} of {int(num(p.get("dpool")))}' if p.get("drank") else ""),
                       ("FACEIT", ext(p.get("url") or "https://www.faceit.com/en/players/" + nick, "Profile on FACEIT"))])
            desc = f"{nick}" + (f" ({p.get('team')})" if p.get("team") else "") + f" in ESEA {p.get('region')} {p.get('division')}: K/D {num(p.get('kd')):.2f}, ADR {num(p.get('adr')):.1f} over {int(num(p.get('rounds')))} rounds."
            ogk = ("cs-team-" + tid) if tid and ("cs-team-" + tid) in self.og_jobs else None
            if num(p.get("rounds")) >= PLAYER_CARD_MIN_ROUNDS:   # v5.3 season card share image (real stats only)
                ogk = "cs-pl-" + slug(nick) + "-" + hashlib.sha1(nick.encode()).hexdigest()[:6]
                self.og_jobs[ogk] = (nick, (f"{p.get('team')} · " if p.get("team") else "") + f"ESEA {p.get('region')} {p.get('division')} · season card"[:70],
                                     [("K/D", f'{num(p.get("kd")):.2f}'), ("ADR", f'{num(p.get("adr")):.1f}'),
                                      ("DIV RANK" if p.get("drank") else "ROUNDS", f'#{int(num(p.get("drank")))}/{int(num(p.get("dpool")))}' if p.get("drank") else str(int(num(p.get("rounds")))))], (217, 80, 0))
            self.add("player/cs2/" + nick, f"{nick} :: CS2 ESEA player", desc, std(e(nick), "CS2 &middot; ESEA League player", info),
                     og=ogk, kind="player",
                     ld={"@context": "https://schema.org", "@type": "Person", "name": nick, "url": self.site + "player/cs2/" + nick + "/"})
        # matches
        for m in self.fin:
            t1, t2 = m.get("t1") or {}, m.get("t2") or {}
            sc = f'{int(num(m.get("s1")))}:{int(num(m.get("s2")))}'
            dn = f'{m.get("region")} {m.get("division")}'
            maps = m.get("maps") or []
            mp = "".join(
                f'<h2 class="subhead">{e(x.get("map"))} <small>{int(num(x.get("s1")))}:{int(num(x.get("s2")))}</small></h2>'
                + "".join(table([f'<th class="first">{e(side.get("name"))}</th>', '<th class="n">K</th>', '<th class="n">D</th>', '<th class="n">ADR</th>'],
                                [f'<tr><td class="team">{self.plink(r[0])}</td><td class="n">{int(num(r[1]))}</td><td class="n">{int(num(r[2]))}</td><td class="n">{num(r[3]):.1f}</td></tr>' for r in (x.get(pk) or [])])
                          for side, pk in ((t1, "p1"), (t2, "p2")))
                for x in maps)
            info = kv([("Division", ilink("cs2/" + slug(dn), dn) + f' &middot; round {int(num(m.get("round")))} &middot; best of {int(num(m.get("bo") or 1))}'),
                       ("Finished", e(pt(m.get("t")))), ("Result", f'{self.cs_side(t1)} <b>{sc}</b> {self.cs_side(t2)}'),
                       ("Map veto", ("Picked: <b>" + e(", ".join(m.get("pick") or [])) + "</b>") if m.get("pick") else '<span class="dim">not published for this match</span>'),
                       ("FACEIT", ext(pr.room_url(m), "Match room on FACEIT"))])
            body = std(f'{e(t1.get("name"))} vs {e(t2.get("name"))}', "CS2 &middot; ESEA match", info) + (mp or '<div class="empty">No scoreboard in the tracked data for this match.</div>')
            date = pt(m.get("t"), "%b %-d, %Y")
            desc = f"{t1.get('name')} {sc} {t2.get('name')} - ESEA {dn}, round {int(num(m.get('round')))}" + (f", {date}" if date else "") + (f". Maps: {', '.join(x.get('map') for x in maps)}." if maps else ".")
            ogk = "cs-match-" + m["id"]
            self.og_jobs[ogk] = (f"{t1.get('name')} vs {t2.get('name')}", f"ESEA {dn} · round {int(num(m.get('round')))}", [("SCORE", sc), ("MAPS", ", ".join(x.get("map") for x in maps)[:22] or "-"), ("DATE", date or "-")], (217, 80, 0))
            self.add("match/cs2/" + m["id"], f"{t1.get('name')} vs {t2.get('name')} :: ESEA match", desc, body, og=ogk, kind="match",
                     ld={"@context": "https://schema.org", "@type": "SportsEvent", "name": f"{t1.get('name')} vs {t2.get('name')}", "sport": "Counter-Strike 2",
                         "startDate": m.get("t"), "eventStatus": "https://schema.org/EventScheduled",
                         "competitor": [{"@type": "SportsTeam", "name": t1.get("name")}, {"@type": "SportsTeam", "name": t2.get("name")}],
                         "url": self.site + "match/cs2/" + m["id"] + "/"})

    def plink(self, nick):
        nick = str(nick or "")
        p = self.players.get(nick.lower())
        return ilink("player/cs2/" + nick, nick) if SAFE_SEG.match(nick) and p and num(p.get("matches")) >= 1 else e(nick)

    # ------------------------------------------------------------- Valorant
    def build_val(self):
        val = self.d.get("valorant") or {}
        evs = val.get("events") or []
        order = sorted(range(len(evs)), key=lambda i: 0 if re.search(r"north america", evs[i].get("title") or "", re.I) else 1)
        teams = {}
        for i, ev in enumerate(evs):
            rows = []
            for t in ev.get("standings") or []:
                teams.setdefault(slug(t.get("team")), {"name": t.get("team"), "place": [], "res": [], "country": t.get("country")})["place"].append((ev, t, i))
                rows.append(f'<tr><td class="rk"><span>{e(t.get("place"))}</span></td><td class="team">{self.vteam_link(t.get("team"))}<span class="cc">{e(t.get("country"))}</span></td><td class="n">{e(t.get("prize"))}</td></tr>')
            body = std(e(ev.get("title")) + " :: Final Standings", e(ev.get("dates")), table(['<th class="first c">Place</th>', "<th>Team</th>", '<th class="n">Prize</th>'], rows)
                       + f'<div class="note">{ext(ev.get("url"), "event page on vlr.gg")}</div>')
            w0 = (ev.get("standings") or [{}])[0]
            self.add(f"valorant/event-{i + 1}", f"{ev.get('title')} :: Valorant", f"{ev.get('title')} ({ev.get('dates')}) final standings" + (f", won by {w0.get('team')}" if w0.get("team") else "") + ". Teams, prize money and top players on Esports Scoreboard.", body)
        rows = [f'<tr><td class="team">{ilink("valorant/event-" + str(i + 1), evs[i].get("title"))}</td><td class="hide-sm dim">{e(evs[i].get("dates"))}</td></tr>' for i in order]
        self.add("valorant", "Valorant :: Challengers / Game Changers", f"{len(evs)} Valorant Challengers and Game Changers events tracked: final standings, results and top players.",
                 std("Valorant :: Tracked Events", "", table(['<th class="first">Event</th>', '<th class="hide-sm">Dates</th>'], rows)))
        for m in self.vres:
            for side in ("team1", "team2"):
                if slug(m.get(side)):
                    teams.setdefault(slug(m.get(side)), {"name": m.get(side), "place": [], "res": [], "country": ""})["res"].append(m)
        self.add("valorant/results", "Valorant Results :: Challengers / Game Changers", f"Latest {len(self.vres)} tier-2 and Game Changers Valorant results from vlr.gg.",
                 std("Valorant :: Recent Results", "", self.v_results(self.vres, 60)))
        acols = self.vx.get("agg_cols") or []
        agg = [dict(zip(acols, r)) for r in self.vx.get("agg") or []]
        tp = sorted([p for p in agg if num(p.get("rnd")) >= 100 and num(p.get("rating"))], key=lambda p: (-num(p.get("rating")), -num(p.get("acs")), str(p.get("name")).lower()))[:100] or (val.get("top_players") or [])
        rows = [f'<tr><td class="rk"><span>{i + 1}</span></td><td class="team">{self.vplink(p.get("name"))}</td><td class="n">{num(p.get("rating")):.2f}</td><td class="n">{round(num(p.get("acs")))}</td></tr>' for i, p in enumerate(tp)]
        self.add("valorant/players", "Valorant Top Players :: Challengers / Game Changers", f"Top {len(tp)} Valorant Challengers / Game Changers players by vlr.gg rating (100+ rounds) across the tracked events.",
                 std("Valorant :: Top Players", "", table(['<th class="first c">#</th>', "<th>Player</th>", '<th class="n">R</th>', '<th class="n">ACS</th>'], rows)))
        for sl, t in teams.items():
            if not t["res"] or not SAFE_SEG.match(sl):
                continue                  # >= 1 tracked match
            w = sum(1 for m in t["res"] if (m.get("winner") == 0 and slug(m.get("team1")) == sl) or (m.get("winner") == 1 and slug(m.get("team2")) == sl))
            l = len(t["res"]) - w
            pl = "".join(f'<tr><td class="rk"><span>{e(x.get("place"))}</span></td><td class="team">{ilink("valorant/event-" + str(i + 1), ev.get("title"))}</td><td class="n">{e(x.get("prize"))}</td></tr>' for ev, x, i in t["place"])
            body = (std(e(t["name"]), "Valorant &middot; team", kv([("Recent series", f"{w}W {l}L in the tracked results"), ("Country / region", e(t["country"]))]))
                    + ('<h2 class="subhead">Event Placings</h2>' + table(['<th class="first c">Place</th>', "<th>Event</th>", '<th class="n">Prize</th>'], [pl]) if pl else "")
                    + '<h2 class="subhead">Recent Results</h2>' + self.v_results(t["res"]))
            ogk = "val-team-" + sl
            self.og_jobs[ogk] = (t["name"], "Valorant · Challengers / Game Changers", [("SERIES", f"{w}-{l}"), ("EVENTS", str(len(t["place"]))), ("LATEST", pt(t["res"][0].get("ts"), "%b %-d") or "-")], (200, 40, 40))
            self.add("team/val/" + sl, f"{t['name']} :: Valorant team", f"{t['name']}: {w}-{l} in the tracked Valorant tier-2 results" + (f", {len(t['place'])} event placing(s)" if t["place"] else "") + ". Results and roster on Esports Scoreboard.",
                     body, og=ogk, kind="team", ld={"@context": "https://schema.org", "@type": "SportsTeam", "name": t["name"], "sport": "Valorant", "url": self.site + "team/val/" + sl + "/"})
        self._vteams = teams
        cols = self.vx.get("agg_cols") or []
        best = {}   # one page per name (case-insensitive), the entry with most rounds - same pick as app.js vPlayerVal
        for r in self.vx.get("agg") or []:
            p = dict(zip(cols, r))
            k = str(p.get("name") or "").lower()
            if k not in best or num(p.get("rnd")) > num(best[k].get("rnd")):
                best[k] = p
        for p in best.values():
            name = str(p.get("name") or "")
            if not SAFE_SEG.match(name) or num(p.get("rnd")) < 1 or num(p.get("maps")) < 1:
                continue
            tm = (self.vteams_meta.get(str(p.get("team"))) or {}).get("name") if p.get("team") else ""
            info = kv([("Team", self.vteam_link(tm) if tm and slug(tm) in teams and teams[slug(tm)]["res"] else e(tm or p.get("tag") or "-")),
                       ("Rating", f'<b>{num(p.get("rating")):.2f}</b>'), ("ACS", str(round(num(p.get("acs"))))), ("K/D", f'{num(p.get("kd")):.2f}' if p.get("kd") is not None else "-"),
                       ("Rounds / maps", f'{int(num(p.get("rnd")))} / {int(num(p.get("maps")))}')])
            self.add("player/val/" + name, f"{name} :: Valorant player", f"{name}" + (f" ({tm})" if tm else "") + f": vlr.gg rating {num(p.get('rating')):.2f}, ACS {round(num(p.get('acs')))} over {int(num(p.get('rnd')))} rounds in the tracked Challengers / Game Changers events.",
                     std(e(name), "Valorant &middot; player", info), og=("val-team-" + slug(tm)) if tm and ("val-team-" + slug(tm)) in self.og_jobs else None, kind="player",
                     ld={"@context": "https://schema.org", "@type": "Person", "name": name, "url": self.site + "player/val/" + name + "/"})
        for m in self.vres:
            i = self.vid(m.get("url"))
            det = self.vdet.get(i) or {}
            maps = det.get("maps") or []
            rows = [f'<tr><td><b>{e(x.get("map"))}</b></td><td class="c">{int(num(x.get("s1")))}</td><td class="c">{int(num(x.get("s2")))}</td></tr>' for x in maps]
            sc = f'{m.get("score1")}:{m.get("score2")}'
            info = kv([("Event", e(m.get("event")) + (f' &middot; {e(m.get("series"))}' if m.get("series") else "")), ("Date", e(pt(m.get("ts")))),
                       ("Result", f'{self.vteam_link(m.get("team1"))} <b>{e(sc)}</b> {self.vteam_link(m.get("team2"))}'),
                       ("Map veto", e(det.get("veto")) if det.get("veto") else ""), ("vlr.gg", ext(m.get("url"), "Match page on vlr.gg"))])
            body = std(f'{e(m.get("team1"))} vs {e(m.get("team2"))}', "Valorant &middot; match", info) + table(['<th class="first">Map</th>', f'<th class="c">{e(m.get("team1"))}</th>', f'<th class="c">{e(m.get("team2"))}</th>'], rows)
            date = pt(m.get("ts"), "%b %-d, %Y")
            ogk = "val-match-" + i
            self.og_jobs[ogk] = (f"{m.get('team1')} vs {m.get('team2')}", str(m.get("event") or "Valorant")[:60], [("SCORE", sc), ("MAPS", ", ".join(x.get("map") for x in maps)[:22] or "-"), ("DATE", date or "-")], (200, 40, 40))
            self.add("match/val/" + i, f"{m.get('team1')} vs {m.get('team2')}" + (f", {pt(m.get('ts'), '%b %-d')}" if m.get("ts") else "") + " :: Valorant match", f"{m.get('team1')} {sc} {m.get('team2')} - {m.get('event')}" + (f", {date}" if date else "") + ".", body, og=ogk, kind="match",
                     ld={"@context": "https://schema.org", "@type": "SportsEvent", "name": f"{m.get('team1')} vs {m.get('team2')}", "sport": "Valorant", "startDate": m.get("ts"),
                         "competitor": [{"@type": "SportsTeam", "name": m.get("team1")}, {"@type": "SportsTeam", "name": m.get("team2")}], "url": self.site + "match/val/" + i + "/"})

    def vplink(self, name):
        return ilink("player/val/" + str(name), name) if SAFE_SEG.match(str(name or "")) else e(name)

    # ------------------------------------------------------------- WoW + news
    def build_rest(self):
        wow = self.d.get("wow") or {}
        raid = (wow.get("raid") or {}).get("name") or "Mythic raid"
        for rg in ("us", "eu"):
            rows = [f'<tr><td class="rk"><span>{e(g.get("rank"))}</span></td><td class="team">{e(g.get("guild"))}</td><td class="hide-sm">{e(g.get("realm"))}</td><td>{e(g.get("progress"))}</td></tr>' for g in (wow.get("rankings") or {}).get(rg) or []]
            if rows:
                top = ((wow.get("rankings") or {}).get(rg) or [{}])[0]
                self.add("wow/" + rg, f"WoW {rg.upper()} Mythic Rankings :: {raid}", f"World of Warcraft {rg.upper()} Mythic raid race in {raid}: #1 {top.get('guild')} ({top.get('progress')}). Top {len(rows)} guilds from Raider.IO.",
                         std(f"WoW :: {rg.upper()} Mythic Rankings", e(raid), table(['<th class="first c">#</th>', "<th>Guild</th>", '<th class="hide-sm">Realm</th>', "<th>Progress</th>"], rows)
                             + f'<div class="note">{ext(pr.rio_page(wow.get("raid"), rg), "Full rankings on Raider.IO")}</div>'))
        news = sorted((self.d.get("news") or {}).get("items") or [], key=lambda n: n.get("date") or "", reverse=True)[:40]
        if news:
            self.add("news", "Esports News :: Esports Scoreboard", f"Latest esports headlines (CS2, Valorant, WoW) from {', '.join(sorted({str(n.get('source')) for n in news})[:5])}.",
                     std("Esports Scoreboard News Wire", f"{len(news)} headlines", '<div class="newsbox">' + "".join(f'<div class="item">{ext(n.get("url"), n.get("title"))}<span class="src">({e(n.get("source"))})</span></div>' for n in news) + "</div>"))

        # audit B5: natural section URLs get real pages (the SPA takes over with JS)
        cs = self.d.get("cs") or {}
        today = [m for m in (cs.get("upcoming") or []) + (cs.get("live") or [])][:30]
        self.add("cs2/today", "CS2 Matches Today :: ESEA League", "Today's ESEA CS2 matches with live status, times in Pacific Time, and links to FACEIT match rooms.",
                 std("Matches Today", "CS2 &middot; ESEA", f'<div class="infobox">{len(today)} upcoming or live ESEA matches in the latest data. Enable JavaScript for live status, filters and the day strip.</div>' +
                     "".join(f'<div class="spot-line">{e(pt(m.get("t"), "%a %H:%M"))} &middot; {e((m.get("t1") or {}).get("name"))} vs {e((m.get("t2") or {}).get("name"))} <span class="dim">{e(m.get("region"))} {e(m.get("division"))}</span></div>' for m in today[:20])))
        disc = "https://github.com/winecoolermike/fragnet/discussions"
        self.add("forums", "Forums :: Esports Scoreboard", "Esports Scoreboard community forums on GitHub Discussions: CS2, Valorant, WoW, match threads and site feedback.",
                 std("Forums", "GitHub Discussions", f'<div class="infobox">The forums run on GitHub Discussions. {ext(disc, "Open the forums")}</div>'))
        self.add("recruiting", "LFP / LFT recruiting board :: Esports Scoreboard", "Amateur and semi-pro teams looking for players and players looking for teams, reviewed before posting.",
                 std("LFP / LFT Recruiting Board", "reviewed posts", '<div class="infobox">Teams looking for players and players looking for teams. Posts are reviewed before they appear. Enable JavaScript to see the board and the post forms.</div>'))
        self.add("wow", "World of Warcraft Mythic Raid Race :: Esports Scoreboard", f"World of Warcraft Mythic raid race in {raid}: US and EU guild rankings from Raider.IO.",
                 std("World of Warcraft :: Mythic Raid Race", e(raid), f'<div class="infobox">{ilink("wow/us", "US rankings")} &middot; {ilink("wow/eu", "EU rankings")}</div>'))
        self.add("about", "About :: Esports Scoreboard", "About Esports Scoreboard, an independent fan-made tracker for ESEA League CS2, Valorant Challengers and the WoW Mythic raid race.",
                 std("About Esports Scoreboard", "independent fan project", '<div class="infobox">An independent fan project tracking ESEA League CS2, Valorant Challengers / Game Changers and the WoW Mythic raid race. Data from FACEIT, vlr.gg and Raider.IO; every team, player and guild links to its source. Not affiliated with FACEIT, ESEA, Valve, Riot Games or Blizzard.</div>'))
        self.add("search", "Search :: Esports Scoreboard", "Search teams, players, guilds and headlines on Esports Scoreboard.",
                 std("Search", "teams, players, guilds", '<div class="infobox">Search needs JavaScript. Browse: ' + ilink("cs2", "CS2 standings") + " &middot; " + ilink("valorant", "Valorant") + " &middot; " + ilink("wow", "WoW") + "</div>"))

    # ------------------------------------------------------------- v5.2 weekly roundups (spot.json from spotlight.py)
    def spot_html(self, b, routes):
        def lk(route, text):
            return ilink(route, text) if route in routes else e(text)
        out = []
        ups = b.get("upsets") or []
        out.append('<h2 class="subhead">Upset of the week</h2>' + (
            "".join(f'<div class="spot-line">{lk("team/cs2/" + u["winner"]["id"], u["winner"]["name"])} (#{u["winner"]["rank"]}) beat '
                    f'{lk("team/cs2/" + u["loser"]["id"], u["loser"]["name"])} (#{u["loser"]["rank"]}) {lk("match/cs2/" + u["id"], u["score"])} '
                    f'<span class="dim">{e(u["region"])} {e(u["division"])}</span></div>' for u in ups[:3])
            or '<div class="empty">No upset by this rule in this period.</div>'))
        fr = b.get("fraggers") or []
        out.append('<h2 class="subhead">Top fragger by division</h2>' + (table(["<th class=\"first\">Division</th>", "<th>Player</th>", "<th class=\"n\">Kills</th>", "<th class=\"n\">Maps</th>"],
            [f'<tr><td>{e(f["div"])}</td><td class="team">{lk("player/cs2/" + f["nick"], f["nick"])} <span class="dim">{e(f["team"])}</span></td><td class="n">{lk("match/cs2/" + str(f["match"]), str(f["kills"]))}</td><td class="n">{f["maps"]}</td></tr>' for f in fr])
            or '<div class="empty">No FACEIT scoreboards in this period.</div>'))
        st = b.get("streaks") or []
        out.append('<h2 class="subhead">Hottest streak</h2>' + ("".join(f'<div class="spot-line">{lk("team/cs2/" + x["id"], x["name"])}: {x["n"]} wins in a row <span class="dim">{e(x["div"])}</span></div>' for x in st[:3])
                   or '<div class="empty">No team is on a 3+ win streak.</div>'))
        w = b.get("wow") or {}
        out.append(f'<h2 class="subhead">WoW Mythic kills</h2>' + ("".join(f'<div class="spot-line">{ext(g.get("url"), g.get("guild"))} ({e(g.get("region", "").upper())}): {g["kills"]} kill{"s" if g["kills"] != 1 else ""} &middot; {e(", ".join(g.get("bosses") or []))}</div>' for g in w.get("guilds") or [])
                   or '<div class="empty">No Mythic kills by tracked guilds in this period.</div>'))
        return "".join(out)

    def build_roundups(self):
        sp = load(os.path.join(self.dist, "spot.json"))
        weeks = sp.get("weeks") or []
        if not weeks:
            return
        routes = {p["route"] for p in self.pages}
        rows = []
        for w in weeks:
            if not re.match(r"^\d{4}-w\d{2}$", str(w.get("id"))):
                continue
            num_ = int(w["id"][-2:])
            intro = (f'<div class="infobox">Week {num_}{" (so far)" if w.get("current") else ""}: {w["cs_matches"]} CS2 results tracked ({w["cs_with_scoreboards"]} with scoreboards) '
                     f'and {(w.get("wow") or {}).get("kills", 0)} WoW Mythic boss kills by tracked guilds. {e(sp.get("upset_rule"))}</div>')
            self.add("roundup/" + w["id"], f"Weekly Roundup {w['id'].upper()} ({w['label']})",
                     f"Esports Scoreboard weekly roundup, {w['label']}: upsets, top fraggers per ESEA division, win streaks and WoW Mythic kills, from tracked results.",
                     std(f"Weekly Roundup :: {e(w['label'])}", "week " + str(num_), intro + self.spot_html(w, routes) + '<div class="crumbs"><a href="roundup/">All roundups</a></div>'))
            rows.append(f'<tr><td class="team">{ilink("roundup/" + w["id"], w["label"])}</td><td class="n">{w["cs_matches"]}</td><td class="n">{(w.get("wow") or {}).get("kills", 0)}</td></tr>')
        self.add("roundup", "Weekly Roundups", "Archive of Esports Scoreboard weekly roundups built from tracked ESEA League, Valorant and WoW data.",
                 std("Weekly Roundups", f"{len(rows)} weeks", table(['<th class="first">Week</th>', '<th class="n">CS2 results</th>', '<th class="n">WoW kills</th>'], rows)))

    def build_v6(self):
        """v6.0-6.4 static snapshots (ranking, top 20, methodology, awards, playoffs) and v6.2 weekly pick cards."""
        rk = load(os.path.join(self.dist, "rank.json"))
        if not rk:
            return
        routes = {p["route"] for p in self.pages}
        def tl(t):
            r = "team/cs2/" + t["id"]
            return ilink(r, t["name"]) if r in routes else e(t["name"])
        def pl(n):
            r = "player/cs2/" + n
            return ilink(r, n) if r in routes else e(n)
        asof = e(pt(rk.get("generated")))
        for reg in ("NA", "EU"):
            rows = [f'<tr><td class="first c">{t["rank_region"]}</td><td class="team">{tl(t)}</td><td>{e(t["division"])}</td><td class="n">{round(t["pts"])}</td><td class="n">{t["w"]}-{t["l"]}</td><td class="n">#{t["rank"]}</td></tr>'
                    for t in rk["teams"] if t["region"] == reg][:100]
            body = (f'<div class="infobox">ESB Team Ranking, {reg}, as of {asof}. {e(rk["formula_team"])} <a href="cs2/methodology/">Methodology</a></div>' +
                    (table(['<th class="first c">#</th>', "<th>Team</th>", "<th>Division</th>", '<th class="n">Points</th>', '<th class="n">W-L</th>', '<th class="n">Overall</th>'], rows) if rows
                     else '<div class="empty">No team has played 3 matches yet this season, so nobody is ranked yet.</div>'))
            self.add("cs2/ranking" + ("" if reg == "NA" else "/eu"), f"ESB Team Ranking {reg} :: CS2 ESEA", f"Weekly Elo-style ranking of ESEA {reg} CS2 teams across Advanced, Main and Intermediate, from real FACEIT map results.",
                     std(f"ESB Team Ranking :: {reg}", f"{len(rows)} teams", body))
        def t20(lst):
            rows = [f'<tr><td class="first c">{i + 1}</td><td class="team">{pl(p["nick"])}</td><td>{e(p["region"] + " " + p["division"])}</td><td class="n"><b>{p["rating"]:.2f}</b></td><td class="n">{p["rounds"]}</td></tr>' for i, p in enumerate(lst)]
            return table(['<th class="first c">#</th>', "<th>Player</th>", "<th>Division</th>", '<th class="n">Rating</th>', '<th class="n">Rounds</th>'], rows) if rows else '<div class="empty">No player has enough rounds yet.</div>'
        def dsl(k):
            return slug(k.replace(" ", "-"))
        tops = rk.get("top20") if isinstance(rk.get("top20"), dict) else {}
        divs = rk.get("divs") or list(tops)
        end = (rk.get("season") or {}).get("end")
        inprog = not end or datetime.now(timezone.utc).isoformat() < end
        a = rk.get("awards") or {}
        for k in divs:
            lst = tops.get(k) or []
            route = "cs2/top20" + ("" if k == "NA Advanced" else "/" + dsl(k))
            self.add(route, f"{k} Top 20 CS2 players of the season :: ESEA", f"Top 20 ESEA {k} CS2 players of the season by ESB Rating 1.0 ({k} average = 1.00).",
                     std(f"Top 20 :: {e(k)}", "season", f'<div class="infobox">As of {asof}. {e(rk["formula_player"])}</div>' + t20(lst)))
            d = (a.get("divs") or {}).get(k) or {}
            aw = [f'<tr><th>MVP</th><td>{pl(d["mvp"]["nick"]) + " (rating " + format(d["mvp"]["rating"], ".2f") + ")" if d.get("mvp") else "no eligible pick yet"}</td></tr>',
                  f'<tr><th>Best team</th><td>{tl(d["best_team"]) if d.get("best_team") else "no ranked team yet"}</td></tr>',
                  f'<tr><th>Breakout team</th><td>{tl(d["breakout"]) + " (+" + format(d["breakout"]["gain"], ".1f") + ")" if d.get("breakout") else "no ranked team yet"}</td></tr>']
            self.add("cs2/awards" + ("" if k == "NA Advanced" else "/" + dsl(k)), f"{k} CS2 season awards :: ESEA", f"ESEA {k} CS2 season awards: MVP, best team and breakout team from published formulas.",
                     std(f"Season Awards :: {e(k)}", "season in progress" if inprog else "final", f'<div class="infobox">{"Season in progress, standings as of " + asof if inprog else "Season finished"}.</div>' +
                         '<table class="tbl awards"><tbody>' + "".join(aw) + "</tbody></table>" + f'<div class="note">Not awarded: {e(" ".join(a.get("omitted") or []))}</div>' + t20(lst)))
        self.add("cs2/top20/esea", "ESEA Top 20 (just for fun) :: CS2", "Combined ESEA CS2 Top 20, just for fun: Advanced players only until opponent-strength weighting exists.",
                 std("ESEA Top 20 :: just for fun", "Advanced only", '<div class="infobox">Just for fun: ratings compare players within their own division, so until opponent-strength weighting arrives (planned midseason) this list shows Advanced players only.</div>' + t20(rk.get("top20_fun") or [])))
        self.add("cs2/methodology", "ESB Ranking and Rating methodology", "Exact formulas for the Esports Scoreboard team ranking (Elo on maps) and ESB Rating 1.0 for ESEA CS2 players, compared per division.",
                 std("Ranking and Rating Methodology", "formulas", f'<div class="infobox method"><h3>ESB Team Ranking</h3><p>{e(rk["formula_team"])}</p><h3>ESB Rating 1.0</h3><p>{e(rk["formula_player"])}</p></div>'))
        po = rk.get("playoffs") or {}
        self.add("cs2/playoffs", "ESEA CS2 playoffs :: Esports Scoreboard", "ESEA CS2 playoff brackets and event MVP once FACEIT publishes playoff matches.",
                 std("Playoffs", "ESEA", ('<div class="infobox">' + (f"{len(po.get('matches') or [])} playoff matches listed." if po.get("matches") else "Playoffs have not started; the bracket appears once FACEIT lists playoff matches.") + "</div>") +
                     "<ul>" + "".join(f'<li>{ext(d["link"], "ESEA " + d["region"] + " " + d["division"] + " on FACEIT")}</li>' for d in po.get("links") or [] if d.get("link")) + "</ul>"))
        # v6.2 weekly pick cards
        sp = load(os.path.join(self.dist, "spot.json"))
        for w in sp.get("weeks") or []:
            if not re.match(r"^\d{4}-w\d{2}$", str(w.get("id"))):
                continue
            P, T = w.get("potw") or {}, w.get("totw") or {}
            if P.get("nick"):
                P = {P["div"]: P}
            if T.get("id"):
                T = {f'{T["region"]} {T["division"]}': T}
            for k, p in P.items():
                if not p or k not in divs:
                    continue
                key = f"potw-{w['id']}-{dsl(k)}"
                self.og_jobs[key] = (p["nick"], f"{k} Player of the Week · {w['label']}"[:70], [("RATING", f'{p["rating"]:.2f}'), ("K-D", f'{p["k"]}-{p["d"]}'), ("MAPS", str(p["maps"]))], (217, 80, 0))
                self.add(f"roundup/{w['id']}/potw-{dsl(k)}", f"{k} Player of the Week {w['id'].upper()}: {p['nick']}", f"{p['nick']} ({p['team']}) is the Esports Scoreboard {k} Player of the Week, {w['label']}: rating {p['rating']:.2f} over {p['maps']} maps.",
                         std(f"{e(k)} Player of the Week", e(w["label"]), f'<div class="infobox">{pl(p["nick"])} ({e(p["team"])}): ESB rating {p["rating"]:.2f} over {p["maps"]} maps, {p["k"]}-{p["d"]} K-D. <a href="roundup/{w["id"]}/">Week roundup</a></div>'), og=key)
            for k, t in T.items():
                if not t or k not in divs:
                    continue
                key = f"totw-{w['id']}-{dsl(k)}"
                self.og_jobs[key] = (t["name"], f"{k} Team of the Week · {w['label']}"[:70], [("GAIN", f'+{t["gain"]:.1f}'), ("POINTS", str(round(t["pts"]))), ("MATCHES", str(t["played"]))], (217, 80, 0))
                self.add(f"roundup/{w['id']}/totw-{dsl(k)}", f"{k} Team of the Week {w['id'].upper()}: {t['name']}", f"{t['name']} is the Esports Scoreboard {k} Team of the Week, {w['label']}: +{t['gain']:.1f} ranking points.",
                         std(f"{e(k)} Team of the Week", e(w["label"]), f'<div class="infobox">{tl(t)}: +{t["gain"]:.1f} ranking points from {t["played"]} matches. <a href="roundup/{w["id"]}/">Week roundup</a></div>'), og=key)

    # ------------------------------------------------------------- output
    def head_tags(self, p, rel, og_url):
        path = p.get("path") or p["route"]
        url = self.site + (path + "/" if path else "")
        tags = [f'<base href="{rel}">', f'<link rel="canonical" href="{e(url)}">', f'<meta name="fragnet-route" content="{e(p["route"])}">']
        if og_url:
            tags += [f'<meta property="og:image" content="{e(og_url)}">', '<meta property="og:image:width" content="1200">', '<meta property="og:image:height" content="630">',
                     f'<meta property="og:image:alt" content="{e(p["title"])}">']
        if p.get("ld"):
            tags.append('<script type="application/ld+json">' + json.dumps(p["ld"], ensure_ascii=False).replace("<", "\\u003c") + "</script>")
        return tags, url

    def render_page(self, tpl, p, og_url):
        rel = "../" * ((p.get("path") or p["route"]).count("/") + 1)
        tags, url = self.head_tags(p, rel, og_url)
        page = tpl
        vp = '<meta name="viewport" content="width=device-width, initial-scale=1">'
        if page.count(vp) != 1:
            raise ValueError("viewport meta not found")
        page = page.replace(vp, vp + "\n" + tags[0], 1)       # <base> before any relative URL
        title = p["title"] if p["title"].endswith("Esports Scoreboard") else p["title"] + " :: Esports Scoreboard"
        page = re.sub(r"<title>[^<]*</title>", lambda _: f"<title>{e(title)}</title>", page, count=1)
        for attr, val in (('name="description"', p["desc"]), ('property="og:description"', p["desc"]), ('property="og:title"', title), ('property="og:url"', url)):
            pat = re.compile(r'(<meta ' + re.escape(attr) + r' content=")[^"]*(">)')
            page = pat.sub(lambda m, v=val: m.group(1) + e(v) + m.group(2), page, count=1)
        if og_url:
            page = page.replace('<meta name="twitter:card" content="summary">', '<meta name="twitter:card" content="summary_large_image">', 1)
        page = page.replace("</head>", "\n".join(tags[1:]) + "\n</head>", 1)
        page = page.replace('href="#pane-middle"', f'href="{e(p["route"])}/#pane-middle"', 1)   # in-page skip link despite <base>
        if not pr.well_formed(p["body"]):
            raise ValueError("snapshot not well-formed: " + p["route"])
        view = '<div id="view" aria-live="polite"></div>'
        if page.count(view) != 1:
            raise ValueError("#view not found")
        note = ('<div class="note noscript-note">Static snapshot of Esports Scoreboard data fetched ' + e(pt(self.d.get("fetched_at"))) +
                '. <a href="./">Front page</a></div>')
        body = PATH_RE.sub(lambda m: 'href="' + PATH_MAP.get(m.group(1), m.group(1)) + '/"', p["body"])
        end = body.find("</h1>")
        if end >= 0:   # audit B9: one h1 per page
            body = body[:end + 5] + re.sub(r"<(/?)h1\b", r"<\1h2", body[end + 5:])
        page = page.replace(view, f'<div id="view" aria-live="polite" {pr.MARK}>{body}{note}</div>', 1)
        page = page.replace('<div class="sb-upd" id="hdr-upd">data: loading&hellip;</div>', f'<div class="sb-upd" id="hdr-upd">updated {e(pt(self.d.get("fetched_at")))}</div>', 1)
        return page


# ----------------------------------------------------------------- share images
def _font(size, bold=True):
    from PIL import ImageFont
    for f in (("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),):
        for d in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF"):
            p = os.path.join(d, f)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def draw_og(path, title, sub, stats, accent):
    """1200x630 retro portal card: dark page, slate header bar with the FRAGNET wordmark (text, no logos),
    big title, subtitle and up to three stat tiles."""
    from PIL import Image, ImageDraw
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), (11, 13, 16))
    d = ImageDraw.Draw(im)
    for y in range(0, 118):                                   # header bar, subtle vertical gradient
        c = int(44 - y * 0.18)
        d.line([(0, y), (W, y)], fill=(c, c + 2, c + 5))
    d.rectangle([0, 118, W, 124], fill=accent)
    f_logo = _font(64)
    f_logo = _font(56)
    d.text((48, 26), "ESPORTS ", font=f_logo, fill=(255, 255, 255))
    d.text((48 + d.textlength("ESPORTS ", font=f_logo), 26), "SCOREBOARD", font=f_logo, fill=(244, 196, 48))
    d.text((52, 92), "ESPORTS LEAGUE TRACKER", font=_font(18), fill=(201, 210, 219))
    d.rectangle([40, 160, W - 40, 590], fill=(26, 29, 33), outline=(58, 64, 72))
    d.rectangle([40, 160, 48, 590], fill=accent)
    size = 66
    while size > 30 and d.textlength(title, font=_font(size)) > W - 140:
        size -= 2
    t = title
    while d.textlength(t, font=_font(size)) > W - 140 and len(t) > 4:
        t = t[:-2]
    if t != title:
        t = t.rstrip() + "…"
    d.text((76, 190), t, font=_font(size), fill=(255, 255, 255))
    d.text((78, 200 + size + 8), sub[:70], font=_font(28, False), fill=(156, 199, 238))
    x0, tw = 76, (W - 152 - 2 * 24) // 3
    for i, (lab, val) in enumerate(stats[:3]):
        x = x0 + i * (tw + 24)
        d.rectangle([x, 400, x + tw, 560], fill=(34, 40, 49), outline=(58, 69, 82))
        d.text((x + 20, 418), lab, font=_font(22), fill=(140, 150, 163))
        vs = 52
        while vs > 22 and d.textlength(str(val), font=_font(vs)) > tw - 40:
            vs -= 2
        d.text((x + 20, 462), str(val), font=_font(vs), fill=(255, 255, 255))
    d.text((W - 48, 606), SITE_LABEL[0], font=_font(18, False), fill=(120, 130, 142), anchor="rs")
    im = im.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    im.save(path, optimize=True)


def build(dist, site, og_cache, do_og=True):
    t0 = time.time()
    SITE_LABEL[0] = re.sub(r"^https?://", "", site).rstrip("/")
    s = Site(dist, site)
    s.build_cs()
    s.build_val()
    s.build_rest()
    s.build_roundups()
    s.build_v6()
    path_map(s)
    tpl_path = os.path.join(dist, "index.html")
    with open(tpl_path, encoding="utf-8") as fh:
        tpl = fh.read()
    if pr.MARK in tpl:
        raise SystemExit("[pages] dist/index.html is already pre-rendered; run pages.py before prerender.py")
    # audit B13: crawlable path hrefs in the site chrome; the SPA swaps them back to hash routes (data-h) on boot
    have = {p["route"] for p in s.pages}
    def _nav(m):
        r = m.group(1)
        if r == "home":
            return f'href="./" data-h="#home"'
        return f'href="{r}/" data-h="#{r}"' if r in have else m.group(0)
    tpl = re.sub(r'href="#(home|cs2|valorant|wow|news|forums|about|search|recruiting|roundup)"', _nav, tpl)
    # share images (teams + matches + site), cached by content hash
    og_url, n_drawn, n_reused = {}, 0, 0
    if do_og:
        try:
            import PIL  # noqa: F401
            have_pil = True
        except ImportError:
            have_pil = False
            print("[pages] Pillow not installed - pages are written without share images")
        if have_pil:
            cache_dir = os.path.join(og_cache, "og")
            os.makedirs(cache_dir, exist_ok=True)
            os.makedirs(os.path.join(dist, "og"), exist_ok=True)
            man = load(os.path.join(og_cache, "manifest.json"), {})
            new_man = {}
            jobs = dict(s.og_jobs)
            cs = s.d.get("cs") or {}
            jobs["site"] = ("ESEA · Valorant · WoW", "Standings, results and the Mythic raid race", [("CS2", (cs.get("season") or {}).get("name") or "ESEA"), ("VALORANT", "Tier 2"), ("WOW", ((s.d.get("wow") or {}).get("raid") or {}).get("name", "Mythic")[:14])], (217, 80, 0))
            for k, (title, sub, stats, accent) in jobs.items():
                h = hashlib.sha1(json.dumps([OG_VERSION, SITE_LABEL[0], title, sub, stats, accent], ensure_ascii=False).encode()).hexdigest()[:16]
                fn = k + ".png"
                cp = os.path.join(cache_dir, fn)
                if man.get(k) != h or not os.path.exists(cp):
                    draw_og(cp, str(title), str(sub), stats, accent)
                    n_drawn += 1
                else:
                    n_reused += 1
                new_man[k] = h
                shutil.copyfile(cp, os.path.join(dist, "og", fn))
                og_url[k] = site + "og/" + fn
            for f in os.listdir(cache_dir):                       # prune images of entities no longer listed
                if f[:-4] not in new_man:
                    os.remove(os.path.join(cache_dir, f))
            with open(os.path.join(og_cache, "manifest.json"), "w", encoding="utf-8") as fh:
                json.dump(new_man, fh)
    # pages
    n = 0
    for p in s.pages:
        out = os.path.join(dist, *(p.get("path") or p["route"]).split("/"), "index.html")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(s.render_page(tpl, p, og_url.get(p["og"]) or og_url.get("site")))
        n += 1
    # front page: canonical, share image, JSON-LD (prerender.py adds the snapshot afterwards)
    home = re.sub(r'(<meta property="og:url" content=")[^"]*(">)', lambda m: m.group(1) + e(site) + m.group(2), tpl, count=1)
    home = home.replace("</head>", f'<link rel="canonical" href="{e(site)}">\n'
                       + (f'<meta property="og:image" content="{e(og_url["site"])}">\n<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">\n' if og_url.get("site") else "")
                       + '<script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", "@type": "WebSite", "name": "Esports Scoreboard", "url": site}).replace("<", "\\u003c") + "</script>\n</head>", 1)
    if og_url.get("site"):
        home = home.replace('<meta name="twitter:card" content="summary">', '<meta name="twitter:card" content="summary_large_image">', 1)
    with open(tpl_path + ".tmp", "w", encoding="utf-8") as fh:
        fh.write(home)
    os.replace(tpl_path + ".tmp", tpl_path)
    # audit B12: small home.json for the front page's first paint (the SPA loads data.json right after)
    try:
        d = s.d
        now = datetime.now(timezone.utc)
        def near(m, hrs):
            try:
                return abs((datetime.fromisoformat(str(m.get("t")).replace("Z", "+00:00")) - now).total_seconds()) < hrs * 3600
            except Exception:
                return False
        cs = d.get("cs") or {}
        hd = {k: d.get(k) for k in ("fetched_at", "generator", "display_tz", "status")}
        hd["cs"] = {"season": cs.get("season"), "live": cs.get("live") or [],
                    "divisions": [dict({k: v for k, v in dv.items() if k != "teams"}, teams=(dv.get("teams") or [])[:3]) for dv in cs.get("divisions") or []],
                    "upcoming": [m for m in cs.get("upcoming") or [] if near(m, 30)], "matches": [m for m in cs.get("matches") or [] if near(m, 30)]}
        va = d.get("valorant") or {}
        hd["valorant"] = {k: v for k, v in va.items() if k not in ("events", "results", "top_players")}
        hd["valorant"].update(events=[{k: v for k, v in ev.items() if not isinstance(v, (list, dict))} for ev in va.get("events") or []], top_players=(va.get("top_players") or [])[:1], results=[])
        wo = d.get("wow") or {}
        hd["wow"] = dict(wo, rankings={k: (v or [])[:3] for k, v in (wo.get("rankings") or {}).items()})
        hd["news"] = dict(d.get("news") or {}, items=((d.get("news") or {}).get("items") or [])[:15])
        hd["partial"] = True
        with open(os.path.join(dist, "home.json"), "w", encoding="utf-8") as fh:
            json.dump(hd, fh, ensure_ascii=False, separators=(",", ":"))
    except Exception as ex:
        print("[pages] home.json skipped:", ex)
    # audit B5: 404.html with site chrome; known or old paths redirect to the matching hash route
    from urllib.parse import urlparse
    base = urlparse(site).path or "/"
    nf = tpl.replace("<head>", '<head>\n<script>(function(){var B=' + json.dumps(base) + ',p=location.pathname;if(p.indexOf(B)===0){p=p.slice(B.length).replace(/\\/+$/,"").replace(/\\/index\\.html$/,"");}if(p&&!/\\.(png|js|json|css|svg|xml|txt|webmanifest)$/i.test(p)){location.replace(B+"#"+(/^(home|cs2|valorant|wow|news|forums|roundup|recruiting|about|search|status|team|player|match|guild)(\\/|$)/.test(p)?p:"notfound/"+p));}})();</script>', 1)
    nf = nf.replace('<meta name="viewport" content="width=device-width, initial-scale=1">', '<meta name="viewport" content="width=device-width, initial-scale=1">\n<base href="' + e(base) + '">\n<meta name="robots" content="noindex">', 1)
    nf = re.sub(r"<title>[^<]*</title>", "<title>Page not found :: Esports Scoreboard</title>", nf, count=1)
    nf = nf.replace('<div id="view" aria-live="polite"></div>', '<div id="view" aria-live="polite"><div class="std"><div class="std-header"><h1>Page not found</h1></div><div class="empty miss">That page doesn&rsquo;t exist. <a href="./">Front page</a> &middot; <a href="cs2/">CS2</a> &middot; <a href="valorant/">Valorant</a> &middot; <a href="wow/">WoW</a></div></div></div>', 1)
    with open(os.path.join(dist, "404.html"), "w", encoding="utf-8") as fh:
        fh.write(nf)
    # sitemap + robots
    day = (s.d.get("fetched_at") or datetime.now(timezone.utc).isoformat())[:10]
    urls = [site] + [site + (p.get("path") or p["route"]) + "/" for p in s.pages]
    # audit B10: old URLs stay valid as tiny redirect pages (not in the sitemap)
    for old, new in PATH_MAP.items():
        out = os.path.join(dist, *old.split("/"), "index.html")
        if os.path.exists(out):
            continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        rel = "../" * (old.count("/") + 1)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Moved :: Esports Scoreboard</title><meta name="robots" content="noindex"><meta name="esb-redirect">'
                     f'<link rel="canonical" href="{e(site + new + "/")}"><meta http-equiv="refresh" content="0; url={e(rel + new + "/")}">'
                     f'<script>location.replace({json.dumps(rel + new + "/")} + location.hash)</script></head><body><a href="{e(rel + new + "/")}">This page moved</a></body></html>')
    with open(os.path.join(dist, "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                 + "".join(f"<url><loc>{e(u)}</loc><lastmod>{day}</lastmod></url>\n" for u in urls) + "</urlset>\n")
    with open(os.path.join(dist, "robots.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"User-agent: *\nAllow: /\nSitemap: {site}sitemap.xml\n")
    kinds = {}
    for p in s.pages:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    print(f"[pages] {n} path pages ({', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))}), sitemap {len(urls)} URLs; "
          f"share images: {n_drawn} drawn, {n_reused} reused; {time.time() - t0:.1f}s")
    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:   # lets the workflow save the image cache only when something was drawn
        with open(gh, "a", encoding="utf-8") as fh:
            fh.write(f"og_drawn={n_drawn}\npages={n}\n")
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description="Esports Scoreboard path pages, sitemap and share images")
    ap.add_argument("dist")
    ap.add_argument("--site", default=SITE)
    ap.add_argument("--og-cache", default=".ogcache")
    ap.add_argument("--no-og", action="store_true")
    a = ap.parse_args(argv)
    site = a.site if a.site.endswith("/") else a.site + "/"
    build(a.dist, site, a.og_cache, not a.no_og)
    return 0


if __name__ == "__main__":
    sys.exit(main())
