#!/usr/bin/env python3
"""One-off / manual full-season backfill of data/esea-s<N>-matches.json (history.py) from the FACEIT Data API.

    FACEIT_API_KEY=... python tools/backfill_history.py [dist/data.json dist/teams.json ...]

Reads the active season + conferences from FACEIT's public season tree, merges the matches in the given data files
(they carry per-map scores), then pages every conference's finished matches to the end. The key is only sent as a
request header (fetch_data.data_api); it is never printed.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import fetch_data as fd  # noqa: E402
import history  # noqa: E402


def main(argv):
    seasons = fd.get_json(f"{fd.FACEIT_WEB}/api/team-leagues/v2/leagues/{fd.ESEA_LEAGUE_ID}/seasons")["payload"]
    s = sorted([x for x in seasons if x.get("status") == "active"] or seasons, key=lambda x: x.get("season_number", 0), reverse=True)[0]
    season = {"id": s["id"], "name": s.get("season_name") or f"Season {s.get('season_number')}", "number": s.get("season_number"),
              "start": s.get("time_start"), "end": s.get("time_end")}
    tree = fd.get_json(f"{fd.FACEIT_WEB}/api/team-leagues/v2/seasons/tree?entityType=season&entityId={s['id']}")["payload"]
    confs = []
    for rg in tree["regions"]:
        if rg.get("code") not in fd.WANT_REGIONS:
            continue
        for dv in rg.get("divisions", []):
            if dv.get("name") not in fd.WANT_DIVS:
                continue
            st = next((x for x in dv.get("stages", []) if x.get("phase") == 1), None)
            for c in (st or {}).get("conferences") or []:
                if c.get("championship_id"):
                    confs.append((rg["code"], dv["name"], c.get("name", ""), c["championship_id"]))
    confs.sort(key=lambda c: (0 if c[0] == "NA" else 1, c[1]))   # US first
    path = history.path_for(season)
    h = history.load(season, path)
    for f in argv:
        j = json.load(open(f, encoding="utf-8"))
        ms = (j.get("cs") or {}).get("matches") if "cs" in j else j.get("matches")
        print(f, "+", history.merge(h, ms))
    for _, _, _, cid in confs:
        h["backfill"].setdefault(cid, {"offset": 0, "done": False})
    used, added, errs = fd.backfill_history(h, confs, 10000)
    history.save(h, path, force=True)
    print(f"{season['name']}: {len(confs)} conferences, {used} requests, +{added} backfilled, {len(h['rows'])} matches total -> {path} "
          f"({os.path.getsize(path):,} bytes)" + (f"; errors: {errs[:5]}" if errs else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
