# Actions minutes vs private repo (2026-10-15)

Last 30 successful runs: average 5.28 min (max 8.4).

Cadence today:
- cron `13,43 * * * *` = 48 scheduled runs/day
- plus workflow_dispatch backups from tools/refresh_if_stale.sh when a run is overdue

Estimates (private Free = 2,000 min/month):
| Cadence | Min/month |
|---|---|
| Current cron every 30 min alone | ~7,600 |
| Observed mix (~20 runs/day) | ~3,200 |
| Hourly cron | ~3,800 |
| Every 2 hours | ~1,900 (borderline) |
| Every 3 hours | ~1,270 (under 1,800) |

Decision: do NOT make the repo private at the current cadence.
Options for Jeffrey: (1) keep public and rename the repo to something that does not name the account;
(2) slow cron to every 3 hours (or longer) then go private; (3) GitHub Pro/Team for more minutes;
(4) move the scheduled fetch off Actions (external cron + Cloudflare direct upload).
