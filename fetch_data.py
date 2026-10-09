#!/usr/bin/env python3
"""Esports Scoreboard data fetcher (v3.4).

Pulls REAL public data (no accounts, no API keys, no logins) and writes
data.json + data.js (identical content; data.js lets index.html work from
file://). Every source records a status:
  OK    - fetched and parsed this run
  STALE - this run failed; the last good data from a previous run is kept
          (with its own fetched_at timestamp) and flagged on the page
  MISS  - not fetched / failed and no earlier good data; `reason` says why
Nothing is ever invented: with no good data a section stays empty + MISS.

Usage:  python3 fetch_data.py               writes data.json + data.js next to this file
        python3 fetch_data.py --out dist    writes into dist/ (the publish folder); the
                                            last-good data is read from the same folder
Deps:   requests, feedparser, beautifulsoup4, lxml   (Python 3.9+)
"""
import argparse
import calendar
import copy
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import feedparser
import requests
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
GENERATOR = "Esports Scoreboard fetch_data.py v3.4"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 EsportsScoreboard/4.7 (hobby tracker)")
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
DELAY = 1.2            # minimum seconds between two requests to the same host
TIMEOUT = (10, 25)     # (connect, read) seconds
RETRIES = 1            # one polite retry on timeouts / 429 / 5xx
_last_hit = {}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get(url, **kw):
    """GET with per-host rate limit, timeout and one retry on transient errors."""
    host = urlparse(url).netloc
    for attempt in range(RETRIES + 1):
        wait = HOST_DELAY.get(host, DELAY) - (time.monotonic() - _last_hit.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        _last_hit[host] = time.monotonic()
        try:
            r = S.get(url, timeout=TIMEOUT, **kw)
        except (requests.ConnectionError, requests.Timeout):
            if attempt < RETRIES:
                time.sleep(3)
                continue
            raise
        if r.status_code in (429, 500, 502, 503, 504) and attempt < RETRIES:
            time.sleep(5)
            continue
        return r


def get_json(url):
    r = get(url)
    r.raise_for_status()
    return r.json()


def status(name, url, ok, count=0, reason=None, **extra):
    d = {"source": name, "url": url, "status": "OK" if ok else "MISS",
         "count": count, "fetched_at": now_iso()}
    if reason:
        d["reason"] = reason
    d.update({k: v for k, v in extra.items() if v is not None})
    return d


def stale_status(name, url, reason, data_fetched_at, count, page=None):
    """Source failed this run, but last good data (from data_fetched_at) is kept."""
    d = {"source": name, "url": url, "status": "STALE", "count": count,
         "fetched_at": now_iso(), "data_fetched_at": data_fetched_at,
         "reason": f"{reason} - showing last good data"}
    if page:
        d["page"] = page
    return d


def short_err(e):
    s = str(e)
    return (s[:180] + "...") if len(s) > 180 else s


def as_int(x, default=0):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return default


def as_float(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def http_url(u):
    """Only keep absolute http(s) URLs (anything else is dropped)."""
    u = (u or "").strip()
    return u if re.match(r"^https?://", u, re.I) else None


def norm(s):
    """Collapse whitespace. Names are kept verbatim otherwise (the page HTML-escapes everything)."""
    return re.sub(r"\s+", " ", str(s or "")).strip()


def strip_html(s):
    """For text a feed declares as HTML: drop tags/entities, keep the words."""
    return norm(BeautifulSoup(s or "", "lxml").get_text(" "))


def mark_stale(obj):
    """Return a deep copy flagged stale (keeps its original fetched_at)."""
    o = copy.deepcopy(obj)
    if isinstance(o, dict):
        o["stale"] = True
    return o


# ---------------------------------------------------------------- FACEIT / ESEA
ESEA_LEAGUE_ID = "a14b8616-45b9-4581-8637-4dfd0b5f6af8"
FACEIT_WEB = "https://www.faceit.com"
ESEA_PAGE = f"{FACEIT_WEB}/en/cs2/league/ESEA%20League/{ESEA_LEAGUE_ID}"
# Divisions shown per region (FACEIT tier names, checked Oct 2026:
# Advanced > Main > Intermediate > Entry (EU) > Open*)
WANT_REGIONS = ["NA", "EU"]
WANT_DIVS = ["Advanced", "Main", "Intermediate"]
STANDINGS_PAGE = 100       # FACEIT standings JSON caps limit at 100 -> page through the full table
STANDINGS_MAX_PAGES = 5    # per stage / conference (500 teams)
TOP_INLINE = 20            # top N per division keep roster + FACEIT url inline in data.json;
                           # every other team's roster + match lines go to the lazy teams.json
PLAYER_PAGE_SIZE = 100
PLAYER_MAX_PAGES = 8      # conferences have ~100-450 players; stop early when a page is short
TOP_PLAYERS = 15
MIN_ROUNDS = 20            # ranking only (top fraggers); every player with >= 1 round is shown on his page
TOP_PER_DIV = 10           # top fraggers per division, inline in data.json
PREV_EXTRA = {}            # previous teams.json (last-good lazy player stats), set by main()
# Roster pages (championship subscription, public): limit=20 per page. Cap total
# requests so a slow FACEIT day cannot blow the Actions 10-minute timeout.
ROSTER_PAGE = 20
ROSTER_MAX_REQ = 80          # total GETs for rosters across all conferences (~45 needed in Oct 2026)
ROSTER_MAX_PAGES_PER_CONF = 12   # 240 teams per conference at most
# Official FACEIT Data API (open.faceit.com) - used for match results ONLY when the
# FACEIT_API_KEY env var is set (GitHub Actions secret). The key is sent solely as the
# Authorization header and is never printed, logged or written to data files.
FACEIT_API_KEY = (os.environ.get("FACEIT_API_KEY") or "").strip() or None
FACEIT_DATA_API = "https://open.faceit.com/data/v4"


PLAYER_ROW = ("nick", "region", "division", "matches", "rounds", "kills", "deaths", "kd", "adr", "hs",
              "team_id", "drank", "dpool")   # team name: app.js looks it up from team_id


def player_row(p):
    """Compact lazy row (teams.json "players"): values in PLAYER_ROW order."""
    return [p.get(k) for k in PLAYER_ROW]


def players_from_rows(r):
    try:
        p = dict(zip(PLAYER_ROW, r))
        p["url"] = f"{FACEIT_WEB}/en/players/{quote(p['nick'], safe='')}"
        p.setdefault("team", None)
        return p
    except Exception:
        return None


def fetch_faceit(prev):
    prev = prev or {}
    out = {"league": "ESEA League (FACEIT)", "page": ESEA_PAGE, "season": None,
           "divisions": [], "top_players": [], "players": [], "top_players_meta": None, "matches": [], "upcoming": [], "live": [],
           "matches_meta": None, "sources": [], "_extra": {"rosters": {}, "matches": [], "upcoming": [], "players": []}}
    def reuse_everything(name, url, reason):
        """Seasons/tree failed: keep the previous season data, flagged stale."""
        if prev.get("season"):
            for k in ("season", "all_tiers", "top_players_meta"):
                if prev.get(k) is not None:
                    out[k] = mark_stale(prev[k])
            out["divisions"] = [mark_stale(d) for d in prev.get("divisions", [])]
            out["top_players"] = copy.deepcopy(prev.get("top_players", []))
            out["players"] = copy.deepcopy(prev.get("players", []))
            out["top_by_div"] = copy.deepcopy(prev.get("top_by_div") or {})
            out["matches"] = copy.deepcopy(prev.get("matches", []))
            out["upcoming"] = copy.deepcopy(prev.get("upcoming", []))
            if prev.get("matches_meta"):
                out["matches_meta"] = mark_stale(prev["matches_meta"])
            if out.get("top_players_meta"):
                out["top_players_meta"]["stale"] = True
            out["sources"].append(stale_status(name, url, reason, prev["season"].get("fetched_at") or prev.get("fetched_at"),
                                               sum(len(d.get("teams", [])) for d in out["divisions"])))
        else:
            out["sources"].append(status(name, url, False, reason=reason))
        return out

    # 1) seasons (public JSON served to the faceit.com league page)
    url = f"{FACEIT_WEB}/api/team-leagues/v2/leagues/{ESEA_LEAGUE_ID}/seasons"
    try:
        seasons = get_json(url)["payload"]
        active = [s for s in seasons if s.get("status") == "active"] or seasons
        season = sorted(active, key=lambda s: s.get("season_number", 0), reverse=True)[0]
        maps = []
        for mp in season.get("map_pool") or []:
            for m in (mp.get("maps") or []):
                if m.get("name"):
                    maps.append(m["name"])
        out["season"] = {"id": season["id"], "name": season.get("season_name") or f"Season {season.get('season_number')}",
                         "number": season.get("season_number"), "status": season.get("status"),
                         "start": season.get("time_start"), "end": season.get("time_end"),
                         "team_count": season.get("current_team_count"),
                         "prize_pool": season.get("total_prize_pool"),
                         "maps": maps, "fetched_at": now_iso()}
        out["sources"].append(status("FACEIT ESEA seasons (public web JSON)", url, True, 1, page=ESEA_PAGE))
    except Exception as e:
        return reuse_everything("FACEIT ESEA seasons (public web JSON)", url, f"request failed: {short_err(e)}")

    sid = out["season"]["id"]
    same_season = (prev.get("season") or {}).get("id") == sid
    season_page = f"{ESEA_PAGE}/{sid}"
    # 2) season tree -> regions/divisions/stages/conferences
    url = f"{FACEIT_WEB}/api/team-leagues/v2/seasons/tree?entityType=season&entityId={sid}"
    try:
        tree = get_json(url)["payload"]
        regions = tree["regions"]
        out["sources"].append(status("FACEIT ESEA season tree", url, True, len(regions), page=season_page))
    except Exception as e:
        season_fresh = out["season"]
        if same_season:
            reuse_everything("FACEIT ESEA season tree", url, f"request failed: {short_err(e)}")
            out["season"] = season_fresh
        else:
            out["sources"].append(status("FACEIT ESEA season tree", url, False, reason=f"request failed: {short_err(e)}"))
        return out

    out["all_tiers"] = {rg.get("code"): [d.get("name") for d in rg.get("divisions", [])] for rg in regions}
    prev_divs = {(d.get("region"), d.get("division")): d for d in prev.get("divisions", [])} if same_season else {}
    stat_champs, n_fresh, stale_divs, miss_divs = [], 0, [], []
    for rg in regions:
        if rg.get("code") not in WANT_REGIONS:
            continue
        for dv in rg.get("divisions", []):
            if dv.get("name") not in WANT_DIVS:
                continue
            stage = next((s for s in dv.get("stages", []) if s.get("phase") == 1), None)
            if not stage or not stage.get("conferences"):
                continue
            confs = stage["conferences"]

            def qs(c):
                return f"?region={rg['id']}&division={dv['id']}&stage={stage['id']}&conference={c['id']}"
            entry = {"region": rg["code"], "division": dv["name"], "stage": stage.get("name", ""),
                     "conferences": [c.get("name", "") for c in confs],
                     "link": f"{season_page}/standings{qs(confs[0])}",
                     "conf_links": [{"name": c.get("name", ""), "url": f"{season_page}/standings{qs(c)}"} for c in confs],
                     "teams": [], "fetched_at": now_iso()}
            def all_rows(eid, etype):
                rows_ = []
                for pg_ in range(STANDINGS_MAX_PAGES):
                    u_ = (f"{FACEIT_WEB}/api/team-leagues/v2/standings?entityId={eid}"
                          f"&entityType={etype}&userId=&offset={pg_ * STANDINGS_PAGE}&limit={STANDINGS_PAGE}")
                    part = get_json(u_)["payload"]["standings"] or []
                    rows_ += part
                    if len(part) < STANDINGS_PAGE:
                        break
                return rows_
            try:
                rows = all_rows(stage["id"], "stage")
                # team -> conference (only needed when the stage has >1 conference)
                conf_of = {}
                if len(confs) > 1:
                    for c in confs:
                        try:
                            for t in all_rows(c["id"], "conference"):
                                conf_of[t.get("premade_team_id")] = c.get("name")
                        except Exception:
                            pass  # conference labels are optional
                for t in rows:
                    try:
                        if not norm(t.get("name")):
                            continue
                        tb = t.get("tie_breakers") or {}
                        rs, re_ = t.get("rank_start"), t.get("rank_end")
                        rank = str(rs) if rs == re_ else f"{rs}-{re_}"
                        tid = t.get("premade_team_id")
                        row = {"id": tid, "rank": rank, "name": norm(t.get("name")), "tag": norm(t.get("nickname")),
                               "country": (t.get("country_code") or "").upper()[:3],
                               "conf": conf_of.get(tid),
                               "w": as_int(t.get("won")), "l": as_int(t.get("lost")), "t": as_int(t.get("tied")),
                               "pts": as_int(t.get("points")),
                               "rounds": f"{as_int(tb.get('rounds_won'))}-{as_int(tb.get('rounds_lost'))}",
                               "dq": bool(t.get("is_disqualified", False))}
                        if len(entry["teams"]) < TOP_INLINE:
                            row.update(roster=[], url=f"{FACEIT_WEB}/en/teams/{tid}" if tid else None)
                        else:                      # compact row: app.js derives the FACEIT link from the id
                            row = {k: v for k, v in row.items() if v not in (None, False) and not (k == "t" and v == 0)}
                        entry["teams"].append(row)
                    except Exception:
                        continue  # skip one malformed row, keep the rest
                entry["status"] = "OK"
                n_fresh += len(entry["teams"])
            except Exception as e:
                p = prev_divs.get((rg["code"], dv["name"]))
                if p and p.get("teams"):
                    entry = mark_stale(p)
                    entry["status"] = "OK"
                    entry["stale_reason"] = f"standings request failed: {short_err(e)}"
                    stale_divs.append(f"{rg['code']} {dv['name']}")
                else:
                    entry["status"] = "MISS"
                    entry["reason"] = f"standings request failed: {short_err(e)}"
                    miss_divs.append(f"{rg['code']} {dv['name']}")
            out["divisions"].append(entry)
            if True:   # v3.7.2: player stats for every tracked division (was Advanced only)
                for c in confs:
                    if c.get("championship_id"):
                        stat_champs.append((rg["code"], dv["name"], c["championship_id"], f"{season_page}/stats{qs(c)}"))
    surl = f"{FACEIT_WEB}/api/team-leagues/v2/standings?entityType=stage&entityId=<stage>"
    spage = f"{season_page}/standings"
    if n_fresh and not stale_divs and not miss_divs:
        out["sources"].append(status("FACEIT ESEA standings (public web JSON)", surl, True, n_fresh, page=spage))
    elif stale_divs:
        out["sources"].append(stale_status("FACEIT ESEA standings (public web JSON)", surl,
                                           "request failed for " + ", ".join(stale_divs),
                                           min(d.get("fetched_at", "") for d in out["divisions"] if d.get("stale")),
                                           sum(len(d.get("teams", [])) for d in out["divisions"]), page=spage))
    else:
        out["sources"].append(status("FACEIT ESEA standings (public web JSON)", surl, n_fresh > 0, n_fresh, page=spage,
                                     reason=("no standings for " + ", ".join(miss_divs)) if miss_divs else
                                     (None if n_fresh else "no standings rows returned")))


    # 2b) conference rosters (public championship subscription JSON) - attach to
    #     standings teams we already have; never invent members for missing teams.
    by_id = {t["id"]: t for d in out["divisions"] for t in d.get("teams", [])[:TOP_INLINE] if t.get("id")}
    all_ids = {t["id"] for d in out["divisions"] for t in d.get("teams", []) if t.get("id")}
    extra_r = out["_extra"]["rosters"]
    nick_team = {}      # lower(nick) -> {"id", "name"} for every team seen (players' team lookup)
    roster_n, roster_req, roster_err = 0, 0, []
    for dname in WANT_DIVS:                      # Advanced first, so the cap hits lower tiers last
        for rg in regions:
            if rg.get("code") not in WANT_REGIONS:
                continue
            dv = next((x for x in rg.get("divisions", []) if x.get("name") == dname), None)
            stage = next((x for x in (dv or {}).get("stages", []) if x.get("phase") == 1), None)
            if not stage:
                continue
            want = {t["id"] for d in out["divisions"] if d["region"] == rg.get("code") and d["division"] == dname
                    for t in d.get("teams", []) if t.get("id")}
            found = set()
            for c in stage.get("conferences") or []:
                cid = c.get("championship_id")
                pages = 0
                while cid and roster_req < ROSTER_MAX_REQ and pages < ROSTER_MAX_PAGES_PER_CONF:
                    if dname != "Advanced" and want and want <= found:
                        break                    # all shown teams found; Advanced keeps paging for player->team
                    rurl = (f"{FACEIT_WEB}/api/championships/v1/championship/{cid}/subscription"
                            f"?limit={ROSTER_PAGE}&offset={pages * ROSTER_PAGE}")
                    roster_req += 1
                    pages += 1
                    try:
                        items = (get_json(rurl).get("payload") or {}).get("items") or []
                    except Exception as e:
                        roster_err.append(f"{rg.get('code')} {dname} {c.get('name')}: {short_err(e)}")
                        break
                    for it in items:
                        try:
                            team = it.get("team") or {}
                            tid = team.get("id")
                            members = team.get("members") or []
                            roster_ids = set(it.get("roster") or [])
                            sub_ids = set(it.get("substitutes") or [])
                            rows = []
                            for m in members:
                                nick = norm(m.get("nickname"))
                                mid = m.get("id")
                                if not nick or (mid not in roster_ids and mid not in sub_ids):
                                    continue             # FACEIT team members not registered for this league
                                rows.append({"nick": nick, "country": (m.get("country") or "").upper()[:3],
                                             "sub": mid in sub_ids, "_id": mid})
                                nick_team.setdefault(nick.lower(), {"id": tid, "name": norm(team.get("name"))})
                            if tid in by_id:
                                by_id[tid]["leader"] = next((m["nick"] for m in rows if m["_id"] == it.get("leader")), None)
                                by_id[tid]["roster"] = [{k: v for k, v in m.items() if k != "_id"} for m in rows]
                                found.add(tid)
                                roster_n += 1
                            elif tid in all_ids and tid not in extra_r:
                                # compact: [nick, country, sub(0/1)], leader nick
                                extra_r[tid] = {"r": [[m["nick"], m["country"], 1 if m["sub"] else 0] for m in rows],
                                                "lead": next((m["nick"] for m in rows if m["_id"] == it.get("leader")), None)}
                                found.add(tid)
                                roster_n += 1
                        except Exception:
                            continue
                    if len(items) < ROSTER_PAGE:
                        break
    rname = "FACEIT ESEA conference rosters (public web JSON)"
    rpage = f"{season_page}/standings"
    if roster_n:
        out["sources"].append(status(rname, f"{FACEIT_WEB}/api/championships/v1/championship/<id>/subscription",
                                     True, roster_n, page=rpage,
                                     note=f"{roster_req} request(s)" + (f"; partial: {'; '.join(roster_err)}" if roster_err else "")))
    elif roster_err:
        # leave teams with empty roster lists; detail pages show an honest empty state
        out["sources"].append(status(rname, f"{FACEIT_WEB}/api/championships/v1/championship/<id>/subscription",
                                     False, page=rpage, reason="; ".join(roster_err)))
    else:
        out["sources"].append(status(rname, f"{FACEIT_WEB}/api/championships/v1/championship/<id>/subscription",
                                     False, page=rpage, reason="no roster rows matched standings teams"))

    # 3) player season stats for every tracked division/conference from the public
    #    competition stats JSON (paged, 100 per request). Every player with >= 1 round is
    #    kept; rankings (top fraggers) need MIN_ROUNDS. Ranked Advanced players stay inline
    #    in data.json; everyone else goes to the lazy teams.json ("players", compact rows).
    #    A conference that fails keeps its last-good players (same season), flagged stale.
    players, errs, preq, failed_groups = [], [], 0, set()
    for region, div, cid, link in stat_champs:
        for page in range(PLAYER_MAX_PAGES):
            url = (f"{FACEIT_WEB}/api/stats/v1/competitions/{cid}/players"
                   f"?page={page}&size={PLAYER_PAGE_SIZE}&sort=stats.m2,desc")
            preq += 1
            try:
                batch = get_json(url)["payload"].get("players") or []
            except Exception as e:
                errs.append(f"{region} {div} page {page}: {short_err(e)}")
                failed_groups.add((region, div))
                break
            for p in batch:
                try:
                    st = p.get("stats") or {}
                    rounds = as_int(st.get("m8"))
                    if rounds < 1 or not p.get("nickname"):
                        continue
                    players.append({
                        "nick": norm(p["nickname"]), "id": p.get("id"),
                        "region": region, "division": div,
                        "matches": as_int(st.get("m1")), "kills": as_int(st.get("m3")),
                        "deaths": as_int(st.get("m4")), "kd": as_float(st.get("k5")),
                        "adr": as_float(st.get("k17")), "hs": as_float(st.get("k8")),
                        "rounds": rounds, "team_id": None, "team": None,
                        "url": f"{FACEIT_WEB}/en/players/{quote(p['nickname'], safe='')}"})
                except Exception:
                    continue
            if len(batch) < PLAYER_PAGE_SIZE:
                break
    # one row per player and division (a player listed in two conferences keeps the larger sample)
    best = {}
    for p in players:
        k = ((p.get("id") or p["nick"].lower()), p["region"], p["division"])
        if k not in best or p["rounds"] > best[k]["rounds"]:
            best[k] = p
    players = list(best.values())
    # last-good players for divisions whose stats failed this run (same season only)
    n_reused = 0
    if failed_groups and same_season:
        have = {(p["region"], p["division"]) for p in players}
        old = list(prev.get("players") or []) + [players_from_rows(r_) for r_ in (PREV_EXTRA.get("players") or [])]
        for p in old:
            if p and (p.get("region"), p.get("division")) in failed_groups and (p.get("region"), p.get("division")) not in have:
                players.append({k_: v_ for k_, v_ in p.items() if k_ not in ("rank", "drank", "dpool")})
                n_reused += 1
    # attach team from the public rosters (case-insensitive nick match)
    for p in players:
        t = nick_team.get((p.get("nick") or "").lower())
        if t:
            p["team_id"] = t.get("id")
            p["team"] = t.get("name")
    key = lambda p: (p["kd"], p["adr"])
    # division rank among players with >= MIN_ROUNDS
    by_div = {}
    for p in sorted(players, key=key, reverse=True):
        if p["rounds"] >= MIN_ROUNDS:
            by_div.setdefault((p["region"], p["division"]), []).append(p)
    for grp in by_div.values():
        for i, p in enumerate(grp):
            p["drank"], p["dpool"] = i + 1, len(grp)
    adv = sorted((p for p in players if p["division"] == "Advanced"), key=lambda p: (p["rounds"] >= MIN_ROUNDS, p["kd"], p["adr"]), reverse=True)
    ranked_adv = [p for p in adv if p["rounds"] >= MIN_ROUNDS]
    for i, p in enumerate(ranked_adv):
        p["rank"] = i + 1
    purl = f"{FACEIT_WEB}/api/stats/v1/competitions/<championship>/players"
    pname = "FACEIT ESEA player stats, all tracked divisions (public web JSON)"
    ppage = stat_champs[0][3] if stat_champs else f"{season_page}/stats"
    if players:
        out["players"] = ranked_adv                             # ranked Advanced pool inline
        out["stats_links"] = {}
        for rg_, dv_, _cid, lk in stat_champs:
            out["stats_links"].setdefault(rg_, lk)
            out["stats_links"].setdefault(f"{rg_} {dv_}", lk)
        out["top_players"] = ranked_adv[:TOP_PLAYERS]
        out["top_by_div"] = {f"{rg_} {dv_}": [dict(p) for p in grp[:TOP_PER_DIV]] for (rg_, dv_), grp in by_div.items()}
        out["_extra"]["players"] = [player_row(p) for p in players if not p.get("rank")]   # everyone else (lazy)
        out["top_players_meta"] = {"fetched_at": now_iso(), "stale": bool(n_reused), "pool": len(ranked_adv),
                                   "min_rounds": MIN_ROUNDS, "total": len(players),
                                   "per_div": {f"{a} {b}": len(g) for (a, b), g in by_div.items()}}
        out["sources"].append(status(pname, purl, True, len(players), page=ppage,
                                     note=f"{len(players)} players with stats ({len(ranked_adv)} Advanced ranked); {preq} request(s)"
                                          + (f"; {n_reused} reused from last good data" if n_reused else "")
                                          + (f"; errors: {'; '.join(errs)}" if errs else "")))
    elif same_season and prev.get("top_players"):
        out["top_players"] = copy.deepcopy(prev["top_players"])
        out["players"] = copy.deepcopy(prev.get("players", []))
        out["top_by_div"] = copy.deepcopy(prev.get("top_by_div") or {})
        if PREV_EXTRA.get("players"):
            out["_extra"]["players"] = copy.deepcopy(PREV_EXTRA["players"])
        out["top_players_meta"] = mark_stale(prev.get("top_players_meta") or {"fetched_at": prev.get("fetched_at")})
        out["sources"].append(stale_status(pname, purl, "; ".join(errs) or "no player stats returned",
                                           out["top_players_meta"].get("fetched_at"), len(out["top_players"]), page=ppage))
    else:
        out["sources"].append(status(pname, purl, False, page=ppage,
                                     reason="; ".join(errs) or "no player stats yet"))

    # 4) match results + upcoming via the official FACEIT Data API (needs FACEIT_API_KEY).
    #    Without a key (or on 401/403/429) the section is MISS, or STALE with last-good data.
    conf_champs = []
    for rg in regions:
        if rg.get("code") not in WANT_REGIONS:
            continue
        for dv in rg.get("divisions", []):
            if dv.get("name") not in WANT_DIVS:
                continue
            stage = next((x for x in dv.get("stages", []) if x.get("phase") == 1), None)
            for c in (stage or {}).get("conferences") or []:
                if c.get("championship_id"):
                    conf_champs.append((rg["code"], dv["name"], c.get("name", ""), c["championship_id"]))
    fetch_matches(out, prev, conf_champs, season_page, same_season)
    return out


# ------------------------------------------------- FACEIT Data API (matches)
DATA_API_DELAY = 0.5        # s between Data API calls (limit is 20/s; stay far below)
DATA_API_MAX_REQ = 150      # hard cap per run (lists + match stats)
MATCH_STATS_MAX = 100       # new /matches/{id}/stats calls per run (finished stats are reused)
RECENT_PER_DIV = 12         # newest finished matches kept per division (+ tracked teams' matches)
UPCOMING_PER_DIV = 8        # next scheduled matches kept per division (+ each tracked team's next match)
KEEP_PER_DIV = 60           # hard cap of stored finished / upcoming matches per division
HOST_DELAY = {"open.faceit.com": DATA_API_DELAY}


class DataApiError(Exception):
    pass


def data_api(path, **params):
    """GET an official FACEIT Data API path. The key is only ever sent as a header;
    it is never logged, stored or put into URLs / error messages."""
    if not FACEIT_API_KEY:
        raise DataApiError("no FACEIT_API_KEY")
    url = f"{FACEIT_DATA_API}{path}"
    r = get(url, params=params or None,
            headers={"Authorization": "Bearer " + FACEIT_API_KEY, "Accept": "application/json"})
    if r.status_code in (401, 403):
        raise DataApiError(f"HTTP {r.status_code} (key rejected or not allowed)")
    if r.status_code == 429:
        raise DataApiError("HTTP 429 (rate limited)")
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise DataApiError(f"HTTP {r.status_code}")
    try:
        return r.json()
    except ValueError:
        raise DataApiError("invalid JSON")


def epoch_iso(x):
    try:
        x = int(x)
        return datetime.fromtimestamp(x, timezone.utc).isoformat(timespec="seconds") if x > 0 else None
    except (TypeError, ValueError, OSError):
        return None


def map_name(m):
    m = norm(m)
    return re.sub(r"^de_", "", m).replace("_", " ").title() if m else ""


def room_url(item):
    u = http_url((item.get("faceit_url") or "").replace("{lang}", "en"))
    return u or (f"{FACEIT_WEB}/en/cs2/room/{quote(item['match_id'], safe='')}" if item.get("match_id") else None)


def side(team):
    team = team or {}
    if team.get("type") == "bye" or team.get("faction_id") in (None, "", "bye"):
        return None
    return {"id": team.get("faction_id"), "name": norm(team.get("name")) or "TBD"}


def parse_stats(st):
    """/matches/{id}/stats -> [{map, s1, s2, p1, p2}] in faction order of the match."""
    maps = []
    for rd in (st or {}).get("rounds") or []:
        rs = rd.get("round_stats") or {}
        teams = rd.get("teams") or []
        if len(teams) != 2:
            continue
        def lines(t):
            out = []
            for p in t.get("players") or []:
                ps = p.get("player_stats") or {}
                out.append([norm(p.get("nickname")), as_int(ps.get("Kills")), as_int(ps.get("Deaths")),
                            round(as_float(ps.get("ADR")), 1), as_int(ps.get("Headshots %"))])
            out.sort(key=lambda x: (x[1], x[3]), reverse=True)
            return out
        maps.append({"map": map_name(rs.get("Map")), "tid": [teams[0].get("team_id"), teams[1].get("team_id")],
                     "fs": [as_int((teams[0].get("team_stats") or {}).get("Final Score")),
                            as_int((teams[1].get("team_stats") or {}).get("Final Score"))],
                     "pl": [lines(teams[0]), lines(teams[1])]})
    return maps


def orient(maps, t1id):
    """Order per-map team data as (team1, team2) of the match listing."""
    out = []
    for m in maps:
        a, b = (0, 1) if m["tid"][0] == t1id or m["tid"][1] != t1id else (1, 0)
        out.append({"map": m["map"], "s1": m["fs"][a], "s2": m["fs"][b], "p1": m["pl"][a], "p2": m["pl"][b]})
    return out


def fetch_matches(out, prev, conf_champs, season_page, same_season):
    lname = "FACEIT Data API: ESEA match lists"
    sname = "FACEIT Data API: match stats (maps, scoreboards)"
    lurl = f"{FACEIT_DATA_API}/championships/<conference>/matches"
    surl = f"{FACEIT_DATA_API}/matches/<id>/stats"
    prev_ok = same_season and (prev.get("matches") or prev.get("upcoming"))

    def keep_prev(reason, name=lname, url=lurl):
        if prev_ok:
            out["matches"] = copy.deepcopy(prev.get("matches") or [])
            out["upcoming"] = copy.deepcopy(prev.get("upcoming") or [])
            out["matches_meta"] = mark_stale(prev.get("matches_meta") or {"fetched_at": prev.get("fetched_at")})
            out["sources"].append(stale_status(name, url, reason, out["matches_meta"].get("fetched_at"),
                                               len(out["matches"]), page=season_page))
        else:
            out["sources"].append(status(name, url, False, reason=reason, page=season_page))

    if not FACEIT_API_KEY:
        keep_prev("FACEIT Data API needs an API key (FACEIT_API_KEY not set) - not fetched (no sign-up per rules)")
        return
    tracked = {}   # team id -> (region, division); the top TOP_INLINE of each division
    for d in out["divisions"]:
        for t in d.get("teams", [])[:TOP_INLINE]:
            if t.get("id"):
                tracked[t["id"]] = (d["region"], d["division"])
    nreq, errs, fin, upc, ong = 0, [], {}, {}, {}
    for region, div, conf, cid in conf_champs:
        key = (region, div)
        for kind in ("past", "ongoing", "upcoming"):
            if nreq >= DATA_API_MAX_REQ:
                errs.append("request cap reached")
                break
            nreq += 1
            try:
                d = data_api(f"/championships/{quote(cid, safe='')}/matches", type=kind, offset=0, limit=100)
            except DataApiError as e:
                errs.append(f"{region} {div} {conf} {kind}: {e}")
                if "401" in str(e) or "403" in str(e) or "429" in str(e):
                    return keep_prev(str(e))
                continue
            except Exception as e:
                errs.append(f"{region} {div} {conf} {kind}: {short_err(e)}")
                continue
            for it in (d or {}).get("items") or []:
                try:
                    t1, t2 = side((it.get("teams") or {}).get("faction1")), side((it.get("teams") or {}).get("faction2"))
                    if not t1 or not t2:
                        continue                         # byes are not matches
                    m = {"id": it["match_id"], "region": region, "division": div, "conf": conf,
                         "round": as_int(it.get("round")), "bo": as_int(it.get("best_of"), 1),
                         "t1": t1, "t2": t2}
                    picks = ((it.get("voting") or {}).get("map") or {}).get("pick") or []
                    picks = [map_name(x) for x in picks if isinstance(x, str) and x][:5]
                    if picks:
                        m["pick"] = picks         # v4.4: map(s) chosen in the veto (FACEIT lists no bans here)
                    u = room_url(it)          # app.js derives the standard room URL from the id
                    if u and u != f"{FACEIT_WEB}/en/cs2/room/{it['match_id']}":
                        m["url"] = u
                    if kind == "past":
                        if it.get("status") != "FINISHED":
                            continue
                        res = it.get("results") or {}
                        sc = res.get("score") or {}
                        m.update({"t": epoch_iso(it.get("finished_at")) or epoch_iso(it.get("started_at")) or epoch_iso(it.get("scheduled_at")),
                                  "s1": as_int(sc.get("faction1")), "s2": as_int(sc.get("faction2")),
                                  "winner": 1 if res.get("winner") == "faction1" else 2 if res.get("winner") == "faction2" else 0})
                        fin.setdefault(key, []).append(m)
                    elif kind == "ongoing":           # live now (as of this fetch)
                        m["t"] = epoch_iso(it.get("started_at")) or epoch_iso(it.get("scheduled_at"))
                        m["status"] = norm(it.get("status")) or "ONGOING"
                        ong.setdefault(key, []).append(m)
                    else:
                        m["t"] = epoch_iso(it.get("scheduled_at"))
                        upc.setdefault(key, []).append(m)
                except Exception:
                    continue
    nlist = nreq
    if not fin and not upc and not ong:
        return keep_prev("; ".join(errs) or "no matches returned")

    now_ts = datetime.now(timezone.utc).timestamp()

    def near(m):
        """within ~30 h of now: keeps every match of 'today' (Pacific) for the front-page board."""
        try:
            return abs(datetime.fromisoformat(m["t"]).timestamp() - now_ts) < 30 * 3600
        except (KeyError, TypeError, ValueError):
            return False

    def pick(rows, n, newest_first, per_team):
        """newest/next n of the division + every match within ~30 h + up to per_team matches of every tracked team."""
        rows.sort(key=lambda m: m.get("t") or "", reverse=newest_first)
        seen, keep, cnt = set(), [], {}
        for i, m in enumerate(rows):
            if m["id"] in seen:
                continue
            want = i < n or near(m)
            for tid in (m["t1"]["id"], m["t2"]["id"]):
                if tid in tracked and cnt.get(tid, 0) < per_team:
                    want = True
            if want:
                seen.add(m["id"])
                keep.append(m)
                for tid in (m["t1"]["id"], m["t2"]["id"]):
                    cnt[tid] = cnt.get(tid, 0) + 1
        return keep[:KEEP_PER_DIV]
    matches = [m for k in fin for m in pick(fin[k], RECENT_PER_DIV, True, 3)]
    upcoming = [m for k in upc for m in pick(upc[k], UPCOMING_PER_DIV, False, 1)]
    live_ids = {m["id"] for k in ong for m in ong[k]}
    live = [m for k in ong for m in ong[k]][:60]
    upcoming = [m for m in upcoming if m["id"] not in live_ids]
    # match stats: reuse finished-match stats from last-good data, fetch the rest (newest first)
    old = {m["id"]: m.get("maps") for m in (prev.get("matches") or []) if m.get("maps")} if same_season else {}
    # matches that had no published stats >6 h after finishing (forfeits / technical results) are not re-asked
    cutoff = (datetime.now(timezone.utc).timestamp() - 6 * 3600)
    old_nostats = {m["id"] for m in (prev.get("matches") or []) if same_season and m.get("nostats") and m.get("t")
                   and datetime.fromisoformat(m["t"]).timestamp() < cutoff}
    nstats, nreuse, serr, nmiss = 0, 0, [], 0
    matches.sort(key=lambda m: m.get("t") or "", reverse=True)
    # priority: the newest RECENT_PER_DIV of every division first, then everything else
    first = set()
    for k in fin:
        for m in sorted(fin[k], key=lambda m: m.get("t") or "", reverse=True)[:RECENT_PER_DIV]:
            first.add(m["id"])
    for m in sorted(matches, key=lambda m: (m["id"] not in first, -(datetime.fromisoformat(m["t"]).timestamp() if m.get("t") else 0))):
        if m["id"] in old:
            m["maps"] = old[m["id"]]
            nreuse += 1
            continue
        if m["id"] in old_nostats:
            m["nostats"] = True
            nmiss += 1
            nreuse += 1
            continue
        if nstats >= MATCH_STATS_MAX or nreq >= DATA_API_MAX_REQ:
            continue
        nreq += 1
        nstats += 1
        try:
            st = data_api(f"/matches/{quote(m['id'], safe='')}/stats")
        except DataApiError as e:
            serr.append(str(e))
            if "429" in str(e) or "401" in str(e) or "403" in str(e):
                break
            continue
        except Exception as e:
            serr.append(short_err(e))
            continue
        maps = orient(parse_stats(st), m["t1"]["id"]) if st else []
        if maps:
            m["maps"] = maps
        else:
            m["nostats"] = True
            nmiss += 1
    out["matches"] = matches
    out["upcoming"] = upcoming
    # every other listed match (no stats; no extra requests) -> lazy teams.json for all team pages
    kept = {m["id"] for m in matches} | {m["id"] for m in upcoming} | live_ids
    out.setdefault("_extra", {"rosters": {}})
    out["_extra"]["matches"] = sorted((m for k in fin for m in fin[k] if m["id"] not in kept), key=lambda m: m.get("t") or "", reverse=True)
    out["_extra"]["upcoming"] = sorted((m for k in upc for m in upc[k] if m["id"] not in kept), key=lambda m: m.get("t") or "")
    out["live"] = live
    out["matches_meta"] = {"fetched_at": now_iso(), "stale": False, "requests": nreq, "list_requests": nlist,
                           "stats_requests": nstats, "stats_reused": nreuse,
                           "with_maps": sum(1 for m in matches if m.get("maps")), "live": len(live)}
    out["sources"].append(status(lname, lurl, True, len(matches) + len(upcoming), page=season_page,
                                 note=f"{len(matches)} finished + {len(live)} live + {len(upcoming)} upcoming kept from {len(conf_champs)} conferences; "
                                      f"{nlist} list request(s)" + (f"; errors: {'; '.join(errs[:4])}" if errs else "")))
    with_maps = out["matches_meta"]["with_maps"]
    sreason = None if with_maps else ("; ".join(serr[:3]) or "no stats returned")
    out["sources"].append(status(sname, surl, with_maps > 0, with_maps, page=season_page, reason=sreason,
                                 note=f"{nstats} fetched, {nreuse} reused from last run" + (f", {nmiss} without published stats" if nmiss else "")
                                      + (f"; errors: {'; '.join(serr[:3])}" if serr and with_maps else "")))


# ---------------------------------------------------------------- VLR.gg
VLR = "https://www.vlr.gg"
# vlr.gg renders match times/dates for anonymous visitors in US Central time
# (verified Oct 2026: match page shows "6:20 AM CDT" for a list entry "6:20 AM").
VLR_TZ = ZoneInfo("America/Chicago")
RESULT_PAGES = 3          # vlr.gg results pages to scan (polite: DELAY between each)
RESULTS_KEEP = 120        # max kept after filtering
# Tier-2 / Game Changers circuits are never excluded (note "Challengers 2026:
# LATAM North ACE Masters" is a Challengers event despite the word Masters).
TIER2_RE = re.compile(r"^(Challengers|VCL|Game Changers|GC)\b", re.I)
# International VCT events: "Valorant Champions 2026", "Valorant Masters Toronto",
# "Champions Tour 2025: Masters Bangkok", ...
INTL_RE = re.compile(r"\b(Champions|Masters)\b")
# Franchised tier-1 partner leagues ("VCT 2026: Americas Stage 2"). They are not
# international, but Esports Scoreboard tracks Challengers / Game Changers / tier-2, so they
# are excluded too. Set to False to show them.
EXCLUDE_VCT_PARTNER_LEAGUES = True
PARTNER_RE = re.compile(r"^(VCT|Champions Tour) 20\d\d:")


def vlr_excluded(event):
    """Return 'international', 'partner' or None for a vlr.gg event name."""
    if TIER2_RE.search(event):
        return None
    if INTL_RE.search(event):
        return "international"
    if EXCLUDE_VCT_PARTNER_LEAGUES and PARTNER_RE.search(event):
        return "partner"
    return None


def vlr_events(tier, label):
    s = BeautifulSoup(get_html(f"{VLR}/events/?tier={tier}"), "lxml")
    evs = []
    for a in s.select("a.event-item"):
        try:
            title = a.select_one(".event-item-title")
            st = a.select_one(".event-item-desc-item-status")
            dates = a.select_one(".event-item-desc-item.mod-dates")
            if not title or not a.get("href"):
                continue
            evs.append({"title": title.get_text(" ", strip=True), "status": st.get_text(strip=True) if st else "",
                        "dates": re.sub(r"\s*Dates$", "", dates.get_text(" ", strip=True)) if dates else "",
                        "url": VLR + a["href"], "circuit": label})
        except Exception:
            continue
    return evs


def get_html(url):
    r = get(url)
    r.raise_for_status()
    return r.text


VAL_CH_EVENTS = 10        # latest completed main event per Challengers / VCL circuit (region)
VAL_GC_EVENTS = 4         # ... and per Game Changers circuit
VAL_STATS_REQ_MAX = 30    # event stats pages per run (completed events are cached -> ~0 after the first run)
VAL_TEAM_REQ_MAX = 20     # vlr.gg team pages (rosters) per run
VAL_TEAM_TTL_H = 72       # refresh a cached roster after this many hours
VAL_MATCH_REQ_MAX = 12    # v4.4: vlr.gg match pages (veto line, map scores) per run; finished matches are cached for good
VAL_MIN_RND = 100         # rounds needed for the Valorant top players ranking
VAL_REQ = {}              # request counters (reported in the source notes)
PREV_VAL = {}             # previous val.json (last-good lazy Valorant players/teams), set by main()
_SKIP_EV = re.compile(r"Cash Cup|Last Chance|Qualifier|Showmatch", re.I)


def val_circuit(title):
    """'Challengers 2026: North America ACE Stage 3' -> 'North America ACE' (one event per circuit)."""
    t = re.sub(r"^(Challengers 20\d\d|VCL \d\d|Game Changers 20\d\d):\s*", "", title)
    t = re.sub(r"\s*\b(Stage \d+|Split \d+|Season Finals|Finals|Main Event|Masters|Playoffs|Kickoff|Championship)\b.*$", "", t)
    return t.strip().lower() or title.lower()


def pick_val_events(evs):
    picks = []
    for pat, n in ((r"^(Challengers 20\d\d|VCL \d\d):", VAL_CH_EVENTS), (r"^Game Changers 20\d\d:", VAL_GC_EVENTS)):
        seen = set()
        for e in evs:                       # vlr.gg lists completed events newest-first
            if e["status"] != "completed" or not re.search(pat, e["title"]) or _SKIP_EV.search(e["title"]):
                continue
            c = val_circuit(e["title"])
            if c in seen:
                continue
            seen.add(c)
            picks.append(dict(e, region=c))
            if len(seen) >= n:
                break
    return picks


def vlr_event_standings(ev):
    s = BeautifulSoup(get_html(ev["url"]), "lxml")
    tbl = s.select_one(".wf-ptable--standings")
    rows = []
    # every team linked on the event page (group tables, bracket, placements) -> rosters
    ev["team_ids"] = sorted({m.group(1) for a in s.select('a[href^="/team/"]')
                             for m in [re.match(r"^/team/(\d+)/", a.get("href") or "")] if m}, key=int)
    if not tbl:
        return rows
    for row in tbl.select(".row")[1:]:
        try:
            cells = row.select(".cell")
            team_a = row.select_one(".cell.mod-team a")
            if len(cells) < 3 or not team_a:
                continue
            name_div = team_a.select_one(".text-of") or team_a
            country = name_div.select_one(".ge-text-light")
            cname = country.get_text(strip=True) if country else ""
            if country:
                country.extract()
            rows.append({"place": re.sub(r"\s+", "", cells[0].get_text(" ", strip=True)),
                         "prize": cells[1].get_text(" ", strip=True),
                         "team": name_div.get_text(" ", strip=True), "country": cname,
                         "points": re.sub(r"\+\s+", "+", cells[3].get_text(" ", strip=True)) if len(cells) > 3 else "",
                         "note": cells[4].get_text(" ", strip=True) if len(cells) > 4 else "",
                         "url": VLR + team_a["href"] if team_a.get("href") else None})
        except Exception:
            continue
    return rows


def vlr_ts(day, tm):
    """'Sun, September 20, 2026' + '4:00 AM' (US Central) -> UTC ISO, or None."""
    try:
        d = datetime.strptime(f"{day} {tm}", "%a, %B %d, %Y %I:%M %p").replace(tzinfo=VLR_TZ)
        return d.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (ValueError, TypeError):
        return None


def parse_vlr_results(html, page):
    s = BeautifulSoup(html, "lxml")
    res = []
    for card in s.select(".wf-card"):
        lab = card.find_previous_sibling("div", class_="wf-label")
        day = re.sub(r"\s*(Today|Yesterday)$", "", lab.get_text(" ", strip=True)) if lab else ""
        for a in card.select("a.match-item"):
            try:
                teams = a.select(".match-item-vs-team")
                ev_div = a.select_one(".match-item-event")
                if len(teams) != 2 or not ev_div:
                    continue
                series = ev_div.select_one(".match-item-event-series")
                series_t = series.get_text(" ", strip=True) if series else ""
                if series:
                    series.extract()
                event = ev_div.get_text(" ", strip=True)

                def txt(x, sel):
                    el = x.select_one(sel)
                    return el.get_text(" ", strip=True) if el else ""
                t = [txt(x, ".match-item-vs-team-name") for x in teams]
                sc = [txt(x, ".match-item-vs-team-score") for x in teams]
                tm = txt(a, ".match-item-time")
                res.append({"date": day, "time": tm, "ts": vlr_ts(day, tm),
                            "team1": t[0], "score1": sc[0], "team2": t[1], "score2": sc[1],
                            "winner": 0 if "mod-winner" in teams[0].get("class", []) else
                                      (1 if "mod-winner" in teams[1].get("class", []) else None),
                            "event": event, "series": series_t, "url": VLR + a["href"], "page": page})
            except Exception:
                continue
    return res


def fetch_vlr(prev):
    prev = prev or {}
    out = {"events": [], "results": [], "sources": []}
    # events lists: Challengers (tier 61) and Game Changers (tier 63)
    evs, ev_fail = [], []
    for tier, label in ((61, "Challengers / VCL"), (63, "Game Changers")):
        url = f"{VLR}/events/?tier={tier}"
        try:
            e = vlr_events(tier, label)
            evs += e
            out["sources"].append(status(f"vlr.gg events: {label}", url, bool(e), len(e),
                                         reason=None if e else "no events parsed"))
            if not e:
                ev_fail.append(label)
        except Exception as ex:
            ev_fail.append(label)
            out["sources"].append(status(f"vlr.gg events: {label}", url, False, reason=f"request failed: {short_err(ex)}"))
    if len(ev_fail) == 2 and prev.get("event_list") is not None:
        out["event_list"] = copy.deepcopy(prev["event_list"])
        out["event_list_meta"] = mark_stale(prev.get("event_list_meta") or {"fetched_at": prev.get("fetched_at")})
        for s in out["sources"]:
            if s["source"].startswith("vlr.gg events:"):
                s.update(stale_status(s["source"], s["url"], s.get("reason", "failed"),
                                      out["event_list_meta"].get("fetched_at"), len(out["event_list"])))
    else:
        out["event_list"] = [e for e in evs if e["status"] != "completed"]  # ongoing + upcoming
        out["event_list_meta"] = {"fetched_at": now_iso(), "stale": False}

    # final standings: most recent completed official Challengers/VCL + Game Changers events
    picks = pick_val_events(evs)
    prev_ev = {e.get("url"): e for e in prev.get("events", []) if e.get("standings")}
    n_rows, n_stale = 0, 0
    VAL_REQ["events"] = 0
    for ev in picks:
        pe_ = prev_ev.get(ev["url"])
        if pe_ and pe_.get("team_ids") is not None and not pe_.get("stale"):
            out["events"].append({**pe_, **ev, "cached": True})        # completed event: final standings do not change
            n_rows += len(pe_.get("standings") or [])
            continue
        try:
            VAL_REQ["events"] += 1
            rows = vlr_event_standings(ev)
            out["events"].append({**ev, "standings": rows, "fetched_at": now_iso(),
                                  "status_note": "OK" if rows else "no final standings table on page"})
            n_rows += len(rows)
        except Exception as ex:
            p = prev_ev.get(ev["url"])
            if p:
                pe = mark_stale(p)
                pe["status_note"] = f"STALE: request failed ({short_err(ex)})"
                out["events"].append(pe)
                n_stale += 1
            else:
                out["events"].append({**ev, "standings": [], "fetched_at": now_iso(),
                                      "status_note": f"MISS: request failed: {short_err(ex)}"})
    if not picks and prev.get("events"):
        out["events"] = [mark_stale(e) for e in prev["events"]]
        n_stale = len(out["events"])
    surl = VLR + "/events"
    if n_stale:
        out["sources"].append(stale_status("vlr.gg event final standings", surl, f"{n_stale} event page(s) failed",
                                           min(e.get("fetched_at") or "" for e in out["events"] if e.get("stale")),
                                           sum(len(e.get("standings", [])) for e in out["events"])))
    else:
        out["sources"].append(status("vlr.gg event final standings", surl, n_rows > 0, n_rows,
                                     reason=None if n_rows else "no standings parsed"))

    # recent results (excluding international VCT + partner leagues).
    res, pages_ok, page_errs = [], 0, []
    for page in range(1, RESULT_PAGES + 1):
        url = f"{VLR}/matches/results" + ("" if page == 1 else f"/?page={page}")
        try:
            res += parse_vlr_results(get_html(url), page)
            pages_ok += 1
        except Exception as ex:
            page_errs.append(f"page {page}: {short_err(ex)}")
    seen, uniq = set(), []
    for m in res:
        if m["url"] not in seen:
            seen.add(m["url"])
            uniq.append(m)
    kinds = {}
    kept = []
    for m in uniq:
        k = vlr_excluded(m["event"])
        if k:
            kinds.setdefault(k, set()).add(m["event"])
            kinds[k + "_n"] = kinds.get(k + "_n", 0) + 1
        else:
            kept.append(m)
    url = f"{VLR}/matches/results"
    rname = f"vlr.gg recent results (pages 1-{RESULT_PAGES}, tier-2/GC)"
    if kept:
        out["results"] = kept[:RESULTS_KEEP]
        out["results_meta"] = {
            "fetched_at": now_iso(), "stale": False, "scanned": len(uniq), "pages": pages_ok,
            "excluded_international": kinds.get("international_n", 0),
            "excluded_partner": kinds.get("partner_n", 0),
            "excluded_events": sorted(kinds.get("international", set()) | kinds.get("partner", set())),
            "tz_note": "vlr.gg list times are US Central; converted to UTC in 'ts'"}
        out["sources"].append(status(rname, url, True, len(out["results"]),
                                     note=f"{len(uniq)} results scanned on {pages_ok} page(s); "
                                          f"excluded {kinds.get('international_n', 0)} international (Champions/Masters) "
                                          f"+ {kinds.get('partner_n', 0)} VCT partner-league"
                                          + (f"; errors: {'; '.join(page_errs)}" if page_errs else "")))
    elif prev.get("results"):
        out["results"] = copy.deepcopy(prev["results"])
        out["results_meta"] = mark_stale(prev.get("results_meta") or {"fetched_at": prev.get("fetched_at")})
        out["sources"].append(stale_status(rname, url, "; ".join(page_errs) or "no tier-2 results parsed",
                                           out["results_meta"].get("fetched_at"), len(out["results"])))
    else:
        out["sources"].append(status(rname, url, False, reason="no tier-2 results parsed"
                                     + (f" ({'; '.join(page_errs)})" if page_errs else "")))
    out["results_events"] = sorted({m["event"] for m in out["results"]})
    fetch_vlr_depth(out, prev)
    out["sources"].append(status("Valorant Premier (in-game Riot ladder)", "https://playvalorant.com/",
                                 False, reason="Premier standings live in the Riot client / Riot API (key required) - no public page; not fetched"))
    return out


def vlr_event_stats(ev):
    """Player stats table of a vlr.gg event (/event/stats/<id>): one row per player."""
    m = re.search(r"/event/(\d+)/", ev["url"])
    if not m:
        return []
    s = BeautifulSoup(get_html(f"{VLR}/event/stats/{m.group(1)}"), "lxml")
    rows = []
    for tr in s.select("table.st-table tbody tr"):
        try:
            a = tr.select_one('a[href^="/player/"]')
            nm = tr.select_one(".st-pl-name")
            if not a or not nm:
                continue
            pid = re.match(r"^/player/(\d+)/", a["href"])
            tag = tr.select_one(".st-pl-country")
            flag = tr.select_one("i.flag")
            cc = next((c[4:] for c in (flag.get("class") or []) if c.startswith("mod-")), "") if flag else ""

            def col(c):
                td = tr.select_one(f'td[data-col="{c}"]')
                return td.get_text(" ", strip=True) if td else ""
            agents = []
            for ag in tr.select(".st-agent"):
                img = ag.select_one("img")
                n = re.search(r"/agents/([a-z0-9_-]+)\.png", (img.get("src") or "") if img else "")
                if n:
                    agents.append(n.group(1))
            rnd = as_int(col("rnd"))
            if not rnd:
                continue
            rows.append({"name": norm(nm.get_text(" ", strip=True)), "pid": pid.group(1) if pid else None,
                         "tag": norm(tag.get_text(" ", strip=True)) if tag else "", "cc": cc.upper()[:2],
                         "agents": agents[:3], "maps": as_int(col("maps")), "rnd": rnd,
                         "rating": as_float(col("rating2")), "acs": as_float(col("acs")), "kd": as_float(col("kd")),
                         "kast": as_float(col("kast").rstrip("%")), "adr": as_float(col("adr")),
                         "hs": as_float(col("hsp").rstrip("%")), "k": as_int(col("k")), "d": as_int(col("d")),
                         "a": as_int(col("a"))})
        except Exception:
            continue
    return rows


def vlr_team(tid):
    """vlr.gg team page -> name, tag, country, active roster (players + staff)."""
    s = BeautifulSoup(get_html(f"{VLR}/team/{tid}"), "lxml")
    name = s.select_one(".team-header-name h1") or s.select_one(".team-header-name")
    tag = s.select_one(".team-header-tag")
    ctry = s.select_one(".team-header-country")
    roster = []
    for it in s.select(".team-roster-item"):
        a = it.select_one('a[href^="/player/"]')
        if not a:
            continue
        pm = re.match(r"^/player/(\d+)/", a["href"])
        alias = it.select_one(".team-roster-item-name-alias")
        role = it.select_one(".team-roster-item-name-role")
        nick = norm((alias or a).get_text(" ", strip=True))
        if nick:
            roster.append([nick, pm.group(1) if pm else None, norm(role.get_text(" ", strip=True)).lower() if role else ""])
    return {"id": str(tid), "name": norm(name.get_text(" ", strip=True)) if name else "",
            "tag": norm(tag.get_text(" ", strip=True)) if tag else "",
            "country": norm(ctry.get_text(" ", strip=True)) if ctry else "",
            "url": f"{VLR}/team/{tid}", "roster": roster, "fetched_at": now_iso()}


VAL_PCOLS = ("name", "pid", "tag", "cc", "agents", "maps", "rnd", "rating", "acs", "kd", "kast", "adr", "hs", "k", "d", "a", "ev", "team")


VETO_RE = re.compile(r"\b(ban|pick|remains)\b", re.I)


def parse_vlr_match(html):
    """vlr.gg match page -> {veto, maps:[{map, s1, s2, pick}]} (pick: 1/2 = team that picked the map, 0 = decider/unknown).
    Only what the page shows: the veto line is copied as written, unplayed maps are skipped."""
    s = BeautifulSoup(html, "lxml")
    veto = ""
    for n in s.select(".match-header-note"):
        t = norm(n.get_text(" ", strip=True))
        if VETO_RE.search(t) and ";" in t:
            veto = t[:300]
            break
    maps = []
    for g in s.select(".vm-stats-game"):
        if g.get("data-game-id") in (None, "", "all"):
            continue
        h = g.select_one(".vm-stats-game-header")
        if not h:
            continue
        sc = [norm(x.get_text(" ", strip=True)) for x in h.select(".score")]
        mn = h.select_one(".map-name") or h.select_one(".map")
        if len(sc) != 2 or not all(x.isdigit() for x in sc) or not mn:
            continue
        pk = mn.select_one(".picked")
        pick = 0
        if pk:
            cls = pk.get("class") or []
            pick = 1 if "mod-1" in cls else 2 if "mod-2" in cls else 0
            pk.extract()
        name = norm(re.sub(r"\s+", " ", mn.get_text(" ", strip=True)))
        name = re.sub(r"\s*\d+:\d+(:\d+)?\s*$", "", name).strip(" -")
        if not name:
            continue
        maps.append({"map": name[:20], "s1": int(sc[0]), "s2": int(sc[1]), "pick": pick})
    return {"veto": veto, "maps": maps[:5]}


def vlr_match_id(url):
    m = re.search(r"vlr\.gg/(\d+)/", url or "")
    return m.group(1) if m else None


def parse_vlr_upcoming(html):
    """vlr.gg /matches (upcoming + live) -> list like parse_vlr_results plus 'live'."""
    s = BeautifulSoup(html, "lxml")
    res = []
    for card in s.select(".wf-card"):
        lab = card.find_previous_sibling("div", class_="wf-label")
        day = re.sub(r"\s*(Today|Yesterday|Tomorrow)$", "", lab.get_text(" ", strip=True)) if lab else ""
        for a in card.select("a.match-item"):
            try:
                teams = a.select(".match-item-vs-team")
                ev_div = a.select_one(".match-item-event")
                if len(teams) != 2 or not ev_div:
                    continue
                series = ev_div.select_one(".match-item-event-series")
                series_t = series.get_text(" ", strip=True) if series else ""
                if series:
                    series.extract()
                st = a.select_one(".ml-status")
                stt = st.get_text(" ", strip=True).lower() if st else ""
                t = [(x.select_one(".match-item-vs-team-name") or x).get_text(" ", strip=True) for x in teams]
                tm = (a.select_one(".match-item-time") or a).get_text(" ", strip=True) if a.select_one(".match-item-time") else ""
                res.append({"ts": vlr_ts(day, tm), "team1": norm(t[0]), "team2": norm(t[1]),
                            "event": ev_div.get_text(" ", strip=True), "series": series_t,
                            "url": VLR + a["href"], "live": stt == "live"})
            except Exception:
                continue
    return res


def fetch_vlr_depth(out, prev):
    """v3.8: Valorant player stats (event stats pages), rosters (team pages) and upcoming
    matches. Completed events are cached (their stats never change); rosters are refreshed
    after VAL_TEAM_TTL_H hours, at most VAL_TEAM_REQ_MAX per run. Everything that fails keeps
    its last-good copy. Lazy data (all player rows + rosters) -> val.json via out["_val"]."""
    pv = PREV_VAL or {}
    cols = pv.get("player_cols") or list(VAL_PCOLS)
    prev_rows = {}
    for r_ in pv.get("players") or []:
        d_ = dict(zip(cols, r_))
        prev_rows.setdefault(d_.get("ev"), []).append(d_)
    prev_teams = dict(pv.get("teams") or {})
    # 1) player stats per tracked event
    rows, n_req, errs, n_cached, n_stale = [], 0, [], 0, 0
    for ev in out.get("events") or []:
        eid = (re.search(r"/event/(\d+)/", ev.get("url") or "") or [None, None])[1]
        if not eid:
            continue
        if ev.get("cached") and prev_rows.get(eid):
            rows += prev_rows[eid]
            n_cached += 1
            ev["n_players"] = len(prev_rows[eid])
            continue
        if n_req >= VAL_STATS_REQ_MAX:
            if prev_rows.get(eid):
                rows += prev_rows[eid]
                n_stale += 1
            continue
        try:
            n_req += 1
            got = vlr_event_stats(ev)
            for g in got:
                g["ev"] = eid
            rows += got
            ev["n_players"] = len(got)
        except Exception as ex:
            errs.append(f"event {eid}: {short_err(ex)}")
            if prev_rows.get(eid):
                rows += prev_rows[eid]
                n_stale += 1
    VAL_REQ["stats"] = n_req
    # 2) rosters for every team in the tracked events (cached, TTL, capped)
    want = []
    for ev in out.get("events") or []:
        for tid in ev.get("team_ids") or []:
            if tid not in want:
                want.append(tid)
    teams, t_req, t_err = {}, 0, []
    now = datetime.now(timezone.utc)

    def age_h(t):
        try:
            return (now - datetime.fromisoformat(t["fetched_at"])).total_seconds() / 3600
        except Exception:
            return 1e9
    for tid in sorted(want, key=lambda t: -age_h(prev_teams[t]) if t in prev_teams else -1e10):
        old = prev_teams.get(tid)
        if old and age_h(old) < VAL_TEAM_TTL_H:
            teams[tid] = old
            continue
        if t_req >= VAL_TEAM_REQ_MAX:
            if old:
                teams[tid] = old
            continue
        try:
            t_req += 1
            tm = vlr_team(tid)
            if tm["name"]:
                teams[tid] = tm
            elif old:
                teams[tid] = old
        except Exception as ex:
            t_err.append(f"team {tid}: {short_err(ex)}")
            if old:
                teams[tid] = old
    VAL_REQ["teams"] = t_req
    # player -> team: roster membership (player id), else the event tag of a team in that event
    by_pid = {}
    for tid, tm in teams.items():
        for nick, pid, role in tm.get("roster") or []:
            if pid and "coach" not in role and "manager" not in role and "analyst" not in role:
                by_pid.setdefault(pid, tid)
    ev_tag = {}
    for ev in out.get("events") or []:
        eid = (re.search(r"/event/(\d+)/", ev.get("url") or "") or [None, None])[1]
        for tid in ev.get("team_ids") or []:
            if teams.get(tid, {}).get("tag"):
                ev_tag[(eid, teams[tid]["tag"].lower())] = tid
    for r_ in rows:
        r_["team"] = ev_tag.get((r_.get("ev"), (r_.get("tag") or "").lower())) or by_pid.get(r_.get("pid"))
    # 3) aggregate per player across events (round-weighted averages)
    agg = {}
    for r_ in rows:
        k = r_.get("pid") or r_["name"].lower()
        a = agg.setdefault(k, {"name": r_["name"], "pid": r_.get("pid"), "cc": r_.get("cc"), "rnd": 0, "maps": 0,
                               "k": 0, "d": 0, "a": 0, "_w": {}, "agents": {}, "events": [], "team": None, "tag": "", "_tagr": 0})
        n = r_["rnd"]
        a["rnd"] += n
        a["maps"] += r_.get("maps") or 0
        for f in ("k", "d", "a"):
            a[f] += r_.get(f) or 0
        for f in ("rating", "acs", "kast", "adr", "hs"):
            a["_w"][f] = a["_w"].get(f, 0) + (r_.get(f) or 0) * n
        for i, ag in enumerate(r_.get("agents") or []):
            a["agents"][ag] = a["agents"].get(ag, 0) + n * (3 - i)
        a["events"].append(r_.get("ev"))
        if r_.get("team") and not a["team"]:
            a["team"] = r_["team"]
        if n > a["_tagr"] and r_.get("tag"):
            a["tag"], a["_tagr"] = r_["tag"], n
    players = []
    for a in agg.values():
        n = a["rnd"] or 1
        p = {k: v for k, v in a.items() if not k.startswith("_") and k != "agents"}
        for f, v in a["_w"].items():
            p[f] = round(v / n, 2 if f == "rating" else 1)
        p["kd"] = round(a["k"] / a["d"], 2) if a["d"] else None
        p["agents"] = [x for x, _ in sorted(a["agents"].items(), key=lambda kv: -kv[1])[:3]]
        players.append(p)
    ranked = sorted((p for p in players if p["rnd"] >= VAL_MIN_RND), key=lambda p: (p.get("rating") or 0, p.get("acs") or 0), reverse=True)
    for i, p in enumerate(ranked):
        p["rank"] = i + 1
    tname = {tid: tm.get("name") for tid, tm in teams.items()}
    out["top_players"] = [dict(p, team_name=tname.get(p.get("team"))) for p in ranked[:50]]
    out["top_players_meta"] = {"fetched_at": now_iso(), "pool": len(ranked), "total": len(players),
                               "min_rnd": VAL_MIN_RND, "events": sum(1 for e in out.get("events") or [] if e.get("n_players")),
                               "stale": bool(n_stale)}
    for ev in out.get("events") or []:
        eid = (re.search(r"/event/(\d+)/", ev.get("url") or "") or [None, None])[1]
        evr = sorted((r_ for r_ in rows if r_.get("ev") == eid and r_["rnd"] >= 40), key=lambda r_: r_.get("rating") or 0, reverse=True)
        ev["top_players"] = [{k: r_.get(k) for k in ("name", "pid", "tag", "rnd", "rating", "acs", "kd", "adr", "team")} for r_ in evr[:5]]
        ev.pop("cached", None)
    # 4) upcoming / live tier-2 matches (1 request)
    url = f"{VLR}/matches"
    try:
        up = [m for m in parse_vlr_upcoming(get_html(url)) if not vlr_excluded(m["event"])]
        out["upcoming"] = up[:60]
        out["upcoming_meta"] = {"fetched_at": now_iso(), "stale": False}
        out["sources"].append(status("vlr.gg upcoming matches (tier-2/GC)", url, True, len(up)))
    except Exception as ex:
        if prev.get("upcoming") is not None:
            out["upcoming"] = copy.deepcopy(prev["upcoming"])
            out["upcoming_meta"] = mark_stale(prev.get("upcoming_meta") or {"fetched_at": prev.get("fetched_at")})
            out["sources"].append(stale_status("vlr.gg upcoming matches (tier-2/GC)", url, short_err(ex),
                                               out["upcoming_meta"].get("fetched_at"), len(out["upcoming"])))
        else:
            out["upcoming"] = []
            out["sources"].append(status("vlr.gg upcoming matches (tier-2/GC)", url, False, reason=f"request failed: {short_err(ex)}"))
    # sources
    sname = "vlr.gg event player stats"
    if rows:
        out["sources"].append(status(sname, VLR + "/event/stats/<id>", True, len(players),
                                     note=f"{len(rows)} event lines, {len(players)} players; {n_req} request(s), {n_cached} event(s) cached"
                                          + (f", {n_stale} reused" if n_stale else "") + (f"; errors: {'; '.join(errs)}" if errs else "")))
    else:
        out["sources"].append(status(sname, VLR + "/event/stats/<id>", False, reason="; ".join(errs) or "no player stats parsed"))
    out["sources"].append(status("vlr.gg team pages (rosters)", VLR + "/team/<id>", bool(teams), len(teams),
                                 note=f"{t_req} request(s); {len(want)} teams in tracked events" + (f"; errors: {'; '.join(t_err)}" if t_err else ""),
                                 reason=None if teams else ("; ".join(t_err) or "no teams")))
    # 5) v4.4 match pages for the newest tracked results (veto line + map scores), capped and cached
    prev_m = pv.get("matches") if isinstance(pv.get("matches"), dict) else {}
    mres, m_req, m_err = {}, 0, []
    for r_ in out.get("results") or []:
        mid = vlr_match_id(r_.get("url"))
        if not mid or mid in mres:
            continue
        if mid in prev_m:
            mres[mid] = prev_m[mid]
            continue
        if m_req >= VAL_MATCH_REQ_MAX:
            continue
        try:
            m_req += 1
            got = parse_vlr_match(get_html(r_["url"]))
            if got["maps"] or got["veto"]:
                got["fetched_at"] = now_iso()
                mres[mid] = got
        except Exception as ex:
            m_err.append(f"match {mid}: {short_err(ex)}")
    VAL_REQ["matches"] = m_req
    n_res = len([1 for r_ in out.get("results") or [] if vlr_match_id(r_.get("url"))])
    out["sources"].append(status("vlr.gg match pages (veto, map scores)", VLR + "/<match id>", bool(mres) or not n_res, len(mres),
                                 note=f"{m_req} request(s), {len(mres)} of {n_res} results have match details (cached)" + (f"; errors: {'; '.join(m_err[:3])}" if m_err else ""),
                                 reason=None if (mres or not n_res) else ("; ".join(m_err[:3]) or "no match details parsed")))
    out["_val"] = {"player_cols": list(VAL_PCOLS), "players": [[r_.get(c) for c in VAL_PCOLS] for r_ in rows], "matches": mres,
                   "agg": [[p.get(c) for c in ("name", "pid", "cc", "team", "tag", "rnd", "maps", "rating", "acs", "kd", "kast", "adr", "hs", "k", "d", "a", "rank")] + [p.get("agents"), p.get("events")] for p in players],
                   "agg_cols": ["name", "pid", "cc", "team", "tag", "rnd", "maps", "rating", "acs", "kd", "kast", "adr", "hs", "k", "d", "a", "rank", "agents", "events"],
                   "teams": teams}


# ---------------------------------------------------------------- Raider.IO
RIO = "https://raider.io/api/v1"


def rio_page(slug, region):
    """Public Raider.IO rankings page, e.g. https://raider.io/the-venomous-abyss/rankings/us/mythic"""
    return f"https://raider.io/{slug}/rankings/{region}/mythic"


def fetch_raiderio(prev):
    prev = prev or {}
    out = {"raid": None, "rankings": {}, "rankings_meta": {}, "sources": []}
    exp_id, static, err = None, None, None
    for eid in (13, 12, 11, 10):  # newest expansion first; unsupported ids return HTTP 400
        url = f"{RIO}/raiding/static-data?expansion_id={eid}"
        try:
            r = get(url)
        except Exception as ex:
            err = short_err(ex)
            break
        if r.status_code == 200:
            try:
                exp_id, static = eid, r.json()
                if not static.get("raids"):
                    static = None
                    continue
            except ValueError:
                static = None
                continue
            break
    if not static:
        reason = f"request failed: {err}" if err else "no supported expansion_id found"
        if prev.get("raid"):
            out["raid"] = mark_stale(prev["raid"])
            out["rankings"] = copy.deepcopy(prev.get("rankings", {}))
            out["rankings_meta"] = {k: mark_stale(v) for k, v in (prev.get("rankings_meta") or {}).items()}
            out["sources"].append(stale_status("Raider.IO static-data", f"{RIO}/raiding/static-data", reason,
                                               prev["raid"].get("fetched_at") or prev.get("fetched_at"),
                                               sum(len(v) for v in out["rankings"].values())))
        else:
            out["sources"].append(status("Raider.IO static-data", f"{RIO}/raiding/static-data", False, reason=reason))
        return out
    now = datetime.now(timezone.utc)

    def ts(x):
        try:
            return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        except ValueError:
            return None
    raids = [r for r in static["raids"] if r.get("slug") and r.get("encounters")]
    active = [r for r in raids if (r.get("starts") or {}).get("us") and ts(r["starts"]["us"]) and ts(r["starts"]["us"]) <= now
              and (not (r.get("ends") or {}).get("us") or not ts(r["ends"]["us"]) or now < ts(r["ends"]["us"]))]
    pool = active or raids
    raid = max(pool, key=lambda r: (len(r["encounters"]), (r.get("starts") or {}).get("us") or ""))
    out["raid"] = {"slug": raid["slug"], "name": raid.get("name", raid["slug"]), "expansion_id": exp_id,
                   "bosses": [e.get("name", "?") for e in raid["encounters"]],
                   "boss_slugs": [e.get("slug") for e in raid["encounters"]],
                   "starts_us": (raid.get("starts") or {}).get("us"), "fetched_at": now_iso()}
    out["sources"].append(status("Raider.IO static-data", f"{RIO}/raiding/static-data?expansion_id={exp_id}",
                                 True, len(raids), page=rio_page(raid["slug"], "world"), note=f"current raid auto-selected: {out['raid']['name']} ({raid['slug']})"))
    nboss = len(raid["encounters"])
    boss_slugs = [e.get("slug") for e in raid["encounters"]]
    same_raid = (prev.get("raid") or {}).get("slug") == raid["slug"]
    for region in ("us", "eu"):
        url = f"{RIO}/raiding/raid-rankings?raid={raid['slug']}&difficulty=mythic&region={region}"
        name = f"Raider.IO mythic raid rankings ({region.upper()})"
        try:
            rows = []
            for g in get_json(url).get("raidRankings", []):
                try:
                    kills = g.get("encountersDefeated") or []
                    last = max((k.get("firstDefeated") or "" for k in kills), default="") or None
                    gd = g["guild"]
                    first = {k.get("slug"): k.get("firstDefeated") for k in kills if k.get("slug")}
                    kill_dates = [(first.get(sl) or "").replace(".000Z", "Z") or None for sl in boss_slugs]
                    rows.append({"rank": g["rank"], "guild": norm(gd["name"]),
                                 "realm": norm((gd.get("realm") or {}).get("name", "")),
                                 "realm_slug": (gd.get("realm") or {}).get("slug") or slug_txt((gd.get("realm") or {}).get("name", "")),
                                 "faction": gd.get("faction"), "progress": f"{len(kills)}/{nboss} M",
                                 "kills": len(kills), "last_first_kill": last, "kill_dates": kill_dates,
                                 "url": "https://raider.io" + gd["path"] if gd.get("path") else None})
                except Exception:
                    continue
            if not rows:
                raise ValueError("no rankings rows in response")
            out["rankings"][region] = rows
            out["rankings_meta"][region] = {"fetched_at": now_iso(), "stale": False}
            out["sources"].append(status(name, url, True, len(rows), page=rio_page(raid["slug"], region)))
        except Exception as ex:
            p = (prev.get("rankings") or {}).get(region)
            if same_raid and p:
                out["rankings"][region] = copy.deepcopy(p)
                out["rankings_meta"][region] = mark_stale((prev.get("rankings_meta") or {}).get(region)
                                                          or {"fetched_at": prev.get("fetched_at")})
                out["sources"].append(stale_status(name, url, f"request failed: {short_err(ex)}",
                                                   out["rankings_meta"][region].get("fetched_at"), len(p),
                                                   page=rio_page(raid["slug"], region)))
            else:
                out["sources"].append(status(name, url, False, reason=f"request failed: {short_err(ex)}"))
    return out


# ---------------------------------------------------------------- News RSS
FEEDS = [  # (name, feed URL, tag, public site page)
    ("HLTV", "https://www.hltv.org/rss/news", "CS", "https://www.hltv.org/"),
    ("vlr.gg", "https://www.vlr.gg/rss", "VAL", "https://www.vlr.gg/news"),
    ("Dexerto Esports", "https://www.dexerto.com/esports/feed/", "ESPORTS", "https://www.dexerto.com/esports/"),
    ("Dot Esports", "https://dotesports.com/feed", "ESPORTS", "https://dotesports.com/"),
    ("Esports Insider", "https://esportsinsider.com/feed", "ESPORTS", "https://esportsinsider.com/"),
    ("Wowhead", "https://www.wowhead.com/news/rss/all", "WOW", "https://www.wowhead.com/news"),
]
PER_FEED = 15


def entry_date(e):
    for k in ("published_parsed", "updated_parsed"):
        if e.get(k):
            try:
                return datetime.fromtimestamp(calendar.timegm(e[k]), timezone.utc).isoformat(timespec="seconds")
            except (TypeError, ValueError, OverflowError):
                pass
    return None


def fetch_news(prev):
    prev = prev or {}
    out = {"items": [], "sources": []}
    prev_items = prev.get("items") or []
    for name, url, tag, page in FEEDS:
        try:
            r = get(url)
            ctype = r.headers.get("content-type", "")
            if r.status_code != 200:
                if r.status_code == 403:
                    cf = "Cloudflare bot challenge" if ("Just a moment" in r.text[:2000] or "cf-" in r.text[:3000]) else "blocked"
                    raise RuntimeError(f"HTTP 403 ({cf}) for non-browser requests - not fetched")
                raise RuntimeError(f"HTTP {r.status_code} - not fetched")
            f = feedparser.parse(r.content)
            if not f.entries:
                why = "URL returns an HTML page, not an RSS feed" if "html" in ctype else "feed parsed with 0 entries"
                raise RuntimeError(f"{why} - no items")
            n, ts = 0, now_iso()
            for e in f.entries:
                if n >= PER_FEED:
                    break
                td = e.get("title_detail") or {}
                raw = e.get("title", "")
                title = strip_html(raw) if "html" in (td.get("type") or "") else norm(raw)
                link = http_url(e.get("link"))
                if not title or not link:
                    continue
                out["items"].append({"title": title, "source": name, "tag": tag, "date": entry_date(e),
                                     "url": link, "fetched_at": ts})
                n += 1
            if not n:
                raise RuntimeError("feed entries had no usable title/link")
            out["sources"].append(status(name, url, True, n, page=page))
        except Exception as ex:
            reason = short_err(ex) if isinstance(ex, RuntimeError) else f"request failed: {short_err(ex)}"
            old = [dict(i, stale=True) for i in prev_items if i.get("source") == name]
            if old:
                out["items"] += old
                out["sources"].append(stale_status(name, url, reason, min(i.get("fetched_at") or "" for i in old),
                                                   len(old), page=page))
            else:
                out["sources"].append(status(name, url, False, reason=reason, page=page))
    seen, uniq = set(), []
    for i in out["items"]:
        if i["url"] not in seen:
            seen.add(i["url"])
            uniq.append(i)
    uniq.sort(key=lambda x: x["date"] or "", reverse=True)
    out["items"] = uniq
    return out


# ---------------------------------------------------------------- main
SECTIONS = (("cs", fetch_faceit), ("valorant", fetch_vlr), ("wow", fetch_raiderio), ("news", fetch_news))


def load_prev(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def write_atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    return tmp


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Fetch public Esports Scoreboard data into data.json + data.js.")
    ap.add_argument("--out", metavar="DIR", default=HERE,
                    help="output folder (default: next to this script). e.g. --out dist")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    out_dir = os.path.abspath(args.out)
    if not os.path.isdir(out_dir):
        print(f"[fragnet] output folder does not exist: {out_dir}", file=sys.stderr)
        return 2
    out_json = os.path.join(out_dir, "data.json")
    out_js = os.path.join(out_dir, "data.js")
    prev = load_prev(out_json)
    global PREV_EXTRA
    PREV_EXTRA = load_prev(os.path.join(out_dir, "teams.json"))
    global PREV_VAL
    PREV_VAL = load_prev(os.path.join(out_dir, "val.json"))
    data = {"fetched_at": now_iso(), "generator": GENERATOR, "display_tz": "America/Los_Angeles"}
    for key, fn in SECTIONS:
        print(f"[fragnet] fetching {key} ...", flush=True)
        p = prev.get(key) if isinstance(prev.get(key), dict) else {}
        try:
            data[key] = fn(p)
            data[key]["fetched_at"] = now_iso()
        except Exception as ex:  # never fake - keep last good section, or record the failure
            reason = f"fetcher crashed: {type(ex).__name__}: {short_err(ex)}"
            if p and any(s.get("status") in ("OK", "STALE") for s in p.get("sources", [])):
                sec = copy.deepcopy(p)
                for s in sec.get("sources", []):
                    if s.get("status") == "OK":
                        s.update(stale_status(s["source"], s.get("url", ""), reason,
                                              s.get("fetched_at"), s.get("count", 0)))
                sec["stale"] = True
                data[key] = sec
            else:
                data[key] = {"sources": [status(key, "", False, reason=reason)], "fetched_at": now_iso()}
    data["status"] = [s for k, _ in SECTIONS for s in data[k].get("sources", [])]
    # lazy side file for team pages beyond the top 20: rosters + all listed matches.
    # Only replaced when this run produced something (a failed run keeps the previous file).
    extra = (data.get("cs") or {}).pop("_extra", None) or {}
    if extra.get("rosters") or extra.get("matches") or extra.get("upcoming") or extra.get("players"):
        extra = {"fetched_at": now_iso(), "player_cols": list(PLAYER_ROW), **extra}
        tblob = json.dumps(extra, ensure_ascii=False, separators=(",", ":"))
        t3 = write_atomic(os.path.join(out_dir, "teams.json"), tblob + "\n")
        t4 = write_atomic(os.path.join(out_dir, "teams.js"), "window.FRAGNET_TEAMS = " + tblob.replace("</", "<\\/") + ";\n")
        os.replace(t3, os.path.join(out_dir, "teams.json"))
        os.replace(t4, os.path.join(out_dir, "teams.js"))
        print(f"[fragnet] teams.json: {len(extra.get('rosters', {}))} rosters, {len(extra.get('matches', []))} + "
              f"{len(extra.get('upcoming', []))} extra matches, {len(extra.get('players', []))} player stat rows")
    # lazy Valorant side file (v3.8): every event player line, per-player totals, rosters
    vx = (data.get("valorant") or {}).pop("_val", None) or {}
    if vx.get("players") or vx.get("teams"):
        vx = {"fetched_at": now_iso(), **vx}
        vblob = json.dumps(vx, ensure_ascii=False, separators=(",", ":"))
        t5 = write_atomic(os.path.join(out_dir, "val.json"), vblob + "\n")
        t6 = write_atomic(os.path.join(out_dir, "val.js"), "window.FRAGNET_VAL = " + vblob.replace("</", "<\\/") + ";\n")
        os.replace(t5, os.path.join(out_dir, "val.json"))
        os.replace(t6, os.path.join(out_dir, "val.js"))
        print(f"[fragnet] val.json: {len(vx.get('players', []))} event player lines, {len(vx.get('agg', []))} players, {len(vx.get('teams', {}))} rosters")
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # write both files from the same serialized object, then swap them in
    t1 = write_atomic(out_json, blob + "\n")   # compact: smaller page weight (pipe through `python -m json.tool` to read)
    t2 = write_atomic(out_js, "window.FRAGNET_DATA = " + blob.replace("</", "<\\/") + ";\n")
    os.replace(t1, out_json)
    os.replace(t2, out_js)
    n = {"OK": 0, "STALE": 0, "MISS": 0}
    for s in data["status"]:
        n[s["status"]] = n.get(s["status"], 0) + 1
        print(f"  {s['status']:5} {s['count']:>4}  {s['source']}" + (f"  -- {s['reason']}" if s.get("reason") else ""))
    print(f"[fragnet] {n['OK']} OK / {n['STALE']} STALE / {n['MISS']} MISS -> {out_json}, {out_js}")
    return 0 if n["OK"] or n["STALE"] else 1


if __name__ == "__main__":
    sys.exit(main())
