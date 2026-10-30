# configuration.yaml Additions

This file contains YAML snippets that must be added to `/config/configuration.yaml` on
HA Green before deploying the new automations. None of these go into `automations.yaml`
— they are top-level configuration directives.

---

## 1. Scripts file include

Add this line to `configuration.yaml` so HA loads `scripts.yaml`:

```yaml
script: !include scripts.yaml
```

SCP the scripts file first:
```bash
scp -P 22222 -i ~/.ssh/ha_green scripts.yaml root@192.168.68.3:/config/scripts.yaml
```

---

## 2. Ping (Internet Outage) Sensor

Required by the `sys_internet_down` / `sys_internet_up` automations.

```yaml
binary_sensor:
  - platform: ping
    host: 8.8.8.8
    name: ping_google
    count: 2
    scan_interval: 60
```

This creates `binary_sensor.ping_google`. State is `on` (reachable) or `off` (unreachable).

> **Note:** If you already have a `binary_sensor:` section, add the list entry inside
> the existing section — do not create a second `binary_sensor:` key.

---

## 3. Notification Group (both phones)

Required by laundry alerts, away mode, and any automation that calls `notify.all_phones`.

```yaml
notify:
  - platform: group
    name: "all_phones"
    services:
      - service: mobile_app_pixel_8       # Riley's Pixel 8 — confirmed
      - service: mobile_app_casey_s_galaxy  # Casey's Samsung — confirmed
```

**How to find the exact service slugs:**
1. Install HA Companion App on both phones and log in.
2. In HA: Developer Tools → Services → search `notify.mobile_app_`
3. The full service names appear, e.g. `notify.mobile_app_pixel_8` or
   `notify.mobile_app_sm_s918b`. The part after `notify.` is the service name
   that goes in the `services:` list above.

> If `notify.all_phones` is called before the group is configured, HA will log an
> error but won't crash — the TTS announcement still fires.

---

## 4. Person Entities (Riley & Casey)

Required by `presence_away_mode` and `presence_arriving_home` automations.

**Preferred: configure via the UI** (easier, handles tracker linking automatically):
1. Settings → People → Add Person → "Riley" → link to Riley's phone device tracker
2. Settings → People → Add Person → "Casey" → link to Casey's phone device tracker

This creates `person.riley_hollis` and `person.cassandra_quinlan` (done — both Companion Apps installed).

**Alternative: YAML** (add to `configuration.yaml`):
```yaml
person:
  - name: Riley
    id: riley
    device_trackers:
      - device_tracker.pixel_8          # [VERIFY slug — appears in States after Companion App]
  - name: Casey
    id: casey
    device_trackers:
      - device_tracker.galaxy_s         # [VERIFY slug]
```

> **Important:** The `device_tracker` entity IDs depend on the phone's name as
> registered in the Companion App. Check Developer Tools → States → filter by
> `device_tracker.` to see what appeared after app install.

---

## 5. Helpers (packages approach — recommended)

Instead of manually merging `helpers.yaml` into `configuration.yaml`, use packages:

```bash
# On HA Green:
ssh root@192.168.68.3 -p 22222 -i ~/.ssh/ha_green "mkdir -p /config/packages"
```

Add to `configuration.yaml`:
```yaml
homeassistant:
  packages: !include_dir_named packages
```

Then copy the helpers file:
```bash
scp -P 22222 -i ~/.ssh/ha_green \
  HomeAssistant/helpers.yaml \
  root@192.168.68.3:/config/packages/helpers.yaml
```

---

## Full Deploy Sequence

Run this after making all the configuration.yaml edits above:

```bash
# 1. Copy automations
scp -P 22222 -i ~/.ssh/ha_green \
  HomeAssistant/automations.yaml \
  root@192.168.68.3:/config/automations.yaml

# 2. Copy scripts
scp -P 22222 -i ~/.ssh/ha_green \
  HomeAssistant/scripts.yaml \
  root@192.168.68.3:/config/scripts.yaml

# 3. Copy helpers (if using packages approach)
scp -P 22222 -i ~/.ssh/ha_green \
  HomeAssistant/helpers.yaml \
  root@192.168.68.3:/config/packages/helpers.yaml

# 4. Full restart (required when configuration.yaml changes)
ssh root@192.168.68.3 -p 22222 -i ~/.ssh/ha_green "ha core restart"

# 5. After restart, verify helpers exist:
#    Settings → Devices & Services → Helpers → confirm all input_booleans and
#    input_datetimes appear with their new names.

# 6. Reload automations only (faster, after automations-only changes):
ssh root@192.168.68.3 -p 22222 -i ~/.ssh/ha_green "ha core reload automations"
```

---

## What the Room-Toggle and Snooze Helpers Initialize To

After HA restarts with the new helpers, every `input_boolean` with `initial: true` will
default to **on** (automations enabled). The snooze `input_datetime` values default to
`unknown` (never snoozed).

To confirm initial state: Settings → Developer Tools → States → filter by
`input_boolean.automations_` — all should show `on`.
