#!/usr/bin/env python3
"""Pull the live config into this repo so git tracks what's actually running.

Live Home Assistant is the source of truth (ha-mcp writes straight to it), so
this copies HA Green's /config and the Mac Mini side of the stack (Frigate,
its sidecar services, the status portal, launchd jobs) into the repo, then
shows what changed. Run it at the end of any session that touched config
(/ha-wrap does), review `git diff`, commit.

    python3 tools/sync.py            # HA + Mac Mini
    python3 tools/sync.py --ha       # HA Green only
    python3 tools/sync.py --mac      # Mac Mini only

Two kinds of private data, handled differently:
  * Secrets (passwords, keys, Zigbee network key) are stripped HERE, one-way,
    so they never land in the repo folder at all.
  * Personal identifiers (names, hostname, MACs) stay real in the working tree
    — the YAML has to remain deployable — and are swapped for pseudonyms by the
    git clean filter (tools/redact.py) on their way into git.
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")
SSH = ["ssh", "-p", "22222", "-i", f"{HOME}/.ssh/ha_green", "-o", "ConnectTimeout=10",
       "root@192.168.68.3"]

# /config path on HA Green -> repo path
HA_FILES = {
    "automations.yaml": "automations.yaml",
    "scripts.yaml": "scripts.yaml",
    "configuration.yaml": "configuration.yaml",
    "ui-lovelace.yaml": "lovelace/ui-lovelace.yaml",
    "packages/helpers.yaml": "helpers.yaml",
    "packages/bird_tracker.yaml": "packages/bird_tracker.yaml",
    "packages/code_enforcement.yaml": "packages/code_enforcement.yaml",
    "themes/kiosk_dark.yaml": "themes/kiosk_dark.yaml",
    "zigbee2mqtt/configuration.yaml": "zigbee2mqtt/configuration.yaml",
}
HA_DIRS = {"lovelace": "lovelace"}  # mirrored file-by-file (repo-only extras kept)
HA_STORAGE_HELPERS = ["input_boolean", "input_datetime", "input_number",
                      "input_select", "input_text", "counter", "timer", "schedule"]

# Mac Mini sources -> repo path. Directories copy only the listed globs.
FRIGATE = f"{HOME}/frigate"
MAC_FILES = {
    f"{FRIGATE}/docker-compose.yml": "frigate/docker-compose.yml",
    f"{FRIGATE}/config/config.yml": "frigate/config/config.yml",
    f"{FRIGATE}/start-frigate.sh": "frigate/start-frigate.sh",
    f"{FRIGATE}/autostart.sh": "frigate/autostart.sh",
    f"{HOME}/Desktop/claude_code/StatusPortal/monitor.py": "statusportal/monitor.py",
    f"{HOME}/Desktop/claude_code/StatusPortal/worker.js": "statusportal/worker.js",
    f"{HOME}/Desktop/claude_code/StatusPortal/wrangler.toml": "statusportal/wrangler.toml",
}
MAC_DIRS = {
    f"{FRIGATE}/bird_tracker": "frigate/bird_tracker",
    f"{FRIGATE}/code_enforcement": "frigate/code_enforcement",
    f"{FRIGATE}/vehicle_dashboard": "frigate/vehicle_dashboard",
    f"{FRIGATE}/sdcard_review": "frigate/sdcard_review",
    f"{HOME}/reid": "reid",
}
MAC_DIR_EXTS = (".py", ".txt", ".yml", ".yaml", ".sh", ".md", ".toml", ".js")
MAC_DIR_NAMES = ("Dockerfile",)
LAUNCHD = [f"{HOME}/Library/LaunchAgents/{n}.plist" for n in (
    "com.frigate.startup", "com.rileyhollis.speedtest",
    "com.rileyhollis.upsmonitor", "com.rileyhollis.housemonitor")]
ENV_FILE = f"{FRIGATE}/.env"

changed = []


def write(rel, content):
    dest = os.path.join(REPO, rel)
    if isinstance(content, str):
        content = content.encode("utf-8")
    old = open(dest, "rb").read() if os.path.exists(dest) else None
    if old == content:
        return
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(content)
    changed.append(("new " if old is None else "upd ") + rel)


# ── one-way scrubbers ─────────────────────────────────────────────────────────

def short_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()[:10]


def scrub_z2m(text):
    """Zigbee network key/PAN IDs and MQTT creds -> <redacted>; IEEE addresses ->
    stable hashes (keeps the device list readable without exposing hardware IDs)."""
    text = re.sub(r"(?m)^(\s*(?:password|user|network_key|pan_id|ext_pan_id|auth_token)\s*:)"
                  r"(?:[ \t]*\n(?:[ \t]+-.*\n)+|.*)",
                  lambda m: m.group(1) + " <redacted>" + ("\n" if m.group(0).endswith("\n") else ""),
                  text)
    text = re.sub(r"'?0x([0-9a-f]{16})'?",
                  lambda m: f"'ieee-{short_hash(m.group(1))}'", text)
    return text


def scrub_plist(text):
    """Blank launchd EnvironmentVariables that hold credentials."""
    return re.sub(r"(<key>[A-Z0-9_]*(?:KEY|TOKEN|PASS|SECRET)[A-Z0-9_]*</key>\s*<string>)[^<]*",
                  r"\1REPLACE_ME", text)


def env_example(text):
    return re.sub(r"(?m)^([A-Z0-9_]+)=.*$", r"\1=", text)


def storage_helpers_yaml(blob):
    """.storage/<domain> JSON -> the equivalent YAML a person would read."""
    items = json.loads(blob)["data"]["items"]
    return {it.pop("id"): it for it in items}


# ── HA Green ──────────────────────────────────────────────────────────────────

def sync_ha():
    paths = list(HA_FILES) + list(HA_DIRS) + [f".storage/{d}" for d in HA_STORAGE_HELPERS]
    # tar what exists; missing storage domains are fine
    cmd = "cd /config && tar cf - $(ls -d " + " ".join(paths) + " 2>/dev/null)"
    raw = subprocess.run(SSH + [cmd], capture_output=True, check=True).stdout
    tar = tarfile.open(fileobj=io.BytesIO(raw))
    members = {m.name: m for m in tar.getmembers() if m.isfile()}

    def read(name):
        return tar.extractfile(members[name]).read().decode("utf-8")

    for src, dest in HA_FILES.items():
        if src not in members:
            print(f"  ! missing on HA: {src}")
            continue
        text = read(src)
        if src.startswith("zigbee2mqtt/"):
            text = scrub_z2m(text)
        write(dest, text)

    for src_dir, dest_dir in HA_DIRS.items():
        for name in members:
            if name.startswith(src_dir + "/"):
                write(dest_dir + name[len(src_dir):], read(name))

    helpers = {}
    for d in HA_STORAGE_HELPERS:
        if f".storage/{d}" in members:
            items = storage_helpers_yaml(read(f".storage/{d}"))
            if items:
                helpers[d] = items
    header = ("# UI/ha-mcp-created helpers — exported from HA's .storage by tools/sync.py.\n"
              "# Read-only record: these live in HA's storage, not YAML. Edit via ha-mcp or the UI.\n")
    write("helpers_storage.yaml", header + yaml.safe_dump(helpers, sort_keys=True, allow_unicode=True))

    out = subprocess.run(SSH + ["for m in /config/custom_components/*/manifest.json; do cat $m; echo '\x1e'; done"],
                         capture_output=True, check=True, text=True).stdout
    comps = [json.loads(c) for c in out.split("\x1e") if c.strip()]
    write("custom_components.txt",
          "# HACS / custom integrations installed on HA Green (tools/sync.py)\n" +
          "".join(f"{c['domain']:<12} {c.get('version', '?'):<10} {c.get('documentation', '')}\n"
                  for c in sorted(comps, key=lambda c: c["domain"])))


# ── Mac Mini ──────────────────────────────────────────────────────────────────

def sync_mac():
    for src, dest in MAC_FILES.items():
        if os.path.exists(src):
            write(dest, open(src, "rb").read())
        else:
            print(f"  ! missing: {src}")
    for src, dest in MAC_DIRS.items():
        for root, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if not d.startswith((".", "__"))]
            for f in files:
                if f.endswith(MAC_DIR_EXTS) or f in MAC_DIR_NAMES:
                    p = os.path.join(root, f)
                    write(os.path.join(dest, os.path.relpath(p, src)), open(p, "rb").read())
    # git's filter rewrites file contents but not file names, so pseudonymize names here
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import redact
    clean = dict(redact.load_pairs())
    for p in LAUNCHD:
        if os.path.exists(p):
            name = redact.translate(os.path.basename(p), clean)
            write("macmini/launchd/" + name, scrub_plist(open(p).read()))
    if os.path.exists(ENV_FILE):
        write("frigate/.env.example", env_example(open(ENV_FILE).read()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ha", action="store_true")
    ap.add_argument("--mac", action="store_true")
    a = ap.parse_args()
    both = not (a.ha or a.mac)
    if a.ha or both:
        print("Syncing from HA Green…")
        sync_ha()
    if a.mac or both:
        print("Syncing from Mac Mini…")
        sync_mac()
    print("\n".join("  " + c for c in changed) or "  (no changes)")
    if changed and shutil.which("git"):
        subprocess.run(["git", "-C", REPO, "status", "--short"])


if __name__ == "__main__":
    sys.exit(main())
