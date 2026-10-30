# Reolink Camera + Frigate Vision System — Current State

## Context

Local computer-vision layer: Reolink PoE cameras → Frigate NVR (Mac Mini, Docker/Colima) → Frigate's **built-in face recognition** (Frigate 0.17+) for known-person identification, plus custom Python services for vehicle/bird/code-enforcement detection. Everything publishes to Mosquitto on HA Green; HA automations trigger off `frigate/events` and the custom services' MQTT topics.

**This doc previously described a CompreFace + Double Take + InsightFace/FAISS re-ID architecture that was designed but subsequently abandoned.** CompreFace and Double Take were removed 2026-06-17 (OOM issues under Colima) in favor of Frigate's own face recognition. The re-ID clustering service (`~/reid/`) was built but is currently stopped, pending the street-facing camera that never materialized — kept in place, not deleted, in case that's revisited. What actually shipped is simpler and cheaper to run than the original plan.

---

## Live Hardware

| Camera | Model | IP | Role | Frigate objects tracked |
|---|---|---|---|---|
| Front Yard | CX810 (8MP, F1.0, true color no-IR) | `192.168.68.139` | Front yard + road | person, car |
| Backyard | RLC-1212A (12MP, F1.6) | `192.168.68.144` | Backyard + bird feeder | person, dog, bird |
| **Front Yard Floodlight** (new) | Reolink Floodlight | `192.168.68.100` | **Replacing CX810 as the front-yard camera** — CX810 will be repositioned elsewhere once this is tuned in. See "Floodlight Project" below. | TBD |

Admin creds and RTSP paths live in `~/frigate/.env` (not in this repo). Standard Reolink RTSP path: `rtsp://admin:{pass}@{ip}:554/h264Preview_01_main` (main) / `..._sub` (detect stream).

**Not built / abandoned, despite earlier plans:**
- Street-facing camera + face/vehicle re-ID clustering (InsightFace/FAISS) — service exists at `~/reid/` but is stopped; no street camera was ever installed.
- Reolink Video Doorbell / "Casey arrival via face match" automation — never built.
- Right-side/rear-entry camera — never installed.

---

## Software Architecture (as actually running)

```
MAC MINI (192.168.68.142, Docker via Colima)
  ├── frigate            — NVR, built-in face_recognition, port 5050 (web UI + API)
  ├── code-enforcement    — OCR (EasyOCR) + pHash vehicle fingerprinting, watches road_zone
  ├── bird-tracker        — backyard bird_feeder zone classification
  ├── vehicle-dashboard   — Streamlit review UI, port 8501
  └── reid-service        — built, currently stopped (no street camera)
        │
        ▼ MQTT (frigate/events, code_enforcement/*, birds/*)
Home Assistant Green (192.168.68.3)
  - cam_* automations (see automations.yaml) — identity + zone based alerts/lighting
  - code_enforcement_vehicle_alert, bird_new_species_alert
```

Frigate config lives on the Mac Mini at `~/frigate/config/config.yml` (edit this) → pushed into the running container as `/config/config.yaml` via:
```bash
cat ~/frigate/config/config.yml | docker exec -i frigate tee /config/config.yaml > /dev/null
docker compose restart frigate
```
A LaunchAgent (`com.frigate.startup`) re-pushes this automatically every 5 min and on login, to work around Colima virtiofs staleness.

**Frigate face recognition** (replaces CompreFace/Double Take): known faces registered via `POST /api/faces/{name}/register` (multipart image upload, Frigate does its own detection/crop) or deleted via `POST /api/faces/{name}/delete`. Current known people: Riley, Casey. Reference photo quality matters a lot — see `HomeAssistant/HANDOFF.md` for the 2026-07-07 fix where 3 bad Riley reference photos (obscured/distorted) were silently causing a 0% match rate.

---

## Network

| Device | IP | Notes |
|---|---|---|
| Mac Mini (Frigate host) | `192.168.68.142` | Docker/Colima; Frigate UI at `:5050` (not `:5000` — macOS AirPlay occupies 5000) |
| Netgear GS308Ev4 (managed switch) | `192.168.68.2` | Mac Mini + HA Green + TP-Link PoE switch all hang off this |
| TP-Link PoE switch | — (no known mgmt IP) | Feeds the Reolink cameras only |
| Front Yard camera (CX810) | `192.168.68.139` | To be repositioned once floodlight is live |
| Backyard camera (RLC-1212A) | `192.168.68.144` | |
| Front Yard Floodlight (new) | `192.168.68.100` | Native Reolink HA integration already configured; Frigate integration pending |

---

## Face Recognition — Known People

Registered via Frigate's own face library (`/media/frigate/clips/faces/<Name>/` inside the container), not CompreFace:
- **Riley**: 4 reference photos (fixed 2026-07-07 — see HANDOFF.md)
- **Casey**: 5 reference photos

