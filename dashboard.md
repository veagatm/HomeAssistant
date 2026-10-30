# Dashboard Architecture

Design, implementation guide, and deploy instructions for the HA Lovelace dashboards.

## Local Files (source of truth)

All dashboard YAML lives under `HomeAssistant/lovelace/`:

```
lovelace/
  ui-lovelace.yaml          — main dashboard entry point (mobile-optimized)
  resources.yaml            — HACS frontend dependencies
  views/
    01_home.yaml            — Home: presence, lighting modes, climate, lights, quick actions
    02_rooms.yaml           — Per-room light + scene + media controls (Bubble Card popups)
    03_presence.yaml        — Who's home, away mode, snooze, find-phone buttons
    04_laundry.yaml         — Washer/dryer live status, timestamps, alert snooze
    05_automations.yaml     — Room toggles, per-automation toggles, full snooze control panel
    06_energy.yaml          — Leviton LWHEM whole-home power + circuit breakdown charts
    07_cameras.yaml         — Blink cameras (6): snapshots, motion status, alerts, snooze
    08_garden.yaml          — Irrigation zones + Bubble Card popups + soil moisture + charts
  kiosk/
    kitchen_panel.yaml      — Kitchen wall display: Kitchen + LR lights + cameras + soil
  desktop/
    desktop.yaml            — Desktop command center: Overview · Cameras · Garden (3 panel views)
```

> **Naming note**: The local file `07_garden.yaml` does not exist — the garden view was deployed as `08_garden.yaml` on the server to avoid a filename collision with cameras. The canonical local source is `08_garden.yaml` matching the server name.

## Deploy

### Mobile dashboard (main)
```bash
# Views deploy individually — edit the specific view file, then:
scp -P 22222 -i ~/.ssh/ha_green HomeAssistant/lovelace/views/07_cameras.yaml \
    root@192.168.68.3:/config/lovelace/views/07_cameras.yaml
scp -P 22222 -i ~/.ssh/ha_green HomeAssistant/lovelace/views/08_garden.yaml \
    root@192.168.68.3:/config/lovelace/views/08_garden.yaml
# Then reload: HA → three-dot menu → Reload Dashboard (+ Cmd+Shift+R in browser)
```

### Kitchen panel
```bash
scp -P 22222 -i ~/.ssh/ha_green HomeAssistant/lovelace/kiosk/kitchen_panel.yaml \
    root@192.168.68.3:/config/lovelace/kiosk/kitchen_panel.yaml
# Reload: navigate to /lovelace-kitchenpanel → three-dot → Reload Dashboard
```

### Desktop dashboard
```bash
scp -P 22222 -i ~/.ssh/ha_green HomeAssistant/lovelace/desktop/desktop.yaml \
    root@192.168.68.3:/config/lovelace/desktop/desktop.yaml
# Reload: navigate to /lovelace-desktop → three-dot → Reload Dashboard
```

### Full redeploy (all files)
```bash
ssh root@192.168.68.3 -p 22222 -i ~/.ssh/ha_green \
    "mkdir -p /config/lovelace/views /config/lovelace/kiosk /config/lovelace/desktop"
scp -P 22222 -i ~/.ssh/ha_green HomeAssistant/lovelace/ui-lovelace.yaml \
    root@192.168.68.3:/config/ui-lovelace.yaml
scp -P 22222 -i ~/.ssh/ha_green HomeAssistant/lovelace/views/*.yaml \
    root@192.168.68.3:/config/lovelace/views/
scp -P 22222 -i ~/.ssh/ha_green HomeAssistant/lovelace/kiosk/kitchen_panel.yaml \
    root@192.168.68.3:/config/lovelace/kiosk/kitchen_panel.yaml
scp -P 22222 -i ~/.ssh/ha_green HomeAssistant/lovelace/desktop/desktop.yaml \
    root@192.168.68.3:/config/lovelace/desktop/desktop.yaml
```

## Dashboard Registry (configuration.yaml)

Three dashboards registered under `lovelace.dashboards`:

| Key | Title | URL | File | Purpose |
|---|---|---|---|---|
| *(main)* | Home | `/lovelace/home` | `ui-lovelace.yaml` | Mobile — 8 tabbed views |
| `kitchen-panel` | Kitchen Panel | `/lovelace-kitchenpanel` | `lovelace/kiosk/kitchen_panel.yaml` | Wall display — cast to Nest Hub |
| `lovelace-desktop` | Desktop | `/lovelace-desktop/overview` | `lovelace/desktop/desktop.yaml` | Desktop command center — 3 panel views |

> Adding a new dashboard requires editing `configuration.yaml` and **restarting HA** (not just reload). Views within an existing dashboard only need a dashboard reload.

---

---

## HACS Frontend Components — Install First

