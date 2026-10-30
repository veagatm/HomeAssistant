# Automation Test Plans

Two complementary test layers:

**Automated (Python)** — `HomeAssistant/tests/` — run from the Mac at any time:
```bash
cd HomeAssistant/tests
pip3 install requests paho-mqtt   # once
echo "YOUR_LONG_LIVED_TOKEN" > ~/.ha_token   # once
echo "YOUR_MQTT_PASSWORD" > ~/.mqtt_pass     # once
python3 run_all.py health         # post-upgrade first step (read-only)
python3 run_all.py                # full suite
```

**Manual** — this file — for tests that require physical interaction
(pressing a switch, walking in front of a sensor, listening for TTS).

---

## After Every HA Upgrade — Automated Health Check

Run immediately after restart. This is read-only and safe at any time:
```bash
python3 run_all.py health
```
Checks:
- All 46 automations are loaded and enabled
- All critical entities exist (lights, sensors, cameras, persons, climate)
- All 35+ helpers exist
- All scripts exist
- Room automation toggles are enabled

If any fail, check Developer Tools → Logs for YAML parse errors or entity
registry migrations before running the full suite.

---

## Automated Test Modules

| Module | What it tests | Run time |
|---|---|---|
| `health` | Entity registry, automation count, helpers (read-only) | ~5s |
| `snooze` | snooze/clear_snooze scripts, guard template | ~15s |
| `presence` | Away mode, arriving home, sleep/snooze blocks | ~30s |
| `scripts` | good_night_all, set_trash_night, find phone | ~15s |
| `cameras` | Camera entity health, motion alert automations | ~10s |
| `soil` | Soil sensor registration, alert automations | ~15s |
| `motion` | Motion → light automations (MQTT inject) | ~60s |
| `tv` | TV state → light dimming automations | ~90s |
| `switch` | Bedroom switch single/double/hold actions | ~45s |
| `laundry` | Washer/dryer vibration detection | ~20s |

---

## Adding Tests for New Capabilities

**Convention:** when adding a new automation via ha-mcp, also:
1. Add its alias to `REQUIRED_AUTOMATION_ALIASES` in `test_health.py`
2. Update `EXPECTED_AUTOMATION_COUNT` in `test_health.py`
3. Add a test function to the relevant module (or create `test_<area>.py`)
4. Register new helpers in `REQUIRED_HELPERS` in `test_health.py`
5. Register new critical entities in `CRITICAL_ENTITIES` in `test_health.py`

---

## MCP vs REST for Testing

**Use the Python REST tests** (`tests/`) for all automated testing — they run
from the Mac without Claude Code and can be scheduled or run in CI. The REST API
is always available and is what ha-mcp uses internally.

**Use ha-mcp** (Claude Code) when:
- Pulling live automation configs to verify test coverage matches reality
- Investigating a test failure (check automation traces, entity state, logs)
- Generating new test stubs when a new automation is added

---

## Before All Manual Tests — Verify Prerequisites

1. All helpers exist: Settings → Devices & Services → Helpers
   - Confirm all `input_boolean.automations_*` show as **on**
   - Confirm all `input_boolean.automation_*` show as **on**
   - Confirm all `input_datetime.snooze_*` exist (state will be `unknown`)

2. All automations loaded: Settings → Automations — count should be **46**.
   If any are missing, check Developer Tools → Logs for YAML parse errors.

3. Scripts loaded: Developer Tools → Services → search `script.snooze_automation`
   — it should appear.

---

## Snooze System

### Test: snooze_automation script
**Trigger:** Developer Tools → Services → `script.snooze_automation`
```yaml
snooze_id: lr_motion
duration_minutes: 30
```
**Expected:**
- `input_datetime.snooze_lr_motion` changes from `unknown` to a timestamp
  ~30 minutes from now.

**Verify:** Developer Tools → States → `input_datetime.snooze_lr_motion`
Should show a future time.

---

### Test: Snooze blocks the automation
**Setup:** With snooze active on `lr_motion` (from above test):
1. Developer Tools → Services → `homeassistant.turn_on`
   target: `binary_sensor.living_room_motion_sensor_occupancy` (can't do this —
   binary sensors are read-only)

**Better method:** Use Template Editor to check the snooze template manually:
```jinja
{% set ts = state_attr('input_datetime.snooze_lr_motion', 'timestamp') %}
{{ ts is none or ts < now().timestamp() }}
```
While snoozed → should return `false`.

---

### Test: clear_snooze script
**Trigger:** Developer Tools → Services → `script.clear_snooze`
```yaml
snooze_id: lr_motion
```
**Expected:** `input_datetime.snooze_lr_motion` resets to `1970-01-01 00:00:00`.
Template from above now returns `true`.

