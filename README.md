# FragNet v3.8 - esports league tracker (2007 portal style)

Static site (index.html + style.css + app.js + data.json/data.js). The look recreates
the *style* of mid-2000s esports portals (Gotfrag circa 2007, studied via the Wayback
Machine): black page, 1100px container, grey side panes, white centre column, gradient
title bars, beige news list, phpBB-style forum tables. No Gotfrag logo, images or name
are used; branding is the FragNet text logo and favicon.svg.

## Run it

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python fetch_data.py      # writes data.json + data.js (~40 polite requests, ~45 s)
    python3 -m http.server 8080         # open http://localhost:8080/

## Publish folder (dist/)
    .venv/bin/python build_dist.py              # (re)builds dist/ with ONLY the live files
    .venv/bin/python build_dist.py --zip        # ... and writes fragnet-v3.2.zip from dist/ only
    .venv/bin/python fetch_data.py --out dist   # refresh data straight into dist/
dist/ = index.html (incl. the About page), style.css, app.js, favicon.svg, data.json,
data.js, fonts/ (woff2 + licences). build_dist.py refuses to finish if shots, tests,
backups, scripts, docs or terms listed in .banned-terms (local, untracked) end up in dist/, or if data.js != data.json.
`--out DIR` also reads the previous data.json in DIR as the last-good (STALE) source.

