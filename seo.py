#!/usr/bin/env python3
"""Search-engine and AI-agent extras for Esports Scoreboard (Nov 13, 2026 SEO pass, mirrors PatchMeter).

Called by pages.py after the path pages are written (never on its own):
  - front-page JSON-LD: Organization + WebSite with a SearchAction (/?q=...)
  - robots.txt that welcomes search engines and AI crawlers by name, plus the sitemap
  - sitemap.xml with a per-page lastmod (match date, team's latest match, else the data date)
  - /llms.txt (short) and /llms-full.txt (text digest of standings, results and the Elo win-probability preview)
  - small public JSON endpoints under /api/ (index, CS2 standings, results, upcoming)
  - /og.png (copy of the site share image) and the IndexNow key file
  - optional list of changed URLs for the IndexNow ping in deploy.yml (INDEXNOW_LIST, written outside dist/)
Only public data already on the site; NA is always listed before EU.
"""
import json
import os
import shutil
from datetime import datetime, timedelta, timezone

INDEXNOW_KEY = "0ba1a82d10901a85fc101fa90282bdd9"   # public by design (IndexNow proves site ownership with this file)
NAME = "Esports Scoreboard"
AI_BOTS = ["Googlebot", "Bingbot", "DuckDuckBot", "Applebot", "Applebot-Extended", "YandexBot", "Google-Extended", "GPTBot",
           "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-User", "Claude-SearchBot", "anthropic-ai", "PerplexityBot",
           "Perplexity-User", "CCBot", "Meta-ExternalAgent", "Amazonbot", "cohere-ai", "MistralAI-User"]


def na_first(items, key=lambda x: x.get("region")):
    return sorted(items, key=lambda x: 0 if str(key(x) or "").upper() in ("NA", "US") else 1)


def home_ld(site):
    org = {"@context": "https://schema.org", "@type": "Organization", "@id": site + "#org", "name": NAME, "url": site,
           "logo": site + "icon-512.png", "description": "Independent fan-made tracker for amateur and semi-pro esports: ESEA League CS2, Valorant Challengers and the WoW raid race."}
    web = {"@context": "https://schema.org", "@type": "WebSite", "@id": site + "#website", "name": NAME, "url": site, "inLanguage": "en-US",
           "publisher": {"@id": site + "#org"},
           "potentialAction": {"@type": "SearchAction", "target": {"@type": "EntryPoint", "urlTemplate": site + "?q={search_term_string}"},
                               "query-input": "required name=search_term_string"}}
    return [org, web]


def ld_tags(objs):
    return "".join('<script type="application/ld+json">' + json.dumps(o, ensure_ascii=False).replace("<", "\\u003c") + "</script>\n" for o in objs)


def robots(site):
    return (f"# {NAME} welcomes search engines, AI crawlers and agents. Summary for LLMs: {site}llms.txt\n\n"
            + "".join(f"User-agent: {b}\n" for b in AI_BOTS) + "Allow: /\n\nUser-agent: *\nAllow: /\n\n"
            + f"Sitemap: {site}sitemap.xml\n")


def lastmod_of(p, day):
    lm = str(p.get("lastmod") or "")[:10]
    return lm if len(lm) == 10 and lm <= day else day


def sitemap(site, pages, day):
    from xml.sax.saxutils import escape
    rows = [(site, day)] + [(site + (p.get("path") or p["route"]) + "/", lastmod_of(p, day)) for p in pages]
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(f"<url><loc>{escape(u)}</loc><lastmod>{d}</lastmod></url>\n" for u, d in rows) + "</urlset>\n"), rows


def _pt(iso):
    try:
        from zoneinfo import ZoneInfo
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(ZoneInfo("America/Los_Angeles")).strftime("%b %-d, %Y %-I:%M %p %Z")
    except Exception:
        return str(iso or "")


