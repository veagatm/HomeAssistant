"""
Infrastructure health checks — run after any HA upgrade or config change.
Read-only: makes no state changes, safe to run anytime.

Usage:
    python3 run_all.py health
    python3 run_all.py              # included in full suite
"""

import sys
import os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(__file__))

import requests
from ha_client import get_state, _headers, _session, HA_URL

# ── Counts ────────────────────────────────────────────────────────────────────
# Update when adding new automations
EXPECTED_AUTOMATION_COUNT = 100

# ── Critical entities ─────────────────────────────────────────────────────────
# If any are missing (404), the test fails hard.
# If any are "unavailable", the test warns but doesn't fail — some devices
# go offline temporarily (Zigbee sensors asleep, Matter devices, etc.).
CRITICAL_ENTITIES = [
    # Lights
    "light.living_room", "light.kitchen", "light.bedroom",
    "light.lamp", "light.lightstrip", "light.tv_light",
    "light.front_left", "light.front_right", "light.back_left",
    # Media
    "media_player.roku_ultra", "media_player.kitchen_speaker",
    # Soil sensors (Zigbee — may sleep)
    "sensor.fescue_grass_soil_moisture_soil_moisture",
    "sensor.green_giant_soil_sensor_soil_moisture",
    "sensor.indoor_tree_soil_moisture_soil_moisture",
    # Motion sensors
    "sensor.kitchen_motion_sensor_illuminance",
    "sensor.mmw_motion_sensor_illumination",
    "binary_sensor.mmw_motion_sensor_occupancy",
    "binary_sensor.bedroom_motion_sensor_occupancy",
    "binary_sensor.kitchen_motion_sensor_occupancy",
    # Presence
    "person.riley_hollis", "person.cassandra_quinlan",
    # Infrastructure
    "sensor.breaker_panel_watts",
    "binary_sensor.ping_google",
    "binary_sensor.192_168_68_142",   # Mac Mini (Frigate host, IP .142)
    "climate.ecobee",
    "sensor.mac_mini_speed_test_download_speed",   # freshness checked separately, see test_speedtest_freshness
    # Energy monitoring — console plugs
    "sensor.entertainment_console_plug1_power",
    "sensor.entertainment_console_plug2_power",
    # Blinds (Matter over Thread)
    "cover.kitchen_blinds",
    "cover.living_room_blinds",
    # Outdoor lights
    "light.h702b",   # Govee outdoor string lights ("outdoor color lights"), backyard
    # Door sensors (ThirdReality Zigbee, added 2026-07-22)
    "binary_sensor.front_door_contact",
    "binary_sensor.back_door_contact",
    # LR 4-way button (Sonoff Zigbee, added 2026-09-14)
    "sensor.4_way_button_battery",
    # UPS (CyberPower via Mac Mini ups_monitor.py → MQTT, added 2026-10-06)
    "binary_sensor.ups_on_battery",
    "sensor.ups_battery",
]

