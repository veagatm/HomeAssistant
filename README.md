# Smart Home — Home Assistant Build

A local-first smart home running on **Home Assistant Green**, with a self-hosted computer-vision
layer (Frigate NVR + custom detection services) running in Docker on a repurposed **Mac Mini M1**.
Everything here is the actual configuration driving a real house — not a demo.

The repo tracks both halves: the Home Assistant config (YAML, automations, helpers, dashboards,
Zigbee2MQTT) and the Mac Mini stack (Frigate config, the Docker Compose file, the custom detection
services, launchd jobs). Both are pulled from the running systems by
[`tools/sync.py`](tools/sync.py), so what's committed is what's actually deployed.

**[→ View the interactive architecture walkthrough](https://veagatm.github.io/HomeAssistant/)**
— a seven-layer, OSI-inspired tour of every device and service in the build, source in
[`docs/index.html`](docs/index.html) (served by [GitHub Pages](https://docs.github.com/pages) from
the `/docs` folder of `main`).

## Why this stack

**Home Assistant Green, not a hosted platform.** Local-first control was the whole point of the
migration off Google Home — no cloud dependency for anything that can run on the LAN, cameras
included. See [`project_smarthome_architecture.md`](project_smarthome_architecture.md) for the
full hardware/protocol map and the original design rationale.

**Native YAML automations, not Node-RED.** The project started on Node-RED for its visual flow
editor, but every flow has since been rewritten as native HA automations in
[`automations.yaml`](automations.yaml) — one automation format to read, version, and test instead
of two. The old flow export is kept out of this repo; the migration itself is the interesting
part, not the legacy file.

**Frigate on a Mac Mini M1 via Colima, not a dedicated NVR appliance or a cloud camera plan.**
The Mac Mini was already-owned hardware, so the computer-vision layer runs there instead of buying
a Coral TPU box or paying for cloud NVR storage:
- **Colima over Docker Desktop** — a lighter, license-free Docker runtime on macOS, backed by
  Apple's `Virtualization.framework`. Tradeoffs surfaced and were worked through in production:
  Colima's VM needed explicit CPU/memory sizing (found capped at 4 CPU/6GB against the M1's real
  8-core/16GB — resizing to 6 CPU/10GB took combined detection throughput from 11.8 to 28.6 FPS
  across three camera feeds), and its virtiofs mount has host-edit staleness that required a small
  LaunchAgent-driven push workaround.
- **CPU-only detection over a Coral USB accelerator** — investigated and deliberately rejected:
  Docker on macOS has no native USB passthrough, and every VM-based workaround for it (Parallels,
  other Linux VMs) reports the Coral disconnecting every 15–30s. Properly resourced, the M1's CPU
  detector runs the model in 7–11ms per inference, which was fast enough — so the added hardware
  and complexity weren't worth it.
- **Frigate's built-in face recognition over a CompreFace + Double Take + InsightFace/FAISS
  pipeline** — the original, more elaborate architecture was designed and built, then abandoned
  after real OOM issues under Colima. What's running now is simpler, cheaper to run, and does the
  same job. Full evolution of that decision is in
  [`cameras/plan.md`](cameras/plan.md).

**Two-layer disable pattern for every automation** (room-level `input_boolean` + per-automation
`input_boolean`, plus a snooze-by-timestamp helper) so any automation can be suppressed instantly
from the dashboard without editing YAML — a small piece of UX design carried consistently across
~50 automations rather than bolted on per-automation as needed.

## Repo layout

```
HANDOFF.md                         — running engineering log: what shipped, what broke, what's next
BACKLOG.md                         — deferred/non-urgent work, pulled from when picking up new tasks
project_smarthome_architecture.md  — hardware inventory, protocol map, original design doc
blueprint_review.md                — equipment gap analysis against a reference "smart home blueprint"
dashboard.md                       — Lovelace dashboard architecture (mobile / kiosk / desktop)
test_plans.md                      — manual test instructions per automation
docs/automation_notes.md           — design notes for automation groups (HA strips YAML comments)

── Home Assistant Green (/config, pulled by tools/sync.py) ──
configuration.yaml                 — top-level config: packages, YAML-mode dashboards, notify group
automations.yaml                   — all HA automations (~100)
scripts.yaml                       — snooze system, find-phone, good-night scripts
helpers.yaml                       — YAML helpers (deployed as packages/helpers.yaml)
helpers_storage.yaml               — UI/ha-mcp-created helpers, exported read-only from .storage
packages/                          — MQTT-backed packages (bird tracker, code-enforcement OCR alert)
lovelace/                          — dashboard YAML (main, kiosk, desktop) + design mockups
themes/                            — kiosk theme
zigbee2mqtt/configuration.yaml     — Z2M coordinator + device list (keys redacted, IEEE IDs hashed)
custom_components.txt              — HACS integrations and versions

── Mac Mini M1 (Docker via Colima, pulled by tools/sync.py) ──
frigate/config/config.yml          — cameras, detectors, zones, masks, face recognition
frigate/docker-compose.yml         — Frigate + sidecar services; credentials come from .env
frigate/.env.example               — the variables the compose file expects
frigate/{start-frigate,autostart}.sh — boot + watchdog scripts (Colima virtiofs workaround)
frigate/bird_tracker/              — bird-feeder visit logger (Frigate MQTT → SQLite → HA)
frigate/code_enforcement/          — street-vehicle OCR detector (pHash de-dupe + EasyOCR)
frigate/vehicle_dashboard/         — Streamlit review UI for vehicle detections
frigate/sdcard_review/             — pulls clips straight off camera SD cards (outlives Frigate retention)
reid/                              — street-camera re-ID clustering (InsightFace + FAISS); dormant
                                     until the street camera is installed
statusportal/                      — Cloudflare Worker status page + heartbeat monitor
macmini/launchd/                   — LaunchAgents (Frigate watchdog, speedtest, UPS, heartbeat)
speedtest/ ups/                    — hourly speed test + UPS monitor → MQTT discovery sensors
cameras/plan.md                    — Frigate/computer-vision architecture, current hardware, gotchas

tests/                             — Python REST/MQTT test suite (run_all.py health | full suite)
tools/                             — sync, redaction filter, leak checker, git hooks
```

`HANDOFF.md` in particular is a real day-by-day debugging log, not polished documentation — kept
that way deliberately, since the root-cause investigations in it (a macOS Local Network privacy
permission silently blocking LAN traffic post-update; a Frigate face-recognition gap traced to bad
reference photos, not a config bug; a stuck MQTT subscription that looked identical to "no
traffic") are more representative of the actual engineering work than a cleaned-up summary would
be.

## A note on what's redacted

This repo is a real household's live configuration, published deliberately and filtered
mechanically rather than by hand:

- **Personal identifiers are pseudonymized.** Household members' names (including the ones baked
  into entity IDs like `person.riley_hollis`), the pet's name, the public hostname, email address,
  device MACs, the Tailscale address and a hardware serial are swapped for stable pseudonyms
  (`Riley`, `ha.example.net`, `mac-floodlight`, …) as files enter git. The live system uses the
  real values; the names you see here are consistent but not real.
- **Secrets never enter the repo at all.** Passwords, API keys and the Zigbee network key are
  stripped by `tools/sync.py` before files are written (`<redacted>`, `REPLACE_ME`, blank
  `.env.example`). Runtime code reads credentials from env vars or untracked files.
- **Zigbee IEEE addresses** are replaced with short stable hashes (`ieee-e32f3efda0`).
- **Excluded entirely** via `.gitignore`: biometric face-training photos, Frigate media and
  databases, the old superseded snapshot directory, and the legacy Node-RED export.
- **Kept as-is:** private LAN addresses (`192.168.x.x`) — not internet-routable and only
  meaningful on this network.

## Publishing safely (how the filtering works)

The working tree holds **real** values so the YAML stays deployable to Home Assistant unchanged.
A git [clean/smudge filter](https://git-scm.com/book/en/v2/Customizing-Git-Git-Attributes)
([`tools/redact.py`](tools/redact.py), enabled for every file by [`.gitattributes`](.gitattributes))
swaps real → pseudonym when content is staged and back on checkout, using a private map that lives
outside the repo (`~/.config/ha-repo/redact_map.tsv`). The filter is marked *required*, so if the
map is missing git refuses to stage rather than committing real values.

Three backstops check what will actually be published, i.e. the filtered content:

| Layer | What it checks |
|---|---|
| `pre-commit` → `check_leaks.py --staged` | staged blobs + file names: any real value from the map, known secret values (read from the untracked credential files), MACs, JWTs, private keys, Tailscale IPs, personal emails, inline passwords |
| `pre-push` → `check_leaks.py --range` | the same, over every commit being pushed, plus commit messages and author identity |
| GitHub Action (`leak-scan`) | gitleaks over full history on every push |

Routine workflow:

```bash
python3 tools/sync.py            # pull live HA + Mac Mini config into the repo
git diff                         # review (diffs show real values locally; git stores pseudonyms)
git add -A && git commit         # pre-commit hook scans
git push                         # pre-push hook scans
```

One-time setup on a new clone: `sh tools/setup.sh` (git config isn't versioned). After adding a
term to the map, run `git add --renormalize .` so already-tracked files are re-filtered.
