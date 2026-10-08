# FragNet

**Live site: https://winecoolermike.github.io/fragnet/**

FragNet is an independent, fan-made tracker for **amateur and semi-pro esports**, styled
like a classic mid-2000s esports portal:

- **Counter-Strike 2 / ESEA League**: current season, standings (top 20) for EU and NA
  Advanced, Main and Intermediate, and top fraggers in Advanced.
- **Valorant**: Challengers / VCL and Game Changers calendar, recent final standings and
  tier-2 match results.
- **World of Warcraft**: Mythic raid progression rankings (top 50, US and EU).
- **News**: esports headlines that link to the original articles.

Every team, player and guild name opens a detail page (CS2 team with standings and
registered roster, CS2 player season stats, Valorant team placings and results, WoW guild
progress with first Mythic kill dates), each linking back to its source.

It shows only data from public web pages and open, keyless endpoints. Nothing is invented:
if a source can't be fetched, the page marks it **MISS** (no data) or **STALE** (the
latest fetch failed, so the last good data is shown with its timestamp). All times are
shown in Pacific Time. Forums are read-only for now.

## Data sources

| Source | Used for |
|---|---|
| [FACEIT - ESEA League](https://www.faceit.com/en/cs2/league/ESEA%20League/a14b8616-45b9-4581-8637-4dfd0b5f6af8) public pages | season info, standings, league rosters, player stats |
| [vlr.gg](https://www.vlr.gg/) | Valorant tier-2 events, standings, results, news (RSS) |
| [Raider.IO](https://raider.io/) public API | Mythic raid rankings and boss kill dates |
| [Wowhead](https://www.wowhead.com/news), [Dexerto](https://www.dexerto.com/esports/), [Esports Insider](https://esportsinsider.com/) | headlines (RSS) |

Requests are rate-limited (at least 1.2 s apart per host) and use an identifying User-Agent.

## How the site updates

A GitHub Actions workflow (`.github/workflows/deploy.yml`) runs on every push to `main`,
on demand, and on a schedule about every 30 minutes (at :07 and :37 past the hour;
GitHub may delay scheduled runs). Each run:

1. builds `dist/` from the site files (`python build_dist.py`);
2. restores the most recent last-good `data.json` from the Actions cache, falling back to
   the copy in the repo;
3. runs `python fetch_data.py --out dist`; if a source fails, its last good data is kept
   and flagged STALE, and if the whole fetch fails the site is still deployed with the
   previous data;
4. checks that `data.js` matches `data.json` and deploys `dist/` to GitHub Pages.

The official FACEIT Data API is not used yet. If a `FACEIT_API_KEY` repository secret is
added later, the workflow passes it to the fetcher, which currently only records that the
key is configured (match results remain unavailable until that integration is written).

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
