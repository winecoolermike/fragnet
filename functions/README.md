# Pages Functions (Esports Scoreboard)

`api/t.js` is the free, cookieless time-on-site beacon endpoint (`POST /api/t`). `wrangler pages deploy dist`
(deploy.yml) compiles this folder automatically; `_routes.json` limits the Function to `/api/t`, so every other
file is still served as a plain static asset (no Function invocations).

## One-time Cloudflare setup (Jeff, nothing is created automatically)

The endpoint stores nothing until the Pages project has an Analytics Engine binding:

1. Cloudflare dashboard > Workers & Pages > **esportsscoreboard** > Settings > Bindings > Add > **Analytics Engine**.
2. Variable name: `ESB_TIME`, dataset: `esb_time_on_site` (the dataset is created on the first write). Add it for Production.
3. The next deploy picks it up. Free plan: 100,000 data points written and 10,000 read queries per day
   (https://developers.cloudflare.com/analytics/analytics-engine/pricing/); this site sends about one data point per page view (one more each time a tab comes back into view).

Columns: blob1 = route, blob2 = section (e.g. `team/cs2`), blob3 = phone/desktop, double1 = seconds visible, double2 = 1 for the first beacon of a page view.

Reading it needs an API token with **Account Analytics: Read** (the current site token has Zone Analytics Read only):

```
curl -s https://api.cloudflare.com/client/v4/accounts/<account id>/analytics_engine/sql \
  -H "Authorization: Bearer <token>" \
  --data "SELECT blob2 AS section, SUM(_sample_interval * double2) AS views, SUM(_sample_interval * double1) / SUM(_sample_interval * double2) AS avg_seconds_per_view
          FROM esb_time_on_site WHERE timestamp > NOW() - INTERVAL '7' DAY GROUP BY section ORDER BY views DESC"
```