All of these go through HACS → Frontend. Install HACS first if not done:
```bash
# In HA Terminal sidebar:
wget -O - https://get.hacs.xyz | bash -
# Restart HA, then Settings → Devices & Services → Add Integration → HACS
```

| Component | HACS Name | Why |
|---|---|---|
| **Mushroom Cards** | `mushroom` | Clean, compact cards for lights, media, persons, climate |
| **Bubble Card** | `bubble-card` | Pop-up sub-views — keeps main dashboard uncluttered |
| **Atomic Calendar Revive** | `atomic-calendar-revive` | Google Calendar on dashboard |
| **Kiosk Mode** | `kiosk-mode` | Hides HA header/sidebar for tablet wall display |
| **Frosted Glass Theme** | `ha-glasscoder` | iOS-style theme — install "light" variant only |
| **Mini Graph Card** | `mini-graph-card` | Compact sensor history graphs |
| **Simple Thermostat** | `simple-thermostat` | Better Ecobee UI than the default |

---

## Dashboard Views

### Overview of Views

| View | Path | Purpose |
|---|---|---|
| Home | `/lovelace/home` | Quick status at a glance, primary controls |
| Rooms | `/lovelace/rooms` | Per-room light/media controls |
| Presence | `/lovelace/presence` | Who's home, away mode, phone locations |
| Laundry | `/lovelace/laundry` | Washer/dryer status |
| Automations | `/lovelace/automations` | Room toggles, snooze controls, state flags |
| Energy | `/lovelace/energy` | Leviton LWHEM whole-home monitor |

---

## View 1: Home (Main Dashboard)

The one screen you glance at constantly. Keep it minimal.

**Top row — Status chips (Mushroom Chips Card):**
- Person chip: Riley (shows home/away with avatar)
- Person chip: Casey (shows home/away with avatar)
- Entity chip: `input_boolean.away_mode_active` (icon: mdi:home-export-outline)
- Entity chip: `input_boolean.sleep_mode_active` (icon: mdi:sleep)
- Entity chip: `binary_sensor.ping_google` — red dot if internet down (alert flashes Govee + LR lamp, not hallway/foyer — those are not color-capable)

**Center — Climate (Simple Thermostat card):**
- `climate.ecobee` — current temp, setpoint, mode

**Light summary row (Mushroom Light Cards, horizontal stack):**
- `light.living_room` — "Living Room"
- `light.kitchen` — "Kitchen"
- `light.bedroom` — "Bedroom"

**Quick actions (Mushroom Template Cards):**
- "Good Night" → `script.good_night_all`
- "Set Trash Night" → `script.set_trash_night`
- "Find Riley" → `script.find_riley_phone`
- "Find Casey" → `script.find_casey_phone`

**Persistent notifications area:**
- `persistent_notification.internet_outage` visible here when active

---

## View 2: Rooms

One section per room using vertical stacks inside horizontal stacks.

### Living Room section
```yaml
type: vertical-stack
cards:
  - type: mushroom-title-card
    title: Living Room
    subtitle: "{{ states('sensor.living_room_motion_sensor_illuminance_lux') | round(0) }} lux"
  - type: mushroom-light-card
    entity: light.living_room
    show_brightness_control: true
    show_color_temp_control: true
    collapsible_controls: true
  - type: mushroom-light-card
    entity: light.lamp
    name: Lamp
  - type: mushroom-media-player-card
    entity: media_player.roku_ultra
    use_media_info: true
    collapsible_controls: true
```

### Bedroom section
```yaml
type: vertical-stack
cards:
  - type: mushroom-title-card
    title: Bedroom
  - type: mushroom-light-card
    entity: light.bedroom
    show_brightness_control: true
    show_color_temp_control: true
    collapsible_controls: true
  - type: mushroom-light-card
    entity: light.govee_lamp_1
    name: Floor Lamp
    show_brightness_control: true
    show_color_temp_control: true
  - type: mushroom-media-player-card
    entity: media_player.bedroom_tv_2
    collapsible_controls: true
```

### Kitchen section
```yaml
type: vertical-stack
cards:
  - type: mushroom-title-card
    title: Kitchen
  - type: mushroom-light-card
    entity: light.kitchen
    show_brightness_control: true
    show_color_temp_control: true
    collapsible_controls: true
  - type: mushroom-light-card
    entity: light.lightstrip
    name: Counter Strip
```

### Hallway / Foyer (compact row)
```yaml
type: horizontal-stack
cards:
  - type: mushroom-light-card
    entity: light.hallway
    name: Hallway
  - type: mushroom-light-card
    entity: light.foyer
    name: Foyer
```

---

## View 3: Presence

**Person cards (Mushroom Person Cards):**
```yaml
type: horizontal-stack
cards:
  - type: mushroom-person-card
    entity: person.riley
    name: Riley
    use_entity_picture: true
  - type: mushroom-person-card
    entity: person.casey
    name: Casey
    use_entity_picture: true
```