---

### Test: snooze_until_morning script
**Trigger:** Developer Tools → Services → `script.snooze_until_morning`
```yaml
snooze_id: lr_motion
```
**Expected:** `input_datetime.snooze_lr_motion` is set to tomorrow at 07:00:00.

---

## Room-Level Toggle

### Test: Disable Living Room automations
1. Developer Tools → Services → `input_boolean.turn_off`
   target: `input_boolean.automations_living_room`
2. Walk into living room (or simulate: fire motion trigger via MQTT Dev Tools)
3. **Expected:** Lights do NOT turn on.
4. Re-enable: `input_boolean.turn_on` → `input_boolean.automations_living_room`
5. Confirm lights turn on on next motion.

---

## Memory Lights

### Test: Snapshot and restore (Living Room)
**Prerequisites:** Living room lights must be on and the Roku must be off/idle.

1. Turn on living room lights manually and set a non-default color (e.g., dim red).
2. Simulate "no motion for 10 min" by either:
   - Waiting 10 min with no motion, OR
   - Temporarily change the `for: minutes: 10` to `for: seconds: 10` in automations.yaml,
     redeploy, and trigger.
3. **Expected after 10 min no-motion:**
   - `input_datetime.memory_lights_lr_off_at` is set to now
   - `scene.memory_lights_lr` is created
   - Lights turn off
4. Within 30 minutes: trigger motion again (wave in front of sensor, or use
   MQTT Dev Tools to publish to `zigbee2mqtt/Living Room Motion Sensor` with
   `{"occupancy": true}`)
5. **Expected:** Lights restore to the dim red state, not the default
   time-of-day brightness.

---

### Test: Memory lights expire after 30 min
Same as above, but wait >30 minutes before re-triggering motion.
**Expected:** Lights turn on using time-of-day logic (not the red scene).

---

## Washer / Dryer Done

### Test: Washer done alert
**Prerequisites:** Vibration sensor paired to Z2M. Entity should be
`binary_sensor.vibration_sensor_1_vibration` (verify in States).

**Method 1 (manual vibration):**
1. Set `input_datetime.washer_started_at` via Services to a time >15 min ago:
   ```yaml
   service: input_datetime.set_datetime
   target: input_datetime.washer_started_at
   data:
     datetime: "{{ (now() - timedelta(minutes=20)).strftime('%Y-%m-%d %H:%M:%S') }}"
   ```
2. Vibrate the washer sensor (tap it) to get the `on` state.
3. Stop vibrating and wait 3 minutes.
4. **Expected:** Push notification on both phones titled "🧺 Washer Done" and
   TTS on kitchen speaker.

**Method 2 (MQTT inject):**
In Z2M web UI → Washer vibration sensor → publish `{"vibration": false}` manually.

**Snooze test:**
1. Snooze `washer_alert` for 30 min via `script.snooze_automation`.
2. Repeat the trigger above.
3. **Expected:** No notification fires.

---

## Presence — Away Mode

### Prerequisites
- HA Companion App installed on Riley's Pixel 8 and Casey's Samsung.
- `person.riley_hollis` and `person.cassandra_quinlan` exist in States (both Companion Apps installed).
- `input_boolean.away_mode_active` is `off`.

### Test: Away mode activates when both leave
1. Confirm both persons show `home` in States.
2. Have both people physically leave the home zone (or test by moving phones
   outside GPS geofence).
3. **Expected after 5 min:** 
   - `input_boolean.away_mode_active` → `on`
   - All lights turn off
   - `climate.ecobee` preset changes to `away`
   - Both phones receive "🏠 Away Mode On" notification

### Test: Away mode does NOT fire during sleep
1. Set `input_boolean.sleep_mode_active` to `on`.
2. Trigger the away condition (both phones away 5 min).
3. **Expected:** Away mode does NOT activate.

### Test: Arriving home
1. With `input_boolean.away_mode_active = on`, have one person enter the home zone.
2. **Expected:**
   - `input_boolean.away_mode_active` → `off`
   - Foyer and hallway lights turn on (warm, medium brightness)
   - Ecobee preset → `home`
   - TTS: "Welcome home, Riley!" (or Casey, whichever triggered)

### Test: Second person arriving after away mode cleared
1. Riley arrives (away mode cleared by test above).
2. Casey arrives.
3. **Expected:** No automation fires (away_mode_active is already off).

---

## Internet Outage

### Prerequisites
Ping sensor configured in configuration.yaml and `binary_sensor.ping_google` exists.

