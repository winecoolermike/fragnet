Self-hosted fallback fonts for FragNet (used only when Tahoma/Verdana/Arial are not installed).

fn-sans-*.woff2    = subset of DejaVu Sans, renamed "FragNet Sans" (Bitstream Vera / DejaVu licence: LICENSE-DejaVu.txt)
fn-grotesk-*.woff2 = subset of Liberation Sans, renamed "FragNet Grotesk" (SIL OFL 1.1, Reserved Font Name "Liberation": LICENSE-Liberation.txt)

v3.1: re-subset with pyftsubset (unhinted, ~20 KB each) to Basic Latin, Latin-1, Latin Extended A/B/Additional,
basic Cyrillic, general punctuation, currency, arrows, a few symbols. The same ranges are declared as
unicode-range in style.css so browsers fall back to system fonts for anything else.