**Away mode controls:**
```yaml
type: entities
title: Away Mode
entities:
  - entity: input_boolean.away_mode_active
    name: Away Mode Active
  - entity: input_boolean.automation_away_mode
    name: Away Automation Enabled
  - entity: input_boolean.automation_arriving_home
    name: Arriving Home Automation Enabled
```

**Snooze away mode (Mushroom Template Cards):**
```yaml
type: horizontal-stack
cards:
  - type: mushroom-template-card
    primary: Snooze 1hr
    icon: mdi:alarm-snooze
    tap_action:
      action: call-service
      service: script.snooze_automation
      service_data:
        snooze_id: away_mode
        duration_minutes: 60
  - type: mushroom-template-card
    primary: Until Morning
    icon: mdi:weather-night
    tap_action:
      action: call-service
      service: script.snooze_until_morning
      service_data:
        snooze_id: away_mode
```

---

## View 4: Laundry

```yaml
type: vertical-stack
cards:
  - type: mushroom-title-card
    title: Laundry
  - type: entities
    entities:
      - entity: binary_sensor.vibration_sensor_1_vibration
        name: Washer (vibration)
      - entity: binary_sensor.vibration_sensor_2_vibration
        name: Dryer (vibration)
      - entity: input_datetime.washer_started_at
        name: Washer Started
      - entity: input_datetime.dryer_started_at
        name: Dryer Started
  - type: horizontal-stack
    cards:
      - type: mushroom-entity-card
        entity: input_boolean.automation_washer_alert
        name: Washer Alert On
      - type: mushroom-entity-card
        entity: input_boolean.automation_dryer_alert
        name: Dryer Alert On
  # Snooze laundry alerts
  - type: mushroom-title-card
    subtitle: Snooze alerts
  - type: horizontal-stack
    cards:
      - type: mushroom-template-card
        primary: Snooze Washer 30m
        icon: mdi:alarm-snooze
        tap_action:
          action: call-service
          service: script.snooze_automation
          service_data: { snooze_id: washer_alert, duration_minutes: 30 }
      - type: mushroom-template-card
        primary: Snooze Dryer 30m
        icon: mdi:alarm-snooze
        tap_action:
          action: call-service
          service: script.snooze_automation
          service_data: { snooze_id: dryer_alert, duration_minutes: 30 }
```

---

## View 5: Automations Control Panel

This is the main control surface for the snooze/toggle system.

### Room master switches
```yaml
type: entities
title: Room Automations
entities:
  - entity: input_boolean.automations_living_room
    name: Living Room — all automations
    icon: mdi:sofa
  - entity: input_boolean.automations_bedroom
    name: Bedroom — all automations
    icon: mdi:bed
  - entity: input_boolean.automations_kitchen
    name: Kitchen — all automations
    icon: mdi:chef-hat
```

### Per-automation toggles
```yaml
type: entities
title: Individual Automations
entities:
  - entity: input_boolean.automation_washer_alert
    name: Washer Done Alert
  - entity: input_boolean.automation_dryer_alert
    name: Dryer Done Alert
  - entity: input_boolean.automation_internet_outage
    name: Internet Outage Warning
  - entity: input_boolean.automation_away_mode
    name: Away Mode (both phones)
  - entity: input_boolean.automation_arriving_home
    name: Arriving Home
  - entity: input_boolean.automation_sleep_mode
    name: Sleep Mode (vibration)
  - entity: input_boolean.automation_wake_mode
    name: Wake Routine (vibration)
  - entity: input_boolean.automation_trash_reminder
    name: Trash Reminder
  - entity: input_boolean.automation_memory_lights_lr
    name: Memory Lights — Living Room
  - entity: input_boolean.automation_memory_lights_bed
    name: Memory Lights — Bedroom
  - entity: input_boolean.automation_memory_lights_kit
    name: Memory Lights — Kitchen
```

### Snooze buttons — Reusable pattern

For each automation, pair three Mushroom Template Cards in a horizontal stack:
- 30 min snooze
- 2 hr snooze
- Clear snooze (with a conditional icon that shows red when snoozed)