# ── Required helpers ──────────────────────────────────────────────────────────
# All must exist. Missing helper = automation will break silently.
# Add new helpers here when created.
REQUIRED_HELPERS = [
    # Room-level toggles
    "input_boolean.automations_living_room",
    "input_boolean.automations_bedroom",
    "input_boolean.automations_kitchen",
    # State flags
    "input_boolean.sleep_mode_active",
    "input_boolean.away_mode_active",
    "input_boolean.trash_night",
    "input_boolean.bed_manual_mode",
    # Irrigation placeholders (pre-created for when hardware arrives)
    "input_boolean.irrigation_sprinklers_enabled",
    "input_boolean.irrigation_trees_enabled",
    "input_boolean.irrigation_rain_skip",
    # Snooze datetimes
    "input_datetime.snooze_lr_motion",
    "input_datetime.snooze_bed_motion",
    "input_datetime.snooze_kit_motion",
    "input_datetime.snooze_washer_alert",
    "input_datetime.snooze_dryer_alert",
    "input_datetime.snooze_internet_outage",
    "input_datetime.snooze_away_mode",
    "input_datetime.snooze_arriving_home",
    "input_datetime.snooze_sleep_mode",
    "input_datetime.snooze_wake_mode",
    "input_datetime.snooze_trash_reminder",
    "input_datetime.snooze_memory_lights_lr",
    "input_datetime.snooze_memory_lights_bed",
    "input_datetime.snooze_memory_lights_kit",
    # Laundry tracking
    "input_datetime.washer_started_at",
    "input_datetime.dryer_started_at",
    # Irrigation schedule tracking
    "input_datetime.irrigation_sprinklers_last_run",
    "input_datetime.irrigation_trees_last_run",
    # Lighting mode selectors (note: room selectors use lighting_mode_<room> pattern)
    "input_select.house_lighting_mode",
    "input_select.lighting_mode_living_room",
    "input_select.lighting_mode_bedroom",
    "input_select.lighting_mode_kitchen",
    # Party color selectors
    "input_select.party_color_living_room",
    "input_select.party_color_bedroom",
    "input_select.party_color_kitchen",
    # Lighting mode settings sliders
    "input_number.mode_working_brightness",
    "input_number.mode_working_color_temp",
    "input_number.mode_casual_brightness",
    "input_number.mode_casual_color_temp",
    "input_number.mode_chill_brightness",
    "input_number.mode_chill_color_temp",
    "input_number.mode_movie_brightness",
    "input_number.mode_movie_color_temp",
    # Camera / security helpers (Frigate)
    "input_boolean.camera_automations_enabled",
    "input_boolean.riley_in_backyard",
    "input_boolean.backyard_mode_active",
    "counter.unknown_visitors_week",
    "input_number.unknown_visitor_threshold",
    "input_datetime.unknown_visitor_counter_reset",
    # Soil moisture reference lines
    "input_number.plant_fescue_target_low",
    "input_number.plant_fescue_target_high",
    "input_number.plant_green_giant_target_low",
    "input_number.plant_green_giant_target_high",
    "input_number.plant_indoor_tree_target_low",
    "input_number.plant_indoor_tree_target_high",
    # Front Yard Floodlight
    "input_boolean.floodlight_siren_escalation_enabled",
    # Door sensors (ThirdReality Zigbee, added 2026-07-22)
    "input_boolean.door_recently_opened_front",
    "input_boolean.door_recently_opened_back",
    # Bedroom TV camera PiP via QuickBars (added 2026-10-08)
    "input_boolean.automation_bed_tv_camera_pip",
    "input_datetime.snooze_bed_tv_camera_pip",
]

