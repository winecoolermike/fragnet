#!/usr/bin/env python3
"""Pre-render a static front page into dist/index.html (FragNet no-JS fallback; v4.0 calm home).

    python prerender.py dist/index.html dist/data.json

Writes a plain-HTML snapshot (three game cards with live teasers and outbound section
buttons, the latest 5 ESEA results, 5 headlines; North America first) into #view / #side-news / #hdr-upd and a live summary into the
description + og/twitter description, so no-JS visitors, search engines and link
previews see real data. app.js replaces it on boot (it renders #view / #side-news
wholesale) and removes the data-prerender marker.

Safety: every data value goes through html.escape(quote=True); links only if http(s)
(safe_url); no data inside <script>. Snapshot links are real outbound URLs (FACEIT,
vlr.gg, Raider.IO, articles) - never #routes, which need JavaScript.
The file is replaced atomically and only after the result parses and validates.
"""
import html
import json
import os
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
MARK = 'data-prerender="1"'
N_TEAMS = 5
ESEA_PAGE = "https://www.faceit.com/en/cs2/league/ESEA%20League/a14b8616-45b9-4581-8637-4dfd0b5f6af8"


def e(s):
    return html.escape("" if s is None else str(s), quote=True)


def safe_url(u):
    u = str(u or "").strip()
    return u if re.match(r"^https?://[^\s\"'<>]+$", u, re.I) else ""


def ext(u, text):
    su = safe_url(u)
    return f'<a href="{e(su)}" target="_blank" rel="noopener">{e(text)}</a>' if su else e(text)


def pt(iso, f="%b %-d, %H:%M %Z"):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(PT).strftime(f)
    except (TypeError, ValueError):
        return ""


def std(title, meta, inner, sid=""):
    idattr = f' id="{sid}"' if sid else ""
    return (f'<div class="std"{idattr}><div class="std-header"><h1>{title}</h1>'
            + (f'<span class="meta">{meta}</span>' if meta else "") + f"</div>{inner}</div>")


def team_url(t):
    tid = str((t or {}).get("id") or "")
    return t.get("url") or (f"https://www.faceit.com/en/teams/{tid}" if re.match(r"^[0-9a-f-]{36}$", tid, re.I) else "")


def room_url(m):
    mid = str(m.get("id") or "")
    return m.get("url") or (f"https://www.faceit.com/en/cs2/room/{mid}" if re.match(r"^[0-9a-z-]+$", mid, re.I) else "")


def rio_page(raid, region):
    slug = (raid or {}).get("slug")
    return f"https://raider.io/{slug}/rankings/{region}/mythic" if slug and re.match(r"^[a-z0-9-]+$", slug) else "https://raider.io/"


def card(game, name, sub, teaser, btns):
    b = "".join(f'<a class="gbtn" href="{e(safe_url(u))}" target="_blank" rel="noopener">{e(t)}</a>' for t, u in btns if safe_url(u))
    return (f'<section class="gcard g-{game}" aria-label="{e(name)}"><div class="gc-head"><span class="gc-name">{e(name)}</span><span class="gc-sub">{e(sub)}</span></div>'
            f'<div class="gc-teaser">{teaser or "<span class=dim>No data yet.</span>"}</div><div class="gc-btns">{b}</div></section>')


def na_first(divs):
    return sorted(divs or [], key=lambda dv: 0 if dv.get("region") == "NA" else 1)


