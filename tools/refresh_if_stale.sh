#!/usr/bin/env bash
# Backup trigger for the FragNet refresh: dispatch deploy.yml only if there was no
# successful run in the last 35 minutes and none is queued/running right now.
# Needs: gh authenticated for winecoolermike/fragnet. Prints one status line; never prints secrets.
set -euo pipefail
REPO=winecoolermike/fragnet; WF=deploy.yml; MAX_AGE_MIN=${MAX_AGE_MIN:-35}
active=$(gh run list -R "$REPO" -w "$WF" -L 10 --json status -q '[.[] | select(.status=="queued" or .status=="in_progress" or .status=="waiting" or .status=="pending")] | length')
if [ "$active" -gt 0 ]; then echo "skip: $active run(s) already queued/running"; exit 0; fi
last=$(gh run list -R "$REPO" -w "$WF" -s success -L 1 --json updatedAt -q '.[0].updatedAt // ""')
now=$(date -u +%s); age=999999
[ -n "$last" ] && age=$(( (now - $(date -u -d "$last" +%s)) / 60 ))
if [ "$age" -lt "$MAX_AGE_MIN" ]; then echo "skip: last successful run ${age} min ago"; exit 0; fi
gh workflow run "$WF" -R "$REPO" --ref main
echo "dispatched: last successful run ${age} min ago"
