# Automation & Script Design Notes

`automations.yaml`, `scripts.yaml` and `helpers.yaml` are pulled verbatim from the live system by
`tools/sync.py`. Home Assistant rewrites those files whenever an automation is saved via the UI or
ha-mcp and drops every YAML comment, so design notes that used to live inline are kept here.

## Snooze system (`scripts.yaml`)

Every automation checks `input_datetime.snooze_<id>` and skips while `now()` is before it.
`unknown` (never set) means not snoozed; clearing sets it to 1970-01-01.

```yaml
# Snooze living-room lights 30 min
service: script.snooze_automation
data: { snooze_id: "lr_motion", duration_minutes: 30 }

# Snooze the washer alert until 7am tomorrow
service: script.snooze_until_morning
data: { snooze_id: "washer_alert" }

# Clear a snooze immediately
service: script.clear_snooze
data: { snooze_id: "lr_motion" }
```

Valid `snooze_id` values: `lr_motion`, `bed_motion`, `kit_motion`, `hall_motion`,
`washer_alert`, `dryer_alert`, `internet_outage`, `away_mode`, `arriving_home`, `sleep_mode`,
`wake_mode`, `trash_reminder`, `memory_lights_lr`, `memory_lights_bed`, `memory_lights_kit`,
plus the per-camera `cam_*` snoozes created in the UI (see `helpers_storage.yaml`).

## Helpers

- **Room master switches** (`input_boolean.automations_<room>`): off disables every automation
  for that room. **Per-automation toggles** (`input_boolean.automation_<name>`): off disables one.
- **Memory lights**: `input_datetime.memory_lights_<room>_off_at` records when lights were last
  auto-turned-off. Re-entry within 30 minutes restores the previous scene; older falls back to
  time-of-day logic.
- **Laundry**: `input_datetime.{washer,dryer}_started_at` timestamps the cycle start so the
  "done" alert can require a minimum run time (15 min).
- Helpers created through the UI or ha-mcp live in HA's `.storage`, not YAML; they're exported
  read-only to `helpers_storage.yaml`.

## Door sensors → camera alert suppression

`binary_sensor.front_door_contact` / `back_door_contact` (ThirdReality Zigbee, paired
2026-07-22) each drive a grace-period automation that sets
`input_boolean.door_recently_opened_{front,back}` for a short window after the door opens.
The "Unknown Person" camera automations (`cam_unknown_front_yard`, `cam_unknown_backyard`,
`cam_unknown_visitor_count`, `floodlight_unknown_person_alert`) check these flags and skip the
alert/counter when someone appears on camera right after a door opened. The assumption is that
it's a household member Frigate's face recognition missed (it has a known miss rate; see
HANDOFF.md), not an unrecognized visitor.

## Camera notifications

Notification images use the Cloudflare-tunnel proxy URL
(`https://ha.example.net/api/frigate/notifications/<event>/snapshot.jpg`) so they load
off-LAN. The `.jpg` extension is required. Without it the image 404s silently and the
notification arrives with no thumbnail (fixed 2026-07-08).

## Irrigation (staged)

The `Irrigation:` automations target 3× Sonoff Hydro ONE (SWV-ZFU/ZFE) Zigbee valves with
assumed Z2M friendly names *Trees Valve*, *Sprinklers Valve* and *Utility Valve*
(`switch.trees_valve`, …). They're deployed ahead of the hardware: HA skips actions for
unavailable entities, so they're inert until the valves are paired.

## LR 4-way button

The Sonoff 4-button remote is physically in the living room but drives the living room and
kitchen lighting modes together, plus dedicated blinds control: button 1 toggles and cycles modes,
2 selects scenes, 3 runs the blinds, and 4 handles outdoor lights and find-my-phone.
