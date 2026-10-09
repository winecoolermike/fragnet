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
Refresh data straight into the publish folder:  python3 fetch_data.py --out dist
"""
import argparse
import fnmatch
import json
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")
VERSION = "3.2"
FILES = ["index.html", "style.css", "app.js", "favicon.svg", "data.json", "data.js"]
OPTIONAL = ["teams.json", "teams.js"]   # lazy team rosters / match lines (v3.6); copied when present
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
        if any(fnmatch.fnmatch(p, pat) for p in parts for pat in FORBIDDEN):
            problems.append(f"forbidden file in dist: {rel}")
        if terms and rel.endswith((".html", ".css", ".js", ".json", ".txt", ".svg")):
            with open(os.path.join(DIST, rel), encoding="utf-8", errors="replace") as fh:
                text = fh.read().lower()
            problems += [f"banned term {t!r} found in {rel}" for t in terms if t in text]
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
    if "teams.json" in files or "teams.js" in files:
        try:
            with open(os.path.join(DIST, "teams.json"), encoding="utf-8") as fh:
                tj = json.load(fh)
            with open(os.path.join(DIST, "teams.js"), encoding="utf-8") as fh:
                tjs = fh.read().strip()
            tpre = "window.FRAGNET_TEAMS = "
            if not (tjs.startswith(tpre) and tjs.endswith(";")) or json.loads(tjs[len(tpre):-1].replace("<\\/", "</")) != tj:
                problems.append("teams.js does not match teams.json")
        except (OSError, ValueError) as e:
            problems.append(f"teams.json/teams.js unreadable: {e}")
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
    a = ap.parse_args()
    if not a.check:
        build()
    if a.prerender:
        sys.path.insert(0, HERE)
        import prerender
        if prerender.main([os.path.join(DIST, "index.html"), os.path.join(DIST, "data.json")]) != 0:
            print("[build] prerender failed - dist/index.html left without snapshot")
    files, problems = verify()
    total = 0
    for rel in files:
        size = os.path.getsize(os.path.join(DIST, rel))
        total += size
        print(f"  {size:>9,}  {rel}")
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
