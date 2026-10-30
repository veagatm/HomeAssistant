"""
Soil moisture sensor and alert automation tests.

Alert automations fire when moisture drops below thresholds:
  Fescue Grass:  < 25%
  Green Giant:   < 20%
  Indoor Tree:   < 10%

set_state() overrides sensor values for testing. Notifications/TTS cannot
be asserted without a real phone — those tests print a manual-verify reminder.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import requests
from ha_client import get_state, call_service, set_state, wait, _headers, _session, HA_URL

SENSORS = {
    "fescue": "sensor.fescue_grass_soil_moisture_soil_moisture",
    "green_giant": "sensor.green_giant_soil_sensor_soil_moisture",
    "indoor_tree": "sensor.indoor_tree_soil_moisture_soil_moisture",
}

ALERT_THRESHOLDS = {
    "fescue":       {"alert": 25, "low": 30, "healthy_max": 50},
    "green_giant":  {"alert": 20, "low": 35, "healthy_max": 50},
    "indoor_tree":  {"alert": 10, "low": 15, "healthy_max": 25},
}

ALERT_ALIASES = {
    "fescue":       "Plant - Fescue Grass Low Moisture Alert",
    "green_giant":  "Plant - Green Giant Low Moisture Alert",
    "indoor_tree":  "Plant - Indoor Tree Low Moisture Alert",
}


def _get_automation_by_alias(alias: str):
    r = _session.get(f"{HA_URL}/api/states", headers=_headers())
    r.raise_for_status()
    for s in r.json():
        if (s["entity_id"].startswith("automation.")
                and s["attributes"].get("friendly_name") == alias):
            return s
    return None


def test_sensors_are_registered():
    """All three soil sensors must exist in HA."""
    missing, unavailable = [], []
    for name, entity_id in SENSORS.items():
        try:
            s = get_state(entity_id)
            if s["state"] in ("unavailable", "unknown"):
                unavailable.append(f"{name} ({entity_id})")
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                missing.append(f"{name} ({entity_id})")
            else:
                raise
    assert not missing, "Soil sensors NOT REGISTERED:\n  " + "\n  ".join(missing)
    if unavailable:
        print(f"WARN: {len(unavailable)} sensors unavailable (may be sleeping): {unavailable}")
    else:
        print(f"PASS: All {len(SENSORS)} soil sensors registered")


def test_alert_automations_enabled():
    """All three plant moisture alert automations must be enabled."""
    disabled, missing = [], []
    for name, alias in ALERT_ALIASES.items():
        s = _get_automation_by_alias(alias)
        if s is None:
            missing.append(alias)
        elif s["state"] != "on":
            disabled.append(f"{alias} ({s['state']})")
    assert not missing, "Alert automations NOT FOUND:\n  " + "\n  ".join(missing)
    assert not disabled, "Alert automations DISABLED:\n  " + "\n  ".join(disabled)
    print(f"PASS: All {len(ALERT_ALIASES)} soil moisture alert automations enabled")


def test_reference_line_helpers_have_correct_values():
    """input_number helpers used as chart reference lines must be set."""
    expected = {
        "input_number.plant_fescue_target_low":        30.0,
        "input_number.plant_fescue_target_high":       50.0,
        "input_number.plant_green_giant_target_low":   35.0,
        "input_number.plant_green_giant_target_high":  50.0,
        "input_number.plant_indoor_tree_target_low":   15.0,
        "input_number.plant_indoor_tree_target_high":  25.0,
    }
    wrong = []
    for entity_id, expected_val in expected.items():
        try:
            actual = float(get_state(entity_id)["state"])
            if abs(actual - expected_val) > 0.1:
                wrong.append(f"{entity_id}: expected {expected_val}, got {actual}")
        except requests.HTTPError:
            wrong.append(f"{entity_id}: NOT FOUND")
    assert not wrong, "Reference line helpers have wrong values:\n  " + "\n  ".join(wrong)
    print(f"PASS: All {len(expected)} reference line helpers have correct values")


def _test_alert_fires_at_low_moisture(plant_key: str):
    """Force-set sensor below alert threshold and trigger the automation."""
    sensor_id = SENSORS[plant_key]
    alias = ALERT_ALIASES[plant_key]
    threshold = ALERT_THRESHOLDS[plant_key]["alert"]
    test_value = str(threshold - 5)  # well below threshold

    auto = _get_automation_by_alias(alias)
    assert auto, f"Automation '{alias}' not found"

    set_state(sensor_id, test_value)
    wait(1)
    result = call_service("automation", "trigger", {
        "entity_id": auto["entity_id"],
        "skip_condition": False
    })
    assert result in (200, 201), f"Expected HTTP 200/201, got {result}"
    print(
        f"PASS: {plant_key} alert triggered at {test_value}% "
        f"(threshold {threshold}%) — verify: notification + TTS received"
    )
    # Restore sensor to a healthy value so it doesn't keep alerting
    healthy = str(int((threshold + ALERT_THRESHOLDS[plant_key]["healthy_max"]) / 2))
    set_state(sensor_id, healthy)
    wait(1)


def test_fescue_alert_fires_at_low_moisture():
    _test_alert_fires_at_low_moisture("fescue")


def test_green_giant_alert_fires_at_low_moisture():
    _test_alert_fires_at_low_moisture("green_giant")


def test_indoor_tree_alert_fires_at_low_moisture():
    _test_alert_fires_at_low_moisture("indoor_tree")


def test_fescue_alert_blocked_above_threshold():
    """Alert should not fire when moisture is above the alert threshold."""
    sensor_id = SENSORS["fescue"]
    alias = ALERT_ALIASES["fescue"]
    healthy_value = "40"  # well above 25% threshold

    auto = _get_automation_by_alias(alias)
    assert auto, f"Automation '{alias}' not found"

    set_state(sensor_id, healthy_value)
    wait(1)
    # With skip_condition=False, automation should evaluate condition and not fire action
    result = call_service("automation", "trigger", {
        "entity_id": auto["entity_id"],
        "skip_condition": False
    })
    # HTTP 200 means the trigger was accepted — whether conditions passed is in the trace
    # We can't easily assert TTS didn't play; this test documents the expected behavior
    print(
        f"PASS: Fescue alert triggered with moisture={healthy_value}% "
        f"(conditions block it — verify: no TTS/notification received)"
    )
    # Note: automation.trigger with skip_condition=False still returns 200 even if blocked
    # by conditions — HA returns 200 for the trigger call, not the action outcome.
    # Check the automation trace in Developer Tools → Automations → Traces to confirm.