def render(d):
    """v4.0 calm home: three game cards, the latest 5 ESEA results, 5 headlines (North America first)."""
    cs, val, wow = d.get("cs") or {}, d.get("valorant") or {}, d.get("wow") or {}
    upd = pt(d.get("fetched_at"))
    parts = [std("FragNet Front Page", "updated " + e(upd),
                 '<div class="infobox hub-intro">Amateur &amp; semi-pro esports: ESEA League CS2, Valorant Challengers and the WoW Mythic raid race. '
                 "This is a static snapshot; with JavaScript enabled you get every division, team and player page, match scoreboards and search. All times Pacific.</div>")]
    divs = [dv for dv in na_first(cs.get("divisions")) if dv.get("teams")]
    d0 = divs[0] if divs else None
    cs_t = " &middot; ".join(x for x in [
        e(cs.get("season", {}).get("name")) if cs.get("season") else "",
        (f'{e(d0.get("region"))} {e(d0.get("division"))} leader <b>{e(d0["teams"][0].get("name"))}</b>' if d0 else "")] if x)
    evs = val.get("events") or []
    tp = (val.get("top_players") or [None])[0]
    na_ev = next((ev for ev in evs if re.search(r"north america", ev.get("title") or "", re.I)), None)
    val_t = " &middot; ".join(x for x in [
        f"{len(evs)} events tracked" if evs else "",
        (f'top player <b>{e(tp.get("name"))}</b> ({float(tp.get("rating") or 0):.2f})' if tp else "")] if x)
    rk, raid = wow.get("rankings") or {}, wow.get("raid") or {}
    us, eu = (rk.get("us") or [None])[0], (rk.get("eu") or [None])[0]
    wow_t = " &middot; ".join(x for x in [
        e(raid.get("name")) if raid.get("name") else "",
        (f'US #1 <b>{e(us.get("guild"))}</b> {e(us.get("progress"))}' if us else ""),
        (f'EU #1 <b>{e(eu.get("guild"))}</b> {e(eu.get("progress"))}' if eu else "")] if x)
    parts.append('<div class="gcards">'
                 + card("cs2", "Counter-Strike 2", "ESEA League", cs_t,
                        [((d0.get("region") + " " + d0.get("division") + " standings") if d0 else "Standings", (d0 or {}).get("link") or ESEA_PAGE), ("ESEA League on FACEIT", ESEA_PAGE)])
                 + card("valorant", "Valorant", "Challengers / Game Changers", val_t,
                        [("NA event on vlr.gg" if na_ev else "Events on vlr.gg", (na_ev or {}).get("url") or "https://www.vlr.gg/events"), ("Results on vlr.gg", "https://www.vlr.gg/matches/results")])
                 + card("wow", "World of Warcraft", "Mythic raid race", wow_t,
                        [("US Rankings", rio_page(raid, "us")), ("EU Rankings", rio_page(raid, "eu"))])
                 + "</div>")
    # latest ESEA results (short)
    fin = sorted([m for m in cs.get("matches") or [] if m.get("t")], key=lambda m: m["t"], reverse=True)[:5]
    rr = []
    for m in fin:
        w = m.get("winner")
        rr.append(f'<tr><td class="dim hide-sm">{e(pt(m["t"], "%b %-d"))}</td>'
                  f'<td class="n {"win" if w == 1 else "lose"}">{ext(team_url(m.get("t1") or {}), (m.get("t1") or {}).get("name"))}</td>'
                  f'<td class="score">{ext(room_url(m), str(m.get("s1")) + ":" + str(m.get("s2")))}</td>'
                  f'<td class="{"win" if w == 2 else "lose"}">{ext(team_url(m.get("t2") or {}), (m.get("t2") or {}).get("name"))}</td>'
                  f'<td class="hide-sm">{e((m.get("region") or "") + " " + (m.get("division") or ""))}</td></tr>')
    parts.append(std("Latest ESEA Results", "",
                     '<div class="rankbox"><table class="tbl res"><thead><tr><th class="first hide-sm">Date</th><th class="n">Team 1</th><th class="c">Score</th><th>Team 2</th><th class="hide-sm">Division</th></tr></thead><tbody>'
                     + "".join(rr) + "</tbody></table></div>" if rr else '<div class="empty">Match results coming soon.</div>'))
    # news
    news = sorted((d.get("news") or {}).get("items") or [], key=lambda n: n.get("date") or "", reverse=True)
    parts.append(std("Latest Esports News", "",
                     '<div class="newsbox">' + "".join(f'<div class="item">{ext(n.get("url"), n.get("title"))}<span class="src">({e(n.get("source"))})</span></div>' for n in news[:5]) + "</div>"
                     if news else '<div class="empty">No headlines.</div>', "home-news"))
    side = "".join(f'<li>{ext(n.get("url"), n.get("title"))}<span class="cnt">{e(pt(n.get("date"), "%b %-d"))}</span></li>' for n in news[:8])
    leaders = [f'{dv.get("region")} {dv.get("division")}: {dv["teams"][0].get("name")}' for dv in divs if dv.get("division") == "Advanced"][:3]
    desc = ("FragNet - ESEA League CS2 standings and results" + (f" (leaders {', '.join(leaders)})" if leaders else "")
            + ", Valorant tier-2 results, WoW Mythic raid race and esports news." + (f" Updated {upd}." if upd else ""))
    return "".join(parts), side, upd, desc