Automations branch on `sub_label` in the `frigate/events` MQTT payload (e.g., `cam_riley_backyard_mode` triggers on `sub_label == 'Riley'`).

---

## Floodlight Project (live as of 2026-07-07)

**Front Yard Floodlight** (`192.168.68.100`) is now onboarded to Frigate (`front_floodlight` camera, person+car tracking, first-draft `yard_zone`/`driveway_zone`) and has 8 automations covering night-baseline dimming, identity-aware welcome/alert lighting, animal notification, unexpected-vehicle alerting, and an opt-in loitering siren escalation. Added to all three dashboards. Full detail in `HomeAssistant/HANDOFF.md` (2026-07-07 entry) — not duplicated here.

Still open: CX810's new location (TBD — currently still running as `front` in Frigate), and the `yard_zone`/`driveway_zone`/`street_zone` polygons need redrawing once the floodlight is physically mounted/aimed in its final position (current ones are from single snapshots). `dog` tracking added 2026-07-07 (Biscuit appeared in-frame during a walk-test but wasn't logged). Light-escalation automations (welcome/unknown-person) are now night-only (`condition: sun`) — the passive baseline dimming already was, but the person-triggered ones weren't originally, causing a daytime false trigger the same day.

**Now also a code-enforcement OCR source**: `front`'s `road_zone` only captures a thin sliver of curb vehicles (steep yard slope, no optical zoom); the floodlight's `street_zone` frames them much better. A second `code-enforcement-floodlight` service instance watches it, sharing the same DB as the original — see `HANDOFF.md` 2026-07-07 for the MQTT-client-ID gotcha this required fixing.

---

## SD Card Review Helper (added 2026-07-08)

`front` and `front_floodlight` have onboard SD cards (~119GB / ~59GB, AI-triggered recording, ~7-9 days retention) — `backyard` doesn't. `~/frigate/sdcard_review/sdcard_review.py` pulls clips directly from a camera's SD card via its own HTTPS API (search/download/extract-frames), completely bypassing Frigate and Mac Mini storage. On-demand review tool, not a service — nothing runs continuously or persists. Use it when a Frigate thumbnail alone isn't enough to judge something, or when investigating past what Frigate has already purged. `floodlight` downloads currently 404 (search works, some path-format difference vs. `front` not yet resolved) — `front` works correctly.

**Capability correction:** the floodlight is **tunable white only** (`supported_color_modes: ["color_temp"]`, 3000K–6000K) — not full RGB/hue color despite it having "different hues" in casual description. Automation design leans on color-temperature + brightness + the built-in AI person/vehicle/animal binary sensors, not arbitrary color.

---

## Known Operational Gotchas (carried forward, still relevant)

- **CX810 stability**: needs RTSP-over-TCP (`input_args: preset-rtsp-restream`) — direct/UDP is unstable.
- **Frigate port is 5050, not 5000** — macOS AirPlay Receiver occupies 5000 and intercepts traffic.
- **Frigate reads `config.yaml`, edit `config.yml`** — the push step renames on deploy; editing the container's `config.yaml` directly gets overwritten by the next LaunchAgent push.
- **OCR gotcha**: use `/thumbnail.jpg` not `/snapshot.jpg` for any image-based classification — snapshot burns in Frigate's bounding-box label text.
- **`required_zones` is not a valid Frigate 0.17 field** — don't reintroduce it.
- **ExFAT storage**: Frigate media on `/Volumes/Primary/HomeAssistant/frigate` (external drive) — no Unix permissions/symlinks, this is expected and not a bug.
- **macOS Local Network privacy permission** (System Settings → Privacy & Security → Local Network) can silently block a whole app's LAN access after an OS update, with symptoms that look exactly like a network/router/switch problem. Check this **first** before deep network diagnosis — see HANDOFF.md 2026-07-07 entry for the full story.

---

## Roadmap

Active phased roadmap (false-positive tuning → behavior-driven lighting → Claude-assisted review dashboard, package detection on backburner) lives at `/Users/homeuser/.claude/plans/i-want-to-see-swift-volcano.md`, not duplicated here. Phase 0 (tuning) is complete as of 2026-07-07.

---

## Future Ideas (not started)

**Copperhead snake detection** (raised 2026-07-07): recurring real concern on the property. **Not a config/resolution problem** — the `cpu` detector's stock model is COCO-trained, and COCO has no snake/reptile class at all, so no threshold or zone tuning can produce a detection that the model has no output for. Even with a hypothetical snake-capable model, resolution would be a real secondary problem given how thin/ground-level/camouflaged snakes are versus the cameras' high overhead mounting. Would need a custom-trained detector (adapted wildlife/herpetology model, or trained from scratch) — a separate ML project, not something to casually bolt on. Revisit if frequency/risk escalates or a usable pre-trained model surfaces.
