#!/usr/bin/env python3
"""v5.0 community: latest GitHub Discussions for the forum index + site config (Esports Scoreboard).

Writes dist/forum.json + dist/forum.js (window.ESB_FORUM) with the Discussion categories and the
latest threads, and injects window.ESB_CONFIG into dist/index.html (so the path pages built later
inherit it). Comments (giscus) are switched on only when GISCUS_ENABLED=1 AND a category named
"Match threads" exists; until then nothing third-party loads. DISCORD_INVITE (https://discord.gg/...)
shows the Join-the-Discord boxes. Needs GITHUB_TOKEN (Actions: discussions: read) for the listing;
without it only the config is written.

Usage: python discussions.py dist [--repo owner/name]
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

REPO = "winecoolermike/fragnet"
COMMENTS_CATEGORY = "Match threads"
QUERY = """query($o:String!,$n:String!){repository(owner:$o,name:$n){id url hasDiscussionsEnabled
 discussionCategories(first:25){nodes{id name slug emoji description}}
 discussions(first:30,orderBy:{field:UPDATED_AT,direction:DESC}){totalCount nodes{title url number createdAt updatedAt
  author{login} category{name slug} comments{totalCount}}}}}"""
INVITE_RE = re.compile(r"^https://(discord\.gg|discord\.com/invite)/[A-Za-z0-9-]{2,32}/?$")


def gql(token, owner, name):
    req = urllib.request.Request("https://api.github.com/graphql", method="POST",
                                 data=json.dumps({"query": QUERY, "variables": {"o": owner, "n": name}}).encode(),
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                                          "User-Agent": "EsportsScoreboard/5.0 (hobby tracker)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.load(r)
    if out.get("errors"):
        raise RuntimeError("GraphQL: " + "; ".join(str(e.get("message"))[:120] for e in out["errors"]))
    return out["data"]["repository"]


def shape(repo, now=None):
    """Raw GraphQL repository -> the small public forum.json (no ids except the giscus ones)."""
    cats = repo.get("discussionCategories", {}).get("nodes") or []
    nodes = (repo.get("discussions") or {}).get("nodes") or []
    count = {}
    for d in nodes:
        s = (d.get("category") or {}).get("slug")
        count[s] = count.get(s, 0) + 1
    latest = [{"title": d.get("title"), "url": d.get("url"), "n": d.get("number"), "created": d.get("createdAt"), "updated": d.get("updatedAt"),
               "author": (d.get("author") or {}).get("login") or "ghost", "cat": (d.get("category") or {}).get("name"),
               "cat_slug": (d.get("category") or {}).get("slug"), "comments": (d.get("comments") or {}).get("totalCount", 0)}
              for d in nodes if str(d.get("url", "")).startswith("https://github.com/")]
    out = {"fetched_at": now or datetime.now(timezone.utc).isoformat(timespec="seconds"), "url": repo.get("url", "") + "/discussions",
           "enabled": bool(repo.get("hasDiscussionsEnabled")), "total": (repo.get("discussions") or {}).get("totalCount", 0),
           "categories": [{"name": c.get("name"), "slug": c.get("slug"), "desc": c.get("description") or "", "recent": count.get(c.get("slug"), 0)} for c in cats],
           "latest": latest}
    mt = next((c for c in cats if (c.get("name") or "").strip().lower() == COMMENTS_CATEGORY.lower()), None)
    giscus = {"repo_id": repo.get("id"), "category": mt.get("name"), "category_id": mt.get("id")} if mt and repo.get("id") else None
    return out, giscus


def config(repo_name, giscus, env):
    cfg = {"repo": repo_name, "discussions": f"https://github.com/{repo_name}/discussions"}
    if giscus and env.get("GISCUS_ENABLED", "").strip() in ("1", "true", "yes"):
        cfg["giscus"] = giscus
    inv = (env.get("DISCORD_INVITE") or "").strip()
    if INVITE_RE.match(inv):
        cfg["discord"] = inv
    return cfg


def inject(index_path, cfg):
    page = open(index_path, encoding="utf-8").read()
    tag = "<script>window.ESB_CONFIG = " + json.dumps(cfg, ensure_ascii=True).replace("<", "\\u003c") + ";</script>\n"
    page = re.sub(r"<script>window\.ESB_CONFIG = .*?;</script>\n", "", page)
    if page.count("</head>") != 1:
        raise ValueError("no </head> in index.html")
    open(index_path, "w", encoding="utf-8").write(page.replace("</head>", tag + "</head>", 1))


def write_forum(dist, forum):
    blob = json.dumps(forum, ensure_ascii=False, separators=(",", ":"))
    open(os.path.join(dist, "forum.json"), "w", encoding="utf-8").write(blob)
    open(os.path.join(dist, "forum.js"), "w", encoding="utf-8").write("window.ESB_FORUM = " + blob.replace("</", "<\\/") + ";\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dist")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY") or REPO)
    ap.add_argument("--fixture", help="read the GraphQL repository object from this JSON file (tests)")
    a = ap.parse_args(argv)
    owner, name = a.repo.split("/", 1)
    token = os.environ.get("GITHUB_TOKEN") or ""
    giscus, wrote = None, False
    if token or a.fixture:
        try:
            forum, giscus = shape(json.load(open(a.fixture, encoding="utf-8")) if a.fixture else gql(token, owner, name))
            write_forum(a.dist, forum)
            wrote = True
            print(f"[discussions] {forum['total']} discussions, {len(forum['categories'])} categories, comments category: {'found' if giscus else 'missing'}")
        except Exception as e:   # the forum index then shows its honest empty state
            print(f"[discussions] listing unavailable: {str(e)[:200]}")
    else:
        print("[discussions] no GITHUB_TOKEN - listing skipped")
    cfg = config(a.repo, giscus, os.environ)
    if wrote:
        cfg["forum"] = True
    if os.path.exists(os.path.join(a.dist, "spot.js")):
        cfg["spot"] = True
    inject(os.path.join(a.dist, "index.html"), cfg)
    print(f"[discussions] config: comments {'on' if 'giscus' in cfg else 'off'}, discord {'on' if 'discord' in cfg else 'off'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