# ── Automation entity IDs ─────────────────────────────────────────────────────
# HA generates entity_id from the alias (friendly name), not from the YAML id: field.
# Update this list whenever automations are added or renamed.
NAMED_AUTOMATIONS = [
    "automation.lr_motion_on_lights",
    "automation.lr_no_motion_10_min_lights_off",
    "automation.lr_tv_on_pre_movie_mode_2",
    "automation.lr_tv_playing_movie_mode",
    "automation.lr_tv_paused_idle_dim_warm",
    "automation.lr_tv_off_restore",
    "automation.lr_lighting_mode_changed_update_lights",
    "automation.bed_motion_on_lights",
    "automation.bed_no_motion_15_min_lights_off",
    "automation.bed_tv_on_pre_movie_mode_2",
    "automation.bed_tv_playing_movie_mode",
    "automation.bed_tv_paused_idle_dim_warm",
    "automation.bed_tv_off_restore",
    "automation.bed_switch_single_toggle",
    "automation.bed_switch_double_movie_mode",
    "automation.bed_switch_hold_good_night",
    "automation.bed_manual_mode_auto_expire_30_min",
    "automation.bed_sleep_mode_expires_at_10am",
    "automation.bed_sleep_routine_vibration_at_night",
    "automation.bed_wake_routine_vibration_in_morning",
    "automation.bed_lighting_mode_changed_update_lights",
    "automation.kitchen_motion_on_lights",
    "automation.kitchen_no_motion_10_min_lights_off",
    "automation.kitchen_lighting_mode_changed_update_lights",
    "automation.hallway_motion_on_lights",
    "automation.hallway_no_motion_5_min_lights_off",
    "automation.laundry_washer_started",
    "automation.laundry_washer_done",
    "automation.laundry_dryer_started",
    "automation.laundry_dryer_done",
    "automation.presence_away_mode_both_gone_5_min",
    "automation.presence_arriving_home_first_person_back",
    "automation.system_internet_down_alert",
    "automation.system_internet_restored_clear_alert",
    "automation.home_trash_reminder",
    "automation.home_trash_night_reset_at_midnight",
    "automation.home_restore_kitchen_panel_after_media_stops",
    "automation.house_lighting_mode_set_all_rooms",
    "automation.plant_fescue_grass_low_moisture_alert",
    "automation.plant_green_giant_low_moisture_alert",
    "automation.plant_indoor_tree_low_moisture_alert",
    # Irrigation (hardware not yet installed — automations active, valves unavailable)
    "automation.irrigation_sprinklers_morning",
    "automation.irrigation_trees_morning",
    "automation.irrigation_high_flow_burst_alert",
    "automation.irrigation_safety_shutoff_90_min",
    # Backyard string lights
    "automation.backyard_string_lights_on_at_dusk",
    "automation.backyard_string_lights_off_at_sleep",
    "automation.backyard_string_lights_off_interior_dark",
    "automation.backyard_string_lights_off_when_away",
    # Backyard shed lights
    "automation.backyard_shed_lights_on_at_dusk",
    "automation.backyard_shed_lights_off",
    # Blinds
    "automation.lr_tv_on_close_blinds",
    "automation.lr_tv_off_open_blinds",
    "automation.blinds_close_all_when_away",
    "automation.blinds_open_all_when_arriving_home",
    "automation.blinds_open_at_sunrise",
    "automation.blinds_close_at_sunset",
    "automation.blinds_close_at_sleep_mode",
    "automation.kitchen_blinds_close_when_hot_and_sunny",
    "automation.kitchen_blinds_reopen_when_conditions_improve",
    # System monitors
    "automation.system_ha_restarted_notify",
    "automation.system_mac_mini_back_online_notify",
    "automation.system_mac_mini_offline_notify",
    # Frigate camera automations (MQTT-based, mix of YAML and UI storage)
    "automation.camera_unknown_person_backyard_alert",
    "automation.camera_unknown_person_front_yard_alert",
    "automation.camera_backyard_human_detected_lights_on",
    "automation.camera_riley_backyard_mode",
    "automation.camera_unknown_visitor_counter",
    "automation.camera_unknown_visitor_threshold_alert",
    "automation.camera_weekly_visitor_counter_reset",
    # Other active automations
    "automation.bird_new_species_spotted",
    "automation.code_enforcement_vehicle_spotted_on_road",
    # Front Yard Floodlight (storage-mode, created via ha-mcp — see automations.yaml note)
    "automation.floodlight_night_baseline_on",
    "automation.floodlight_night_baseline_off",
    "automation.floodlight_welcome_known_person_light",
    "automation.floodlight_unknown_person_light",
    "automation.floodlight_unknown_person_alert",
    "automation.floodlight_animal_detected_notify",
    "automation.floodlight_unexpected_vehicle_alert",
    "automation.floodlight_loitering_siren_escalation",
    "automation.camera_backyard_floodlight_on_motion",
    "automation.camera_carport_floodlight_on_motion",
    "automation.camera_rear_floodlight_on_motion",
    # Door sensors (ThirdReality Zigbee, storage-mode — see automations.yaml note)
    "automation.door_front_door_opened_arrival_grace_period",
    "automation.door_back_door_opened_arrival_grace_period",
    # LR 4-way button (Sonoff Zigbee, added 2026-09-14) — syncs LR+Kitchen modes/blinds
    "automation.lr_button_1_single_toggle_lights_lr_kitchen",
    "automation.lr_button_1_double_cycle_lighting_mode_lr_kitchen",
    "automation.lr_button_1_hold_good_night",
    "automation.lr_button_2_single_mode_casual_lr_kitchen",
    "automation.lr_button_2_double_mode_chill_lr_kitchen",
    "automation.lr_button_2_hold_mode_movie_lr_kitchen",
    "automation.lr_button_3_single_blinds_open_lr_kitchen",
    "automation.lr_button_3_double_blinds_close_lr_kitchen",
    "automation.lr_button_3_hold_blinds_halfway_lr_kitchen",
    "automation.lr_button_4_single_outdoor_lights_on",
    "automation.lr_button_4_double_outdoor_lights_off",
    "automation.lr_button_4_hold_find_my_phone_riley",
    "automation.home_room_automations_daily_safety_reset",
    # UPS power outage alert (added 2026-10-06)
    "automation.system_ups_power_alert",
    # Bedroom TV camera PiP via QuickBars (added 2026-10-08)
    "automation.bed_front_yard_motion_tv_camera_pip",
]


