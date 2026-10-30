"""
Bedroom switch automation tests.

Publishes real MQTT messages to the switch action topic.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from ha_client import (
    inject_mqtt, get_state, call_service, set_state, wait,
    light_state, light_brightness
)

SWITCH_TOPIC = "zigbee2mqtt/bedroom switch/action"
BED_LIGHTS = ["light.bedroom", "light.govee_lamp_1"]
BED_MOTION_TOPIC = "zigbee2mqtt/Bedroom Motion Sensor"


def _reset():
    # Disable automations during reset to prevent bed_tv_off/bed_motion_on from interfering
    call_service("input_boolean", "turn_off", {"entity_id": "input_boolean.automations_bedroom"})
    call_service("light", "turn_off", {"entity_id": BED_LIGHTS})
    call_service("input_boolean", "turn_off", {"entity_id": "input_boolean.bed_manual_mode"})
    call_service("input_boolean", "turn_off", {"entity_id": "input_boolean.sleep_mode_active"})
    set_state("media_player.bedroom_tv_2", "off")
    inject_mqtt(BED_MOTION_TOPIC, {"occupancy": False, "illuminance_lux": 0, "illuminance": 0})
    wait(1)
    call_service("input_boolean", "turn_on", {"entity_id": "input_boolean.automations_bedroom"})
    wait(1)  # Let HA finish processing the enable event before switch press


def test_single_turns_on_when_off():
    _reset()
    inject_mqtt(SWITCH_TOPIC, "single")
    wait(2)
    state = light_state("light.bedroom")
    assert state == "on", f"Expected lights on after single press (was off), got {state}"
    manual = get_state("input_boolean.bed_manual_mode")["state"]
    assert manual == "off", f"Expected manual mode off after single, got {manual}"
    print("PASS: Single press turns lights on (was off)")


def test_single_turns_off_when_on():
    call_service("light", "turn_on", {"entity_id": BED_LIGHTS, "brightness": 200})
    call_service("input_boolean", "turn_off", {"entity_id": "input_boolean.bed_manual_mode"})
    wait(1)
    inject_mqtt(SWITCH_TOPIC, "single")
    wait(2)
    state = light_state("light.bedroom")
    assert state == "off", f"Expected lights off after single press (was on), got {state}"
    print("PASS: Single press turns lights off (was on)")


def test_single_clears_manual_mode():
    call_service("input_boolean", "turn_on", {"entity_id": "input_boolean.bed_manual_mode"})
    wait(1)
    inject_mqtt(SWITCH_TOPIC, "single")
    wait(2)
    manual = get_state("input_boolean.bed_manual_mode")["state"]
    assert manual == "off", f"Expected manual mode cleared after single, got {manual}"
    print("PASS: Single press clears manual mode")


def test_double_sets_movie_mode():
    _reset()
    inject_mqtt(SWITCH_TOPIC, "double")
    wait(2)
    manual = get_state("input_boolean.bed_manual_mode")["state"]
    assert manual == "on", f"Expected manual mode on after double, got {manual}"
    govee_bri = light_brightness("light.govee_lamp_1")
    assert govee_bri < 100, f"Expected Govee dim in movie mode, got brightness={govee_bri}"
    print(f"PASS: Double press sets movie mode (manual={manual}, govee_bri={govee_bri})")


def test_single_clears_sleep_mode():
    call_service("input_boolean", "turn_on", {"entity_id": "input_boolean.sleep_mode_active"})
    wait(1)
    inject_mqtt(SWITCH_TOPIC, "single")
    wait(2)
    sleep = get_state("input_boolean.sleep_mode_active")["state"]
    assert sleep == "off", f"Expected sleep mode cleared after single, got {sleep}"
    print("PASS: Single press clears sleep mode")


def test_hold_turns_off_all_and_sets_sleep_mode():
    call_service("light", "turn_on", {"entity_id": BED_LIGHTS, "brightness": 200})
    call_service("light", "turn_on", {
        "entity_id": ["light.living_room", "light.kitchen"],
        "brightness": 200
    })
    call_service("input_boolean", "turn_off", {"entity_id": "input_boolean.sleep_mode_active"})
    wait(1)
    inject_mqtt(SWITCH_TOPIC, "hold")
    wait(2)
    for entity in BED_LIGHTS + ["light.living_room", "light.kitchen"]:
        state = light_state(entity)
        assert state == "off", f"Expected {entity} off after hold, got {state}"
    sleep = get_state("input_boolean.sleep_mode_active")["state"]
    assert sleep == "on", f"Expected sleep mode on after hold, got {sleep}"
    call_service("input_boolean", "turn_off", {"entity_id": "input_boolean.sleep_mode_active"})
    print("PASS: Hold turns off all lights and sets sleep mode")
