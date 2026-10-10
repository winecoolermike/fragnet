#!/usr/bin/env python3
"""Build dist/ - the folder that goes live (FragNet v3.2).

Copies ONLY the public site files into dist/ (wiped and rebuilt each run):
  index.html (includes the About page), style.css, app.js, favicon.svg,
  fonts/*.woff2 + font licenses, data.json + data.js
Never copied: shots/ (incl. ref screenshots), tests/, backups, .venv,
fetch_data.py, build_dist.py, README/HOSTING docs, zips.

Usage:  python3 build_dist.py            build dist/ from the current files
        python3 build_dist.py --zip      also write fragnet-v3.2.zip from dist/ only
        python3 build_dist.py --prerender  also pre-render the static front page into dist/index.html
                                           (no-JS fallback, see prerender.py); --check validates it
        python3 build_dist.py --pages      also write the v4.5 path pages, sitemap.xml, robots.txt and
                                           share images (pages.py; needs Pillow for the images)
Refresh data straight into the publish folder:  python3 fetch_data.py --out dist
"""
import argparse
import fnmatch
import json
import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")
VERSION = "3.2"
FILES = ["index.html", "style.css", "app.js", "favicon.svg", "data.json", "data.js"]
OPTIONAL = ["teams.json", "teams.js",   # lazy team rosters / match lines / player stats (v3.6+); copied when present
            "val.json", "val.js",       # lazy Valorant players + rosters (v3.8)
            "giscus-classic.css", "giscus-night.css",
            "manifest.webmanifest", "sw.js", "icon-192.png", "icon-512.png"]   # R10 installable app   # v5.0 comment themes (used only when comments are switched on)
FONT_PATTERNS = ["*.woff2", "LICENSE*", "README.txt"]
BANNED_TERMS_FILE = os.path.join(HERE, ".banned-terms")   # optional, untracked: one term per line
FORBIDDEN = ["shots", "tests", "v1-backup", "v2-backup", ".venv", "fetch_data.py", "build_dist.py",
             "README.md", "HOSTING.md", "requirements*.txt", "*.zip", "*.png", "*.py", "ref-*"]


def build():
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(os.path.join(DIST, "fonts"))
    for f in FILES:
        src = os.path.join(HERE, f)
        if not os.path.isfile(src):
            sys.exit(f"[build] missing {f} (run fetch_data.py first for data files)")
        shutil.copy2(src, os.path.join(DIST, f))
    for f in OPTIONAL:
        if os.path.isfile(os.path.join(HERE, f)):
            shutil.copy2(os.path.join(HERE, f), os.path.join(DIST, f))
    for f in sorted(os.listdir(os.path.join(HERE, "fonts"))):
        if any(fnmatch.fnmatch(f, p) for p in FONT_PATTERNS):
            shutil.copy2(os.path.join(HERE, "fonts", f), os.path.join(DIST, "fonts", f))
    add_counter()


def counter_snippet(code):
    """Optional privacy-friendly visitor counter (GoatCounter: no cookies, no personal data).
    Inert unless GOATCOUNTER_CODE is set (e.g. a GitHub Actions repository variable).
    Only the section part of the hash route is counted (#cs2, #valorant ...), never ids or names."""
    code = (code or "").strip().lower()
    if not re.match(r"^[a-z0-9][a-z0-9-]{1,48}$", code):
        return ""
    return ('<script>window.goatcounter={path:function(p){return p+((location.hash||"#home").split("/")[0])}};</script>\n'
            f'<script data-goatcounter="https://{code}.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>\n')


def add_counter():
    snip = counter_snippet(os.environ.get("GOATCOUNTER_CODE"))
    if not snip:
        return
    ip = os.path.join(DIST, "index.html")
    page = open(ip, encoding="utf-8").read()
    if page.count("</body>") == 1 and "goatcounter" not in page:
        open(ip, "w", encoding="utf-8").write(page.replace("</body>", snip + "</body>"))
        print("[build] visitor counter enabled (GoatCounter)")


def files_in(root):
    out = []
    for d, dirs, fs in os.walk(root):
        for f in fs:
            out.append(os.path.relpath(os.path.join(d, f), root).replace(os.sep, "/"))
    return sorted(out)


def banned_terms():
    try:
        with open(BANNED_TERMS_FILE, encoding="utf-8") as fh:
            return [t.strip().lower() for t in fh if t.strip() and not t.startswith("#")]
    except OSError:
        return []