Opening index.html directly (file://) also works: the page then loads data.js, which
holds exactly the same JSON as data.json. All paths are relative, so the folder can be
served from any sub-path. See HOSTING.md for static hosting + a scheduled fetch.

Refresh: re-run fetch_data.py (cron every 30-60 min is plenty). Exit code is 0 when at
least one source is OK/STALE, 1 when everything failed.

## Data status: OK / STALE / MISS
- **OK** - fetched and parsed in the latest run.
- **STALE** - the latest run failed for that source, so the last good data from an
  earlier run is kept with its own `fetched_at` timestamp and flagged on the page
  (amber STALE badge + "showing last good data from ..."). Other sources still update.
- **MISS** - not fetched and no earlier good data; the reason is shown. Nothing is ever
  invented or filled in.

Known permanent MISS (no login / keys / scraping around blocks, by design):
- Valorant Premier - only in the Riot client / Riot API (key required).
- HLTV RSS - Cloudflare bot challenge (HTTP 403) for non-browser requests.
- Dot Esports - the feed URL redirects to the HTML homepage (no RSS).

## Sources (public pages / unauthenticated endpoints only)
- **FACEIT ESEA League** public web JSON: current season (Season 59: Oct 3 - Dec 20 2026 PT,
  team count, prize pool, map pool), season tree, stage standings (top 20) for EU/NA
  Advanced, Main, Intermediate, conference membership, and player season stats for every
  tracked division and conference (v3.7.2; 100 per request, ~35 requests). Every player with
  >= 1 round is kept; rankings (top 15 overall Advanced, top 10 per division) need 20 rounds.
  Ranked Advanced players are inline in data.json, all other players are compact rows in the
  lazy teams.json ("players", columns in "player_cols").
  Standings are the FACEIT *stage* table (conferences ranked together, exactly as the
  FACEIT standings page shows them); columns are W, L, Pts (3 per win), rounds won-lost.
- **vlr.gg**: Challengers (tier 61) and Game Changers (tier 63) event lists, final
  standings of the 2 most recent completed official Challengers/VCL and 2 Game Changers
  events, and /matches/results pages 1-3. Results from international events
  (Valorant Champions / Masters) are excluded; tier-1 VCT partner leagues
  ("VCT 2026: Americas Stage 2" etc.) are excluded too because FragNet tracks tier 2 -
  set `EXCLUDE_VCT_PARTNER_LEAGUES = False` in fetch_data.py to show them. Challengers
  events whose name contains "Masters" (e.g. "LATAM North ACE Masters") are kept.
  vlr.gg lists times in US Central for anonymous visitors; the fetcher converts them
  to UTC (`ts`) and the page shows Pacific Time.
- **Raider.IO** public API: current raid auto-detected (The Venomous Abyss), Mythic
  progress rankings top 50 for US and EU.
- **RSS**: vlr.gg, Dexerto esports, Esports Insider, Wowhead (15 newest each).

Requests: 1.2 s minimum gap per host, 10 s connect / 25 s read timeout, one retry on
timeouts / 429 / 5xx, identifying User-Agent ("FragNet/3.3 (hobby tracker)").
Only http(s) links are stored and rendered; all scraped text is HTML-escaped by app.js.

## Routes (hash, linkable)
`#home`, `#cs2` / `#cs2/<eu|na>-<advanced|main|intermediate>` (e.g. `#cs2/na-main`),
`#cs2/players`, `#cs2/results`, `#valorant` / `#valorant/results[/pN]`,
`#valorant/calendar`, `#valorant/event-1..4`, `#wow/<us|eu>[/pN]`,
`#news/<all|wow|val|esports>[/pN]`, `#forums`, `#forums/f/<cs2|valorant|wow|general>`,
`#forums/t/<id>`, `#search/<query>`, `#about`, `#status-box` (front page + data status),
detail pages `#team/cs2/<faceit-team-id>`, `#player/cs2/<faceit-nickname>`, `#team/val/<name-slug>`,
`#guild/<us|eu>/<realm-slug>/<guild-name>` (unknown ids show an honest "not tracked" page).
Long lists are paged 25 per page. Unknown routes fall back to a sensible default view.

## Detail pages (v3.3)
Every team, player and guild name in the tables (and in search results) opens a detail page:
- CS2 team: tag, country, division/conference, standings line, registered league roster
  (FACEIT championship "subscription" JSON, Advanced/Main/Intermediate conferences, max 60
  requests, stops once all listed teams are found), K/D + ADR for ranked players, FACEIT links.
- CS2 player: team (from the public rosters), season stats (matches, rounds, K, D, K/D, ADR,
  HS%) for players in every tracked division, rank in the division (min. 20 rounds; fewer rounds
  shows a "few rounds" note instead of a rank), FACEIT profile link. A rostered player with no
  matches yet gets an honest "No season stats yet".
- Valorant team: event placings + tracked tier-2 results from data already scraped; vlr.gg
  team link from event standings (no extra team-page fetches), otherwise a vlr.gg search link.
- WoW guild: realm, region, faction, progress, rank, first Mythic kill date per boss (already
  in the Raider.IO raid-rankings response - no extra requests), Raider.IO profile link.
## Valorant depth (v3.8)
Tracked events: the latest completed main event per Challengers / VCL circuit (up to 10, e.g.
North America ACE, EMEA, Japan, Korea, Brazil, LATAM North/South, SEA, South Asia) and per Game
Changers circuit (up to 4); qualifiers/LCQs are skipped. Per event: the event page (final
standings + every linked team) and the event stats page (rating, ACS, K/D, KAST, ADR, HS%,
agents per player). Completed events are cached (their stats never change); vlr.gg team pages
give current rosters (max 20 per run, refreshed after 72 h). /matches gives upcoming/live tier-2
matches for the Matches today board. All per-event player lines, per-player totals
(round-weighted) and rosters go to the lazy val.json/val.js; data.json keeps the top 50 players
(min. 100 rounds), per-event top 5 and upcoming matches. Routes: #valorant/players,
#player/val/<name>; #team/val/<slug> now shows the roster. The Actions cache keeps the last-good
teams.json and val.json too, so cached rosters/event stats survive between runs.

## No-JavaScript fallback (v3.7)
`prerender.py dist/index.html dist/data.json` (or `build_dist.py --prerender`) writes a static
snapshot of the front page into dist/index.html: intro, CS2 top 5 per division, latest 8 ESEA
results, 6 Valorant results, WoW top 5 and 10 headlines, plus the header update time, the side
news and a description/og/twitter summary with the division leaders. Every value is
HTML-escaped and only http(s) links are kept; snapshot links are real outbound links (FACEIT,
vlr.gg, Raider.IO, articles), never #routes. It validates before an atomic write and is
idempotent; `build_dist.py --check` validates the snapshot when present. With JavaScript,
app.js replaces #view/#side-news on boot and removes the `data-prerender` marker; a tiny head
script hides the snapshot on deep links (#cs2, #team/...) until then. Without JavaScript a
noscript style hides the game nav, ticker, forum box and search box and a footnote explains
the snapshot. The deploy workflow runs it as an optional step (on failure the JS-only page ships).

## Full standings (v3.6)
All teams of every tracked division (Oct 8: EU Adv 69, Main 153, Int 179; NA Adv 65, Main 165,
Int 106 = 737) via paged standings JSON (limit 100 per page). Division pages show 25 per page
(`#cs2/<div>/p2`) or everything (`#cs2/<div>/all`). The top 20 per division keep roster + FACEIT
url inline in data.json; all other teams are compact rows, and their rosters (+ every listed
match not kept in data.json) live in `teams.json` / `teams.js` (`window.FRAGNET_TEAMS`), loaded
lazily by team/player pages only. Cost: ~16 standings + 42 roster requests per run; data.json
447 -> 536 KB (gzip 116 -> 144 KB); teams.json 303 KB (gzip 105 KB, team pages only).

## Matches today (v3.5)
Front-page board (`#today-board`) under the intro: CS2 matches whose time falls on today's
Pacific date (finished: finish time + score + map/scoreboard link; LIVE: from the Data API
`type=ongoing` list, as of the last update; upcoming: start time + "vs" room link) plus vlr.gg
results from today. Busy days (200+ matches) show all live matches, the latest 12 results and
the next 12 starts, with a link to all results; empty day: "No matches scheduled today."
Fetcher: 27 list requests (past/ongoing/upcoming x 9 conferences) and every match within
~30 h is kept (cap 60 per division); stale fallbacks never carry LIVE entries.

## Visitor-facing pages vs. #status (v3.4)
Public pages never show fetch plumbing (no MISS/STALE badges, source/endpoint names or error
text). Each section has a neutral "Data: FACEIT · Updated Oct 8, 12:56 PDT" line; missing data
reads "Match results coming soon" / "Not available yet"; kept-old data reads "Last updated
<time>". The OK/STALE/MISS table per source (counts, timestamps, reasons) is on #status
("Site status"), linked only from the footer and the About page. tests/browser_test.py fails
if MISS, STALE, "public web JSON", "endpoint", "403" etc. appear anywhere outside #status.

## CS2 match results (v3.4, official FACEIT Data API)
The official FACEIT Data API (`https://open.faceit.com/data/v4`) supplies CS2 match results.
The key lives only in the `FACEIT_API_KEY` repository secret (never in the repo); the workflow
passes it to the fetch step, and fetch_data.py sends it only as the `Authorization: Bearer`
header. Per run it makes 2 list requests per tracked conference (past + upcoming, 18 total)
plus up to 100 match-stats requests for matches whose stats are not cached yet, hard-capped
at 150 requests, 0.5 s apart. Without a key (or on HTTP 401/403/429) the match sections keep
the last good data (STALE) or show MISS - nothing is filled in.

Endpoints: `GET /championships/{conference_id}/matches?type=past|upcoming&offset=0&limit=100`
(newest round first, so one page per conference is enough) and `GET /matches/{id}/stats`
(maps, final score and per-player K/D/ADR/HS% in one request). Kept per division: the newest
12 finished + up to 3 per tracked team (max 40) and the next 8 upcoming + each tracked team's
next match. Stats are cached across runs (last-good data); forfeits without stats >6 h old are
not re-asked. Pages: division results/upcoming, #cs2/results (all, paged), front-page box,
team pages (recent + upcoming), player pages (recent matches from scoreboards) and
#match/cs2/<id> (scoreboards). Offline test: `python tests/test_fetch_matches.py`.

## Community: forums and comments (v5.0)
The forums are the repo's **GitHub Discussions** (anyone reads; posting needs a free GitHub account).
At each deploy `discussions.py` lists the 30 most recently active threads into `forum.js` (#forums and
the sidebar) and writes `window.ESB_CONFIG` into the pages. Comment threads on match, team and player
pages use giscus (data-mapping=specific, one thread per page path, themes `giscus-classic.css` /
`giscus-night.css`, loaded only when scrolled to). They stay **off** until all of these are true:
1. the giscus app is installed on the repo: https://github.com/apps/giscus -> Install -> Only select repositories -> fragnet;
2. a Discussions category named exactly **Match threads** exists (type Announcement recommended);
3. repository variable `GISCUS_ENABLED` = `1` (Settings -> Secrets and variables -> Actions -> Variables), then rerun the deploy.
Optional `DISCORD_INVITE` (https://discord.gg/...) shows the Join-the-Discord boxes and footer link.

## About page
`#about` (linked in the top bar, section nav, game nav and footer). The static text lives
in `<template id="about-tpl">` in index.html; app.js only fills in the current fetch
time and OK/STALE/MISS counts. The footer carries a one-line disclaimer.

## Times
Everything is displayed in Pacific Time (America/Los_Angeles, PDT/PST label), regardless
of the visitor's own time zone. data.json stores UTC ISO timestamps.

## Tests
    .venv/bin/pip install -r requirements-dev.txt
    .venv/bin/python tests/browser_test.py http://localhost:8080/ [--shots shots]
Headless Chrome/Chromium: every view and internal link at 1280/1024/768/390 px, console
errors/warnings, failed requests/404s, overflow and clipped tables, tooltips on truncated
text, paging, search (incl. hostile input), read-only forums (notice, no forms, no
storage access, seeded old local posts not shown), #about content/links, no "Gotfrag" in
the DOM, external link attributes, skip link. Also works with `file:///.../index.html`
and sub-path URLs, e.g. `http://localhost:8080/dist/` and `file:///.../dist/index.html`.
v3.7 adds JS-off checks of the pre-rendered snapshot (skipped on the source root, which is
not pre-rendered) and hostile-data escaping. Offline: `tests/test_prerender.py`,
`tests/test_fetch_matches.py`.

## Files
index.html, style.css, app.js, favicon.svg, data.json + data.js (generated),
fetch_data.py, build_dist.py, dist/ (generated publish folder), fonts/ (subset fallback
fonts + licences), shots/ (screenshots; ref-gotfrag-* are local reference captures of a
third-party site - never publish them; they are excluded from dist/ and the v3.2 zip),
tests/, HOSTING.md. Previous versions: v1-backup/, v2-backup/.
