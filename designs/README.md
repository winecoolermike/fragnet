# Redesign previews (not live)

Three visual directions for Esports Scoreboard, built as a layer on top of the current site
(same app.js, same data, same pages). Nothing here changes the live build unless a design is selected.

| flag | name | idea |
|------|------|------|
| `a` | Scoreline | modern sports-scores app: white cards, big numbers, pill nav, bottom tab bar on phones |
| `b` | Press Row | the old portal refined: calm dark slate, monospace labels, airy 3-column scoreboards |
| `c` | Matchday | editorial magazine: serif headlines, predictions as the cover story, article-style previews |

Build one locally: `ESB_DESIGN=a python build_dist.py` (or put the letter in `designs/ACTIVE`).
No flag and no ACTIVE file = the current site, unchanged.

Fonts: Inter, IBM Plex Sans/Mono, Fraunces (SIL Open Font License, self-hosted in dist/fonts/).
