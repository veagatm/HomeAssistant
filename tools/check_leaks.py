#!/usr/bin/env python3
"""Scan what git will publish for personal details and secrets.

    check_leaks.py --staged          blobs in the index (pre-commit)
    check_leaks.py --range REV...    every blob, message and author in commits (pre-push)
    check_leaks.py --all             whole history, all refs
    check_leaks.py --dir PATH        a plain directory (e.g. a sync staging area)

Checks: real values from the private redaction map (they should have been
swapped by the clean filter), secret values from the private deny sources,
and generic patterns (MACs, JWTs, private keys, Tailscale IPs, personal emails,
inline passwords). A line containing `leak-check: allow` is skipped.
Exit 1 on any finding.
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DENY_SOURCES = os.path.expanduser(
    os.environ.get("HA_DENY_SOURCES", "~/.config/ha-repo/deny_sources.txt"))

ALLOWED_EMAIL = re.compile(
    r"@(example\.(com|net|org)|users\.noreply\.github\.com|anthropic\.com)$", re.I)
PLACEHOLDER = re.compile(r"^(\{|<|\$|YOUR|xxx|\*+$|redacted|changeme|example)", re.I)

GENERIC = [
    ("MAC address", re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")),
    ("JWT / HA token", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Tailscale IP", re.compile(r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b")),
    ("email", re.compile(r"\b[\w.+-]+@(?:[\w-]+\.)+[A-Za-z]{2,}\b")),  # not user@<IP>
    ("inline credential", re.compile(
        r"(?i)\b(password|passwd|api_key|apikey|secret|token|network_key)\b\s*[:=]\s*"
        r"[\"']?([^\s\"',}]{6,})")),
    ("URL credential", re.compile(r"[a-z]+://[^/\s:@]+:([^@\s/]{3,})@")),
]
ALLOWED_TAILSCALE = {"100.64.0.10"}


def git(*args, text=True):
    return subprocess.run(["git", *args], capture_output=True, check=True,
                          text=text).stdout


def load_real_terms():
    out = subprocess.run([sys.executable, os.path.join(HERE, "redact.py"), "terms"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("check_leaks: cannot load redaction map — " + out.stderr.strip())
    return [t for t in out.stdout.splitlines() if t]


def load_secrets():
    secrets = []
    if not os.path.exists(DENY_SOURCES):
        return secrets
    for line in open(DENY_SOURCES):
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        kind, val = line.split(":", 1)
        if kind == "literal":
            secrets.append(val)
            continue
        path = os.path.expanduser(val)
        if not os.path.exists(path):
            continue
        content = open(path).read()
        if kind == "whole":
            secrets.append(content.strip())
        elif kind == "env":
            for ln in content.splitlines():
                if "=" in ln and not ln.lstrip().startswith("#"):
                    key, value = ln.split("=", 1)
                    if re.search(r"PASS|KEY|TOKEN|SECRET", key, re.I):
                        secrets.append(value.strip().strip("\"'"))
    return [s for s in secrets if len(s) >= 6 and not PLACEHOLDER.match(s)]


class Scanner:
    def __init__(self):
        self.terms = load_real_terms()
        self.term_re = re.compile("|".join(re.escape(t) for t in self.terms), re.I) \
            if self.terms else None
        self.secrets = load_secrets()
        self.findings = []

    def scan(self, where, text):
        for n, line in enumerate(text.splitlines(), 1):
            if "leak-check: allow" in line:
                continue
            hits = []
            if self.term_re and self.term_re.search(line):
                hits.append("private term (filter not applied?)")
            if any(s in line for s in self.secrets):
                hits.append("SECRET VALUE")
            for name, rx in GENERIC:
                for m in rx.finditer(line):
                    if name == "email" and ALLOWED_EMAIL.search(m.group(0)):
                        continue
                    if name == "Tailscale IP" and m.group(0) in ALLOWED_TAILSCALE:
                        continue
                    if name in ("inline credential", "URL credential") and \
                            PLACEHOLDER.match(m.group(m.lastindex)):
                        continue
                    if name == "inline credential" and re.match(
                            r"^\w+[.(\[]", m.group(2)):
                        continue  # code reading a secret, not the secret itself
                    hits.append(name)
                    break
            for h in hits:
                # never echo the line for secrets — just the location
                shown = "" if h == "SECRET VALUE" else "  " + line.strip()[:140]
                self.findings.append(f"{where}:{n}: {h}{shown}")


def blob_text(sha):
    data = git("cat-file", "blob", sha, text=False)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def scan_commits(sc, rev_args):
    seen = set()
    for c in git("rev-list", *rev_args).split():
        meta = git("show", "-s", "--format=%an <%ae>%n%cn <%ce>%n%B", c)
        sc.scan(f"commit {c[:8]} (message/author)", meta)
        for row in git("ls-tree", "-r", c).splitlines():
            _, kind, sha, path = row.split(None, 3)
            if kind != "blob" or sha in seen:
                continue
            seen.add(sha)
            sc.scan(f"{c[:8]}:{path}", path)  # file names leak too
            t = blob_text(sha)
            if t is not None:
                sc.scan(f"{c[:8]}:{path}", t)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--staged", action="store_true")
    g.add_argument("--range", nargs="+", metavar="REV")
    g.add_argument("--all", action="store_true")
    g.add_argument("--dir")
    a = ap.parse_args()
    sc = Scanner()

    if a.staged:
        for path in git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split("\0"):
            if not path:
                continue
            sc.scan(path, path)
            sha = git("rev-parse", f":{path}").strip()
            t = blob_text(sha)
            if t is not None:
                sc.scan(path, t)
    elif a.range:
        scan_commits(sc, a.range)
    elif a.all:
        scan_commits(sc, ["--all"])
    else:
        # A working directory holds real values; scan it as git would store it.
        sys.path.insert(0, HERE)
        import redact
        clean = dict(redact.load_pairs())
        for root, dirs, files in os.walk(a.dir):
            dirs[:] = [d for d in dirs if d != ".git"]
            for f in files:
                p = os.path.join(root, f)
                try:
                    text = redact.translate(open(p, encoding="utf-8").read(), clean)
                    sc.scan(os.path.relpath(p, a.dir), text)
                except UnicodeDecodeError:
                    pass

    if sc.findings:
        print("check_leaks: possible private data — not publishing:\n", file=sys.stderr)
        print("\n".join(sc.findings), file=sys.stderr)
        print(f"\n{len(sc.findings)} finding(s). Fix, add to the redaction map, or mark a "
              "false positive with `leak-check: allow`.", file=sys.stderr)
        return 1
    print("check_leaks: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
