# Backlog

Things worth revisiting that aren't urgent enough to act on immediately. Not a roadmap with phases/order — just a parking lot so open items survive between sessions instead of living only in conversation history. Pull items out of here when you want to tackle them; add a line whenever something gets flagged but deliberately deferred.

Mark items `[x]` with a date when resolved, or delete once genuinely done and written up elsewhere (HANDOFF.md).

---

## HA Core Health

These have failed *every* `python3 run_all.py health` run since at least 2026-07-07 — none are camera-related, all got silently deprioritized while camera work was happening.

- [ ] `sensor.indoor_tree_soil_moisture_soil_moisture` pinned at 99.99% — very likely disconnected/dead sensor, not a real reading. Check physical sensor.
- [ ] `sensor.green_giant_soil_sensor_soil_moisture` reading ~91%, flagged as anomalously high every run — check placement/calibration.
- [ ] `light.back_left` — `unavailable` all session.
- [ ] `sensor.breaker_panel_watts` — `unavailable` all session.
- [ ] `input_boolean.automations_bedroom` is `off` — bedroom automations have been suppressed the whole time. Confirm this is intentional (vacation/travel?) or turn back on.

## Camera / Frigate Follow-Ups (flagged 2026-07-07/08)

- [ ] **Riley face recognition still unreliable** on `front_floodlight`/`backyard` — a live walk-test showed 84% person-confidence but no face match, even after registering 4 clean reference photos. Needs either a genuinely frontal-facing capture to register, or accept the limitation for departures/casual movement.
- [ ] **Floodlight zone geometry is first-draft** — `yard_zone`/`driveway_zone`/`street_zone` on `front_floodlight` were drawn from single snapshots before final mounting. Redraw once its position is locked in.
- [ ] **CX810 relocation still undecided** — currently still running as `front` in Frigate; floodlight is meant to replace it as the primary front-yard camera.
- [ ] **Code-enforcement target vehicle: still zero confirmed captures** — as of 2026-07-13, pipeline fully re-verified end-to-end (see HANDOFF.md same date) right before an expected Monday pass. A real stuck-MQTT-subscription bug was found and fixed on the `front`/`road_zone` source (silently dead 4+ days) — genuinely unknown how much prior traffic was missed because of it. Both sources confirmed live now.
- [ ] **No monitoring for a silently-stuck code-enforcement subscription** — the 2026-07-13 bug (container alive, MQTT "connected," but zero detections logged for 4+ days, no error anywhere) would only get caught by manually checking logs, which doesn't scale. Worth adding a simple watchdog: e.g., an HA automation or cron check alerting if `code_enforcement/last_seen`-style heartbeat topics go quiet for longer than some threshold, or just a periodic `docker logs --since` sanity check.
- [ ] **Bird tracker has logged zero sightings, ever** — worth checking whether `bird-tracker` service is actually working (config/zone issue?) or silently broken. The dashboard has a whole section presumably showing nothing.
- [ ] **`known_vehicles` fingerprint library is rebuilding from scratch** (cleared 9 bad ones 2026-07-07) — deliberately re-tag real vehicles from clear, mostly-in-frame captures via the Vehicles tab as they come up naturally. One (`#85`, pickup truck) already re-added 2026-07-08.
- [ ] **`floodlight` SD card downloads return 404** (`search` works fine) — some path-format difference vs. `front`'s relative paths, not investigated. Low priority since `front` (the camera actually used for reviews) works.
- [x] **Floodlight notification images use a LAN-only URL** — fixed 2026-07-08 (front/backyard/floodlight person alerts) and 2026-07-13 (code-enforcement alert, found while doing today's pre-flight check). All camera-related phone notifications now use the remote-accessible `ha.example.com` proxy.
- [ ] **Why did front's notification image "work" while backyard's didn't**, given both had the identical missing-`.jpg` bug? Fixed the reproducible issue (both now use `.../snapshot.jpg`) but never resolved why the user only noticed it on backyard specifically. Worth a real-world check next time both cameras fire an unknown-person alert.

## Bigger, Not-Yet-Started

- [ ] **Roadmap Phase 1 — behavior-tracker service** (approach/loiter/pass-by classification, finally implements the dormant Biscuit-vs-coyote zone-entry design). See `/Users/homeuser/.claude/plans/i-want-to-see-swift-volcano.md`.
- [ ] **Roadmap Phase 2 — general identity+behavior lighting tiers.** The porch/floodlight automations built 2026-07-08 are a hand-built instance of this idea for one camera, not the generalized system the roadmap describes.
- [ ] **Claude Suggestions dashboard tabs — Bird Sightings and Faces** not built (only Vehicles exists). Bird tab is moot until sightings actually exist (see above).
- [ ] **Package/carrier detection** — deferred to backburner in the roadmap doc; revisit if wanted.
- [ ] **Snake (copperhead) detection** — see `cameras/plan.md` "Future Ideas" and the `project_snake_detection` memory. Blocked on a real model gap (no reptile class in COCO), not a config tweak — needs a custom-trained detector. Not started, and not a small lift.

## Camera / Frigate Follow-Ups (flagged 2026-08-09)

- [ ] **No DHCP reservation for `front_floodlight`** (MAC `mac-floodlight`) — after its ~25h outage and physical reboot on 2026-08-09, it came back on `.137` instead of its old `.100`, breaking the hardcoded `CAMERA_FLOODLIGHT_IP` in `.env` until caught manually. Set a reservation via the Deco app so this can't silently recur on the next reboot.
- [ ] **CPU detector headroom is thin even after the 2026-08-09 Colima resize** (4→6 CPU, 6→10GB) — combined `detection_fps` reached 28.6 under full 3-camera load, which is workable but not spacious. Do not add more cameras without either a further Colima bump (2 CPU/6GB still in reserve) or dedicated detection hardware — Coral USB was researched and ruled out as non-viable on this Mac (no Docker USB passthrough on macOS).

## Infrastructure Hardening

- [ ] **`~/.mqtt_pass` is a single point of failure with no alerting** — the Mac Mini speedtest launchd job (`com.rileyhollis.speedtest`) went silently broken for ~5 weeks (2026-08-10 to 2026-09-14) because this uncommitted secret file was missing, and nothing surfaced the failure until the user noticed the dashboard graph had gone flat. `test_health.py`'s new `test_speedtest_freshness` now catches this on the next manual test run, but there's still no *automatic/alerting* path (a notification, an HA repair, etc.) — only a human running the test suite. Worth deciding whether this needs a real alert or if periodic manual health checks are enough. Consider the same question for any other script that depends on this file.

## Local LLM

- [ ] **HA Assist — local Ollama conversation agent to replace Google Home voice control.** Deferred until Google Home hardware is actually being swapped out; not a small lift (intent/tool-calling setup, HA's Ollama integration config, mic/speaker hardware decisions). Local Ollama + Qwen2.5-7B-Instruct was set up on the Mac Mini 2026-10-06 for general use first — same install can be pointed at HA's Assist pipeline later, but likely wants a smaller/faster model tuned for tool-calling rather than the general-use 7B.

## External / Not Mine to Fix (tracked here so they don't get lost)

- [ ] **Front door lock (August Lock)** — `lock.front_door` / `binary_sensor.front_door_door` unavailable, cloud-based integration, likely needs re-authentication in HA (Settings → Devices & Services).
- [ ] **Backyard flood light Zigbee signal** — `switch.outdoor_gang_switch_l3` had LQI 72 (weak), user relocating the device to improve signal. Automation (`camera_backyard_floodlight_on_motion`) is already correctly built and needs nothing further once signal improves.
- [ ] Remaining integrations from `HANDOFF.md` "What's Next": Kasa (TP-Link plugs), Leviton LWHEM (HACS), Google Cast.
- [ ] MagicMirror project — separate, deferred until HA is fully stable.
