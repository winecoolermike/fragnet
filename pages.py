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
            self.add("player/cs2/" + nick, f"{nick} :: CS2 ESEA player", desc, std(e(nick), "CS2 &middot; ESEA League player", info),
                     og=("cs-team-" + tid) if tid and ("cs-team-" + tid) in self.og_jobs else None, kind="player",
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

    # ------------------------------------------------------------- output
    def head_tags(self, p, rel, og_url):
        url = self.site + (p["route"] + "/" if p["route"] else "")
        tags = [f'<base href="{rel}">', f'<link rel="canonical" href="{e(url)}">', f'<meta name="fragnet-route" content="{e(p["route"])}">']
        if og_url:
            tags += [f'<meta property="og:image" content="{e(og_url)}">', '<meta property="og:image:width" content="1200">', '<meta property="og:image:height" content="630">',
                     f'<meta property="og:image:alt" content="{e(p["title"])}">']
        if p.get("ld"):
            tags.append('<script type="application/ld+json">' + json.dumps(p["ld"], ensure_ascii=False).replace("<", "\\u003c") + "</script>")
        return tags, url

    def render_page(self, tpl, p, og_url):
        rel = "../" * (p["route"].count("/") + 1)
        tags, url = self.head_tags(p, rel, og_url)
        page = tpl
        vp = '<meta name="viewport" content="width=device-width, initial-scale=1">'
        if page.count(vp) != 1:
            raise ValueError("viewport meta not found")
        page = page.replace(vp, vp + "\n" + tags[0], 1)       # <base> before any relative URL
        title = p["title"] + " :: Esports Scoreboard"
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
        page = page.replace(view, f'<div id="view" aria-live="polite" {pr.MARK}>{p["body"]}{note}</div>', 1)
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
    tpl_path = os.path.join(dist, "index.html")
    with open(tpl_path, encoding="utf-8") as fh:
        tpl = fh.read()
    if pr.MARK in tpl:
        raise SystemExit("[pages] dist/index.html is already pre-rendered; run pages.py before prerender.py")
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
        out = os.path.join(dist, *p["route"].split("/"), "index.html")
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
    # sitemap + robots
    day = (s.d.get("fetched_at") or datetime.now(timezone.utc).isoformat())[:10]
    urls = [site] + [site + p["route"] + "/" for p in s.pages]
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
