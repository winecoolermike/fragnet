"""Redesign preview layer (build flag): python build_dist.py with ESB_DESIGN=a|b|c (or a designs/ACTIVE file).

Adds one design on top of the shipped site without touching app.js or the data:
  * dist/design.css  = designs/common.css + designs/<x>.css, every selector scoped to html[data-d]
  * the base Night rules are switched off (the design brings its own day/night palette)
  * <html data-d="x">, the design stylesheet, designs/design.js, the design fonts
  * footer without data-source credits
No ESB_DESIGN (and no designs/ACTIVE) = the build is byte-for-byte the current site.
"""
import os, re, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = {"a": "Scoreline", "b": "Press Row", "c": "Matchday", "a2": "Scoreline 2"}
LAYERS = {"a2": ["a", "a2"]}   # a2 builds on a


def active():
    d = (os.environ.get("ESB_DESIGN") or "").strip().lower()
    if not d:
        try:
            with open(os.path.join(HERE, "ACTIVE"), encoding="utf-8") as fh:
                d = fh.read().strip().lower()
        except OSError:
            d = ""
    return d if d in NAMES else ""


def scope_sel(sel):
    s = sel.strip()
    if not s:
        return s
    if s.startswith(":root"):
        return "html[data-d]" + s[5:]
    if s.startswith("html"):
        return "html[data-d]" + s[4:]
    if s.startswith("[data-theme") or s.startswith(".rt-"):
        return "html[data-d]" + s
    return "html[data-d] " + s


def split_top(css):
    """yield (prelude, body) for each top-level block; handles nested @media."""
    i, n = 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        prelude = css[i:j].strip()
        depth, k = 1, j + 1
        while k < n and depth:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
            k += 1
        yield prelude, css[j + 1:k - 1]
        i = k


def scope_css(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    for prelude, body in split_top(css):
        if prelude.startswith("@media") or prelude.startswith("@supports"):
            out.append(prelude + "{" + scope_css(body) + "}")
        elif prelude.startswith("@"):
            out.append(prelude + "{" + body + "}")
        else:
            sels = ",".join(scope_sel(x) for x in prelude.split(","))
            out.append(sels + "{" + body.strip() + "}")
    return "\n".join(out) + "\n"


FOOT_DISCLAIMER = ('<div class="foot-note disclaimer-line">Independent fan project &middot; not affiliated with any league, '
                   'publisher or team &middot; all trademarks belong to their owners<span class="js-only"> &middot; '
                   '<a href="#about">About Esports Scoreboard</a></span></div>')


def apply(dist, design=None):
    d = design or active()
    if not d:
        return ""
    css = ""
    for name in ["common.css"] + [x + ".css" for x in LAYERS.get(d, [d])]:
        with open(os.path.join(HERE, name), encoding="utf-8") as fh:
            css += fh.read() + "\n"
    with open(os.path.join(dist, "design.css"), "w", encoding="utf-8") as fh:
        fh.write("/* Esports Scoreboard redesign preview: " + NAMES[d] + " */\n" + scope_css(css))
    shutil.copy2(os.path.join(HERE, "design.js"), os.path.join(dist, "design.js"))
    os.makedirs(os.path.join(dist, "fonts"), exist_ok=True)
    for f in os.listdir(os.path.join(HERE, "fonts")):
        shutil.copy2(os.path.join(HERE, "fonts", f), os.path.join(dist, "fonts", f))
    # the base Night rules give way to the design's own palette
    sp = os.path.join(dist, "style.css")
    with open(sp, encoding="utf-8") as fh:
        base = fh.read()
    with open(sp, "w", encoding="utf-8") as fh:
        fh.write(base.replace("[data-theme=night]", "[data-theme=night-base]"))
    ip = os.path.join(dist, "index.html")
    with open(ip, encoding="utf-8") as fh:
        html = fh.read()
    html = html.replace('<html lang="en">', f'<html lang="en" data-d="{d}">', 1)
    html = re.sub(r'(<link rel="stylesheet" href="style\.css[^"]*">)', r'\1\n<link rel="stylesheet" href="design.css?v=' + d + '1">', html, count=1)
    html = html.replace("</body>", '<script src="design.js?v=' + d + '1" defer></script>\n</body>', 1)
    html = re.sub(r'\s*<div class="foot-note foot-ql">Sources:.*?</div>', "", html, count=1, flags=re.S)
    html = re.sub(r'<div class="foot-note disclaimer-line">.*?</div>', FOOT_DISCLAIMER, html, count=1, flags=re.S)
    html = re.sub(r"&middot; data: FACEIT, vlr\.gg, Raider\.IO and the linked news sites &middot; every team, player and guild page links to its source ", "", html, count=1)
    with open(ip, "w", encoding="utf-8") as fh:
        fh.write(html)
    if d == "a2":
        import copy_clean
        copy_clean.clean_app(os.path.join(dist, "app.js"))
    return d
