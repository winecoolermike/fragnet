#!/usr/bin/env python3
"""v5.4 team-owned extras (Esports Scoreboard): validates the reviewed teams-extra.json and writes
dist/extra.js (window.ESB_EXTRA). Entries reach teams-extra.json only through a pull request that
Jeffrey merges; nothing user-submitted is published automatically.

Safety: logos must be https image URLs (png/jpg/webp/gif, no query string, no credentials) on an allowlisted
image host; socials are handles turned into fixed profile URLs (no free-form links); text is length-capped
and rendered escaped. Invalid fields are dropped with a log line.

Usage: python teams_extra.py dist [--src teams-extra.json]
"""
import json
import os
import re
import sys
from urllib.parse import urlsplit

LOGO_HOSTS = {"i.imgur.com", "raw.githubusercontent.com", "avatars.githubusercontent.com", "user-images.githubusercontent.com",
              "assets.faceit-cdn.net", "distribution.faceit-cdn.net", "owcdn.net", "www.vlr.gg"}
SOCIAL = {
    "x": ("https://x.com/{}", r"^[A-Za-z0-9_]{1,15}$"),
    "twitch": ("https://www.twitch.tv/{}", r"^[A-Za-z0-9_]{3,25}$"),
    "youtube": ("https://www.youtube.com/@{}", r"^[A-Za-z0-9_.-]{3,30}$"),
    "discord": ("https://discord.gg/{}", r"^[A-Za-z0-9-]{2,32}$"),
    "faceit": ("https://www.faceit.com/en/teams/{}", r"^[0-9a-f-]{36}$"),
}
KINDS = ("LFP", "LFT")
KEY_RE = re.compile(r"^(cs2:[0-9a-f-]{36}|val:[a-z0-9-]{1,60})$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def text(v, n):
    v = re.sub(r"[\x00-\x1f<>]", " ", str(v or "")).strip()
    return v[:n]


def logo_ok(u):
    try:
        p = urlsplit(str(u or ""))
    except ValueError:
        return False
    return (p.scheme == "https" and p.hostname in LOGO_HOSTS and not p.query and not p.fragment and not p.username
            and re.search(r"\.(png|jpe?g|webp|gif)$", p.path, re.I) is not None)


def post(r, log, where):
    kind = str(r.get("type", "")).upper()
    if kind not in KINDS:
        log.append(f"{where}: type must be LFP or LFT"); return None
    out = {"type": kind, "role": text(r.get("role"), 30), "note": text(r.get("note"), 200), "region": text(r.get("region"), 20),
           "game": "val" if r.get("game") == "val" else "cs2", "updated": r.get("updated") if DATE_RE.match(str(r.get("updated", ""))) else ""}
    c = r.get("contact") or {}
    for k, (fmt, rx) in SOCIAL.items():
        if isinstance(c, dict) and c.get(k) and re.match(rx, str(c[k])):
            out["contact"] = {"kind": k, "url": fmt.format(c[k]), "label": f"{k}: {c[k]}"}
            break
    if not out["role"] or not out["updated"]:
        log.append(f"{where}: role and updated (YYYY-MM-DD) are required"); return None
    return out


def clean(src):
    log, teams, players = [], {}, []
    for key, t in (src.get("teams") or {}).items():
        if not KEY_RE.match(str(key)) or not isinstance(t, dict):
            log.append(f"bad team key {key!r}"); continue
        o = {"name": text(t.get("name"), 60)}
        if t.get("logo"):
            if logo_ok(t["logo"]):
                o["logo"] = t["logo"]
            else:
                log.append(f"{key}: logo rejected (https, allowlisted host, image file, no query)")
        so = []
        for k, h in (t.get("socials") or {}).items():
            if k in SOCIAL and re.match(SOCIAL[k][1], str(h)):
                so.append({"kind": k, "url": SOCIAL[k][0].format(h), "label": str(h)})
            else:
                log.append(f"{key}: social {k!r} rejected")
        if so:
            o["socials"] = so
        rec = [x for x in (post(dict(r, game=key.split(":")[0]), log, key) for r in (t.get("recruiting") or [])[:3]) if x]
        if rec:
            o["recruiting"] = rec
        teams[key] = o
    for i, r in enumerate((src.get("players") or [])[:200]):
        p = post(r, log, f"players[{i}]")
        if p and p["type"] == "LFT":
            p["nick"] = text(r.get("nick"), 32)
            if p["nick"]:
                players.append(p)
    return {"teams": teams, "players": players}, log


def main(argv=None):
    argv = argv or sys.argv[1:]
    dist = argv[0] if argv else "dist"
    src_path = argv[argv.index("--src") + 1] if "--src" in argv else "teams-extra.json"
    try:
        src = json.load(open(src_path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"[extra] {src_path} unreadable ({str(e)[:80]}) - skipped"); return 0
    out, log = clean(src)
    for l in log:
        print("[extra] dropped: " + l)
    blob = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    open(os.path.join(dist, "extra.js"), "w", encoding="utf-8").write("window.ESB_EXTRA = " + blob.replace("</", "<\\/") + ";\n")
    print(f"[extra] {len(out['teams'])} team entries, {len(out['players'])} LFT posts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
