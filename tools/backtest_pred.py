#!/usr/bin/env python3
"""Walk-forward backtest of the experimental ESB win probability (ranking.py v6.5) on ESEA NA Main.

    python tools/backtest_pred.py data.json teams.json [more snapshots ...] [data/esea-s59-matches.json]

Merges every snapshot given (older committed copies + the live files), keeps each finished match once,
then predicts every match in time order from earlier matches only. Prints Brier score and log loss vs a
50/50 coin flip, accuracy, calibration bins and the split by data confidence. Local tool: never deployed.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ranking as rk  # noqa: E402
import history  # noqa: E402


def load_all(paths):
    seen, out = set(), []
    for p in paths:
        j = json.load(open(p, encoding="utf-8"))
        ms = history.to_matches(j) if "rows" in j else (j.get("cs") or {}).get("matches") if "cs" in j else j.get("matches")
        for m in ms or []:
            if m and m.get("id") not in seen and m.get("winner") in (1, 2) and rk.ts(m.get("t")) and m.get("t1") and m.get("t2"):
                seen.add(m["id"]); out.append(m)
    return sorted(out, key=lambda m: m["t"])


def main(argv):
    res = load_all(argv)
    for region in ("NA", "EU"):
        bt = rk.backtest(res, region, "Main")
        if not bt.get("n"):
            continue
        print(f"== {region} Main: {bt['n']} matches with a result, {bt['first'][:10]} .. {bt['last'][:10]}")
        print(f"   Brier {bt['brier']} (coin flip 0.25, skill {bt['skill_vs_coinflip']:+.1%}) | log loss {bt['logloss']} (coin flip {bt['logloss_coinflip']}) | "
              f"accuracy {bt['accuracy']} on {bt['decided']} non-50/50 picks")
        for b in bt["calibration"]:
            print(f"   favourite {b['range']:>8}: n={b['n']:>3}  predicted {b['predicted']:.3f}  actual {b['actual']:.3f}")
        for c, s in bt["by_confidence"].items():
            if s.get("n"):
                print(f"   confidence {c:<6}: n={s['n']:>3}  Brier {s['brier']}  accuracy {s['accuracy']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
