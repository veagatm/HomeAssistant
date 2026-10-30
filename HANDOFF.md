# Home Assistant Setup — Session Handoff

## Current State (as of 2026-05-15)

### RESOLVED — Mac Mini Host Cannot Reach LAN Peers (2026-07-07)

**Root cause found:** macOS's **Local Network privacy permission** (System Settings → Privacy & Security → Local Network) was off/revoked for the app hosting the Claude Code session (VS Code) — likely reset by the recent macOS software update (`26.5.2`). This is a per-app entitlement, separate from the Application Firewall, `pf`, VPN extensions, or any network config file — it silently blocks that app's outbound connections to LAN/RFC1918 addresses while leaving default-gateway/internet-bound traffic untouched, which is exactly why the gateway (`.1`) always worked while every other LAN peer didn't, and why it survived a full reboot and even a full network-preferences wipe (this permission lives in TCC, not `/Library/Preferences/SystemConfiguration/`). **Fix:** enabled the toggle for the app in that System Settings pane. Immediately after, `HA Green :8123` returned `HTTP 200`, both camera RTSP ports connected, ping succeeded at 0% loss, and `ha-mcp` started working again.

**If this ever recurs after a future macOS update:** check System Settings → Privacy & Security → Local Network *first*, before repeating any of the steps below — this should have been step 1.