### Test: Alert fires
**Method:** Block DNS temporarily at the router level, OR test with Template Editor:
1. Developer Tools → Template Editor:
   ```jinja
   {{ states('binary_sensor.ping_google') }}
   ```
   Should return `on` normally.

2. To simulate without real outage: temporarily edit the automation's trigger
   to fire on `to: "on"` instead of `to: "off"`, save, trigger, then revert.

**Expected when ping fails for 2 min:**
- Persistent notification "⚠️ Internet Down" appears in HA sidebar notification bell.
- Hallway lights flash red for 5 seconds.
- TTS announcement on kitchen speaker.

### Test: Alert clears when internet restores
**Expected:** When `binary_sensor.ping_google` returns to `on`, the persistent
notification disappears automatically.

---

## Sleep Mode

### Test: Bed switch hold → sleep mode
1. Press and hold the bedroom Aqara switch.
2. **Expected:**
   - `input_boolean.sleep_mode_active` → `on`
   - All main lights turn off
3. Trigger bedroom motion (wave in front of sensor).
4. **Expected:** Lights do NOT turn on (sleep mode blocks `bed_motion_on`).

### Test: Bed switch single → clears sleep mode
1. With sleep mode active, single-press the bedroom switch.
2. **Expected:** `input_boolean.sleep_mode_active` → `off`
3. Trigger bedroom motion.
4. **Expected:** Lights turn on normally.

### Test: Vibration sleep routine (nighttime)
1. Ensure time is between 22:00 and 05:30.
2. Set bed frame vibration sensor to active, wait 3+ minutes, then stop.
3. **Expected:**
   - `input_boolean.sleep_mode_active` → `on`
   - Bedroom and living room lights turn off.

### Test: Snooze sleep mode
1. Snooze `sleep_mode` for 30 min.
2. Trigger the vibration at night.
3. **Expected:** Sleep mode does NOT activate.

---

## Wake Routine

### Test: Vibration wake routine (morning)
1. Ensure time is between 05:30 and 09:00.
2. Set `input_boolean.sleep_mode_active = on`.
3. Trigger bed frame vibration sensor.
4. **Expected:**
   - `input_boolean.sleep_mode_active` → `off`
   - Bedroom lights turn on at brightness 51, color_temp 370, 60-second transition.

---

## Trash Reminder

### Test: Reminder fires on kitchen entry
1. Set `input_boolean.trash_night = on` (via Services or dashboard toggle).
2. Clear the snooze: `script.clear_snooze { snooze_id: trash_reminder }`.
3. Ensure time is between 19:00 and 23:00 (or temporarily edit the time condition).
4. Trigger kitchen motion sensor.
5. **Expected:**
   - TTS announcement: "Hey, reminder: tonight is trash night..."
   - `input_datetime.snooze_trash_reminder` is set 2 hours forward (auto-snooze).

### Test: No repeat for 2 hours
1. Trigger kitchen motion again within 2 hours of above test.
2. **Expected:** No TTS fires (auto-snooze is active).

### Test: Midnight reset
1. Wait until 00:01 (or change the trigger time temporarily to test).
2. **Expected:**
   - `input_boolean.trash_night` → `off`
   - `input_datetime.snooze_trash_reminder` reset to `1970-01-01`

---

## Find My Phone Scripts

### Test: Find Riley's phone
1. Developer Tools → Services → `script.find_riley_phone`
2. **Expected:**
   - Riley's Pixel 8 receives a high-priority push notification.
   - TTS on kitchen speaker: "Riley, your phone is being looked for."

### Test: Find Casey's phone
1. Developer Tools → Services → `script.find_casey_phone`
2. **Expected:**
   - Casey's Samsung receives a high-priority push notification.
   - TTS on kitchen speaker: "Casey, your phone is being looked for."

> **Note:** If the notification doesn't appear, check Developer Tools → Services →
> search `notify.mobile_app_` to find the actual service slug for each phone.
> Update the slug in `scripts.yaml` and redeploy.

---

## set_trash_night Script

### Test
1. Developer Tools → Services → `script.set_trash_night`
2. **Expected:**
   - `input_boolean.trash_night` → `on`
   - `input_datetime.snooze_trash_reminder` → `1970-01-01` (cleared, ready to fire)

---

## Good Night Script

### Test
1. Developer Tools → Services → `script.good_night_all`
2. **Expected:**
   - `input_boolean.sleep_mode_active` → `on`
   - All lights in every room turn off.

---

## Camera Integration (Blink)

### Test: Camera images display on dashboard
1. Navigate to `/lovelace/cameras` or the Desktop dashboard Cameras view.
2. **Expected:** All 6 camera cards show a recent image (not a grey placeholder).
3. If images are grey/broken: hard-reload browser (Cmd+Shift+R) first.
4. If still missing: check `camera.driveway` in Developer Tools → States. If `unavailable`,
   the Blink integration may need re-auth via Settings → Integrations → Blink.

