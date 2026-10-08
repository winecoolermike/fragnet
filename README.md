# FragNet

**Live site: https://winecoolermike.github.io/fragnet/**

FragNet is an independent, fan-made tracker for **amateur and semi-pro esports**, styled
like a classic mid-2000s esports portal:

- **Matches today** (front page): today's ESEA matches (Pacific date) - live, finished with
  scores and upcoming with start times - plus any Valorant results from today.
- **Counter-Strike 2 / ESEA League**: current season, standings (top 20) for EU and NA
  Advanced, Main and Intermediate, recent results and upcoming matches with per-map
  scoreboards, and top fraggers in Advanced.
- **Valorant**: Challengers / VCL and Game Changers calendar, recent final standings and
  tier-2 match results.
- **World of Warcraft**: Mythic raid progression rankings (top 50, US and EU).
- **News**: esports headlines that link to the original articles.

Every team, player and guild name opens a detail page (CS2 team with standings and
registered roster and recent / upcoming matches, CS2 player season stats and recent matches, Valorant team placings and results, WoW guild
progress with first Mythic kill dates), each linking back to its source.

It shows only data from public web pages, open endpoints and the official FACEIT Data API. Nothing is invented:
if something isn't available yet the page says so in plain words, and if an update fails
the last good data stays up with its "Last updated" date. Per-source details (OK / STALE /
MISS, record counts, timestamps) are on the low-key **Site status** page (`#status`, linked
from the footer and the About page). All times are
shown in Pacific Time. Forums are read-only for now.

## Data sources

| Source | Used for |
|---|---|
| [FACEIT - ESEA League](https://www.faceit.com/en/cs2/league/ESEA%20League/a14b8616-45b9-4581-8637-4dfd0b5f6af8) public pages | season info, standings, league rosters, player stats |
| [FACEIT Data API](https://docs.faceit.com/docs/data-api/data/) (official, API key) | ESEA match results, upcoming matches, per-map scoreboards |
| [vlr.gg](https://www.vlr.gg/) | Valorant tier-2 events, standings, results, news (RSS) |
| [Raider.IO](https://raider.io/) public API | Mythic raid rankings and boss kill dates |
| [Wowhead](https://www.wowhead.com/news), [Dexerto](https://www.dexerto.com/esports/), [Esports Insider](https://esportsinsider.com/) | headlines (RSS) |

Requests are rate-limited (at least 1.2 s apart per host; 0.5 s for the FACEIT Data API, well under its
limit) and use an identifying User-Agent.

## How the site updates

A GitHub Actions workflow (`.github/workflows/deploy.yml`) runs on every push to `main`,
on demand, and on a schedule about every 30 minutes (at :13 and :43 past the hour;
GitHub may delay scheduled runs). Each run:

1. builds `dist/` from the site files (`python build_dist.py`);
2. restores the most recent last-good `data.json` from the Actions cache, falling back to
   the copy in the repo;
3. runs `python fetch_data.py --out dist`; if a source fails, its last good data is kept
   and flagged STALE, and if the whole fetch fails the site is still deployed with the
   previous data;
4. checks that `data.js` matches `data.json` and deploys `dist/` to GitHub Pages.

The official FACEIT Data API (`https://open.faceit.com/data/v4`) supplies CS2 match results.
The key lives only in the `FACEIT_API_KEY` repository secret (never in the repo); the workflow
passes it to the fetch step, and fetch_data.py sends it only as the `Authorization: Bearer`
header. Per run it makes 2 list requests per tracked conference (past + upcoming, 18 total)
plus up to 100 match-stats requests for matches whose stats are not cached yet, hard-capped
at 150 requests, 0.5 s apart. Without a key (or on HTTP 401/403/429) the match sections keep
the last good data (STALE) or show MISS - nothing is filled in.

### Backup trigger
GitHub's `schedule` event is best-effort and can be delayed or skipped. `tools/refresh_if_stale.sh`
(needs an authenticated `gh`) dispatches `deploy.yml` only when no run is queued/running and the
last successful run is older than 35 minutes; run it every 30 minutes from any scheduler.

## Run locally

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python build_dist.py
    .venv/bin/python fetch_data.py --out dist
    cd dist && python3 -m http.server 8080      # http://localhost:8080/

`dist/index.html` also works when opened directly from disk (it then loads `data.js`).

## Disclaimer

FragNet is an independent fan project. It is not affiliated with, endorsed by, or
sponsored by FACEIT, ESEA, Valve, Riot Games, Blizzard Entertainment, Raider.IO, vlr.gg
or any of the news sites listed above. Counter-Strike, Valorant, World of Warcraft and
all other trademarks belong to their respective owners. Fonts: see `fonts/README.txt`
and the licence files in `fonts/`.