def api_and_llms(s, dist, site, pred=None, path_map=None):
    """Writes /api/*.json and returns (llms_txt, llms_full_txt). pred: {match_id: {...}} from rank.json (may be empty)."""
    d = s.d
    cs = d.get("cs") or {}
    season = (cs.get("season") or {}).get("name") or "ESEA League"
    fetched = d.get("fetched_at")
    pred = pred or {}
    tpath = {old: site + new + "/" for old, new in (path_map or {}).items() if old.startswith("team/cs2/")}   # uuid route -> readable slug-id8 page

    def team_url(tid):
        return tpath.get("team/cs2/" + str(tid)) or ""
    divs = []
    for dv in na_first(s.divs):
        divs.append({"region": dv.get("region"), "division": dv.get("division"), "stage": dv.get("stage"), "faceit": dv.get("link"),
                     "page": site + "cs2/" + s.div_id(dv) + "/",
                     "teams": [{"rank": t.get("rank"), "name": t.get("name"), "id": t.get("id"), "country": t.get("country"), "w": t.get("w"),
                                "l": t.get("l"), "pts": t.get("pts"), "page": team_url(t.get("id")) or None} for t in dv.get("teams") or []]})
    def side(x):
        x = x or {}
        return {"id": x.get("id"), "name": x.get("name"), "page": team_url(x.get("id")) or None}
    results = [{"id": m["id"], "finished": m.get("t"), "region": m.get("region"), "division": m.get("division"), "round": m.get("round"),
                "bo": m.get("bo"), "team1": side(m.get("t1")), "team2": side(m.get("t2")), "score": [m.get("s1"), m.get("s2")],
                "winner": m.get("winner"), "maps": [x.get("map") for x in m.get("maps") or []], "page": site + "match/cs2/" + m["id"] + "/"}
               for m in na_first(s.fin)[:150]]
    upcoming = []
    for m in na_first(s.up)[:200]:
        row = {"id": m.get("id"), "scheduled": m.get("t"), "region": m.get("region"), "division": m.get("division"), "round": m.get("round"),
               "bo": m.get("bo"), "team1": side(m.get("t1")), "team2": side(m.get("t2"))}
        pr_ = pred.get(m.get("id"))
        if pr_:
            row["win_probability"] = {"team1": pr_.get("p1"), "team2": round(1 - pr_.get("p1"), 3), "data_confidence": pr_.get("conf"),
                                      "note": "Experimental model estimate - not a guarantee or betting advice."}
        upcoming.append(row)
    common = {"generated": fetched, "site": site, "docs": site + "llms.txt",
              "license_note": "Unofficial fan project. Match data from FACEIT (ESEA League); every entry links to its source page."}
    endpoints = {"standings": site + "api/cs2/standings.json", "results": site + "api/cs2/results.json", "upcoming": site + "api/cs2/upcoming.json"}
    out = {
        "index.json": dict(common, endpoints=endpoints, note="Small static JSON files, rebuilt about every 30 minutes. NA listed before EU."),
        "cs2/standings.json": dict(common, season=season, divisions=divs),
        "cs2/results.json": dict(common, season=season, results=results),
        "cs2/upcoming.json": dict(common, season=season, upcoming=upcoming),
    }
    for rel, obj in out.items():
        fp = os.path.join(dist, "api", *rel.split("/"))
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))

    head = (f"# {NAME}\n\n> {NAME} ({site}) is an independent, fan-made tracker for amateur and semi-pro esports: ESEA League "
            f"Counter-Strike 2 standings, results, rosters and player stats ({season}, North America first, then Europe), Valorant "
            f"Challengers / Game Changers results, a Valorant Premier explainer, and the World of Warcraft Retail Mythic raid race, with a "
            f"separate WoW Forever page. Data refreshes about every 30 minutes from public sources (FACEIT, vlr.gg, Raider.IO). "
            f"Data refreshed {_pt(fetched)}.\n\n"
            "Not affiliated with FACEIT, ESEA, Valve, Riot Games or Blizzard. Win probabilities on ESEA NA Main match previews are an "
            "experimental Elo model estimate\u2014not a guarantee or betting advice.\n\n"
            "## Machine-readable data\n\n"
            f"- [API index (JSON)]({site}api/index.json)\n- [CS2 standings, every division (JSON)]({site}api/cs2/standings.json)\n"
            f"- [CS2 latest results (JSON)]({site}api/cs2/results.json)\n- [CS2 upcoming matches (JSON)]({site}api/cs2/upcoming.json)\n"
            f"- [Sitemap]({site}sitemap.xml)\n- [Full text digest]({site}llms-full.txt)\n\n## Sections\n\n"
            f"- [Counter-Strike 2 :: ESEA League]({site}cs2/): standings for {len(divs)} divisions\n"
            + "".join(f"- [{x['region']} {x['division']} standings]({x['page']}): {len(x['teams'])} teams\n" for x in divs)
            + f"- [CS2 results]({site}cs2/results/)\n- [CS2 top players]({site}cs2/players/)\n- [ESB Team Ranking (NA)]({site}cs2/ranking/)\n"
            f"- [Ranking and rating methodology]({site}cs2/methodology/)\n- [Valorant]({site}valorant/)\n- [Valorant Premier explainer]({site}valorant/premier/): divisions, zones, where standings live\n"
            f"- [WoW Retail Mythic raid race]({site}wow/)\n- [WoW Forever]({site}wow-forever/)\n- [News]({site}news/)\n\n"
            f"## Optional\n\n- [About]({site}about/)\n")
    full = [head, "\n## CS2 standings (top 10 per division)\n"]
    for x in divs:
        full.append(f"\n### ESEA {x['region']} {x['division']}\n")
        full += [f"{t['rank']}. {t['name']} ({t.get('country') or '-'}) {t['w']}-{t['l']}, {t['pts']} pts\n" for t in x["teams"][:10]]
    full.append("\n## Latest CS2 results\n\n")
    full += [f"- {_pt(r['finished'])}: {r['team1']['name']} {r['score'][0]}:{r['score'][1]} {r['team2']['name']} (ESEA {r['region']} {r['division']}) {r['page']}\n" for r in results[:60]]
    full.append("\n## Upcoming CS2 matches (Pacific Time)\n\n")
    for u in upcoming[:60]:
        wp = u.get("win_probability")
        full.append(f"- {_pt(u['scheduled'])}: {u['team1']['name']} vs {u['team2']['name']} (ESEA {u['region']} {u['division']})"
                    + (f"; model estimate {round(100 * wp['team1'])}% / {round(100 * wp['team2'])}%, data confidence {wp['data_confidence']}" if wp else "") + "\n")
    return head, "".join(full)


