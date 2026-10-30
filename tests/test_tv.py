"""
TV state automation tests.

Uses set_state() to inject fake media player states.
Native HA triggers fire instantly — no 30s poll needed.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from ha_client import (
    set_state, get_state, call_service, inject_mqtt, wait,
    light_brightness, light_state, light_rgb
)

LR_LIGHTS = ["light.living_room", "light.lamp"]
BED_LIGHTS = ["light.bedroom", "light.govee_lamp_1"]
LR_MOTION_TOPIC = "zigbee2mqtt/Living Room Motion Sensor"
BED_MOTION_TOPIC = "zigbee2mqtt/Bedroom Motion Sensor"


def _reset_lr():
    # Disable automations during reset to prevent lr_tv_off/lr_motion_on from interfering
    call_service("input_boolean", "turn_off", {"entity_id": "input_boolean.automations_living_room"})
    call_service("light", "turn_on", {
        "entity_id": LR_LIGHTS,
        "brightness": 200,
        "color_temp_kelvin": 2700
    })
    set_state("media_player.roku_ultra", "off")
    # Set occupancy True so Roku-polling-triggered lr_tv_off restores brightness instead of turning off
    inject_mqtt(LR_MOTION_TOPIC, {"occupancy": True, "illuminance_lux": 0, "illuminance": 0})
    wait(1)
    call_service("input_boolean", "turn_on", {"entity_id": "input_boolean.automations_living_room"})


def _reset_bed():
    # Disable automations during reset to prevent bed_tv_off/bed_motion_on from interfering
    call_service("input_boolean", "turn_off", {"entity_id": "input_boolean.automations_bedroom"})
    call_service("light", "turn_on", {
        "entity_id": BED_LIGHTS,
        "brightness": 200,
        "color_temp_kelvin": 2700
    })
    call_service("input_boolean", "turn_off", {"entity_id": "input_boolean.bed_manual_mode"})
    call_service("input_boolean", "turn_off", {"entity_id": "input_boolean.sleep_mode_active"})
    set_state("media_player.bedroom_tv_2", "off")
    inject_mqtt(BED_MOTION_TOPIC, {"occupancy": False, "illuminance_lux": 0, "illuminance": 0})
    wait(1)
    call_service("input_boolean", "turn_on", {"entity_id": "input_boolean.automations_bedroom"})


# ── Living Room TV ────────────────────────────────────────────────────────────

def test_lr_tv_playing_dims():
    _reset_lr()
    set_state("media_player.roku_ultra", "playing")
    wait(4)  # lr_tv_playing uses transition:3
    bri = light_brightness("light.living_room")
    if bri >= 50:
        # Roku integration may have polled and overwritten "playing" → lr_tv_off restored.
        # Re-assert and give lr_tv_playing another chance.
        set_state("media_player.roku_ultra", "playing")
        wait(4)
        bri = light_brightness("light.living_room")
    assert bri < 50, f"Expected dim (<50) when TV playing, got brightness={bri}"
    print(f"PASS: LR TV playing dims to bri={bri}")


def test_lr_tv_playing_sets_red():
    _reset_lr()
    set_state("media_player.roku_ultra", "playing")
    wait(4)  # lr_tv_playing uses transition:3
    bri = light_brightness("light.living_room")
    rgb = light_rgb("light.living_room")
    if bri >= 50:
        # Roku polled back; re-assert and retry
        set_state("media_player.roku_ultra", "playing")
        wait(4)
        bri = light_brightness("light.living_room")
        rgb = light_rgb("light.living_room")
    # Hue Ambiance bulbs render rgb_color as warm amber at low brightness — check red-dominant
    assert bri < 50, f"Expected dim (<50) in movie mode, got brightness={bri}"
    assert rgb and rgb[0] > rgb[1], f"Expected red-dominant color, got rgb={rgb}"
    print(f"PASS: LR TV playing sets red-tinted movie mode: bri={bri}, rgb={rgb}")


def test_lr_tv_paused_dims_warm():
    _reset_lr()
    set_state("media_player.roku_ultra", "playing")
    wait(4)  # lr_tv_playing uses transition:3
    set_state("media_player.roku_ultra", "paused")
    wait(3)  # lr_tv_paused uses transition:2
    bri = light_brightness("light.living_room")
    if bri >= 100:
        # Roku polled back during playing→paused; retry the whole sequence
        set_state("media_player.roku_ultra", "playing")
        wait(4)
        set_state("media_player.roku_ultra", "paused")
        wait(3)
        bri = light_brightness("light.living_room")
    assert 50 < bri < 100, f"Expected paused dim (50-100), got brightness={bri}"
    print(f"PASS: LR TV paused dims warm to bri={bri}")


def test_lr_tv_idle_dims_medium():
    _reset_lr()
    set_state("media_player.roku_ultra", "idle")
    wait(3)  # lr_tv_paused/idle uses transition:2
    bri = light_brightness("light.living_room")
    if not (100 < bri < 160):
        # Roku polled back; retry
        set_state("media_player.roku_ultra", "idle")
        wait(3)
        bri = light_brightness("light.living_room")
    assert 100 < bri < 160, f"Expected idle medium (100-160), got brightness={bri}"
    print(f"PASS: LR TV idle dims to bri={bri}")


def test_lr_tv_off_restores():
    _reset_lr()
    set_state("media_player.roku_ultra", "playing")
    wait(4)  # lr_tv_playing uses transition:3
    before_bri = light_brightness("light.living_room")
    if before_bri >= 50:
        # Roku polled back; retry
        set_state("media_player.roku_ultra", "playing")
        wait(4)
        before_bri = light_brightness("light.living_room")
    set_state("media_player.roku_ultra", "off")
    wait(4)  # lr_tv_off uses transition:3
    after_bri = light_brightness("light.living_room")
    assert after_bri > before_bri, f"Expected brightness to restore, got {before_bri} → {after_bri}"
    print(f"PASS: LR TV off restores brightness: {before_bri} → {after_bri}")


# ── Bedroom TV ────────────────────────────────────────────────────────────────

def test_bed_tv_playing_triggers_scene():
    _reset_bed()
    set_state("media_player.bedroom_tv_2", "playing")
    wait(4)  # bed_tv_playing govee transition:3
    govee_bri = light_brightness("light.govee_lamp_1")
    govee_rgb = light_rgb("light.govee_lamp_1")
    assert govee_bri < 100, f"Expected Govee dim (<100) when TV playing, got brightness={govee_bri}"
    assert govee_rgb and govee_rgb[0] > 200, f"Expected Govee red, got rgb={govee_rgb}"
    print(f"PASS: Bed TV playing: Govee bri={govee_bri}, rgb={govee_rgb}")


def test_bed_tv_paused_dims_warm():
    _reset_bed()
    set_state("media_player.bedroom_tv_2", "paused")
    wait(3)  # bed_tv_paused uses transition:2
    bri = light_brightness("light.bedroom")
    assert 50 < bri < 100, f"Expected paused dim (50-100), got brightness={bri}"
    print(f"PASS: Bed TV paused dims warm to bri={bri}")


def test_bed_tv_off_respects_manual_mode():
    """When manual mode is on, TV-off should NOT restore lights."""
    _reset_bed()
    call_service("input_boolean", "turn_on", {"entity_id": "input_boolean.bed_manual_mode"})
    set_state("media_player.bedroom_tv_2", "playing")
    wait(4)  # bed_tv_playing govee transition:3
    # At this point lights are in movie/scene state; record govee brightness
    scene_bri = light_brightness("light.govee_lamp_1")
    set_state("media_player.bedroom_tv_2", "off")
    wait(3)  # bed_tv_off uses transition:3 when it fires
    # Manual mode is on — TV-off restore should be blocked, lights stay in scene state
    bri = light_brightness("light.govee_lamp_1")
    assert bri == scene_bri, f"Expected lights to stay in movie scene (manual mode), scene={scene_bri} after_off={bri}"
    call_service("input_boolean", "turn_off", {"entity_id": "input_boolean.bed_manual_mode"})
    print(f"PASS: Bed TV off respects manual mode (scene_bri={scene_bri}, bri after={bri})")