class _Check(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self):
        super().__init__()
        self.stack, self.bad = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.bad.append(tag)
        else:
            self.stack.pop()


def well_formed(fragment):
    p = _Check()
    p.feed(fragment)
    p.close()
    return not p.bad and not p.stack


def inject(page, data):
    view, side, upd, desc = render(data)
    if not (well_formed(view) and well_formed(side)):
        raise ValueError("rendered snapshot is not well-formed HTML")
    reps = [('<div id="view" aria-live="polite"></div>', f'<div id="view" aria-live="polite" {MARK}>{view}</div>'),
            ('<ul class="side-menu counts" id="side-news"></ul>', f'<ul class="side-menu counts" id="side-news">{side}</ul>'),
            ('<div class="sb-upd" id="hdr-upd">data: loading&hellip;</div>', f'<div class="sb-upd" id="hdr-upd">updated {e(upd)}</div>')]
    for a, b in reps:
        if page.count(a) != 1:
            raise ValueError(f"insertion point not found exactly once: {a[:40]}")
        page = page.replace(a, b)
    for attr in ('name="description"', 'property="og:description"', 'name="twitter:description"'):
        pat = re.compile(r'(<meta ' + re.escape(attr) + r' content=")[^"]*(">)')
        if pat.search(page):
            page = pat.sub(lambda m: m.group(1) + e(desc) + m.group(2), page, count=1)
        else:
            page = page.replace('<meta name="twitter:card"', f'<meta {attr} content="{e(desc)}">\n<meta name="twitter:card"', 1)
    return page


def check_page(page):
    """Problems with a pre-rendered page ([] = fine or not pre-rendered)."""
    if MARK not in page:
        return []
    probs = []
    if page.count(MARK) != 1:
        probs.append("data-prerender marker not exactly once")
    m = re.search(r'<div id="view" aria-live="polite" ' + re.escape(MARK) + r'>(.*?)</div>\s*</main>', page, re.S)
    if not m:
        probs.append("prerendered #view not found")
    else:
        if not well_formed(m.group(1)):
            probs.append("prerendered #view is not well-formed")
        if m.group(1).count('class="std-header"') < 3 or m.group(1).count('class="gcard ') != 3:
            probs.append("prerendered #view is missing sections (3 boxes + 3 game cards expected)")
        if re.search(r'href="#', m.group(1)):
            probs.append("prerendered #view contains #route links (need JavaScript)")
    return probs


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    index_path, data_path = argv
    with open(data_path, encoding="utf-8") as fh:
        data = json.load(fh)
    with open(index_path, encoding="utf-8") as fh:
        page = fh.read()
    if MARK in page:
        print("[prerender] already pre-rendered; nothing to do")
        return 0
    page = inject(page, data)
    probs = check_page(page)
    if probs:
        print("[prerender] FAILED: " + "; ".join(probs))
        return 1
    tmp = index_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(page)
    os.replace(tmp, index_path)
    print(f"[prerender] {index_path}: {len(page.encode('utf-8')):,} bytes (snapshot of data fetched {data.get('fetched_at')})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
