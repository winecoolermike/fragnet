#!/usr/bin/env python3
"""Pre-render a static front page into dist/index.html (FragNet v3.7 no-JS fallback).

    python prerender.py dist/index.html dist/data.json

Writes a plain-HTML snapshot (CS2 top 5 per division, latest ESEA + Valorant results,
WoW top 5, headlines) into #view / #side-news / #hdr-upd and a live summary into the
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


def std(title, meta, inner):
    return (f'<div class="std"><div class="std-header"><h1>{title}</h1>'
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


def render(d):
    cs, val, wow = d.get("cs") or {}, d.get("valorant") or {}, d.get("wow") or {}
    upd = pt(d.get("fetched_at"))
    parts = [std("FragNet Front Page", "updated " + e(upd),
                 '<div class="infobox">Welcome to <b>FragNet</b>, an amateur &amp; semi-pro league tracker. '
                 "This is a static snapshot of the front page; with JavaScript enabled you get every division, "
                 "team and player pages, match scoreboards and search. All times Pacific.</div>")]
    # CS2: top N per division
    rows = []
    for dv in cs.get("divisions") or []:
        teams = (dv.get("teams") or [])[:N_TEAMS]
        if not teams:
            continue
        rows.append(f'<tr class="row-header"><td colspan="5">{ext(dv.get("link"), (dv.get("region") or "") + " " + (dv.get("division") or ""))}</td></tr>')
        for t in teams:
            rows.append(f'<tr><td class="rk"><span>{e(t.get("rank"))}</span></td><td class="team">{ext(team_url(t), t.get("name"))}</td>'
                        f'<td class="n w">{e(t.get("w"))}</td><td class="n l">{e(t.get("l"))}</td><td class="n"><b>{e(t.get("pts"))}</b></td></tr>')
    parts.append(std(f"ESEA League Standings :: Top {N_TEAMS}", ext(ESEA_PAGE, "FACEIT ESEA League &raquo;").replace("&amp;raquo;", "&raquo;"),
                     '<div class="rankbox"><table class="tbl pre-st"><thead><tr><th class="first c">#</th><th>Team</th><th class="n">W</th><th class="n">L</th><th class="n">Pts</th></tr></thead><tbody>'
                     + "".join(rows) + "</tbody></table></div>" if rows else '<div class="empty">Standings coming soon.</div>'))
    # latest ESEA results
    fin = sorted([m for m in cs.get("matches") or [] if m.get("t")], key=lambda m: m["t"], reverse=True)[:8]
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
    # Valorant
    vr = (val.get("results") or [])[:6]
    vrows = "".join(
        f'<tr><td class="n {"win" if m.get("winner") == 0 else "lose"}">{e(m.get("team1"))}</td>'
        f'<td class="score">{ext(m.get("url"), str(m.get("score1")) + ":" + str(m.get("score2")))}</td>'
        f'<td class="{"win" if m.get("winner") == 1 else "lose"}">{e(m.get("team2"))}</td><td class="dim hide-sm">{e(m.get("event"))}</td></tr>' for m in vr)
    parts.append(std("Latest Valorant Results", "",
                     '<div class="rankbox"><table class="tbl res"><thead><tr><th class="first n">Team 1</th><th class="c">Score</th><th>Team 2</th><th class="hide-sm">Event</th></tr></thead><tbody>'
                     + vrows + "</tbody></table></div>" if vr else '<div class="empty">Not available yet.</div>'))
    # WoW
    rk, raid = wow.get("rankings") or {}, wow.get("raid") or {}
    us, eu = rk.get("us") or [], rk.get("eu") or []
    if us or eu:
        wrows = "".join(
            f'<tr><td class="rk"><span>{i + 1}</span></td><td class="team">{ext(us[i].get("url"), us[i].get("guild")) if i < len(us) else ""}</td>'
            f'<td class="hide-sm">{e(us[i].get("progress")) if i < len(us) else ""}</td>'
            f'<td class="team">{ext(eu[i].get("url"), eu[i].get("guild")) if i < len(eu) else ""}</td>'
            f'<td class="hide-sm">{e(eu[i].get("progress")) if i < len(eu) else ""}</td></tr>' for i in range(5))
        wow_html = ('<div class="rankbox"><table class="tbl"><thead><tr><th class="first c">#</th><th>US Guild</th><th class="hide-sm">Prog</th><th>EU Guild</th><th class="hide-sm">Prog</th></tr></thead><tbody>'
                    + wrows + "</tbody></table></div>")
    else:
        wow_html = '<div class="empty">Not available yet.</div>'
    parts.append(std("Mythic Raid Race :: Top 5", ext(rio_page(raid, "world"), (raid.get("name") or "Raider.IO") + " rankings"), wow_html))
    # news
    news = sorted((d.get("news") or {}).get("items") or [], key=lambda n: n.get("date") or "", reverse=True)[:10]
    parts.append(std("Latest Esports News", "",
                     '<div class="newsbox">' + "".join(f'<div class="item">{ext(n.get("url"), n.get("title"))}<span class="src">({e(n.get("source"))})</span></div>' for n in news) + "</div>"
                     if news else '<div class="empty">No headlines.</div>'))
    side = "".join(f'<li>{ext(n.get("url"), n.get("title"))}<span class="cnt">{e(pt(n.get("date"), "%b %-d"))}</span></li>' for n in news[:12])
    leaders = [f'{dv.get("region")} {dv.get("division")}: {dv["teams"][0].get("name")}' for dv in cs.get("divisions") or [] if dv.get("teams") and dv.get("division") == "Advanced"][:3]
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
        if m.group(1).count('class="std-header"') < 5:
            probs.append("prerendered #view has fewer than 5 sections")
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