def _get_all_states():
    r = _session.get(f"{HA_URL}/api/states", headers=_headers())
    r.raise_for_status()
    return r.json()


def test_automation_count():
    all_states = _get_all_states()
    automations = [s for s in all_states if s["entity_id"].startswith("automation.")]
    count = len(automations)
    assert count >= EXPECTED_AUTOMATION_COUNT, (
        f"Expected >= {EXPECTED_AUTOMATION_COUNT} automations, got {count}. "
        "Update EXPECTED_AUTOMATION_COUNT in test_health.py if intentional."
    )
    print(f"PASS: {count} automations loaded (expected >= {EXPECTED_AUTOMATION_COUNT})")


def test_named_automations_enabled():
    """All automations with human-readable IDs are present and enabled."""
    all_states = _get_all_states()
    automation_map = {s["entity_id"]: s for s in all_states
                      if s["entity_id"].startswith("automation.")}
    missing, disabled = [], []
    for entity_id in NAMED_AUTOMATIONS:
        if entity_id not in automation_map:
            missing.append(entity_id)
        elif automation_map[entity_id]["state"] != "on":
            disabled.append(f"{entity_id} ({automation_map[entity_id]['state']})")
    assert not missing, "Automations NOT FOUND:\n  " + "\n  ".join(missing)
    assert not disabled, "Automations DISABLED:\n  " + "\n  ".join(disabled)
    print(f"PASS: All {len(NAMED_AUTOMATIONS)} named automations present and enabled")



def test_critical_entities_exist():
    """Critical entities must exist in the registry. Unavailability is a warning."""
    missing, unavailable = [], []
    for entity_id in CRITICAL_ENTITIES:
        try:
            s = get_state(entity_id)
            if s["state"] in ("unavailable", "unknown"):
                unavailable.append(f"{entity_id} ({s['state']})")
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                missing.append(entity_id)
            else:
                raise
    assert not missing, "Entities NOT IN REGISTRY:\n  " + "\n  ".join(missing)
    if unavailable:
        print(f"WARN: {len(unavailable)} entities unavailable (may be normal):")
        for e in unavailable:
            print(f"  {e}")
    else:
        print(f"PASS: All {len(CRITICAL_ENTITIES)} critical entities present and available")


def test_required_helpers_exist():
    """All input_boolean/datetime/select/number helpers referenced in automations must exist."""
    missing = []
    for entity_id in REQUIRED_HELPERS:
        try:
            get_state(entity_id)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                missing.append(entity_id)
            else:
                raise
    assert not missing, (
        f"{len(missing)} helper(s) missing — automations will break silently:\n  "
        + "\n  ".join(missing)
    )
    print(f"PASS: All {len(REQUIRED_HELPERS)} helpers exist")