Example for Living Room Motion:
```yaml
type: vertical-stack
cards:
  - type: mushroom-title-card
    subtitle: LR Motion Lights
  - type: horizontal-stack
    cards:
      - type: mushroom-template-card
        primary: 30 min
        secondary: >
          {% set ts = state_attr('input_datetime.snooze_lr_motion', 'timestamp') %}
          {% if ts and ts > now().timestamp() %}
            snoozed until {{ as_datetime(ts) | as_local | as_timestamp | timestamp_custom('%-I:%M %p') }}
          {% else %}
            not snoozed
          {% endif %}
        icon: mdi:alarm-snooze
        icon_color: >
          {% set ts = state_attr('input_datetime.snooze_lr_motion', 'timestamp') %}
          {{ 'orange' if ts and ts > now().timestamp() else 'grey' }}
        tap_action:
          action: call-service
          service: script.snooze_automation
          service_data: { snooze_id: lr_motion, duration_minutes: 30 }
      - type: mushroom-template-card
        primary: 2 hrs
        icon: mdi:alarm-snooze
        tap_action:
          action: call-service
          service: script.snooze_automation
          service_data: { snooze_id: lr_motion, duration_minutes: 120 }
      - type: mushroom-template-card
        primary: Clear
        icon: mdi:alarm-off
        tap_action:
          action: call-service
          service: script.clear_snooze
          service_data: { snooze_id: lr_motion }
```

Repeat this pattern for each snooze ID. The `secondary` text shows the current
snooze expiry time so you always know when it clears.

### State flags (manual overrides)
```yaml
type: entities
title: State Flags
entities:
  - entity: input_boolean.sleep_mode_active
    name: Sleep Mode Active
    icon: mdi:sleep
  - entity: input_boolean.trash_night
    name: Trash Night
    icon: mdi:trash-can
  - entity: input_boolean.away_mode_active
    name: Away Mode Active
    icon: mdi:home-export-outline
  - entity: input_boolean.bed_manual_mode
    name: Bedroom Manual Mode
    icon: mdi:movie
```

---

## View 6: Energy

```yaml
type: vertical-stack
cards:
  - type: mushroom-title-card
    title: Energy
  - type: sensor
    entity: sensor.leviton_lwhem_power  # [VERIFY entity ID]
    graph: line
    detail: 2
    name: Whole-Home Power (W)
  - type: mini-graph-card
    entity: sensor.leviton_lwhem_energy  # [VERIFY entity ID]
    name: Daily Energy (kWh)
    hours_to_show: 24
    group_by: hour
```

---

## Bubble Card Pop-ups (optional enhancement)

Bubble Card lets you hide detail behind a tap so the main view stays clean.
Install from HACS → Frontend → "Bubble Card".

Example: wrap a room's full controls in a pop-up triggered from a single card:
```yaml
type: custom:bubble-card
card_type: button
button_type: state
entity: light.living_room
name: Living Room
icon: mdi:sofa
tap_action:
  action: fire-dom-event
  bubble_command:
    command: open
    id: lr_popup
```

Then define the pop-up (placed at the end of the view):
```yaml
type: custom:bubble-card
card_type: pop-up
id: lr_popup
title: Living Room Controls
cards:
  - type: mushroom-light-card
    entity: light.living_room
    show_brightness_control: true
    show_color_temp_control: true
  - type: mushroom-light-card
    entity: light.lamp
  - type: mushroom-media-player-card
    entity: media_player.roku_ultra
    collapsible_controls: true
```

---

## Kiosk Mode (Tablet Wall Mount)

To hide the HA header/sidebar on a dedicated wall tablet:
1. Install Kiosk Mode from HACS → Frontend.
2. Append `?kiosk` to the dashboard URL: `http://192.168.68.3:8123/lovelace/home?kiosk`
3. Or configure in `configuration.yaml` to always hide for a specific user.

Ideal tablet setup: create a dedicated HA user (e.g., "Wall Tablet"), log in on the tablet
browser, and bookmark the kiosk URL. The account can be restricted to dashboard-only access.

---

## Frosted Glass Theme

Install via HACS → Frontend → "ha-glasscoder". Apply in your HA profile (bottom-left
avatar → Theme). Use the **light** variant — the dark full variant has rendering bugs
on iPads and causes pop-up glitches with Bubble Card.

---

## Next Dashboard Steps (priority order)

1. Install HACS (prerequisite for everything else)
2. Install Mushroom Cards — enables the card types above
3. Build the **Automations Control Panel** view (most operationally useful — lets you
   snooze/disable without going to Developer Tools)
4. Build the **Home** overview view
5. Install Bubble Card + Frosted Glass Theme for aesthetics
6. Add a dedicated tablet dashboard (Kiosk Mode URL)

---

## Entity IDs to Verify Before Building Dashboards

These appear in the card configs above but need confirmation in Developer Tools → States:

| Alias | Expected entity | Check |
|---|---|---|
| Ecobee thermostat | `climate.ecobee` | States → filter `climate.` |
| Kitchen speaker | `media_player.kitchen_speaker` | States → filter `media_player.` |
| Leviton power sensor | `sensor.leviton_lwhem_power` | States → filter `sensor.leviton` |
| Person Riley | `person.riley` | Created after Companion App + People setup |
| Person Casey | `person.casey` | Created after Companion App + People setup |
| Ping sensor | `binary_sensor.ping_google` | Created after configuration.yaml ping setup |