**Everything else tried below turned out to be unnecessary** (kept only so they're not blindly repeated if a *different* future issue looks similar — this list is not a diagnostic checklist to reach for by default):

**Symptom:** The Mac Mini's native macOS network stack can reach the LAN gateway (`192.168.68.1`) but cannot reach *any* other LAN peer — not the Netgear switch's own management IP (`.2`), not HA Green (`.3`), not either camera (`.139`, `.144`). This is specific to the host OS itself: Frigate/Docker (via Colima's separate Virtualization.framework NAT path) reaches all of these fine, and other devices on the LAN (HA Green, phones) can reach the Mac Mini fine — it's a one-directional, host-specific failure.

**Trigger context:** Surfaced during/after two infrastructure changes happening around the same time: (1) ISP migration to Google Fiber — chain is now `gFiber ONT → Fiber Router → Deco → Netgear GS308Ev4 → Mac Mini`, with Netgear also feeding the TP-Link PoE switch (cameras); Mac Mini's Wi-Fi also consolidated onto the main home SSID; (2) a macOS software update to `26.5.2`. Neither has been proven as the actual cause.

**Full list of things tried, all ruled out (none fixed it — don't repeat these):**
1. Camera IP/DHCP change — ARP-swept the whole DHCP pool; both cameras' MACs (`mac-cam-front` front, `mac-cam-backyard` backyard) confirmed still bound to their original IPs.
2. Stale ARP cache — flushed via `sudo arp -d`; came back `incomplete` (fresh requests sent, zero replies), later came back with correct real MACs resolved, but the kernel still refused to send (`sendto: No route to host` / `EHOSTUNREACH`) despite a valid ARP entry and a clean, correctly-flagged routing table entry (verified via `route -n get`, no reject/blackhole flags).
3. Wi-Fi vs. Ethernet interface confusion — ruled out; identical failure on both interfaces, no duplicate default routes, no leftover VPN routes, Wi-Fi confirmed fully inactive when on Ethernet.
4. Active VPN/killswitch — ProtonVPN confirmed disconnected via `scutil --nc list`.
5. macOS Application Firewall — confirmed disabled.
6. Router-side client/device isolation — confirmed OFF in the Deco app for the Mac Mini and both cameras.
7. Mis-wired topology from the gFiber install — user confirmed the physical chain matches the documented one exactly.
8. Netgear GS308Ev4 power cycle — done, no change.
9. Internet Sharing/NAT — confirmed unconfigured (`com.apple.nat.plist` empty).
10. `pf` packet filter — confirmed `Status: Disabled`, empty ruleset (`sudo pfctl -s all`).
11. Tailscale + ProtonVPN network extensions — found both "activated enabled" via `systemextensionsctl list` (Tailscale itself was unexpectedly logged out / `NeedsLogin` — a separate real issue, needs re-login next time HA remote access via Tailscale is needed); disabled both, no change to the LAN reachability issue.
12. Full network preferences wipe (`rm /Library/Preferences/SystemConfiguration/{preferences,NetworkInterfaces}.plist`) + reboot — the most invasive standard fix for this class of issue — **no change**.
13. New switch port + new Ethernet cable on the Netgear switch — **no change**. This rules out the physical layer (cable, switch port) entirely.
14. IP-layer counters (`netstat -s -p ip`) show 0 "discarded due to no route" and 0 "dropped due to NECP policy" — the failure isn't showing up in kernel accounting at a level readable without root. `log show` (via `/usr/bin/log`, since `log` is shadowed by a shell builtin in this environment) returns no matching entries even with broad predicates — likely redacted as private data without root.

**Separately, still worth doing:** Tailscale was found logged out (`NeedsLogin`) during this investigation and was disabled along with ProtonVPN mid-diagnosis — re-enable Tailscale (System Settings → Login Items & Extensions → Network Extensions) and log back in next time HA remote access via Tailscale (`100.64.0.10`) is needed. ProtonVPN can stay disabled/enabled per personal preference, unrelated to HA.

Full phased roadmap for FP tuning + behavior-driven lighting + Claude-assisted review dashboard (package/carrier detection deferred to backburner) is written up separately at `/Users/homeuser/.claude/plans/i-want-to-see-swift-volcano.md`. Phase 0 (false-positive tuning) is now complete — see "What's Done" below.

### What's Done
- [x] **Repo made publish-safe and complete; first push to the public GitHub repo (2026-10-30)**: audit found no live secrets but several personal leaks in newer docs (email, camera MACs, Tailscale IP, real names) and a sizeable local-vs-live drift (2 automations missing locally, 1 stale, 2 dashboard views, UI helpers untracked, no `configuration.yaml`/Z2M/Frigate in the repo at all).
  - `tools/sync.py` pulls live HA `/config` (incl. `.storage` helpers → `helpers_storage.yaml`, Z2M with keys redacted + IEEE IDs hashed) and the Mac Mini stack (`frigate/`, `reid/`, `statusportal/`, `macmini/launchd/` with API key blanked). Live is truth; local copies now match it.
  - Personal identifiers handled by a required git clean/smudge filter (`tools/redact.py`, private map at `~/.config/ha-repo/redact_map.tsv`): working tree keeps real entity IDs, git stores pseudonyms. `tools/check_leaks.py` runs as pre-commit + pre-push hooks; gitleaks GitHub Action as server-side backstop.
  - HA strips YAML comments on save, so the old inline automation/script notes moved to `docs/automation_notes.md`. Noted while syncing: `reid-service` container is crash-looping (street camera not installed).
- [x] **Govee outdoor string lights ("outdoor color lights", `light.h702b`) onboarded — wired into backyard motion + manual outdoor on/off, added to both dashboards (2026-10-08)**: user added the light via the `govee_light_local` integration (researched the prior session — confirmed-supported model, no manual pairing needed beyond enabling LAN Control in the Govee app) and asked for it to join the existing outdoor automations plus the dashboard's Outdoor group controls. Asked one clarifying question first (physical location — Porch/Backyard/Driveway/manual-only all imply different automation wiring); user confirmed **Backyard**.
  - Added `light.h702b` to `automation.camera_backyard_floodlight_on_motion` (motion-triggered, night-only, 10-min auto-off — same lifecycle as `switch.outdoor_gang_switch_l3`, via a parallel `light.turn_on`/`light.turn_off` action since it's a different domain/service than the switch) and to both `automation.lr_button_4_single_outdoor_lights_on` / `_double_outdoor_lights_off` (the 4-way button's manual "all outdoor lights" on/off). Deliberately **not** added to the carport/rear-floodlight motion automations (different physical zones) or the dimmable-floodlight brightness-escalation automations (`floodlight_night_baseline_on`, `floodlight_welcome/unknown_person_light`) — those are a conceptually separate tiered-brightness subsystem for `light.front_yard_floodlight_floodlight` + `light.porch`, not something to fold a decorative RGBIC string light into without being asked.
  - Dashboard: added a `mushroom-light-card` (brightness + color temp + color, matching the existing `light.living_room` card's control set) to the Backyard section in **both** `lovelace/views/02_rooms.yaml` (main Rooms dashboard) and `lovelace/desktop/desktop.yaml` (Desktop dashboard) — the two files that actually contain this Outdoor/Backyard group (confirmed by grep; `07_cameras.yaml`'s "Backyard" matches are the camera feed section, unrelated). Also added `light.h702b` to the Rooms dashboard's "N lights on" Outdoor tile summary template so the count stays accurate. Deployed both via the documented SCP workflow (YAML-mode dashboards, no restart needed).
  - `automations.yaml` mirror updated for all 3 automations. `test_health.py`: added `light.h702b` to `CRITICAL_ENTITIES` (no automation count change — existing automations modified, none added). `python3 run_all.py health` passes for everything touched (2 pre-existing unrelated failures remain: bedroom room-toggle drift, stale soil sensor; also noted `cover.living_room_blinds` and `light.front_left` showing transient `unavailable`, not investigated, unrelated to this work).
  - **Researched and explicitly ruled out** (previous session): the user's other new device, a Govee Kitchen Composter, has no path into HA — not supported by `govee_light_local` (lights-only) or `govee2mqtt` (checked its SKU list directly), and no official/cloud/community integration exists for it anywhere. Stays Govee-app-only until that changes.
- [x] **`front_floodlight` yard_zone/driveway_zone redrawn — trimmed out of both neighbors' yards (2026-09-30)**: user reported ongoing false alerts from the front floodlight camera and asked to trim detection so the left/right neighbors' yards aren't captured. These zones had never been redrawn since initial placement — the config's own comment called them "first-draft... taken before final physical mount/aim," over a year stale.
  - Pulled a fresh live snapshot from `/api/front_floodlight/latest.jpg` and visually identified landmarks: the left edge of `yard_zone` (previously starting at x=0.07) overlapped the dense tree cluster and, past it, the left neighbor's shed/bin area already called out in this camera's own person-filter mask ("trash can near neighbor's shed"). `driveway_zone`'s right edge ran to x=0.98, past the parked truck into what the frame shows as the right neighbor's side.
  - Trimmed `yard_zone` left edge from x=0.07→0.24 (past the tree-line divider) and `driveway_zone` right edge from x=0.98→0.91 (just past the truck's parking spot); y-coordinates and `street_zone` left untouched (the complaint was specifically left/right yard bleed, not the street strip). Backed up `config.yml` first (`config.yml.bak.20260930_143820`), pushed via the documented `cat config.yml | docker exec -i frigate tee /config/config.yaml` + `docker compose restart frigate` workflow, verified via `/api/config` that the new coordinates are live and via `/api/stats` that all 3 cameras (front, backyard, front_floodlight) came back healthy. `code-enforcement`/`code-enforcement-floodlight` containers were untouched by the restart (their own separate MQTT connections, confirmed still `Up`).
  - **Not verified yet**: this is a best-effort visual trim from a single still frame, not a surveyed property line — same "first-draft, expect to redraw" caveat as the original zones. Worth watching the next few real detections (or comparing against the Frigate UI's live zone overlay) to confirm it doesn't now clip real activity on this side of the yard.
- [x] **Kasa Rear Flood Light: faster motion trigger, reacts to vehicles too (2026-09-30)**: user reported the Kasa floodlight (`switch.rear_flood_light`) turns on noticeably late when backing a vehicle down the driveway — only after they get out and walk into frame. First asked a clarifying question (their description of "turns on once it increases brightness" didn't match this switch's actual automation, which has no brightness logic — that description fits the separate dimmable Reolink floodlight's escalation automations); user clarified they don't want the switch mirroring that dimmable light's always-on dusk baseline, just a faster, more sensitive motion reaction.
  - Root cause found in `automation.camera_rear_floodlight_on_motion`'s Frigate MQTT condition: it only matched `label == 'person'`, so a car pulling into the driveway (zone: `driveway_zone`/`yard_zone` on the `front_floodlight` camera) never triggered anything — it waited for Frigate to track a *person* after the driver got out. Added `'car'` alongside `'person'` for the front_floodlight zones (backyard stays person-only — no vehicle traffic there). Also added Frigate's `'new'` event type to the existing `['update', 'end']` filter, so it fires on the very first sighting of a track instead of waiting for the first periodic update.
  - `automations.yaml` mirror updated to match. No automation count change, `python3 run_all.py health` passes (room toggles now back on via the daily safety-reset automation built 2026-09-14; only the pre-existing soil sensor failure remains, plus a new transient `cover.living_room_blinds` unavailable warning — not investigated, unrelated to this change).
- [x] **Fixed a silently-broken 5-week-old speedtest outage (found while investigating a new request) — `~/.mqtt_pass` had gone missing (2026-09-14)**: user asked how to set up automated internet speed tests trended in HA. Before building anything, should have checked for existing infrastructure first — didn't, and built a whole parallel Docker/MQTT/Ookla-CLI service (`~/frigate/speedtest/`) before discovering, via the dashboard YAML, that a complete system already existed: `com.rileyhollis.speedtest` (launchd, hourly, `~/Desktop/claude_code/HomeAssistant/speedtest/speedtest_push.py`, Cloudflare speed.cloudflare.com) feeding `sensor.mac_mini_speed_test_{download_speed,upload_speed,speedtest_ping}`, with history-graph and statistics-graph cards already built in `06_energy.yaml`.
  - **Root cause of the outage**: `~/.mqtt_pass` (an intentionally-uncommitted secret file the script reads its MQTT password from) had gone missing — every hourly run since **2026-08-10** had been failing with `FileNotFoundError`, confirmed via `/tmp/speedtest_push.err`. The dashboard had been silently showing a 5-week-old value with no visual indication anything was wrong (no availability/staleness indicator on those cards). Recreated the file from the password already on hand in `~/frigate/.env` (`MQTT_PASSWORD`, same broker), `chmod 600`, then verified via a manual run and a `launchctl kickstart` through the real scheduled path (exit status flipped 1→0, fresh data confirmed in HA).
  - **Why the existing system beats what I'd built**: its own header comment documents that Ookla's CLI wouldn't build via Homebrew on this Mac, and `speedtest-cli`'s nearest-server logic returned bogus Canadian servers for this Google Fiber IP block — exactly the class of problem my Ookla-CLI-based replacement would have hit again. Tore down the duplicate (`docker compose down speedtest`, removed the image, deleted `~/frigate/speedtest/`, reverted the `docker-compose.yml` addition) and cleared the retained MQTT discovery/state topics it had published (empty retained payloads) — confirmed no `sensor.speedtest_*` entities were ever actually created, so no HA-side registry cleanup was needed.
  - **Added `test_speedtest_freshness` to `test_health.py`** — asserts `sensor.mac_mini_speed_test_download_speed` updated within the last 3 hours (job runs hourly), specifically to catch a repeat of this exact failure mode instead of relying on a human noticing a flat graph. Also added the sensor to `CRITICAL_ENTITIES`. `python3 run_all.py health` passes for everything touched (2 pre-existing unrelated failures remain: room toggles off, indoor tree soil sensor pinned at 99.99%).
  - **Flagged to BACKLOG.md**: `~/.mqtt_pass` is a single point of failure with no automatic alerting — the new test only catches this on the next manual run, not proactively. Worth deciding later whether that's sufficient.
- [x] **Living Room motion upgraded from PIR to mmWave (Sonoff SNZB-06P); 4-way button payload format corrected (2026-09-14)**: user paired a new "mmw motion sensor" (Sonoff "Zigbee occupancy sensor" / SNZB-06P) and asked what it could do and where it should go.
  - **Real capability difference, not just a new device**: exposes `binary_sensor...occupancy` via mmWave radar (detects stillness/breathing, doesn't need gross movement to stay "occupied" the way PIR does), `number...occupancy_timeout` (15–65535s internal hold, set to 120s), `select...occupancy_sensitivity` (low/medium/high, set to medium), and `sensor...illumination` (lux). No battery entity — mains/USB powered.
  - **Recommended and placed in Living Room**, not Bedroom/Kitchen/Hallway: the existing `lr_no_motion_10_min_lights_off` automation already special-cases Roku playback (skips the timeout while watching TV) but had no protection for someone sitting still *without* the TV on (reading, working, talking) — a real gap PIR can't close and mmWave can. User confirmed a **full swap** (not a hybrid with the existing Aqara PIR) specifically so the freed-up Aqara sensor can be relocated to another room later (room TBD).
  - Swapped the sensor in **all 4** Living Room automations that referenced it — found the 2 obvious ones (`lr_motion_on_lights`, `lr_no_motion_10_min_lights_off`) plus 2 more via a full-text grep of `automations.yaml` that a live entity-reference search missed (`lr_tv_playing_movie_mode`'s brightness-by-illuminance template, `lr_tv_off_restore`'s occupancy condition) — templated references don't show up in HA's reference-graph search, so the local YAML mirror was the more reliable source for finding every usage. Device assigned to the `living_room` area.
  - `automations.yaml` mirror updated (5 total string replacements across those 4 blocks). `test_health.py` CRITICAL_ENTITIES: replaced `binary_sensor.living_room_motion_sensor_occupancy` / `sensor.living_room_motion_sensor_illuminance` with the new `mmw_motion_sensor` equivalents (old Aqara entities dropped from the critical list since they no longer drive anything until relocated). `python3 run_all.py health` passes for everything touched — new sensor reads "unknown" until it detects its first real presence event, which is expected right after pairing.
  - **Not yet done**: destination room for the freed-up Aqara PIR sensor — user said "another room probably" but hasn't decided. When they do, that sensor's entity_id/friendly name should probably be renamed off "living_room_*" to avoid confusion (follow the safe-refactoring workflow — check dashboard/automation references first).
  - **Follow-up same day**: user asked why occupancy wasn't reading. Pulled the device's actual Z2M interview payload (via supervisor add-on logs) rather than guessing — root cause was twofold: (1) this SNZB-06P's `illumination` field is explicitly documented as "only updated when occupancy is detected," so both fields legitimately staying blank ~25 min after pairing just meant nobody had walked in front of it yet, not a binding/config failure (a `zigbee2mqtt/bridge/request/device/configure` reconfigure was tried first and returned `status: ok`, but wasn't actually the fix). (2) **Real bug found in the swap above**: `illumination` is a two-value **enum** (`dim`/`bright`), not a numeric lux reading like the old Aqara sensor — the numeric `| float(0) < 100` / `| float(100) > 80` comparisons carried over from the Aqara-based templates would have silently always evaluated as "dark" (string-to-float fallback = 0), never correctly gating on brightness. Fixed both: `lr_motion_on_lights`'s illuminance gate is now a native `condition: state ... state: dim`; `lr_tv_playing_movie_mode`'s brightness template now compares `== 'bright'` directly. Local `automations.yaml` mirror updated to match both fixes.
  - **Also fixed while testing the 4-way button** (see entry below): the real Z2M action payload format is `<gesture>_button_<n>` (e.g. `double_button_1`), not `<n>_<gesture>` as originally assumed — corrected across all 12 button automations after the user reported real MQTT traffic.
- [x] **LR 4-way Sonoff button onboarded — 12 automations syncing Living Room + Kitchen modes, plus dedicated blinds control (2026-09-14)**: user paired a new Sonoff "Four-way wireless button" (Z2M device, named "4 way button"), placed physically in the Living Room, and asked for it to control both Living Room and Kitchen lighting modes together (synced), plus dedicated blind buttons.
  - Confirmed via device registry: `SONOFF Four-way wireless button`, Zigbee2MQTT-only (no ZHA), exposes battery/linkquality/update entities but no "action" entity — button presses fire over MQTT (`zigbee2mqtt/4 way button/action`) exactly like the existing bedroom Aqara switch, not as HA entities. Assigned device to the `living_room` area.
  - **Built all 12 actions** (4 buttons × single/double/hold) as 12 separate storage-mode automations (`lr_button_<n>_<gesture>_...`), matching the existing `bed_switch_*` one-automation-per-gesture convention rather than one combined automation:
    - **Button 1** (lights): single = synced toggle of all 4 LR+Kitchen light entities based on `light.living_room`'s state; double = cycles both rooms' `input_select.lighting_mode_*` together through Normal→Working→Casual→Chill→Movie→Party; hold = `script.good_night_all`.
    - **Button 2** (mode jumps): single/double/hold = Casual/Chill/Movie, applied to both rooms at once. Unlike the passive mode-change automations (which only react while the room light is already on), these explicitly call `light.turn_on` with the matching `input_number.mode_*_brightness/color_temp` helper values first, so the button works even from an off state. Chill also sets both blinds to 50%.
    - **Button 3** (blinds, dedicated): single = open both, double = close both, hold = set both to 50% — independent of lighting mode, a manual override.
    - **Button 4** (party/away): single = Party mode for both rooms, each keeping its own `input_select.party_color_living_room`/`_kitchen`; double = advances each room's own party color to the next in an 8-color list and reapplies immediately; hold = toggles `input_boolean.away_mode_active`.
  - **Deliberately no room-toggle gating** (`input_boolean.automations_living_room`/`_kitchen`) on any of the 12 — matches the existing bedroom switch precedent that a physical button press is an intentional action and should bypass the passive-automation kill switch.
  - **Unverified assumption, flagged to user**: the Z2M action payload format (`1_single`, `2_hold`, etc.) is the standard Sonoff 4-button convention, not confirmed against this specific device's live MQTT traffic (no Z2M web UI access from this session). User needs to physically test each of the 12 and report back if any gesture doesn't fire — the fix would just be correcting the `payload:` string on that one automation.
  - `automations.yaml` mirror updated (new "LR 4-Way Button" section at end of file). `test_health.py`: `EXPECTED_AUTOMATION_COUNT` 85→97, added all 12 entity_ids to `NAMED_AUTOMATIONS`, added `sensor.4_way_button_battery` to `CRITICAL_ENTITIES`. `python3 run_all.py health` passes for everything touched this session — 2 pre-existing unrelated failures remain: all 3 room-level `automations_<room>` toggles are currently off (suppresses passive automations house-wide, doesn't affect the new button automations by design) and the indoor tree soil sensor still pinned at 99.99%.
- [x] **Blinds now respect Chill/Casual lighting mode across all 5 blind-closing automations, not just mode-change (2026-09-14)**: following the LR/Kitchen Chill-mode blinds feature (below), user asked what else closes those blinds and then asked to make all of them mode-aware. Updated `lr_tv_on_close_blinds`, `blinds_close_at_sunset`, `blinds_close_all_when_away`, `blinds_close_at_sleep_mode`, and `kitchen_blinds_close_when_hot_and_sunny` — each now checks that room's own lighting mode before acting (per-room, since LR and Kitchen can differ): Casual → blind left alone, Chill → set to 50%, any other mode → full close as before. The 4 "reopen" automations (TV off, sunrise, arriving home, kitchen reopen-on-cooldown) were deliberately left untouched — not asked, and opening isn't the "lowering" behavior in question.
- [x] **Living Room + Kitchen Chill/Casual modes now affect blinds (2026-09-14)**: user asked for Casual mode to leave blinds alone and Chill mode to lower them to 50%. Added a `cover.set_cover_position` (50%) action to the Chill branch of both `lr_lighting_mode_changed_update_lights` and `kitchen_lighting_mode_changed_update_lights`; Casual branch needed no change (never touched blinds). Both automations still only fire while the room's main light is already on (pre-existing top-level condition) — flagged to user as a real limitation.
- [x] **Rear Flood Light (Kasa) onboarded + wired into outdoor motion automations; chronic Kasa IP-drift fixed (2026-09-06)**: user added a new TP-Link Kasa HS103 plug ("Rear Flood Light") to control an outdoor floodlight fixture and asked for it to join the existing motion-triggered outdoor lighting.
  - **Onboarding hit a real snag**: adding the discovered device (192.168.68.145) in the HA UI prompted for TP-Link cloud credentials and repeatedly failed login even after a password reset — newer Kasa firmware requires a one-time cloud auth (KLAP protocol) during setup even though control is local afterward. Root cause never fully confirmed (2FA was off; likely a stale cloud-account binding from device manufacture), but it eventually authenticated successfully. **Two** devices ended up added, not one: `switch.rear_flood_light` (.145, MAC ...47:CA) and `switch.front_driveway_floodlight` (.146, MAC ...44:FF) — genuinely separate physical plugs despite the user's initial description of one plug driving both a front and rear head. Only `rear_flood_light` was wired into automations this session; `front_driveway_floodlight` is onboarded but not yet used anywhere — pick up if/when asked.
  - Built `automation.camera_rear_floodlight_on_motion` (storage-mode, via ha-mcp) mirroring the existing `camera_backyard_floodlight_on_motion` (L3) / `camera_carport_floodlight_on_motion` pattern exactly (Frigate MQTT `frigate/events` trigger, `input_boolean.camera_automations_enabled` gate, night-only via `condition: sun`, `mode: restart`, 10-min auto-off) — but with a combined trigger condition across **two** cameras/zones per user's confirmation that this fixture covers both areas: `backyard_zone` (backyard camera) OR `yard_zone`/`driveway_zone` (front_floodlight camera). Since `switch.rear_flood_light` is a plain on/off switch (not dimmable), it was deliberately kept out of the brightness/color escalation automations (`floodlight_welcome_known_person_light`, `floodlight_unknown_person_light`) — those call `light.turn_on` with brightness/color_temp and would fail against a switch entity.
  - `automations.yaml` mirror updated (new block after the carport entry); `test_health.py`: `EXPECTED_AUTOMATION_COUNT` 84→85, added `automation.camera_rear_floodlight_on_motion` to `NAMED_AUTOMATIONS`.
  - **Separately found and fixed while investigating**: the pre-existing 3 Kasa bathroom devices (`bathroom 1 KL125`, `bathroom two KL125`, `bathroom light strips KL400L5`) had been silently failing periodic polling for ~2 months (587 logged timeouts since first occurrence) — same "no DHCP reservation → IP drifted" pattern previously seen on `front_floodlight` (see 2026-08-09 entry below). User set DHCP reservations for all three (now `.131`/`.132`/`.103`); confirmed fixed via HA system logs (no new timeout entries since the reservation) and fresh live state on all three light entities post-fix.
- [x] **All-camera outage diagnosed and fixed: CPU detector oversubscription + front_floodlight DHCP IP change (2026-08-09)**: user reported Frigate "having issues with feeds and capturing activity" across all three cameras. Full audit found two separate, unrelated root causes:
  - **CPU detector oversubscription**: host is an M1 Mac Mini (8 cores/16GB), but Colima's VM was capped at 4 CPU/6GB — half the real hardware — since before `front_floodlight` was added as a 3rd camera. `num_threads: 4` was maxed against that artificial ceiling, not the true capacity. Overall `detection_fps` was only 11.8 combined across cameras, with each camera's `detection_fps` trailing well behind its `camera_fps`, cascading into `frigate.record.maintainer` warnings ("too many unprocessed recording segments... issue with the detect stream") and real recording gaps — `backyard` alone logged 848 such warnings in 24h, plus a 16h50m recording gap overnight. Fixed by resizing Colima to 6 CPU/10GB (`colima stop && colima start --cpu 6 --memory 10`) and raising `detectors.cpu.num_threads` to 6 in `config.yml`. Confirmed real improvement: combined `detection_fps` 11.8 → 28.6 once all 3 cameras were back under full load, each camera now keeping good pace with its own feed.
  - **Researched Google Coral USB Accelerator as an alternative/supplement** — concluded it's not viable on this Mac: Docker on macOS has no native USB passthrough at all, and every VM-based workaround (Parallels, other Linux VMs) that attempts it reports the Coral crashing every 15-30s. Multiple M1 Mac users report CPU-only Frigate performing well once properly resourced (7-11ms inference vs our post-fix 94ms under 3-camera concurrent load — the gap is most likely queue contention under concurrent multi-camera load, not a misconfiguration; ruled out emulation, wrong/oversized model, missing XNNPACK, and thermal throttling as explanations). Recommendation: skip the Coral, don't add more cameras without more capacity first.
  - **`front_floodlight` was separately hard-down for ~25 hours**: RTSP (554) and its HTTPS API (443) both refusing connections while the device still answered ping — matched a known Reolink Duo/Floodlight firmware-crash bug found documented in community/GitHub reports. A physical power cycle fixed it (a remote API-based reboot wasn't possible since the crashed API was the same thing that would've handled the reboot command), but **it came back on a new DHCP-assigned IP** (`192.168.68.137`, MAC `mac-floodlight`) instead of its old `192.168.68.100` — the device now squatting at `.100` is unrelated hardware (different MAC vendor prefix) that happens to answer ping, which is what made this confusing to diagnose (ping "worked," RTSP/API didn't). Updated `CAMERA_FLOODLIGHT_IP` in `~/frigate/.env` to `.137` and recreated the Frigate container (`docker compose up -d frigate`) to pick it up; confirmed healthy via `GetDevInfo` and Frigate stats.
  - **Not yet done**: no DHCP reservation exists for the floodlight's MAC, so this exact IP-change confusion can recur on its next reboot. Worth setting one via the Deco app (reserve `mac-floodlight` → `.137` or back to `.100`) — flagged in BACKLOG.md.
  - Also learned mid-investigation: unplugging a dead/unreachable camera entirely makes things *worse*, not better, while it's still configured in Frigate — the watchdog retries every ~10s regardless of whether the camera is merely unreachable or physically gone, and that retry churn measurably degraded the other two cameras' detection_fps (front dropped from 9.2 to 1.8) more than when the camera was just failing to connect. If a camera's going to be down for a while, comment out its block in `config.yml` rather than leaving it configured against a truly absent device.
- [x] **L2 outdoor outlet renamed — no longer empty (2026-08-04)**: user reported `switch.outdoor_gang_switch_l2` (previously "Backyard Outlet L2 (Empty)") is now running a fan + bike charger. Renamed to "Fan / Bike Charger" via ha-mcp entity registry; updated the matching card (name + icon `mdi:fan`) in both dashboard local mirrors (`lovelace/views/02_rooms.yaml`, `lovelace/desktop/desktop.yaml`, both added just 2 days prior) and redeployed via SCP. No automation involved — manual toggle only, same as before.
- [x] **Carport flood light (switch.outdoor_plug) brought under motion automation + dashboard coverage (2026-08-02)**: user plugged a spotlight into the previously-unused `switch.outdoor_plug` and asked for it to join the backyard motion-light automations, plus wanted all 5 outdoor gang switches visible wherever backyard/outdoor controls live.
  - Renamed `switch.outdoor_plug` → "Carport Flood Light" via ha-mcp entity registry.
  - Built `automation.camera_carport_floodlight_on_motion` (storage-mode, via ha-mcp) — exact mirror of the existing `camera_backyard_floodlight_on_motion` (L3) pattern: Frigate `backyard_zone` person-detection MQTT trigger, `input_boolean.camera_automations_enabled` gate, night-only (`condition: sun`, sunset–sunrise), `mode: restart`, 10-min auto-off. No dedicated "carport" Frigate zone exists, so it reuses the same backyard camera zone per user's confirmed choice.
  - **Learned the main "Overview" dashboard (`ui-lovelace.yaml`) and the Desktop dashboard are YAML-mode, not storage-mode** — `ha_config_set_dashboard(python_transform=...)` fails with `SERVICE_CALL_FAILED: Not supported` against them. Edited the local YAML mirrors instead (`lovelace/views/02_rooms.yaml`, `lovelace/desktop/desktop.yaml`) and deployed via the documented SCP workflow. Confirmed no HA restart/reload call was needed — a `force_reload` fetch immediately showed the new content, meaning YAML-mode dashboards are read fresh from disk on request.
  - Rooms view "Outdoor" popup (`#porch_popup`) previously only exposed L1/L3/L4 + the (unrenamed) outdoor plug — added the two previously-missing gang switches (L2 "Backyard Outlet", L5 "Backyard USB") so all 5 channels are reachable, and updated the Outdoor tile's on-light counter template to include the carport light.
  - Desktop dashboard's Overview had **no backyard/outdoor switch controls at all** (only `light.porch`) — added a new "Backyard / Outdoor" section mirroring the same 5 switches + carport light, placed right after "Room Lights".
  - **Deliberately left the Kitchen Panel untouched** — it's a minimal glance kiosk scoped to Kitchen/Living Room + cameras + soil moisture (it doesn't show Bedroom/Hallway/Office lights either), so adding backyard switches there would break its established minimal-panel intent rather than fill a real gap.
  - `automations.yaml` local mirror updated (new automation block after L3's, same documentation convention as the other storage-mode-but-mirrored automations). `test_health.py`: 84 automations (was 83), added `automation.camera_carport_floodlight_on_motion` to `NAMED_AUTOMATIONS`. `python3 run_all.py health` passes for everything touched this session (2 pre-existing unrelated failures remain: bedroom/living-room automation toggles off, indoor tree soil sensor pinned at 99.99% — not caused by this work).
- [x] **ThirdReality Zigbee door sensors paired + camera false-positive suppression (2026-07-22)**: user's two ThirdReality contact sensors arrived; paired via Zigbee2MQTT (LQI 204 front / 208 back) as `front_door` / `back_door`, renamed to `binary_sensor.front_door_contact` / `binary_sensor.back_door_contact` (deliberately distinct from the pre-existing `binary_sensor.front_door_door`, which is the unrelated August lock's cloud sensor), assigned to `foyer` / `backyard` areas.
  - **Goal**: reduce false "Unknown Person" alerts caused by Frigate's known face-recognition miss-rate (see the 2026-07-17 entry below — Riley in particular is under-recognized) by treating "door opened, then camera sees a person shortly after" as a confirmed resident arrival/departure rather than an unrecognized visitor.
  - Built 2 new automations (`door_front_door_opened_arrival_grace_period`, `door_back_door_opened_arrival_grace_period`, `mode: restart`) that flag `input_boolean.door_recently_opened_{front,back}` for a grace window after the door opens — **90s front / 5min back**, per user's choice (front door → camera is a few steps away; back door covers a longer walk to the `backyard_zone` camera coverage).
  - Added a `not door_recently_opened_{front,back}` condition to all 4 existing "Unknown Person" pathways so they fully suppress (not just soften) during the grace window: `cam_unknown_front_yard`, `cam_unknown_backyard`, `cam_unknown_visitor_count` (the weekly counter — also gated on both flags, front OR back, to avoid inflating the count), and `floodlight_unknown_person_alert` (front_floodlight's yard/driveway coverage, gated on the front flag only).
  - **Deliberately left untouched**: the floodlight's bright/cool "Unknown Person" *light* escalation (`floodlight_unknown_person_light`) and the loitering siren escalation — those aren't alert-fatigue problems the same way notifications are, and redirecting them to the warm "welcome" light behavior on a door-open match would be a bigger scope change than what was asked. Worth revisiting if it comes up again.
  - Tried `door.opened` (the 2026.7+ purpose-specific trigger the best-practices skill recommends) first — rejected by this HA instance with "requires the experimental 'New triggers and conditions' feature... feature flag: `new_triggers_conditions`" despite the skill describing it as default-since-2026.7. Fell back to a plain `state` trigger (`to: "on"`), which is what the rest of this project's automations already use anyway. **If that Labs flag ever gets enabled, the purpose-specific trigger would be the more idiomatic form going forward.**
  - `test_health.py`: 83 automations (was 81), 58 helpers (was 56), added both door `binary_sensor`s to `CRITICAL_ENTITIES`. New `tests/test_doors.py` injects fake Z2M `contact` MQTT payloads (mirrors `test_motion.py`'s pattern) and confirms both grace flags actually flip — verified passing end-to-end, not just registered. `run_all.py` gained a `doors` module.
  - Local mirrors updated: `automations.yaml` (new "Door Sensors" section, storage-mode automations documented per the existing floodlight-block convention) and `helpers.yaml` (new door-sensor input_booleans, same convention).
- [x] **Riley face-recognition gap diagnosed and partially closed (2026-07-17)**: user asked whether all "person"-tagged footage that's actually them had been reviewed and used to improve training. It hadn't. Hard data: only 2 of 1,121 total person events since June 13 were tagged `Riley` (Casey: 22), and Frigate's own auto-training candidate bucket (`train/`, capped at 200 slots, currently full) contained **zero** Riley entries — 161 Casey + 39 unknown. The passive learning loop that keeps reinforcing Casey's recognition has never once produced a usable Riley candidate; he was still running on 5 static reference photos from weeks earlier.
  - Reviewed 417 unlabeled person events from the last 7 days (`backyard`/`front`: 26; `front_floodlight`: 391, most of which turned out to be the camera's known stationary-object false-positive patterns — confirmed individually, not assumed) via 4 parallel background agents, each comparing against real reference photos of Riley and Casey pulled from Frigate's own face library. Found 27 genuine Riley sightings with a visible face, ranked by quality.
  - Curated the 6 best/most diverse candidates (different cameras, days, lighting, activities) and attempted registration via Frigate's `/api/faces/{name}/register` endpoint. Found the endpoint runs its own face-detector on the uploaded crop — tiny native crops (~30x35px, since most source events predate the `crop:false` fix) failed outright; 6x-upscaling got some through. **3 of 6 successfully registered** (Riley now has 8 reference photos, up from 5). The other 3 failed even after upscaling and wider-context recrops — all three were extreme downward/side angles (mowing, reaching, sunglasses) where even Frigate's own detector couldn't find facial landmarks. This is itself a useful diagnostic: it's not just camera framing hurting Riley's recognition, some of his real-world poses are fundamentally undetectable to the current pipeline regardless of photo quality.
  - **Not done / worth revisiting**: the other ~21 lower-quality/moderate candidates from the review weren't attempted for registration (diminishing returns expected, same angle problem likely). No systematic review of the `unknown_person` bucket (real people, no visible face) was done — those are exactly the "leaves via the back of the house" cases flagged earlier as a deferred hardware/zone-based problem, not fixable via more reference photos.
- [x] **Two more `front_floodlight` false-positive masks (2026-07-17)**: user asked to reduce alerts "from the neighbor's yard on the right side of the truck in the driveway." Traced via Frigate's own event DB bounding-box data — found a fixed dark object at the property-line hedge (9 near-identical `person` hits since 7/16, day and night, x:0.90-0.96/y:0.14-0.33) sitting right next to a visually-similar but genuinely real cluster (people working near the parked trailer, x:0.80-0.87) — confirmed each via actual thumbnail before masking, so the real-activity area was correctly left alone. Also found and fixed an edge-case gap in the existing motorcycle mask (a real event's box clipped just outside the old boundary). Both deployed, Frigate restarted clean, all cameras/services verified healthy, and a 15-minute post-restart watch confirmed zero new detections (real or false) in a location that had been firing roughly hourly.
- [x] **Full Claude Suggestions review pass (482 events) + discovered/fixed a major false-positive source drowning the code-enforcement queue (2026-07-16)**: user asked for a full review of recent code-enforcement detections (2026-07-14 through 2026-07-16, ids 4412-4893) so the "🤖 Claude Suggestions" dashboard tab could be mass-approved instead of reviewed one-by-one. Split the work across 4 parallel background agents (one per ~120-row id range) plus a 5th cleanup agent, each visually reviewing every thumbnail individually (per the earlier clustering-mistake lesson — no bulk-labeling without checking each image). Result: **0 code-enforcement (target vehicle) matches** across all 482, rigorously confirmed image-by-image; 473 → `false_positive`, 9 flagged for user judgment (a pickup truck wrongly shape-matched, a too-dark night frame, 6 near-identical wide shots with a garden cart in frame and an unidentifiable distant car).
  - **Root cause found**: traced all 473 false positives back to Frigate's own event DB (`camera`/`zones` fields) — 100% were `front_floodlight`/`street_zone`, all clustered at the same bounding-box region (`x:0.47-0.68, y:0.0-0.13`), a fixed object at the base of a yard tree misfiring as "car" at ~50-60% confidence continuously, day and night, for most of the 3-day window. This wasn't one of the previously-masked objects (trash can/pallets/bin/motorcycle/trailer) — a new, previously-unmasked spot inside `street_zone` itself, meaning ~98% of everything logged in this window was noise, not traffic.
  - **Two fixes deployed and verified live**: (1) `snapshots.crop: true → false` in `config.yml` — a leftover CompreFace-era setting that was cropping every snapshot tightly around the (often tiny) detected box, making low-confidence detections nearly unreadable as small cropped squares in the dashboard table. (2) Added a new `car` filter mask on `front_floodlight` for the tree-base region (`0.44,0.0,0.70,0.0,0.70,0.15,0.44,0.15`), sized from 8+ independently-sampled real bounding boxes with slight padding. Explicitly narrows real `street_zone` coverage for that stretch of curb — the `front` camera's `road_zone` remains a second, independent source for the same stretch if this ever masks a real pass.
  - **Verified for real, not just deployed**: pushed config, restarted Frigate (all 3 cameras confirmed healthy post-restart via `/api/stats`), confirmed both new settings live via `/api/config`, then watched `code-enforcement-floodlight`'s logs for 15+ minutes post-restart — zero detections at all (real or false) in a window where the false object had previously fired every 1-10 minutes for days straight. Cross-checked against Frigate's own event DB to confirm this wasn't stale/cached log output. Strong evidence the mask works without over-suppressing; full confirmation pending the next real car passing through the unmasked portion of the zone.
  - **Also found and fixed mid-review**: two review agents that hit Frigate's 404 "event not found" for already-expired thumbnails initially gave up (`claude_suggestion=NULL`, generic "unavailable" note) instead of checking the `code-enforcement` container's own local thumbnail cache (`/data/thumbnails/{event_id}.jpg`, populated at OCR time, independent of Frigate's own retention) — a later-finishing batch discovered this fallback path. Re-ran a dedicated recovery pass for the 80 affected rows using the cache; all 80 recovered and genuinely reviewed (all false_positive, same tree-base object).
- [x] **Fourth/fifth stationary-object masks + real backyard face registration (2026-07-14)**: user reported `front_floodlight` alerting on their parked motorcycle and trailer.
  - Same pattern as before: 14-sample cluster at `x≈0.92, y≈0.56` (misclassified "person") confirmed via thumbnail as the motorcycle; separate 14-sample cluster at `x≈0.71-0.79, y≈0.24-0.59` (misclassified "car") confirmed as the utility trailer. Added a 4th `person` mask (`0.9,0.53,0.97,0.53,0.97,0.69,0.9,0.69`) and, since the `car` filter had no mask field yet, added one (`0.69,0.2,0.97,0.2,0.97,0.72,0.69,0.72`) — confirmed its y-range doesn't overlap `street_zone` (0.0-0.16), so code-enforcement OCR is unaffected. Deployed; re-verified both code-enforcement MQTT subscriptions survived the restart via the same synthetic-event check now used routinely after any Frigate restart.
  - **Backyard face registration**: user confirmed a recent backyard "person" detection (3-event walking sequence, ~09:29am) was them. Tried registering all 3 snapshots as Riley reference photos — 2 had no detectable face (side/motion angles), 1 (clearer forward-facing angle) registered successfully. Riley now has 5 reference photos (was 4). user reported recurring "unknown person" notifications for a trash/recycling can, and asked why a non-moving object keeps re-triggering. Root cause explained and confirmed via data: Frigate re-runs classification every frame regardless of motion — a stationary object's track can end and immediately restart (triggered by a shadow shift, lighting change, or nearby wind-moved branch), looking like repeated "new" detections. Confirmed via 12 near-identical bounding boxes (`x≈0.95, y≈0.52`) across 13 minutes — a blue recycling bin at the roofline corner, a different spot from the two masks already in place from 2026-07-07 (neighbor's shed trash can, wood pallets — both still holding fine, not the source this time). Added a third mask (`0.94,0.48,0.99,0.48,0.99,0.69,0.94,0.69`), deployed, and re-verified both code-enforcement MQTT subscriptions survived the resulting Frigate restart (today's earlier stuck-subscription bug made this worth double-checking) via the same synthetic-event technique — both confirmed genuinely live post-restart, zero stray rows in the DB.
- [x] **Pre-flight check + real bug found before expected code-enforcement pass (2026-07-13)**: user expected the code-enforcement vehicle today (Monday) and noted their own truck had been relocated, opening up a much clearer street view. Ran a full pipeline verification rather than assuming health:
  - **Found a real silent failure**: the `code-enforcement` container (watching `front`/`road_zone`) had been alive and "connected" to MQTT since 2026-07-09 14:46 but hadn't logged a single detection in 4+ days — a stuck subscription, not just quiet traffic (confirmed via `docker logs` showing zero output since container start, contrasted against `code-enforcement-floodlight` actively logging detections the whole time). Restarted the container; verified the fix was real (not just hopeful) by publishing a synthetic `frigate/events` MQTT message with a fake event_id and confirming it was received and processed — the fake ID predictably 404s on thumbnail fetch, so nothing polluted the database (confirmed 0 stray rows after).
  - **Widened `front_floodlight`'s `street_zone`** (`0.20,0.0,0.70,0.0,0.70,0.14,0.20,0.14` → `0.20,0.0,0.98,0.0,0.98,0.16,0.20,0.16`) — the relocated truck revealed a much longer stretch of street toward the right edge of frame than the original single-snapshot draft captured.
  - **Found and fixed a second LAN-only notification image URL**: `code_enforcement/service.py`'s `publish()` was putting the direct-LAN `snapshot_url` (`http://192.168.68.142:5050/...`) into the `code_enforcement/alert` MQTT payload, which `packages/code_enforcement.yaml`'s automation uses directly for the phone notification image — same class of bug fixed for front/backyard/floodlight on 2026-07-08, just missed on this one at the time. Added `NOTIFICATION_BASE_URL` (defaults to the `ha.example.com` proxy) and used it only for the alert-topic payload, keeping `FRIGATE_URL` (LAN) for the OCR service's own internal image fetches. Rebuilt and redeployed both `code-enforcement` and `code-enforcement-floodlight` images (they share the same Dockerfile but build to separate image tags — both needed rebuilding).
  - **Verified the entire chain end-to-end for real**, not just each piece in isolation: published a synthetic `code_enforcement/alert` MQTT message using a real event's snapshot ID, confirmed `automation.code_enforcement_vehicle_spotted_on_road` fired (`last_triggered` matched exactly, trace showed `execution: finished`, no errors) — this sent an actual test push notification with a real loadable image.
  - Confirmed clean state going in: `known_vehicles` has only 1 legitimate fingerprint (no false-`my_vehicle`-match risk), `input_boolean.camera_automations_enabled` on, zero code-enforcement matches to date (nothing to second-guess).
- [x] **Fixed missing notification images on backyard alerts (real bug, not camera-specific)** (2026-07-08): user reported front-yard unknown-person notifications include a thumbnail but backyard ones don't, despite "fixing this before." Investigation: both automations use an identical `image` URL template (`https://ha.example.com/api/frigate/notifications/{{ id }}/snapshot`), and Frigate itself confirms valid snapshots exist for both cameras' events — so the automation logic and Frigate weren't the problem. Direct testing (with a real HA long-lived token) showed the exact configured URL 404s for **both** cameras; adding a `.jpg` extension (`.../snapshot.jpg`) returns 200 for both. The URL was missing its file extension — likely lost when a past session/edit switched the URL from a direct-LAN Frigate link to this Cloudflare-tunnel proxy (for remote image loading while away from home) without including the extension the proxy route requires. Fixed both `cam_unknown_front_yard` and `cam_unknown_backyard` via ha-mcp; local `automations.yaml` mirror was also fully stale for these two (still showed the old pre-proxy URL) — resynced.
  - **Unresolved side-question**: my testing shows this bug should have affected front equally, which doesn't fully square with "front works, backyard doesn't." Possible the user's "front works" observation predates this drift, or there's a per-camera Frigate-integration notification setting I didn't find. Not chased further since the confirmed fix (`.jpg`) resolves the reproducible 404 for both — worth a quick real-world check next time an actual unknown-person event fires on both cameras.
  - **Related, not yet done**: the floodlight's own notification automations (`floodlight_unknown_person_alert`, `floodlight_unexpected_vehicle_alert`, built 2026-07-07) use the direct-LAN Frigate URL (`http://192.168.68.142:5050/...`), which won't load images when away from home on cellular — same class of issue this fix addresses for front/backyard. Consider switching those to the same `ha.example.com` proxy pattern for consistency.
- [x] **Porch light + backyard floodlight brought under automation control** (2026-07-08):
  - **Porch light** (`light.porch` — note `light.porch_2` is just a Hue group wrapper around the same bulb, not a second fixture; brightness-only, no color_temp support): extended the existing floodlight automations rather than duplicating them, since they share identical triggers. `floodlight_night_baseline_on` now also turns on `light.porch` to 15% at sunset — **but only if it's currently off**, so a manual porch setting doesn't get clobbered. `floodlight_night_baseline_off` always turns porch off at sunrise. `floodlight_welcome_known_person_light` / `floodlight_unknown_person_light` (renamed "Floodlight+Porch: ...") now target both lights together for the brightness escalation (color_temp_kelvin is silently ignored by HA for porch since it doesn't support that attribute — no error, just applies what each entity supports). `floodlight_restore_baseline` script restores both. The "don't clobber a manual setting" guard applies **only** to the sunset baseline trigger, not the reactive escalation — otherwise baseline turning porch on earlier in the night would block the escalation from ever brightening it further.
  - **Backyard floodlight** (`switch.outdoor_gang_switch_l3`, "Backyard Flood Light"): user clarified this is a physical dusk-to-dawn fixture — the HA switch only supplies power; the fixture's own photocell decides actual illumination. It had been left on 24/7, so the photocell lit it every night regardless of yard activity. Built `automation.camera_backyard_floodlight_on_motion` mirroring the existing `cam_backyard_human_lights` pattern exactly (same MQTT trigger/zone check, `mode: restart`, 10-min auto-off) but targeting `switch.outdoor_gang_switch_l3` instead of `switch.outdoor_gang_switch_l1`, plus an added `condition: sun` night-only gate.
  - **Found a real problem while doing this**: `switch.outdoor_gang_switch_l3` hasn't responded to any command in 5 days — `last_changed` stuck at `2026-07-03T18:11:53`, two `switch.turn_off` calls both returned "state change could not be verified" with no effect. Initially flagged as suspiciously close in time to `binary_sensor.front_door_door` going stale, but **user confirmed the actual cause is Zigbee-specific**: LQI 72 (weak link) on this device — the door lock is cloud-based (August Lock), a different protocol, so the timing match was likely coincidental, not a shared root cause. User is relocating the switch to improve signal. The new automation is already correctly configured — nothing further needed from this end; it'll just start working once the device responds reliably again.
- [x] **Claude Suggestions dashboard: inline correction for "needs judgment" items + a clustering mistake caught and fixed** (2026-07-08): user pointed out the "no auto-suggestion" table required switching to the Vehicles tab to actually classify anything — fixed by adding an editable `✏️ Correction` column + bulk-assign + individual save directly to that table (`~/frigate/vehicle_dashboard/dashboard.py`), matching the Vehicles tab's UX. Rebuilt and redeployed.
  - **Mistake made and corrected the same session**: user confirmed 3 specific IDs (548/549/553) as USPS trucks; bulk-applied "usps" to the whole 9-item "recurring white truck" cluster those 3 belonged to, assuming partial confirmation validated the group. User caught it — one was "just a blank white van." Re-pulled full snapshots (not thumbnails) for the other 5 and found the cluster actually contained a pickup truck, a box van, and a sedan/compact SUV — genuinely different vehicles that only looked similar at low resolution/same road position. Reverted the 5 unconfirmed ones back to unclassified, rewrote their notes individually and honestly (shape-only, no carrier guess) instead of the misleading shared "recurring truck" description. Saved as a feedback memory (`feedback_vehicle_review_clustering.md`) — don't bulk-generalize a partial confirmation across a visually-clustered group again.
- [x] **SD card review helper built** (2026-07-08): user asked about using the cameras' onboard SD cards for deeper Claude review without adding Mac Mini storage. Confirmed `front` (CX810, ~119GB) and `front_floodlight` (~59GB) have SD cards mounted with AI-triggered recording enabled (person/vehicle/dog-cat/motion, ~7-9 days retention currently); `backyard` (RLC-1212A) has no SD card. Confirmed the full pipeline works via the cameras' own HTTPS API (bypasses Frigate/Mac Mini storage entirely): search a time window → download a clip → extract frames with ffmpeg (newly installed via `brew install ffmpeg` — wasn't on the host before, had to route through the Frigate container as a workaround during testing).
  - Built `~/frigate/sdcard_review/sdcard_review.py` — reusable CLI (`search` / `download` / `frames` / `review` one-shot) reading camera credentials from `~/frigate/.env`. Not a service — nothing runs continuously, no persistent storage; pull a clip only when there's something specific to review, discard after.
  - Verified working end-to-end on `front`. **Known limitation**: `floodlight`'s `Download` command returns 404 for its SD card paths despite `Search` working fine (its clip paths are prefixed `/mnt/sda/...`, unlike `front`'s relative `Mp4Record/...` — some model-specific difference not yet resolved). Not investigated further since `front` (the primary/longer-standing camera) works correctly. Revisit if floodlight clip access becomes actually needed.
  - **Use case**: when reviewing an ambiguous detection (e.g., a Claude Suggestions item, or investigating something flagged after the fact), pull the actual multi-second clip instead of relying on Frigate's single thumbnail — meaningfully better than one frozen frame for identification, and reaches back further than Frigate's own retention (which has been purging events faster than expected this session).
- [x] **Dog tracking added to front_floodlight + second code-enforcement OCR source (floodlight street_zone)** (2026-07-07): user asked about masking their changing curb parking spot to avoid false vehicle detections. Correctly talked through why masking is the wrong tool here (spatial + permanent, vs. a parking spot that moves — risks silently hiding the target vehicle too) in favor of the identity-based pHash system already in place. While trying to get a clean fingerprint photo of the user's car, found the `front` camera's `road_zone` genuinely only captures a thin edge-of-frame sliver of curb vehicles (camera physically aimed down a steep yard slope, road barely enters frame, CX810 has no optical zoom to compensate) — a real resolution problem likely also limiting OCR legibility, separate from the pHash contamination fixed earlier today.
  - `dog` added to `front_floodlight`'s tracked objects + both zones (Biscuit appeared in-frame during an earlier walk-test but wasn't logged).
  - Checked the floodlight's panoramic view of the street — meaningfully better framing of curb vehicles (clear distinct car shape vs. a sliver). Added a `street_zone` (`x:0.20-0.70, y:0.0-0.14`, first-draft from one snapshot) tracking `car`.
  - **Deployed a second code-enforcement service instance** (`code-enforcement-floodlight` in `docker-compose.yml`) watching `front_floodlight`/`street_zone`, sharing the same `code_enforcement.db`/`known_vehicles`/EasyOCR model dir as the original via the shared `code-enforcement-data` volume — one unified detections table, two camera sources. Required making the MQTT client ID configurable in `code_enforcement/service.py` (`MQTT_CLIENT_ID` env var, was hardcoded `"ce-detector"`) — two instances with the same hardcoded ID would have repeatedly kicked each other off the MQTT connection. Verified both connect cleanly and stay connected (no reconnect-loop). Confirmed working end-to-end: floodlight instance caught a real car in `street_zone` and ran OCR on it within seconds of deploy (no text matched that particular pass — normal, will improve with more samples, not a failure).
  - Whether this actually catches the code-enforcement target vehicle is now genuinely observable going forward — check `code_enforcement.db` `is_code_enforcement`/`category` columns, or the dashboard's Code Enforcement metric.
- [x] **Code enforcement vehicle: zero captures explained, known_vehicles library cleaned up** (2026-07-07): user asked whether the code-enforcement target vehicle (tracked since 2026-05-18, see `cameras/code_enforcement_vehicle` context) had ever actually been captured. Answer: **zero** — `is_code_enforcement=1` and `category='code_enforcement'` are both empty across all 847 OCR-eligible detections. Investigated why rather than assuming it just hadn't driven by.
  - Found the likely real cause: `known_vehicles` (the pHash "my_vehicle" auto-classify library) had exactly 9 fingerprints, **all created within milliseconds of each other on 2026-06-17** (bulk-seeded during that day's stack overhaul, not built up individually via the dashboard). Pulled full snapshots (not just thumbnails) of the source events — they're all near-worthless as fingerprints: a vehicle barely clipping the edge of frame (`car: 54%` confidence, mostly grass in shot), same spot, spanning 6/16 evening through 6/17 morning (one vehicle parked/idling overnight, not a deliberate "tag my car" moment). A pHash built from that is dominated by background, not vehicle shape — exactly the kind of fingerprint that would false-positive-match other passing vehicles (silently auto-classifying them `my_vehicle` and skipping OCR entirely, which would fully explain 3 weeks of zero code-enforcement captures despite the pipeline running the whole time). This is also the same underlying risk already flagged in this file's older notes about lookalike vehicles matching the code-enforcement target at the default threshold.
  - **Deleted all 9 fingerprints** and **lowered `PHASH_THRESHOLD` 12→8** in `docker-compose.yml` (`code-enforcement` service), container recreated and confirmed running with the new value.
  - **Caveat, not resolved**: the ~847 detections already auto-classified as `my_vehicle` before this cleanup were matched against the now-deleted, low-quality fingerprints — their reliability is unknown. Deliberately did NOT bulk-reset them back to unclassified (would recreate the exact backlog just cleared in the Phase 3 work above), but flagging this openly: some may be mislabeled. Going forward, (re-)tag real vehicles via the dashboard's Vehicles tab from a clear, mostly-in-frame capture, not an edge-of-frame sliver.
  - **Still open**: whether the code-enforcement target vehicle has actually passed by since 6/17 and gotten mis-swept into `my_vehicle` under the old loose fingerprints is unconfirmed — only observable going forward now that the bad fingerprints are gone and the threshold is tighter.
- [x] **Floodlight daytime-trigger fix + Riley recognition gap found** (2026-07-07): user walked the front/back yard; floodlight lit up at full brightness during broad daylight. Root cause: `floodlight_unknown_person_light`/`floodlight_welcome_known_person_light` had no day/night gate (only the passive baseline dim automation was sun-conditioned) — the person (Riley) was detected at 84% confidence on `front_floodlight` but face recognition returned no `sub_label`, so the *unknown*-person light automation fired regardless of time of day. Added `condition: sun, after: sunset, before: sunrise` to both automations via `ha_config_set_automation` (python_transform) + mirrored in `automations.yaml`. The already-on light had actually self-corrected via `script.floodlight_restore_baseline`'s day/night check before this fix even landed — that part worked as designed, only the "should it have turned on at all" gate was missing.
  - **Also found**: Riley still isn't reliably recognized on `front_floodlight` (this event) or `backyard` (two more unrecognized events same session, right after Casey was correctly matched on backyard) — the June-photo-based registration fix from earlier today hasn't fully closed the gap on these live captures.
  - **Tried to add better training material from the walk, but couldn't**: the `front_floodlight` capture showed the person mid-stride/walking away — Frigate's face detector found no face in either `thumbnail.jpg` or `snapshot.jpg` for that event (elevated wide-angle mount makes casual-movement frontal face captures hard). Backyard captures were also poor quality (distant, obscured by renovation clutter). No new Riley reference photos were added this pass — needs a future capture with a clearer frontal angle, or picking better crops from a longer event sequence.
  - **Noted, not built**: Biscuit appeared in the `front_floodlight` frame during the walk but wasn't logged as a detection — that camera only tracks `person`+`car` currently (unlike `backyard`, which tracks `dog`). Also worth being direct about a real limitation: Frigate has no per-dog identity recognition the way it does for people — there's no way to "register Biscuit's face" for automatic future recognition. The only planned mechanism for auto-distinguishing Biscuit from e.g. a coyote is the zone-entry-order behavior design in the roadmap's Phase 1 (not yet built), not identity matching. Manually setting `sub_label` on an individual dog event is possible but doesn't generalize or persist as a capability.
- [x] **Vehicle dashboard backlog cleared + Claude Suggestions review tab built (Phase 3 start)** (2026-07-07): user asked what was left to review and where to find "mass approve" — Phase 3 of the roadmap didn't exist yet, built the first piece of it now.
  - Found 2,498 of 2,518 vehicle detections unreviewed. Investigated rather than blindly reviewing: **1,620 of the original 1,675 "uncategorized" backlog (97%) turned out to be one already-fixed bug** — a parked car at night repeatedly re-triggering as a "new" car event every 15–90s due to `road_zone`'s old `inertia:1/loitering_time:0` (same issue fixed for the `front` camera earlier today). Confirmed via thumbnail on 3 separate dates (6/27, 6/29, 7/3 — same vehicle, same spot) before bulk-clearing all of 6/27–7/3 as `false_positive`/reviewed via direct SQL (`UPDATE detections SET user_category='false_positive', reviewed=1 WHERE ...`), not 1,620 individual clicks.
  - That left a genuine 35-item backlog. 18 still had retrievable images (17 were already purged by Frigate — logged as such, not reviewable). Of those 18: 2 confirmed **FedEx** trucks (logo visible), 5 were the *same single car* from one morning fragmented into separate events by tree-branch occlusion (tracking artifact, not 5 vehicles), 9 showed a recurring white/silver truck not yet in `known_vehicles` — genuinely ambiguous, flagged for human judgment rather than guessed.
  - **Built the suggestion infrastructure**: added `claude_suggestion`/`claude_confidence`/`claude_notes` columns to `code_enforcement.db` (`~/frigate/code_enforcement/`, shared volume with `vehicle-dashboard`). Added a **"🤖 Claude Suggestions" tab** to the Streamlit dashboard (`~/frigate/vehicle_dashboard/dashboard.py`, rebuilt + redeployed via `docker compose build/up vehicle-dashboard`) — shows Claude's suggested category + confidence + reasoning with a pre-checked mass-approve table (approve-in-bulk applies `user_category`, fires the same CE-alert/pHash-fingerprint side effects as manual correction), plus a separate read-only section for notes-only items that need a human's judgment call, not a rubber stamp.
  - **Workflow going forward**: Claude review is on-demand (ask in a session — "review pending vehicle detections" or similar), not yet a scheduled/autonomous job. Write suggestions into the DB columns above, then check `http://192.168.68.142:8501` → 🤖 Claude Suggestions tab to approve.
  - Bird sightings table is currently empty — nothing to review there yet; same suggestion-column pattern can extend to `birds.db` when it has data.
  - Remaining roadmap: Phase 3b (Faces tab, Person/Behavior tab) not built; Phases 1–2 (behavior-tracker service, identity+behavior lighting tiers) not started. See `/Users/homeuser/.claude/plans/i-want-to-see-swift-volcano.md`.
- [x] **Front Yard Floodlight false-positive fix** (2026-07-07, shortly after onboarding): user reported the neighbor's blue trash can being detected as a person. Pulled the last 100 `person` events via `/api/events` — 9 of 11 clustered at nearly identical pixel coordinates over 27+ minutes (confirmed via thumbnail: neighbor's trash can near their shed, left edge of frame), and the other 2 were a second, separate static-object source (wood pallets leaning against a tree, upper-right). Added two object-filter masks to `front_floodlight`'s `person` filter covering both regions. **Remove/adjust these masks once the objects are gone** — trash can moves on collection day, pallets are temporary yard debris, not permanent yard features like the tree-line mask on the `front` camera.
- [x] **Front Yard Floodlight camera onboarded** (2026-07-07): new Reolink dual-lens panoramic floodlight (`192.168.68.100`) — will replace the CX810 as the primary front-yard camera; CX810's new location still TBD. Native Reolink HA integration already had 27 entities set up (camera, tunable-white light 3000K–6000K, motion/person/vehicle/animal binary sensors, siren, AI sensitivity numbers, day/night mode, etc.) — **capability correction**: it's tunable-white only (`supported_color_modes: ["color_temp"]`), not full RGB despite "different hues" in casual description.
  - Added to Frigate: `~/frigate/.env` + `docker-compose.yml` env vars, new `front_floodlight` camera block in `config.yml` (person+car tracking, first-draft `yard_zone`/`driveway_zone` polygons — **redraw once physically mounted/aimed**, current ones are from a single pre-mount snapshot). Main stream is `7680x2160` (two 3840-wide lenses stitched side-by-side, not standard single-lens 4K); sub/detect stream `1536x432`, fps capped at 5 (3rd camera on the same CPU-only detector as front+backyard). Verified live via `docker exec frigate ffprobe` before deploying, then confirmed all 3 cameras streaming post-restart.
  - Added `camera.front_yard_floodlight_fluent` to all three dashboards (`07_cameras.yaml`, `kitchen_panel.yaml`, `desktop.yaml`) as a full-width row given its unusually wide/short native aspect ratio — deployed via SCP to `/config/lovelace/{views,kiosk,desktop}/` (this project uses YAML-mode Lovelace, not HA's storage-mode dashboard API). **Flagged, not fixed**: the desktop dashboard's camera grid was still 100% old Blink cameras before this — `front_yard_fluent`/`backyard_fluent` (CX810/RLC-1212A) were never added there, unlike the mobile and kitchen dashboards.
  - Built 8 automations + 1 helper (`input_boolean.floodlight_siren_escalation_enabled`, default off) + 1 script (`script.floodlight_restore_baseline`): dim warm-white baseline at night (sunset/sunrise), brighter warm welcome light for Riley/Casey, bright cool-white + phone alert for unknown persons, animal notification (via the camera's own onboard AI binary sensor — Frigate isn't tracking animals on this camera), unexpected-vehicle-in-driveway alert (night + away_mode only), and an opt-in siren escalation for sustained (45s+) presence at night. Native `binary_sensor.front_yard_floodlight_person` + a `for: 00:00:45` trigger used for the loitering proxy instead of template-based duration math, per the ha-mcp best-practices skill. **Known limitation**: the siren escalation isn't identity-aware (would also fire for Riley/Casey lingering) — proper identity+duration tracking needs the not-yet-built Phase 1 behavior-tracker service from the roadmap; this is an intentionally simple stopgap.
  - **Important nuance discovered**: these 8 automations + the script live in HA's storage-mode config (created via `ha_config_set_automation`/`ha_config_set_script`), NOT in the YAML files, even though this project's other automations are YAML-mode — HA lets both coexist. Manually mirrored into `automations.yaml`/`scripts.yaml`/`helpers.yaml` for documentation, but the live/authoritative copies are in HA's storage — edit via ha-mcp or the UI, not by editing those mirrored blocks.
  - Set `select.front_yard_floodlight_floodlight_mode` to `off` (disables the camera's own automatic floodlight behavior) so HA fully owns brightness/color via the automations above instead of fighting the device's native auto-mode.
  - `test_health.py` updated (80 automations, 56 helpers, 8 scripts) and `python3 run_all.py health` passes (2 pre-existing unrelated failures: bedroom automations toggle off, 2 soil sensors reading anomalously — not touched by this work).
  - `HomeAssistant/cameras/plan.md` rewritten same session: removed stale CompreFace/Double Take/InsightFace-FAISS architecture (abandoned 2026-06-17), now reflects actual live IPs/ports/architecture plus this floodlight project.
- [x] **Frigate face recognition fix — Riley registration** (2026-07-07): found Riley had a 0% recognition rate (0/200 recent face-recognition attempts matched, vs. Casey's 158/200) despite having 4 registered reference faces. Root cause: 3 of the 4 were unusable (sunglasses fully covering eyes, extreme forehead-only crop, mid-bite eating photo with color-cast lighting) — visually confirmed via `docker cp`'d copies from `/media/frigate/clips/faces/Riley/`. Deleted the 3 bad ones via `POST /api/faces/Riley/delete`, registered 3 new clean photos via `POST /api/faces/Riley/register` (multipart upload, Frigate does its own face detection/crop): `HomeAssistant/cameras/training/riley/PXL_20260224_140621419.MP.jpg`, `PXL_20251104_184236320.jpg`, and a cropped quadrant of `20241028_172418-COLLAGE.jpg` (suit+tie photo, bottom-left quadrant). Final set: 4 good-quality Riley faces, comparable to Casey's 5. **Not yet verified against live recognition** — check `/api/events?camera=front&label=person` (or backyard) after Riley is next seen on camera to confirm `sub_label` now populates correctly instead of falling to unknown.
- [x] **Frigate Phase 0 — false-positive tuning** (2026-07-07), data-driven via Frigate's `/api/events` history (not guesswork):
  - Front camera: added `objects.filters.person.mask` over `0.55,0.10,0.90,0.10,0.90,0.53,0.55,0.53` (tree-line noise cluster — 66/165 recent `person` events centered there, confirmed via thumbnails to be wind/shadow, not people); raised `person` filter to `min_score: 0.6, threshold: 0.65` (from 0.4/0.5) — every visually-checked sample in the old 0.50–0.63 range was a false positive, including the highest-scoring ones.
  - Front `road_zone`: `inertia` 1→3 (Frigate default), `loitering_time` 0→2 — was registering cars on a single frame.
  - Backyard `bird` filter: `min_area` 100→350, `min_score` 0.35→0.55, `threshold` 0.45→0.65 — 139/139 recent `bird` events fell entirely outside the `bird_feeder` zone (noise, not birds).
  - Backyard `person`/`dog` filters: left unchanged — data showed healthy, accurate score distributions (0.75–0.84 and 0.62–0.77 respectively), no false positives found.
  - Config backed up to `~/frigate/config/config.yml.bak.20260706_182233` before editing; pushed via the documented `cat config.yml | docker exec -i frigate tee /config/config.yaml` + `docker compose restart frigate` workflow; verified live via `/api/config` post-restart.
  - Confirmed all 7 `cam_*` automation entity_ids plus `code_enforcement_vehicle_alert`/`bird_new_species_alert` via `ha_search` (see test_health.py backfill below).
- [x] Netgear GS308Ev4 switch configured — static IP `192.168.68.2`, password set
- [x] Deco DHCP pool set to start at `.100` (reserves `.2`–`.9` for infrastructure)
- [x] Deco IoT SSID created — separate network for IoT devices (migration deferred)
- [x] HA Green initial setup complete — accessible at `http://192.168.68.3:8123`
- [x] HA Green static IP set to `192.168.68.3`
- [x] ZBT-2 plugged into HA Green, detected at `/dev/ttyACM0`
- [x] Add-ons installed (all have Start on Boot + Watchdog enabled):
  - Mosquitto MQTT Broker (`core_mosquitto`) — Running
  - File Editor (`core_configurator`) — Running
  - Terminal & SSH (`core_ssh`) — Running, **SSH key configured**
  - Zigbee2MQTT (`45df7312_zigbee2mqtt`) — **Running** ✓
  - Tailscale (`a0d7b954_tailscale`) — **Running** ✓
  - Node-RED (`a0d7b954_nodered`) — **Uninstalled** ✓ (2026-05-11)
- [x] SSH access working: `ssh root@192.168.68.3 -p 22222 -i ~/.ssh/ha_green`
- [x] Zigbee2MQTT running — Zigbee network formed on channel 11, connected to MQTT
- [x] All Zigbee devices paired: Aqara motion (LR), Hue SML001 motion (kitchen, bedroom),
      hallway motion, SmartThings vibration sensors ×3 (washer/dryer/bed), Aqara bedroom switch
- [x] Hue bridge integrated — all rooms/bulbs/scenes in HA (bedroom, LR, kitchen, hallway, foyer, dining, office, porch)
- [x] Govee local API integrated — `light.govee_lamp_1` (bedroom floor lamp)
- [x] All automations written in native HA YAML — **Node-RED fully replaced**
  - Motion-reactive lighting for LR, bedroom, kitchen, hallway (with memory lights, TV modes, snooze)
  - Bedroom switch (single/double/hold), manual mode, sleep/wake routines
  - Laundry done alerts (vibration sensors on washer + dryer)
  - Away mode + arriving home (presence detection live)
  - Internet outage warning
  - Trash reminder with auto-snooze
- [x] **Automation hardening applied** (2026-05-09):
  - Fixed vibration anti-bounce bug in `bed_sleep_routine` / `bed_wake_routine`
  - Added `input_boolean.sleep_mode_active` — suppresses bedroom motion lights during sleep
  - Added `bed_sleep_mode_expire` — failsafe clears sleep mode at 10am
  - Kitchen timeout extended 10 → 20 min; lux gate removed
  - Fixed HA 2026.5 breaking change: `color_temp` mireds → `color_temp_kelvin` Kelvin
- [x] **Integration test suite passing** (`HomeAssistant/tests/`) — 10 modules covering all automations; `python3 run_all.py health` is the post-upgrade first step (read-only, 46 automations + 41 helpers + 28 entities checked)
- [x] Snooze system implemented — `script.snooze_automation` / `clear_snooze` / `clear_all_snoozes` / `snooze_until_morning`
- [x] Room-level and per-automation toggles deployed as `input_boolean` helpers
- [x] **HACS installed** — community frontend components available
- [x] **Companion App installed** on both phones:
  - Riley: Pixel 8 → `person.riley_hollis`
  - Casey: Samsung → `person.cassandra_quinlan`
- [x] **Lovelace dashboard deployed** (YAML mode, `!include` views):
  - Mushroom Cards installed via HACS (`/hacsfiles/lovelace-mushroom/mushroom.js`)
  - Bubble Card installed via HACS (`/hacsfiles/Bubble-Card/bubble-card.js`)
  - Views live: Home, Rooms, Presence, Laundry, Automations, Energy
  - Rooms view: 2×3 room grid, each taps to full-detail Bubble Card popup
  - Automations view: conditional active-snooze alert + category popup buttons
- [x] Hallway motion automation added (`hall_motion_on` / `hall_motion_off`)
- [x] Vibration sensor entity IDs confirmed: `binary_sensor.vibration_sensor_{1,2,3}_vibration`
- [x] **ha-mcp configured** (2026-05-14) — MCP server wired into Claude Code via `.mcp.json`. ha-mcp is now the primary interface for all HA operations; SSH/curl demoted to fallback. `uv` installed at `/Users/homeuser/.local/bin/uvx`.
- [x] **Config snapshot archived** (2026-05-14) — full local snapshot at `HomeAssistant/archive/2026-05-14/` before MCP migration.
- [x] **Camera buildout planned** (2026-05-14) — see `HomeAssistant/cameras/plan.md`. Phase 1: CX810 (backyard) + RLC-811A (street intel) + TP-Link TL-SG108PE PoE switch. Frigate on Mac Mini via Docker (Apple Silicon detector).
- [x] **Blink camera integration + dashboard** (2026-05-14):
  - 6 Blink cameras integrated via native HA Blink integration (cloud, snapshot-only)
  - Camera view (`07_cameras.yaml`) deployed: Outdoor (Driveway, Rear Driveway, Backyard, Doorbell) + Indoor (G8V1 Living Room, Tilt Camera)
  - Motion status strip, per-camera alert toggles, snooze controls (1hr/4hr/clear per outdoor camera)
  - Alert logic: outdoor = alerts when dark OR away; indoor = away only
  - Blink refresh automation: `blink.trigger_camera` → 15s delay → `update_entity` every 5 min (fixes stale snapshots)
  - Camera cards use `picture-entity` (snapshot-only cameras; `camera` card with `camera_view: auto` caused config errors)

- [x] **Soil moisture sensors + garden view** (2026-05-14):
  - 3 Smart Soil Sensor Gen2 (Zigbee via Z2M) paired: Fescue Grass, Green Giant, Indoor Tree (Mass Cane)
  - Garden view (`08_garden.yaml`) updated with soil moisture section: color-coded status cards, 7-day `statistics-graph` trend charts with healthy-range reference lines
  - Alert automations: Fescue <25%, Green Giant <20%, Indoor Tree <10% (fires after 30 min continuous, 24hr cooldown)
  - Reference line helpers: `input_number.plant_{fescue/green_giant/indoor_tree}_target_{low/high}` set to healthy range bounds
  - Irrigation helpers created: `input_boolean.irrigation_{sprinklers/trees}_enabled`, `irrigation_rain_skip`, `input_datetime.irrigation_{sprinklers/trees}_last_run`

- [x] **Desktop dashboard** (2026-05-14):
  - New YAML-mode dashboard registered in `configuration.yaml` as `lovelace-desktop`
  - File: `lovelace/desktop/desktop.yaml` — 3 panel views, each full-viewport with no scrolling
  - View 1 (Overview): 3-column — Presence/Laundry/Actions | Climate/Lighting/Rooms/Media | Energy/Automations
  - View 2 (Cameras): 3-wide camera grid (2 rows), motion + alert + snooze controls below
  - View 3 (Garden): Irrigation controls | Soil moisture status | Moisture charts
  - URL: `http://192.168.68.3:8123/lovelace-desktop/overview`

- [x] **Kitchen panel** (2026-05-14):
  - 2-column layout (38fr left / 62fr right) — left: lights/media/snooze; right: cameras (Driveway + Backyard) + soil moisture mini-graphs (7-day sparklines for all 3 plants)
  - Note: HANDOFF previously said "3 columns" — actual deployed panel is 2 columns

- [x] **Repair sweep + security hardening** (2026-05-14):
  - Fixed laundry washer/dryer done automations: `strptime()` → `as_timestamp()` (310 trace failures resolved)
  - Replaced deprecated `binary_sensor: platform: ping` in configuration.yaml with Ping integration (UI setup required)
  - Created `script.cast_kitchen_panel` (cast.show_lovelace_view → media_player.kitchen_speaker) + re-enabled kitchen panel restore automation
  - Confirmed `kitchen_speaker` entity IS the Nest Hub display (supports cast commands)
  - Added `http: ip_ban_enabled: true, login_attempts_threshold: 30` to configuration.yaml (takes effect on next restart)
  - 28,051 failed auth attempts from 192.168.68.102 (Mac Mini) — confirmed our own IP, not nefarious. Source not yet identified. Monitoring to see if count increases.
  - Leviton token expired — requires manual re-auth in browser (Settings → Devices & Services → Leviton LDATA → Re-authenticate with owner@example.net)

- [x] **Bedroom morning fix** (2026-05-14): Before 8:30am → brightness 20%, 2200K, 90s fade; 8:30–9am → 60%, 2700K, 15s fade. Rest of day unchanged.
- [x] **Remote access via Cloudflare Tunnel** (2026-05-19):
  - Cloudflared add-on (`9074a9fa_cloudflared`) installed from Tobias Brenner's repo (`https://github.com/brenner-tobias/ha-addons`)
  - Tunnel "home-assistant" (ID redacted) connects to Cloudflare with token stored in add-on config
  - Route: `ha.example.com` → `http://192.168.68.3:8123` (configured in Cloudflare Zero Trust → Networks → Connectors)
  - Add-on set to boot=auto, watchdog=true
  - `172.30.33.0/24` (supervisor network) added to `trusted_proxies` in `configuration.yaml`
  - `https://ha.example.com` is live and accessible from outside the LAN

- [x] **Maintenance sync** (2026-05-15):
  - `internal_url: "http://192.168.68.3:8123"` added to `configuration.yaml` — fixes Cast/pychromecast hairpin NAT error (`_connect_hass failed for https://ha.example.com`)
  - Test suite updated: 50 automations (was 46), 49 helpers (was 41) — 4 irrigation automations + 8 lighting mode sliders added to `test_health.py`
  - Local `lovelace/resources.yaml` synced to match server (was stale at 1 resource, now all 5)
  - HA restarted to apply config change; Cast warning resolved post-restart
- [x] **Camera system pre-work complete** (2026-05-18):
  - Hardware finalized and ordered: RLC-1212A (backyard, 12MP), CX810 (street, F1.0 true color), TP-Link LS108GP (8-port all-PoE switch, chosen over TL-SG108PE — all 8 ports PoE, Auto Recovery, Extend Mode)
  - DHCP reservations planned: `192.168.68.10` (1212A backyard), `192.168.68.11` (CX810 street)
  - Docker stack written to `~/frigate/`: `docker-compose.yml` (Frigate + CompreFace 4-service + Double Take + reid-service), `config/config.yml` (backyard camera, CPU detection, 7-day recording, dual-stream), `.env` (credentials template)
  - Re-ID clustering service written to `~/reid/`: `service.py` (RTSP → InsightFace → FAISS → MQTT), `clusters.py` (SQLite-backed FAISS index), `ocr.py` (EasyOCR Code Enforcement scanner), `Dockerfile`, `requirements.txt`
  - 6 HA camera helpers created: `input_boolean.camera_automations_enabled/riley_in_backyard/backyard_mode_active`, `counter.unknown_visitors_week`, `input_number.unknown_visitor_threshold`, `input_datetime.unknown_visitor_counter_reset`
  - Training faces organized: `HomeAssistant/cameras/training/casey/` (4 photos) + `training/riley/` (added this session)
  - Code Enforcement vehicle tracking designed: OCR pipeline ("Code Enforcement" door sticker), first confirmed sighting 11:13am 2026-05-18 (Monday), reid-service will log every drive-by and publish to `reid/vehicle/code_enforcement/last_seen`
  - Coyote vs Biscuit differentiation designed: Frigate zone entry logic — dog appearing first in `door_entry_zone` (bottom of frame, house wall) → Biscuit; dog appearing first in `perimeter_zone` (sides/top, fence line) → coyote alert. No door sensor needed.

- [x] **Lighting Modes system deployed** (2026-05-14):
  - 6 modes per room: Normal, Working, Casual, Chill, Movie, Party
  - Per-room selects: `input_select.lighting_mode_{bedroom/living_room/kitchen}`
  - House-wide: `input_select.house_lighting_mode` → cascades to all rooms
  - Party color per room: `input_select.party_color_{bedroom/living_room/kitchen}` (8 named colors)
  - Mode settings (brightness/color_temp per mode) via `input_number.mode_{working/casual/chill/movie}_{brightness/color_temp}` sliders
  - Mode-change automations: lights update immediately when mode switches while on
  - Dashboard: Lighting Mode section on Home view; mode + party color selects in each room popup; Mode Settings popup with sliders (tap from Home view)
  - Room tiles in Rooms view now show current mode: "On · 75% · Casual"

- [x] **Frigate stack fully operational** (2026-05-20):
  - External drive storage: `FRIGATE_MEDIA_PATH=/Volumes/Primary/HomeAssistant/frigate` (ExFAT, Primary volume). `/Volumes` added to Colima mounts. `autostart.sh` waits up to 60s for drive to appear at boot before starting Docker. Subdirs pre-created: `recordings/`, `clips/`, `snapshots/`, `exports/`
  - LaunchDaemon installed: `com.homeuser.frigate-autostart` at `/Library/LaunchDaemons/`, runs as `homeuser` before login. Verified: `runs=1, exit code=0`
  - Docker compose fixes: added missing `compreface-admin` service (nginx in `compreface-fe` proxies to it, not `compreface-api`); fixed `PROXY_CONNECT_TIMEOUT` env var missing; corrected `PROXY_READ_TIMEOUT: 60000ms` → `60s`; reid-service Dockerfile: added `build-essential` (insightface needs g++) + CPU-only torch pre-install (avoids 2GB CUDA downloads in Colima)
  - All 8 containers healthy: `frigate` (healthy on port 5000), `compreface-{postgres,core,api,admin,ui}` (port 8000), `double-take` (port 3000), `reid-service`
  - CompreFace runs under Rosetta emulation (linux/amd64 on arm64) — expected, no ARM64 image available
  - Mac Mini ping sensor confirmed: `binary_sensor.192_168_68_102` (friendly name "Mac Mini"), added to `test_health.py` CRITICAL_ENTITIES
  - Cameras view updated: Frigate NVR section staged (camera.frigate_backyard placeholder), Backyard Intelligence panel (riley_in_backyard, backyard_mode_active, cam alerts toggle, unknown visitor counter with threshold color), Frigate Host status card
  - `test_health.py` updated: 10 per-camera helpers added to REQUIRED_HELPERS (automation toggles + snooze datetimes for backyard/doorbell/driveway/rear-driveway)

- [x] **Vehicle detection stack overhauled** (2026-06-17):
  - Removed CompreFace (5 containers) + Double Take — freed ~2-3GB RAM, eliminated OOM kills on code-enforcement
  - Stopped reid-service (intentional; re-enable when street camera installed)
  - Fixed code-enforcement OOM: EasyOCR loads ~1.5GB PyTorch model; CompreFace was exhausting RAM, kernel silently killed the container (no error in logs — just startup banner repeating)
  - Fixed `conf=0.00` bug: wrong payload path `after.get("data").get("top_score")` → `after.get("top_score", 0)`
  - Fixed OCR poisoning: `/snapshot.jpg` burns Frigate's bbox label into image; OCR read `cor: 52X 4851` instead of vehicle text. Switched to `/thumbnail.jpg` (full frame, no overlays)
  - Fixed Frigate safe mode: `required_zones` is not a valid field anywhere in Frigate 0.17 schema — removed entirely
  - Built **Vehicle Detection Review Dashboard** at `http://192.168.68.142:8501` (Streamlit container, port 8501): metric cards, data_editor table with snapshot thumbnails + correction dropdown, bulk-select/delete, Known Vehicles expander with pHash fingerprints, Plotly charts
  - Added pHash fingerprint matching: every car detection compares `imagehash.phash()` Hamming distance ≤ 12 against `known_vehicles` table — auto-classifies personal vehicles, skips OCR. Tunable via `PHASH_THRESHOLD` env var.
  - Status confirmed: 4 containers running (frigate, code-enforcement, bird-tracker, vehicle-dashboard), 20 detections all my_vehicle, 9 pHash fingerprints, 0 unclassified

- [x] **CX810 front yard camera live in Frigate** (2026-05-20):
  - TP-Link TL-SG108PE PoE switch installed (uplink port 5–8, cameras on ports 1–4). Extend OFF, Recovery OFF.
  - CX810 joined at 192.168.68.139 (DHCP reserved on Deco). Admin password set (redacted). RTSP enabled manually via Reolink app (port 554). Stream confirmed: sub 640×360 H.264, main 3840×2160 HEVC.
  - Camera is **front yard** (not backyard as originally planned) — all configs updated accordingly.
  - Frigate config renamed camera `backyard` → `front`; env vars renamed `CAMERA_BACKYARD_*` → `CAMERA_FRONT_*`; tracked objects changed to `person` + `car`.
  - Frigate port changed 5000 → 5050 (macOS AirPlay Receiver occupies :5000 and intercepts traffic).
  - Frigate auth disabled (`auth: enabled: false`) — local network, no need.
  - Virtiofs cache workaround: Colima virtiofs has stale-read lag after host file edits. Push config changes with: `cat ~/frigate/config/config.yaml | docker exec -i frigate tee /config/config.yaml > /dev/null` then `docker compose restart frigate`. Also: Frigate reads `config.yaml` not `config.yml` — correct extension now in place.
  - Frigate HACS integration installed (v5.15.3), configured at `http://192.168.68.142:5050`.
  - Reolink native integration auto-discovered and added — creates `camera.front_yard_fluent`, `camera.floodlight`.
  - **Mac Mini actual IP is 192.168.68.142** (not .102 as previously documented). Old ping integration for .102 deleted. New ping for .142 must be re-added via UI → creates `binary_sensor.192_168_68_142`.
  - Cameras view updated: Frigate card uses `camera.front_yard_fluent` (bridge until Frigate creates `camera.front`); Indoor section (Living Room + Tilt Camera feeds, motion chips, alert toggles) removed from Cameras view; placeholder second slot relabeled "Backyard (coming soon)".

### What's Next (priority order)
- [x] **Notify slugs verified and deployed** (2026-05-11)
- [x] Node-RED uninstalled (2026-05-11)
- [x] Catppuccin Mocha theme applied
- [x] Bubble Card popup navigation working on Android
- [x] ha-mcp MCP server configured (2026-05-14)
- [x] Ping integration added via UI (2026-05-14)
- [x] Leviton re-auth completed (2026-05-14)
- [x] Stale repairs dismissed (2026-05-14)
- [x] **Monitor failed auth counter** — checked 2026-05-15; no ip_bans.yaml, no login failure warnings in system log. Issue appears resolved (likely was a test script run, not a persistent problem).
- [ ] **Test suite maintenance** — when adding any automation or helper, update `tests/test_health.py` (NAMED_AUTOMATIONS, EXPECTED_AUTOMATION_COUNT, REQUIRED_HELPERS) and add a test function to the relevant module. See CLAUDE.md "Convention" section.
- [ ] Add remaining integrations: Kasa (TP-Link plugs), August Lock, Leviton LWHEM (HACS), Google Cast
- [x] Camera hardware ordered + Docker stack + HA helpers pre-built (2026-05-18) ✓
- [x] Docker stack fully running + LaunchDaemon installed + external drive storage configured (2026-05-20) ✓
- [ ] **Re-add Mac Mini ping sensor** — Settings → Devices & Services → Add Integration → Ping → `192.168.68.142` (creates `binary_sensor.192_168_68_142`; dashboard card already updated to this entity)
- [ ] **Re-enable reid-service** — when street camera (RLC-1212A backyard) is installed; run `docker compose up -d reid-service`
- [ ] **Validate OCR on real commercial vehicles** — thumbnail fix not yet confirmed on actual USPS/FedEx/UPS pass-by (only personal vehicles tested so far with pHash bypass)
- [ ] **Confirm lookalike vs code-enforcement pHash threshold** — a similarly-shaped vehicle and the code-enforcement target vehicle have similar shapes; may need to tune `PHASH_THRESHOLD` down from 12 if false-negatives appear; monitor via dashboard
- [ ] **`docker volume prune`** — reclaim disk space from removed CompreFace/Double Take volumes
- [ ] **DHCP reservation for backyard camera** — 192.168.68.144 in Deco app (when RLC-1212A arrives)
- [ ] **Fix Colima /Volumes permanent mount** — user working on this; recording process crashes without it (Frigate can't write segments to `/Volumes/Primary/HomeAssistant/frigate`)
- [ ] **Draw zones in Frigate UI** — `http://localhost:5050` → Cameras → front → Debug → draw `front_zone` polygon covering yard/approach (replace full-frame placeholder)
- [ ] **Verify MQTT flow** — `mosquitto_sub -h 192.168.68.3 -u addons -P <pass> -t "frigate/#" -v` — should fire on person/car detection in front yard
- [ ] **Camera Phase 1 — CompreFace**: Upload training faces (Riley + Casey from `HomeAssistant/cameras/training/`) via CompreFace UI at `:8000`, configure Double Take at `:3000` to point at CompreFace
- [ ] **Backyard camera** (RLC-1212A) — when installed: add to Frigate config as `backyard`, DHCP reserve, update `.env` with `CAMERA_BACKYARD_IP/PASS`, draw backyard zones
- [ ] **Camera Phase 2+**: Right-side path, Reolink Doorbell PoE, Casey arrival automation
- [ ] **Camera Phase 2**: Right-side path RLC-811A (when rear entry established)
- [ ] **Camera Phase 3**: Reolink Video Doorbell PoE + Casey arrival automation (Double Take front door → `person.casey` home)
- [ ] MagicMirror project (separate repo — after HA is fully stable)

---

## Network Layout

| Device | IP | Notes |
|---|---|---|
| Deco XE75 (gateway) | `192.168.68.1` | Router, DHCP server |
| Netgear GS308Ev4 | `192.168.68.2` | Managed switch |
| HA Green | `192.168.68.3` | Main HA server |
| ecobee thermostat | `192.168.68.129` | Named "Hearthside"; `climate.ecobee` in HA |
| Roku Ultra | `192.168.68.132` | ECP API on port 8060 |
| Hue Bridge v2 | `192.168.68.136` | MAC redacted; DHCP reserved |
| Mac Mini | `192.168.68.142` | Frigate host (Docker + Colima); Frigate UI at `:5050` |
| CX810 front camera | `192.168.68.139` | DHCP reserved; RTSP on :554; admin password redacted |
| DHCP pool | `.100`–`.254` | Regular devices |

### Switch Port Layout
```
Port 1 — Deco uplink
Port 2 — Mac Mini
Port 3 — HA Green
Ports 4-8 — available
```

---

## SSH Setup (complete)

SSH key is at `~/.ssh/ha_green` on the Mac Mini.

```bash
ssh root@192.168.68.3 -p 22222 -i ~/.ssh/ha_green
```

---

## Zigbee2MQTT — Running

### Working configuration (direct serial, 460800 baud)

The ZBT-2 runs at **460800 baud** after being initialized by the homeassistant_connect_zbt2 integration. Z2M connects directly to the serial port — no socat needed.

**Add-on Configuration tab YAML** (`Settings → Add-ons → Zigbee2MQTT → Configuration`):
```yaml
data_path: /config/zigbee2mqtt
socat:
  enabled: false
mqtt: {}
serial: {}
```

**`/config/zigbee2mqtt/configuration.yaml`**:
```yaml
version: 5
mqtt:
  base_topic: zigbee2mqtt
  server: mqtt://core-mosquitto:1883
  user: addons
  password: "<redacted — Mosquitto add-on user password>"
serial:
  port: /dev/serial/by-id/usb-Nabu_Casa_ZBT-2_REDACTEDSN01-if00
  adapter: ember
  baudrate: 460800
advanced:
  log_level: info
frontend:
  enabled: true
  port: 8099
homeassistant:
  enabled: true
permit_join: false
```

### Recovery procedure (if Z2M stops working after HA restart or ZBT-2 replug)

If Z2M fails to start (HOST_FATAL_ERROR loop):
1. Check that ZHA and homeassistant_connect_zbt2 integrations are NOT configured (Settings → Devices & Services)
2. Unplug ZBT-2, wait 15 seconds, replug
3. SSH in and restart Z2M: `ha apps restart 45df7312_zigbee2mqtt`

If Z2M still fails after the above (NCP stuck from ZHA interference):
1. Temporarily add homeassistant_connect_zbt2 via Settings → Devices & Services → Discovered (if not there, delete any ignore entry from core.config_entries)
2. Go through setup: Zigbee → recommended → let firmware flash complete
3. Immediately delete ZHA and homeassistant_connect_zbt2
4. Replug ZBT-2
5. Restart Z2M — it will connect at 460800 baud

**Do NOT re-add ZHA** — it runs bellows which sends RESET_SOFTWARE to the ZBT-2, leaving it in a state Z2M can't recover from without the full recovery procedure above.

**Zigbee2MQTT web UI**: `http://192.168.68.3:8099`

---

## HACS Installation (next up)

In the HA Terminal sidebar, run:
```bash
wget -O - https://get.hacs.xyz | bash -
```
Then restart HA: Settings → System → Restart.

After restart: Settings → Devices & Services → Add Integration → search "HACS" → follow prompts (requires GitHub account).

HACS integrations needed:
- `rwoldberg/ldata-ha` — Leviton LWHEM-2R energy monitor
- `localtuya` — BN-Link smart plugs (local control)

---

## Full Device Integration Plan

| Device | Integration | Local? | Notes |
|---|---|---|---|
| Philips Hue bridge | Hue (built-in) | Yes | Auto-discovered, add via UI |
| Govee WiFi lights | Govee Light Local (built-in) | Yes | Must enable local API in Govee app first |
| TP-Link Kasa HS103 | TP-Link Kasa (built-in) | Yes | Auto-discovered |
| BN-Link plugs | LocalTuya (HACS) | Yes | Requires setup per device |
| August Lock (front) | August (built-in) | No | Cloud only, unavoidable |
| Leviton LWHEM-2R | ldata-ha (HACS) | No | Cloud to my.leviton.com |
| Google Cast devices | Google Cast (built-in) | Yes | Chromecasts + Google speakers |
| Ecobee thermostat | Ecobee (built-in) | Partial | Auto-discovered during onboarding |
| ZBT-2 Zigbee devices | Zigbee2MQTT | Yes | Hue sensors, SmartThings sensors, others |
| GJV Lock (back door) | SKIP | — | Tuya, no good lock support yet |
| Reolink cameras | Reolink (built-in) + Frigate | Yes | Hardware not yet installed |

---

## Architecture Reference

### Protocol Map
```
ZBT-2 (USB on HA Green, /dev/ttyACM0)
├── Zigbee: Hue sensors, SmartThings sensors, off-brand sensors
└── Thread/Matter: Nest Hub 10" (Matter bridge)

Philips Hue Bridge → local API (keep bridge, don't migrate bulbs)

WiFi devices (eventually on IoT SSID):
├── Govee lights → local LAN API
├── Kasa plugs → local
├── BN-Link plugs → LocalTuya
├── August Lock → cloud
├── Leviton LWHEM-2R → cloud (ldata-ha HACS)
└── Reolink cameras (future) → local RTSP + Frigate
```

### Add-on Stack
| Add-on | Slug | Purpose | Status |
|---|---|---|---|
| Mosquitto MQTT | `core_mosquitto` | Message bus | Running ✓ |
| Zigbee2MQTT | `45df7312_zigbee2mqtt` | Zigbee via ZBT-2 | Running ✓ |
| File Editor | `core_configurator` | YAML editing | Running ✓ |
| Terminal & SSH | `core_ssh` | Shell access | Running ✓ |
| Tailscale | `a0d7b954_tailscale` | Remote access | Running ✓ |
| Node-RED | `a0d7b954_nodered` | (unused) | Uninstalled ✓ |
| Matter Server | `core_matter_server` | Matter/Thread | Running ✓ |
| Frigate NVR | — | Camera AI | Not installed (when cameras arrive) |

**HACS** (not an add-on — frontend integration): Installed ✓
- Mushroom Cards (`lovelace-mushroom`) — dashboard cards
- Bubble Card (`Bubble-Card`) — room popup overlays
- Catppuccin HA — dark theme (install via HACS → Frontend if not done)

---

## MagicMirror (separate companion project — do after HA is stable)

- Pi3 B+ dedicated to MagicMirror, located in bathroom
- Keep MagicMirror, don't replace with HA
- Add: MMM-HomeAssistant, MMM-iFrame (HA dashboard), MMM-YouTube
- Audio: route through HA → Google Cast to bathroom speaker
- Define as a separate project/repo

---

## Notes
- **gFiber** arriving in 3-6 months — will replace CM1200 modem with ONT. Rest of network unchanged.
- **IoT SSID migration** deferred — devices work identically on main WiFi, migrate lazily over time
- **NordVPN** — keep for outbound privacy only. Tailscale handles HA remote access.
- **Ecobee thermostat** — discovered during onboarding, was skipped. Add via Settings → Devices & Services when ready.
- **Wired VLAN isolation** — Deco doesn't support 802.1Q trunking. IoT SSID handles WiFi isolation. Wired VLAN requires replacing Deco with a proper router (future project).
- **ZBT-2 runs at 460800 baud direct serial** — socat is **disabled**. If Z2M stops working after a HA update, follow the recovery procedure in the Z2M section above (unplug ZBT-2, wait, replug, restart Z2M). Do NOT re-enable socat.