def test_room_toggles_are_on():
    """Room-level automation toggles should be enabled on a healthy system."""
    room_toggles = [
        "input_boolean.automations_living_room",
        "input_boolean.automations_bedroom",
        "input_boolean.automations_kitchen",
    ]
    off = []
    for entity_id in room_toggles:
        state = get_state(entity_id)["state"]
        if state != "on":
            off.append(f"{entity_id} is '{state}'")
    assert not off, "Room toggles are OFF (automations suppressed):\n  " + "\n  ".join(off)
    print("PASS: All room automation toggles are enabled")


def test_scripts_exist():
    """All scripts referenced in test plans and dashboards must be loaded."""
    required_scripts = [
        "script.snooze_automation",
        "script.clear_snooze",
        "script.snooze_until_morning",
        "script.good_night_all",
        "script.set_trash_night",
        "script.find_riley_phone",
        "script.find_casey_phone",
        "script.cast_kitchen_panel",
    ]
    missing = []
    for entity_id in required_scripts:
        try:
            get_state(entity_id)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                missing.append(entity_id)
            else:
                raise
    assert not missing, "Scripts NOT FOUND:\n  " + "\n  ".join(missing)
    print(f"PASS: All {len(required_scripts)} scripts exist")


SOIL_SENSORS = [
    "sensor.fescue_grass_soil_moisture_soil_moisture",
    "sensor.green_giant_soil_sensor_soil_moisture",
    "sensor.indoor_tree_soil_moisture_soil_moisture",
]

def test_soil_moisture_bounds():
    """Soil moisture readings must be within plausible range (2–95%).
    100% or 0% almost always indicates a disconnected or malfunctioning sensor.
    """
    errors, warnings = [], []
    for entity_id in SOIL_SENSORS:
        try:
            s = get_state(entity_id)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                errors.append(f"{entity_id}: not found")
                continue
            raise
        state = s["state"]
        if state in ("unavailable", "unknown"):
            warnings.append(f"{entity_id}: {state}")
            continue
        try:
            val = float(state)
        except ValueError:
            errors.append(f"{entity_id}: non-numeric state '{state}'")
            continue
        if val >= 98:
            errors.append(f"{entity_id}: {val}% — pinned at max, likely sensor error or disconnected")
        elif val <= 2:
            errors.append(f"{entity_id}: {val}% — at zero, likely sensor error or disconnected")
        elif val > 90:
            warnings.append(f"{entity_id}: {val}% — unusually high, check sensor placement")
    if warnings:
        print(f"WARN: Soil moisture anomalies:")
        for w in warnings:
            print(f"  {w}")
    assert not errors, "Soil moisture out-of-bounds:\n  " + "\n  ".join(errors)
    print(f"PASS: All {len(SOIL_SENSORS)} soil moisture sensors within bounds")


def test_speedtest_freshness():
    """Mac Mini speedtest (launchd, hourly, sensor.mac_mini_speed_test_*) must have
    updated recently. Catches the exact failure mode that went unnoticed for ~5 weeks
    on 2026-09-14: ~/.mqtt_pass went missing, every hourly run silently failed, and the
    dashboard kept showing a month-old value with no indication anything was wrong.
    """
    entity_id = "sensor.mac_mini_speed_test_download_speed"
    try:
        s = get_state(entity_id)
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            raise AssertionError(f"{entity_id}: not found") from e
        raise
    if s["state"] in ("unavailable", "unknown"):
        raise AssertionError(f"{entity_id}: state is '{s['state']}'")
    last_updated = datetime.fromisoformat(s["last_updated"])
    age_hours = (datetime.now(timezone.utc) - last_updated).total_seconds() / 3600
    assert age_hours < 3, (
        f"{entity_id}: last updated {age_hours:.1f}h ago (expected hourly) — "
        f"launchd job may be failing silently again. Check /tmp/speedtest_push.err "
        f"and confirm ~/.mqtt_pass exists."
    )
    print(f"PASS: Speedtest data is fresh ({age_hours:.1f}h old)")
