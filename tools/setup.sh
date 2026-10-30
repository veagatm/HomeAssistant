#!/bin/sh
# One-time setup for a clone of this repo on the machine that holds the private map.
# Wires up the redaction filter and leak-check hooks (git config is not versioned).
set -e
cd "$(git rev-parse --show-toplevel)"
git config filter.redact.clean  "python3 tools/redact.py clean"
git config filter.redact.smudge "python3 tools/redact.py smudge"
git config filter.redact.required true
git config core.hooksPath tools/hooks
python3 tools/redact.py terms >/dev/null && echo "redaction map OK" \
  || echo "WARNING: no redaction map at ~/.config/ha-repo/redact_map.tsv — commits will be refused"
