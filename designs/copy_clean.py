"""Design a2: drop data-source names from visible in-page copy in dist/app.js.
Links keep pointing where they did; only the words change. News headline links are untouched.
Each rule reports how often it matched so a changed app.js shows up in the build log."""
import re

RULES = [
    # standings info line: no "ESEA League (FACEIT)" link
    ('ext(cs.page, cs.league) + " &raquo; <b>"', '"<b>"'),
    # status page: no per-source tables, no source names
    ("var list = (D[sc[0]] || {}).sources || [];\n      if (!list.length) return;\n      html += '<h2 class=\"subhead\">'",
     "var list = [];\n      if (!list.length) return;\n      html += '<h2 class=\"subhead\">'"),
    ("Technical status of every data source in the latest update (", "Status of the latest update ("),
    (" The rest of the site only shows the data itself; this page is for anyone curious about where it comes from and how fresh it is.", ""),
    ('std("Site status", "data sources", html)', 'std("Site status", "latest update", html)'),
    ("Not available: the source needs a login or key, blocks automated requests, or returned nothing usable.", "Not available in the latest update."),
    ("The latest update for this source failed", "The latest update for this part failed"),
    ("function srcLine(sec) {", "function srcLine(sec) { return \"\";"),
    (" ranked together (FACEIT stage table)", " ranked together"),
    # long sentences first
    ("(FACEIT lists the chosen map", "(only the chosen map"),
    ('" only)</span>"', '" shown)</span>"'),
    ('["FACEIT", ru ? ext(ru,', '["Match room", ru ? ext(ru,'),
    ("(&#8599; = vlr.gg)", "(&#8599; = match page)"),
    (" vlr.gg results; excluded ", " results; excluded "),
    ("No roster in the public FACEIT league data for this team.", "No roster published for this team yet."),
    ("Win rate is not included: FACEIT gives team records, not per-player ones.", "Win rate is not included: only team records are published, not per-player ones."),
    ("forfeit (FACEIT result with no rounds played)", "forfeit (result with no rounds played)"),
    ("Scoreboard from the official FACEIT Data API; stats as published by FACEIT.", "Official match scoreboard."),
    ("FACEIT has not published playoff brackets", "Playoff brackets have not been published"),
    ("once FACEIT lists playoff matches", "once playoff matches are listed"),
    ("not an official FACEIT or ESEA rating", "not an official league rating"),
    ("Map scores come from FACEIT", "Map scores are official"),
    ("New events show up here as soon as vlr.gg lists them.", "New events show up here as soon as they are listed."),
    (", as listed on vlr.gg)", ")"),
    (" (Esports Scoreboard reads a few vlr.gg match pages per refresh)", ""),
    ("No map scores on the vlr.gg match page.", "No map scores published yet."),
    ("Results as listed on vlr.gg; dates in Pacific Time.", "Dates in Pacific Time."),
    ("(FACEIT / vlr.gg match room &#8599;)", "(match room &#8599;)"),
    ("= FACEIT match room", "= match room"),
    ("kill dates from Raider.IO raid rankings", "kill dates from the raid rankings"),
    ('ext(g.url, "Raider.IO")', 'ext(g.url, "guild profile")'),
    ("Raider.IO mythic progress rank", "Mythic progress rank"),
    ("FACEIT published no match stats", "No match stats were published"),
    ("Built only from FACEIT results tracked here.", "Built only from results tracked here."),
    ("Results from FACEIT", "Results"),
    ("No FACEIT scoreboards in", "No scoreboards in"),
    ("with FACEIT scoreboards", "with scoreboards"),
    ("without FACEIT match stats", "without match stats"),
    ("no match stats on FACEIT", "no match stats"),
    ("no stats from FACEIT", "no stats"),
    ("vlr.gg rating", "rating"),
    ("Counter-Strike 2 / FACEIT", "Counter-Strike 2"), ("Valorant / vlr.gg", "Valorant"), ("World of Warcraft / Raider.IO", "World of Warcraft"),
    ("CS2 / FACEIT", "CS2"), ("WoW / Raider.IO", "WoW"),
]
REGEX = [
    (r"FACEIT (?=(?:match )?(?:stats|scoreboards)\b)", ""),
    (r"\s*\(as listed on FACEIT; may change\)", " (may change)"),
    (r"as published (?:by|on) (?:FACEIT|vlr\.gg)", "as published"),
    (r"\(?as listed on vlr\.gg\)?", ""),
    (r" on (?:FACEIT|vlr\.gg|Raider\.IO)\b", ""),
]


def clean_app(path):
    with open(path, encoding="utf-8") as fh:
        js = fh.read()
    log = []
    for old, new in RULES:
        n = js.count(old)
        js = js.replace(old, new)
        log.append((n, old[:50]))
    for pat, new in REGEX:
        js, n = re.subn(pat, new, js)
        log.append((n, pat))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(js)
    missed = [o for n, o in log if not n]
    print(f"[design a2] copy clean: {sum(n for n, _ in log)} replacements" + (f"; unmatched: {missed}" if missed else ""))
