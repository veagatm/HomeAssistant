"""
Door sensor tests (ThirdReality Zigbee contact sensors, added 2026-07-22).

Tests inject a fake MQTT contact payload (mirrors test_motion.py's pattern) and
assert the matching grace-period flag turns on. Z2M contact sensors report
contact: true = closed, contact: false = open (HA binary_sensor "on" = open).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import requests
from ha_client import inject_mqtt, get_state, call_service, wait

FRONT_DOOR_TOPIC = "zigbee2mqtt/front_door"
BACK_DOOR_TOPIC = "zigbee2mqtt/back_door"

FRONT_DOOR_ENTITY = "binary_sensor.front_door_contact"
BACK_DOOR_ENTITY = "binary_sensor.back_door_contact"

FRONT_GRACE_FLAG = "input_boolean.door_recently_opened_front"
BACK_GRACE_FLAG = "input_boolean.door_recently_opened_back"


def _reset_flag(entity_id: str) -> None:
    call_service("input_boolean", "turn_off", {"entity_id": entity_id})
    wait(1)


def test_front_door_open_sets_grace_flag():
    _reset_flag(FRONT_GRACE_FLAG)
    inject_mqtt(FRONT_DOOR_TOPIC, {"contact": True})
    wait(1)
    inject_mqtt(FRONT_DOOR_TOPIC, {"contact": False})  # open
    wait(2)
    state = get_state(FRONT_GRACE_FLAG)["state"]
    assert state == "on", f"Expected door_recently_opened_front on, got {state}"
    _reset_flag(FRONT_GRACE_FLAG)
    print("PASS: Front door open sets 90s arrival grace flag")


def test_back_door_open_sets_grace_flag():
    _reset_flag(BACK_GRACE_FLAG)
    inject_mqtt(BACK_DOOR_TOPIC, {"contact": True})
    wait(1)
    inject_mqtt(BACK_DOOR_TOPIC, {"contact": False})  # open
    wait(2)
    state = get_state(BACK_GRACE_FLAG)["state"]
    assert state == "on", f"Expected door_recently_opened_back on, got {state}"
    _reset_flag(BACK_GRACE_FLAG)
    print("PASS: Back door open sets 5min arrival grace flag")


def test_door_sensors_registered():
    missing = []
    for entity_id in (FRONT_DOOR_ENTITY, BACK_DOOR_ENTITY):
        try:
            get_state(entity_id)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                missing.append(entity_id)
            else:
                raise
    assert not missing, "Door sensors NOT REGISTERED:\n  " + "\n  ".join(missing)
    print("PASS: Both door contact sensors registered")
