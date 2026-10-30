#!/usr/bin/env python3
"""Git clean/smudge filter that keeps personal identifiers out of the repo.

The working tree holds real values (entity IDs like person.<name>, hostnames,
MACs) so files stay deployable to Home Assistant as-is. Everything git stores —
and therefore everything pushed to GitHub — has those values swapped for
pseudonyms from a private map that lives outside the repo.

    redact.py clean    real   -> token   (stdin -> stdout, runs on `git add`)
    redact.py smudge   token  -> real    (runs on checkout)
    redact.py terms    print the real values (for the leak checker)

Map file: $HA_REDACT_MAP or ~/.config/ha-repo/redact_map.tsv
    real<TAB>token per line, '#' comments. Purely alphabetic entries are
    expanded to lower/Title/UPPER variants. Replacement is single-pass,
    longest-match-first, so overlapping entries (a domain containing a name)
    resolve to the longest one.

Configured as a *required* filter: if the map is missing this exits non-zero
and git refuses to stage, rather than silently committing real values.
"""
import os
import re
import sys

MAP_PATH = os.path.expanduser(
    os.environ.get("HA_REDACT_MAP", "~/.config/ha-repo/redact_map.tsv"))


def load_pairs():
    pairs = []
    with open(MAP_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            real, token = line.split("\t", 1)
            if real.isalpha() and token.isalpha():
                for fn in (str.lower, str.title, str.upper):
                    pairs.append((fn(real), fn(token)))
            else:
                pairs.append((real, token))
    return pairs


def translate(text, mapping):
    keys = sorted(mapping, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in keys))
    return pattern.sub(lambda m: mapping[m.group(0)], text)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        pairs = load_pairs()
    except FileNotFoundError:
        sys.stderr.write(f"redact.py: map not found at {MAP_PATH} — refusing to "
                         "filter (see README 'Publishing safely')\n")
        return 1
    if mode == "terms":
        print("\n".join(sorted({r for r, _ in pairs})))
        return 0
    if mode not in ("clean", "smudge"):
        sys.stderr.write("usage: redact.py clean|smudge|terms\n")
        return 2
    mapping = dict(pairs) if mode == "clean" else {t: r for r, t in pairs}
    data = sys.stdin.buffer.read()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        sys.stdout.buffer.write(data)  # binary: pass through untouched
        return 0
    sys.stdout.buffer.write(translate(text, mapping).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