### Test: Force a fresh snapshot
1. Developer Tools → Services → `automation.trigger`
   ```yaml
   entity_id: automation.system_blink_snapshot_refresh
   ```
2. Wait 20 seconds.
3. **Expected:** `entity_picture` URLs on camera entities update (timestamp in URL changes).
4. **Automated:** `python3 run_all.py cameras`

### Test: Motion alert fires (Driveway)
1. Trigger motion on the driveway camera (wave in view, or use Blink app to arm + detect).
2. **Expected:** Both phones receive "🚗 Motion: Driveway" notification.
3. **Note:** Alert automations only fire when armed — check `input_boolean.away_mode_active`
   or the per-camera conditions in the automation.

---

## Soil Moisture Sensors

### Test: Sensor reads in dashboard
1. Check kitchen panel 3rd column or Garden view.
2. **Expected:** All three plants show a moisture percentage (not "Unknown").
3. If "Unknown": sensor may be sleeping. Wait ~30 min for next Z2M report.

### Test: Low moisture alert fires
**Automated:** `python3 run_all.py soil`

**Manual verification:**
1. Developer Tools → States → `sensor.fescue_grass_soil_moisture_soil_moisture`
   → set state to `15` via POST (or use Python test).
2. Developer Tools → Services → `automation.trigger`
   ```yaml
   entity_id: automation.plant_fescue_grass_low_moisture_alert
   skip_condition: false
   ```
3. **Expected:** Push notification on both phones and TTS on kitchen speaker.

### Test: Statistics graph shows history
1. Garden view → Fescue Grass chart.
2. **Expected:** A line graph appears with mean moisture over time, two flat reference
   lines (target low/high), and period selector buttons (hour/day/week).
3. If flat/empty: statistics may not have accumulated yet — wait 24h after first pairing.

---

## Lighting Modes

### Test: House-wide mode change
1. Desktop dashboard → Center column → House lighting mode selector.
2. Change from "Normal" to "Movie".
3. **Expected:** All room selectors change to "Movie" and any on lights dim to movie mode.
4. Change back to "Normal".
5. **Expected:** All room selectors update, lights restore to normal brightness.

### Test: Room-level override
1. Change House mode to "Normal".
2. Change only Living Room to "Movie".
3. **Expected:** LR lights dim; Bedroom/Kitchen remain in Normal.

---

## Presence Automations (Manual — requires leaving home zone)

### Test: Away mode activates
1. Both persons must physically leave (or move phone outside GPS geofence).
2. Wait 5 minutes.
3. **Expected:**
   - `input_boolean.away_mode_active` → `on`
   - All lights off
   - Ecobee → away preset
   - Both phones: "🏠 Away Mode On" notification

### Test: Arriving home
1. With away mode active, one person enters the home zone.
2. **Expected:**
   - `input_boolean.away_mode_active` → `off`
   - Foyer/hallway lights on (warm, medium)
   - Ecobee → home preset
   - TTS: "Welcome home, [name]!"

**Note:** Away mode and arriving home automations can also be tested without leaving home
via `python3 run_all.py presence` — that test uses set_state() to fake person locations.

---

## Common Debugging Steps

**Automation didn't fire:**
1. Settings → Automations → find the automation → check Last Triggered time.
2. If it triggered but did nothing: click the automation → Traces tab — shows which
   condition failed and why.
3. If it never triggered: verify the trigger entity ID matches exactly what appears
   in Developer Tools → States.

**TTS didn't play:**
1. Check that `media_player.kitchen_speaker` exists in States and is not `unavailable`.
2. Test TTS directly: Developer Tools → Services → `tts.speak`
   ```yaml
   target:
     entity_id: tts.google_en_com
   data:
     media_player_entity_id: media_player.kitchen_speaker
     message: "Test"
   ```

**Automation count wrong after upgrade:**
```bash
python3 run_all.py health
```
If `test_automation_count` fails, check for automations that failed to load due to YAML
errors or missing entity dependencies. Developer Tools → Logs → filter "automation".

**Vibration sensor entity IDs:**
The `[VERIFY entity ID]` comments in automations.yaml refer to:
- `binary_sensor.vibration_sensor_1_vibration` — Washer
- `binary_sensor.vibration_sensor_2_vibration` — Dryer
- `binary_sensor.vibration_sensor_3_vibration` — Bed frame

Confirm these in Developer Tools → States by filtering for `vibration`. The actual
slug depends on what name was used when pairing in Z2M. If the entity IDs differ,
update automations.yaml accordingly.