def verify():
    problems = []
    files = files_in(DIST)
    terms = banned_terms()
    for rel in files:
        parts = rel.split("/")
        if any(fnmatch.fnmatch(p, pat) for p in parts for pat in FORBIDDEN) and not re.match(r"^(og/[a-z0-9._-]+|icon-(192|512))\.png$", rel, re.I):
            problems.append(f"forbidden file in dist: {rel}")   # share images (v4.5) live in og/ only
        if terms and rel.endswith((".html", ".css", ".js", ".json", ".txt", ".svg")):
            with open(os.path.join(DIST, rel), encoding="utf-8", errors="replace") as fh:
                text = fh.read().lower()
            problems += [f"banned term {t!r} found in {rel}" for t in terms if t in text]
    # audit2 A2: the old name must not appear in user-facing text (URLs, file names, storage keys and code identifiers like fragnet-route are fine)
    old_name = re.compile(r"(?<![-_./A-Za-z])fragnet(?![-_./A-Za-z])", re.I)
    for rel in files:
        if rel.endswith(".html") or rel == "app.js":
            with open(os.path.join(DIST, rel), encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            if rel.endswith(".html"):
                text = re.sub(r"(?is)<(script|style)\b.*?</\1>|<[^>]+>", " ", text)
            if old_name.search(text):
                problems.append(f"old site name in user-facing text of {rel}")
    sys.path.insert(0, HERE)
    import prerender
    with open(os.path.join(DIST, "index.html"), encoding="utf-8") as fh:
        problems += ["index.html: " + p for p in prerender.check_page(fh.read())]
    with open(os.path.join(DIST, "data.json"), encoding="utf-8") as fh:
        dj = json.load(fh)
    with open(os.path.join(DIST, "data.js"), encoding="utf-8") as fh:
        js = fh.read().strip()
    pre = "window.FRAGNET_DATA = "
    if not (js.startswith(pre) and js.endswith(";")) or json.loads(js[len(pre):-1].replace("<\\/", "</")) != dj:
        problems.append("data.js does not match data.json")
    for side, var in (("teams", "FRAGNET_TEAMS"), ("val", "FRAGNET_VAL")):
        if side + ".json" not in files and side + ".js" not in files:
            continue
        try:
            with open(os.path.join(DIST, side + ".json"), encoding="utf-8") as fh:
                tj = json.load(fh)
            with open(os.path.join(DIST, side + ".js"), encoding="utf-8") as fh:
                tjs = fh.read().strip()
            tpre = f"window.{var} = "
            if not (tjs.startswith(tpre) and tjs.endswith(";")) or json.loads(tjs[len(tpre):-1].replace("<\\/", "</")) != tj:
                problems.append(f"{side}.js does not match {side}.json")
        except (OSError, ValueError) as e:
            problems.append(f"{side}.json/{side}.js unreadable: {e}")
    # v4.5 path pages: base + canonical + route meta + one well-formed snapshot each
    n_paths = 0
    for rel in files:
        if not rel.endswith("/index.html"):
            continue
        n_paths += 1
        with open(os.path.join(DIST, rel), encoding="utf-8") as fh:
            pg = fh.read()
        depth = rel.count("/")
        if '<meta name="esb-redirect">' in pg and pg.count('rel="canonical"') == 1 and "http-equiv=\"refresh\"" in pg:
            continue   # audit B10: moved-URL redirect page
        if pg.count('<base href="' + "../" * depth + '">') != 1 or pg.count('rel="canonical"') != 1 or pg.count('name="fragnet-route"') != 1:
            problems.append(f"{rel}: base/canonical/route meta missing")
        elif pg.count(prerender.MARK) != 1:
            problems.append(f"{rel}: snapshot missing")
        if len(problems) > 20:
            break
    for need in FILES + ["fonts/LICENSE-DejaVu.txt", "fonts/LICENSE-Liberation.txt"]:
        if need not in files:
            problems.append(f"missing {need}")
    return files, problems


def make_zip(files):
    zpath = os.path.join(HERE, f"fragnet-v{VERSION}.zip")
    tmp = zpath + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in files:
            z.write(os.path.join(DIST, rel), f"fragnet-v{VERSION}/{rel}")
    os.replace(tmp, zpath)
    return zpath


def main():
    ap = argparse.ArgumentParser(description="Build the FragNet publish folder dist/.")
    ap.add_argument("--zip", action="store_true", help=f"also write fragnet-v{VERSION}.zip from dist/")
    ap.add_argument("--check", action="store_true", help="only verify an existing dist/ (no copy)")
    ap.add_argument("--prerender", action="store_true", help="pre-render the static front page into dist/index.html")
    ap.add_argument("--pages", action="store_true", help="write path pages, sitemap, robots.txt and share images (pages.py)")
    a = ap.parse_args()
    if not a.check:
        build()
    if a.pages:
        sys.path.insert(0, HERE)
        import pages
        pages.build(DIST, pages.SITE, os.path.join(HERE, ".ogcache"))
    if a.prerender:
        sys.path.insert(0, HERE)
        import prerender
        if prerender.main([os.path.join(DIST, "index.html"), os.path.join(DIST, "data.json")]) != 0:
            print("[build] prerender failed - dist/index.html left without snapshot")
    files, problems = verify()
    total, groups = 0, {}
    for rel in files:
        size = os.path.getsize(os.path.join(DIST, rel))
        total += size
        top = rel.split("/")[0]
        if "/" in rel and top not in ("fonts",):
            g = groups.setdefault(top + "/", [0, 0])
            g[0] += 1
            g[1] += size
        else:
            print(f"  {size:>9,}  {rel}")
    for k, (n, size) in sorted(groups.items()):
        print(f"  {size:>9,}  {k} ({n} files)")
    print(f"  {total:>9,}  TOTAL ({len(files)} files)")
    if problems:
        print("[build] FAILED:\n  " + "\n  ".join(problems))
        return 1
    print("[build] dist/ OK")
    if a.zip:
        z = make_zip(files)
        print(f"[build] wrote {z} ({os.path.getsize(z):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