def changed_urls(rows, now=None, hours=36):
    now = now or datetime.now(timezone.utc)
    cut = (now - timedelta(hours=hours)).date().isoformat()
    keep = [u for u, d in rows if d >= cut]
    return keep[:1000]


def write_all(s, dist, site, pages, og_url, path_map=None):
    """Writes everything above except the front page JSON-LD (pages.py adds that to the template)."""
    day = (s.d.get("fetched_at") or datetime.now(timezone.utc).isoformat())[:10]
    sm, rows = sitemap(site, pages, day)
    with open(os.path.join(dist, "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write(sm)
    with open(os.path.join(dist, "robots.txt"), "w", encoding="utf-8") as fh:
        fh.write(robots(site))
    rk = {}
    try:
        with open(os.path.join(dist, "rank.json"), encoding="utf-8") as fh:
            rk = json.load(fh)
    except (OSError, ValueError):
        pass
    short, full = api_and_llms(s, dist, site, (rk.get("pred") or {}).get("matches") if isinstance(rk.get("pred"), dict) else None, path_map)
    with open(os.path.join(dist, "llms.txt"), "w", encoding="utf-8") as fh:
        fh.write(short)
    with open(os.path.join(dist, "llms-full.txt"), "w", encoding="utf-8") as fh:
        fh.write(full)
    site_png = os.path.join(dist, "og", "site.png")
    if os.path.exists(site_png):
        shutil.copyfile(site_png, os.path.join(dist, "og.png"))
    with open(os.path.join(dist, INDEXNOW_KEY + ".txt"), "w", encoding="utf-8") as fh:
        fh.write(INDEXNOW_KEY)
    lst = os.environ.get("INDEXNOW_LIST")
    if lst:
        with open(lst, "w", encoding="utf-8") as fh:
            fh.write("\n".join(changed_urls(rows)) + "\n")
    return len(rows)
