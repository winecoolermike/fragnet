#!/usr/bin/env python3
"""FragNet data fetcher (v3.3).

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
GENERATOR = "FragNet fetch_data.py v3.3"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 FragNet/3.3 (hobby tracker)")
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
        wait = DELAY - (time.monotonic() - _last_hit.get(host, 0))
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
STANDINGS_LIMIT = 20
PLAYER_PAGE_SIZE = 100
PLAYER_MAX_PAGES = 5      # conferences have ~100-250 players; stop early when a page is short
TOP_PLAYERS = 15
MIN_ROUNDS = 20
# Roster pages (championship subscription, public): limit=20 per page. Cap total
# requests so a slow FACEIT day cannot blow the Actions 10-minute timeout.
ROSTER_PAGE = 20
ROSTER_MAX_REQ = 60          # total GETs for rosters across all conferences
ROSTER_MAX_PAGES_PER_CONF = 10   # 200 teams per conference at most
# Official FACEIT Data API (open.faceit.com) - NOT used unless a key is present.
# A later step will store FACEIT_API_KEY as a GitHub Actions secret; until then
# match results stay MISS. No sign-up / no key creation happens in this script.
FACEIT_API_KEY = (os.environ.get("FACEIT_API_KEY") or "").strip() or None
FACEIT_DATA_API = "https://open.faceit.com/data/v4"


def fetch_faceit(prev):
    prev = prev or {}
    out = {"league": "ESEA League (FACEIT)", "page": ESEA_PAGE, "season": None,
           "divisions": [], "top_players": [], "players": [], "top_players_meta": None, "matches": [], "sources": []}
    if FACEIT_API_KEY:
        # Placeholder only: wire official Data API calls here (Authorization: Bearer).
        # No endpoints are hit yet; match-result parsing lands in a later change.
        out["sources"].append(status(
            "FACEIT Data API (open.faceit.com/data/v4)", FACEIT_DATA_API,
            False, reason="FACEIT_API_KEY is set, but Data API match-result calls are not implemented yet - not fetched"))
    else:
        out["sources"].append(status(
            "FACEIT Data API (open.faceit.com/data/v4)", "https://docs.faceit.com/docs/data-api/data",
            False, reason="FACEIT Data API requires an API key (set FACEIT_API_KEY to enable later) - not fetched (no sign-up per rules)"))

    def reuse_everything(name, url, reason):
        """Seasons/tree failed: keep the previous season data, flagged stale."""
        if prev.get("season"):
            for k in ("season", "all_tiers", "top_players_meta"):
                if prev.get(k) is not None:
                    out[k] = mark_stale(prev[k])
            out["divisions"] = [mark_stale(d) for d in prev.get("divisions", [])]
            out["top_players"] = copy.deepcopy(prev.get("top_players", []))
            out["players"] = copy.deepcopy(prev.get("players", []))
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
            surl = (f"{FACEIT_WEB}/api/team-leagues/v2/standings?entityId={stage['id']}"
                    f"&entityType=stage&userId=&offset=0&limit={STANDINGS_LIMIT}")
            try:
                rows = get_json(surl)["payload"]["standings"]
                # team -> conference (only needed when the stage has >1 conference)
                conf_of = {}
                if len(confs) > 1:
                    for c in confs:
                        try:
                            cu = (f"{FACEIT_WEB}/api/team-leagues/v2/standings?entityId={c['id']}"
                                  f"&entityType=conference&userId=&offset=0&limit=100")
                            for t in get_json(cu)["payload"]["standings"]:
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
                        entry["teams"].append({
                            "id": tid, "rank": rank, "name": norm(t.get("name")), "tag": norm(t.get("nickname")),
                            "country": (t.get("country_code") or "").upper()[:3],
                            "conf": conf_of.get(tid),
                            "w": as_int(t.get("won")), "l": as_int(t.get("lost")), "t": as_int(t.get("tied")),
                            "pts": as_int(t.get("points")),
                            "rounds": f"{as_int(tb.get('rounds_won'))}-{as_int(tb.get('rounds_lost'))}",
                            "dq": bool(t.get("is_disqualified", False)),
                            "roster": [],
                            "url": f"{FACEIT_WEB}/en/teams/{tid}" if tid else None})
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
            if dv["name"] == "Advanced":
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
    by_id = {t["id"]: t for d in out["divisions"] for t in d.get("teams", []) if t.get("id")}
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

    # 3) top players (Advanced divisions) from public competition stats JSON (paged)
    players, errs = [], []
    for region, div, cid, link in stat_champs:
        for page in range(PLAYER_MAX_PAGES):
            url = (f"{FACEIT_WEB}/api/stats/v1/competitions/{cid}/players"
                   f"?page={page}&size={PLAYER_PAGE_SIZE}&sort=stats.m2,desc")
            try:
                batch = get_json(url)["payload"].get("players") or []
            except Exception as e:
                errs.append(f"{region} {div} page {page}: {short_err(e)}")
                break
            for p in batch:
                try:
                    st = p.get("stats") or {}
                    rounds = as_int(st.get("m8"))
                    if rounds < MIN_ROUNDS or not p.get("nickname"):
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
    players.sort(key=lambda p: (p["kd"], p["adr"]), reverse=True)
    # attach team from the public rosters (case-insensitive nick match)
    for p in players:
        t = nick_team.get((p.get("nick") or "").lower())
        if t:
            p["team_id"] = t.get("id")
            p["team"] = t.get("name")
    purl = f"{FACEIT_WEB}/api/stats/v1/competitions/<championship>/players"
    pname = "FACEIT ESEA Advanced player stats (public web JSON)"
    ppage = stat_champs[0][3] if stat_champs else f"{season_page}/stats"
    if players:
        out["players"] = [dict(p, rank=i + 1) for i, p in enumerate(players)]   # whole ranked pool (detail pages)
        out["stats_links"] = {rg_: lk for rg_, _dv, _cid, lk in stat_champs}
        out["top_players"] = out["players"][:TOP_PLAYERS]
        out["top_players_meta"] = {"fetched_at": now_iso(), "stale": False, "pool": len(players),
                                   "min_rounds": MIN_ROUNDS}
        out["sources"].append(status(pname, purl, True, len(out["top_players"]), page=ppage,
                                     note=f"{len(players)} players with >= {MIN_ROUNDS} rounds ranked"
                                          + (f"; errors: {'; '.join(errs)}" if errs else "")))
    elif same_season and prev.get("top_players"):
        out["top_players"] = copy.deepcopy(prev["top_players"])
        out["players"] = copy.deepcopy(prev.get("players", []))
        out["top_players_meta"] = mark_stale(prev.get("top_players_meta") or {"fetched_at": prev.get("fetched_at")})
        out["sources"].append(stale_status(pname, purl, "; ".join(errs) or "no player stats returned",
                                           out["top_players_meta"].get("fetched_at"), len(out["top_players"]), page=ppage))
    else:
        out["sources"].append(status(pname, purl, False, page=ppage,
                                     reason="; ".join(errs) or f"no players with >= {MIN_ROUNDS} rounds yet"))

    # 4) match results - public web match-list is login-walled; official Data API
    #    needs FACEIT_API_KEY (not called yet - placeholder only when the key is set).
    if FACEIT_API_KEY:
        out["sources"].append(status(
            "FACEIT ESEA match results", f"{FACEIT_DATA_API}/matches", False, page=season_page,
            reason="FACEIT_API_KEY is set, but Data API match-result calls are not implemented yet - not fetched"))
    elif stat_champs:
        cid = stat_champs[0][2]
        url = f"{FACEIT_WEB}/api/match/v3/match?entityType=championship&entityId={cid}&offset=0&limit=10"
        try:
            r = get(url)
            if r.status_code in (401, 403):
                reason = (f"FACEIT match list endpoint returns HTTP {r.status_code} without login - "
                          "not fetched (no sign-in per rules; set FACEIT_API_KEY later for the Data API)")
            else:
                reason = f"HTTP {r.status_code}; parser not implemented for this response - not shown"
            out["sources"].append(status("FACEIT ESEA match results", url, False, reason=reason, page=season_page))
        except Exception as e:
            out["sources"].append(status("FACEIT ESEA match results", url, False, reason=f"request failed: {short_err(e)}"))
    return out


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
# international, but FragNet tracks Challengers / Game Changers / tier-2, so they
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


def vlr_event_standings(ev):
    s = BeautifulSoup(get_html(ev["url"]), "lxml")
    tbl = s.select_one(".wf-ptable--standings")
    rows = []
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
    picks = []
    skip = re.compile(r"Cash Cup|Last Chance|Qualifier|Showmatch", re.I)
    for pat, n in ((r"^(Challengers 20\d\d|VCL \d\d):", 2), (r"^Game Changers 20\d\d:", 2)):
        cands = [e for e in evs if e["status"] == "completed" and re.search(pat, e["title"]) and not skip.search(e["title"])]
        picks += cands[:n]   # vlr.gg lists completed events newest-first
    prev_ev = {e.get("url"): e for e in prev.get("events", []) if e.get("standings")}
    n_rows, n_stale = 0, 0
    for ev in picks:
        try:
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
    out["sources"].append(status("Valorant Premier (in-game Riot ladder)", "https://playvalorant.com/",
                                 False, reason="Premier standings live in the Riot client / Riot API (key required) - no public page; not fetched"))
    return out


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
    ap = argparse.ArgumentParser(description="Fetch public FragNet data into data.json + data.js.")
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
