"""
Motion sensor automation tests.

Tests inject fake MQTT occupancy/lux payloads and assert light state changes.
Each test first clears occupancy (inject False) to force a clean off→on transition
so the platform:state trigger always fires regardless of prior sensor state.
Native HA triggers fire in <1s, so wait(2) is sufficient.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from ha_client import (
    inject_mqtt, get_state, set_state, wait,
    light_brightness, light_state, call_service
)

LR_MOTION_TOPIC = "zigbee2mqtt/Living Room Motion Sensor"
BED_MOTION_TOPIC = "zigbee2mqtt/Bedroom Motion Sensor"
KIT_MOTION_TOPIC = "zigbee2mqtt/Kitchen Motion Sensor"

LR_OCC_ENTITY = "binary_sensor.living_room_motion_sensor_occupancy"
BED_OCC_ENTITY = "binary_sensor.bedroom_motion_sensor_occupancy"
KIT_OCC_ENTITY = "binary_sensor.kitchen_motion_sensor_occupancy"

LR_LIGHTS = ["light.living_room", "light.lamp"]
BED_LIGHTS = ["light.bedroom", "light.govee_lamp_1"]
KIT_LIGHTS = ["light.kitchen", "light.lightstrip"]


def _clear_occupancy(topic: str) -> None:
    """Force the sensor to 'off' so the next inject creates a real off→on transition."""
    inject_mqtt(topic, {"occupancy": False, "illuminance_lux": 0, "illuminance": 0})
    wait(1)


def _reset_lr():
    """Turn off LR lights, clear TV state, then force occupancy off."""
    # Disable automations during reset to prevent lr_tv_off from interfering
    call_service("input_boolean", "turn_off", {"entity_id": "input_boolean.automations_living_room"})
    call_service("light", "turn_off", {"entity_id": LR_LIGHTS})
    set_state("media_player.roku_ultra", "off")
    wait(1)
    call_service("input_boolean", "turn_on", {"entity_id": "input_boolean.automations_living_room"})
    _clear_occupancy(LR_MOTION_TOPIC)


def _reset_bed():
    """Turn off bedroom lights, clear manual/sleep mode, force occupancy off."""
    call_service("light", "turn_off", {"entity_id": BED_LIGHTS})
    call_service("input_boolean", "turn_off", {"entity_id": "input_boolean.bed_manual_mode"})
    call_service("input_boolean", "turn_off", {"entity_id": "input_boolean.sleep_mode_active"})
    set_state("media_player.bedroom_tv_2", "off")
    _clear_occupancy(BED_MOTION_TOPIC)


def _reset_kit():
    """Turn off kitchen lights and force occupancy off."""
    call_service("light", "turn_off", {"entity_id": KIT_LIGHTS})
    _clear_occupancy(KIT_MOTION_TOPIC)


# ── Living Room ───────────────────────────────────────────────────────────────

def test_lr_motion_low_lux_turns_on():
    _reset_lr()
    inject_mqtt(LR_MOTION_TOPIC, {"occupancy": True, "illuminance_lux": 30, "illuminance": 30})
    wait(2)
    state = light_state("light.living_room")
    assert state == "on", f"Expected on, got {state}"
    print("PASS: LR motion (low lux) turns lights on")


def test_lr_motion_high_lux_skips():
    _reset_lr()
    # Pre-set illuminance via REST API to avoid Z2M race (occupancy fires before illuminance updates)
    set_state("sensor.living_room_motion_sensor_illuminance", "250")
    wait(1)
    inject_mqtt(LR_MOTION_TOPIC, {"occupancy": True, "illuminance_lux": 250, "illuminance": 250})
    wait(2)
    state = light_state("light.living_room")
    assert state == "off", f"Expected no change (high lux), got {state}"
    print("PASS: LR motion (high lux) skips")


def test_lr_motion_blocked_when_tv_playing():
    _reset_lr()
    set_state("media_player.roku_ultra", "playing")
    wait(1)
    # lr_tv_playing automation fires and turns on lights; reset them to test motion behavior
    call_service("light", "turn_off", {"entity_id": LR_LIGHTS})
    _clear_occupancy(LR_MOTION_TOPIC)
    # Re-assert "playing" immediately before inject in case Roku integration overwrote it
    set_state("media_player.roku_ultra", "playing")
    inject_mqtt(LR_MOTION_TOPIC, {"occupancy": True, "illuminance_lux": 10, "illuminance": 10})
    wait(2)
    state = light_state("light.living_room")
    assert state == "off", f"Expected lights to stay off (TV playing), got {state}"
    print("PASS: LR motion blocked when TV is playing")


# ── Bedroom ───────────────────────────────────────────────────────────────────

def test_bed_motion_low_lux_turns_on():
    _reset_bed()
    inject_mqtt(BED_MOTION_TOPIC, {"occupancy": False, "illuminance_lux": 0, "illuminance": 0})
    wait(1)
    inject_mqtt(BED_MOTION_TOPIC, {"occupancy": True, "illuminance_lux": 20, "illuminance": 20})
    wait(2)
    state = light_state("light.bedroom")
    assert state == "on", f"Expected on, got {state}"
    print("PASS: Bed motion (low lux) turns lights on")


def test_bed_motion_blocked_by_sleep_mode():
    _reset_bed()
    call_service("input_boolean", "turn_on", {"entity_id": "input_boolean.sleep_mode_active"})
    wait(1)
    inject_mqtt(BED_MOTION_TOPIC, {"occupancy": True, "illuminance_lux": 10, "illuminance": 10})
    wait(2)
    state = light_state("light.bedroom")
    assert state == "off", f"Expected lights to stay off (sleep mode), got {state}"
    call_service("input_boolean", "turn_off", {"entity_id": "input_boolean.sleep_mode_active"})
    print("PASS: Bed motion blocked by sleep mode")


def test_bed_motion_blocked_by_manual_mode():
    _reset_bed()
    call_service("input_boolean", "turn_on", {"entity_id": "input_boolean.bed_manual_mode"})
    wait(1)
    inject_mqtt(BED_MOTION_TOPIC, {"occupancy": True, "illuminance_lux": 10, "illuminance": 10})
    wait(2)
    state = light_state("light.bedroom")
    assert state == "off", f"Expected lights to stay off (manual mode), got {state}"
    call_service("input_boolean", "turn_off", {"entity_id": "input_boolean.bed_manual_mode"})
    print("PASS: Bed motion blocked by manual mode")


def test_bed_motion_blocked_when_tv_playing():
    _reset_bed()
    set_state("media_player.bedroom_tv_2", "playing")
    wait(1)
    # bed_tv_playing automation fires and turns on lights; reset them to test motion behavior
    call_service("light", "turn_off", {"entity_id": BED_LIGHTS})
    _clear_occupancy(BED_MOTION_TOPIC)
    inject_mqtt(BED_MOTION_TOPIC, {"occupancy": True, "illuminance_lux": 10, "illuminance": 10})
    wait(2)
    state = light_state("light.bedroom")
    assert state == "off", f"Expected lights to stay off (TV playing), got {state}"
    print("PASS: Bed motion blocked when TV is playing")


# ── Kitchen ───────────────────────────────────────────────────────────────────

def test_kit_motion_turns_on():
    _reset_kit()
    # Re-inject False immediately before True to ensure a clean off→on transition
    inject_mqtt(KIT_MOTION_TOPIC, {"occupancy": False, "illuminance_lux": 0, "illuminance": 0})
    wait(1)
    inject_mqtt(KIT_MOTION_TOPIC, {"occupancy": True, "illuminance_lux": 50, "illuminance": 50})
    wait(2)
    state = light_state("light.kitchen")
    assert state == "on", f"Expected on, got {state}"
    print("PASS: Kitchen motion turns lights on")


def test_kit_motion_turns_on_regardless_of_lux():
    """Kitchen has no lux gate — should turn on even at high ambient light."""
    _reset_kit()
    inject_mqtt(KIT_MOTION_TOPIC, {"occupancy": False, "illuminance_lux": 500, "illuminance": 500})
    wait(1)
    inject_mqtt(KIT_MOTION_TOPIC, {"occupancy": True, "illuminance_lux": 500, "illuminance": 500})
    wait(2)
    state = light_state("light.kitchen")
    assert state == "on", f"Expected on (kitchen has no lux gate), got {state}"
    print("PASS: Kitchen motion turns on even at high lux (no lux gate)")
