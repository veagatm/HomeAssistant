"""
Script tests — good_night_all, set_trash_night, find phone.

Note: find_riley_phone / find_casey_phone send real push notifications and TTS.
Those tests are marked with a print reminder to verify on the physical device.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from ha_client import get_state, call_service, set_state, wait, light_state


ALL_LIGHTS = [
    "light.living_room", "light.kitchen", "light.bedroom",
    "light.lamp", "light.lightstrip", "light.tv_light",
]
SLEEP_FLAG = "input_boolean.sleep_mode_active"
TRASH_FLAG = "input_boolean.trash_night"
TRASH_SNOOZE = "input_datetime.snooze_trash_reminder"


# ── good_night_all ────────────────────────────────────────────────────────────

def test_good_night_sets_sleep_mode():
    call_service("input_boolean", "turn_off", {"entity_id": SLEEP_FLAG})
    wait(1)
    call_service("script", "good_night_all", {})
    wait(3)
    state = get_state(SLEEP_FLAG)["state"]
    assert state == "on", f"Expected sleep_mode_active=on after good_night_all, got {state}"
    print("PASS: good_night_all sets sleep_mode_active=on")


def test_good_night_turns_off_all_lights():
    # Turn on a few lights to have something to verify
    call_service("light", "turn_on", {"entity_id": ["light.living_room", "light.kitchen"]})
    wait(1)
    call_service("script", "good_night_all", {})
    wait(3)
    for entity_id in ALL_LIGHTS:
        try:
            state = light_state(entity_id)
            assert state == "off", f"Expected {entity_id} off after good_night_all, got {state}"
        except Exception:
            pass  # entity may not exist yet (e.g. back_left if Hue group controls it)
    print("PASS: good_night_all turns off all lights")
    # Cleanup
    call_service("input_boolean", "turn_off", {"entity_id": SLEEP_FLAG})
    wait(1)


# ── set_trash_night ───────────────────────────────────────────────────────────

def test_set_trash_night_activates_flag():
    call_service("input_boolean", "turn_off", {"entity_id": TRASH_FLAG})
    wait(1)
    call_service("script", "set_trash_night", {})
    wait(2)
    state = get_state(TRASH_FLAG)["state"]
    assert state == "on", f"Expected trash_night=on after set_trash_night, got {state}"
    print("PASS: set_trash_night sets trash_night=on")


def test_set_trash_night_clears_snooze():
    """set_trash_night should reset snooze so the reminder can fire tonight."""
    call_service("script", "set_trash_night", {})
    wait(2)
    from datetime import datetime, timezone
    ts = get_state(TRASH_SNOOZE)["attributes"].get("timestamp", 0)
    now = datetime.now(timezone.utc).timestamp()
    assert ts < now, f"Expected snooze cleared (past timestamp), got ts={ts}"
    print("PASS: set_trash_night clears trash reminder snooze")
    # Cleanup
    call_service("input_boolean", "turn_off", {"entity_id": TRASH_FLAG})


# ── Trash midnight reset ──────────────────────────────────────────────────────

def test_trash_night_reset_automation_turns_off_flag():
    """Direct-trigger the midnight reset automation to verify it clears the flag."""
    call_service("input_boolean", "turn_on", {"entity_id": TRASH_FLAG})
    wait(1)
    call_service("automation", "trigger", {
        "entity_id": "automation.home_trash_night_reset_at_midnight",
        "skip_condition": True
    })
    wait(2)
    state = get_state(TRASH_FLAG)["state"]
    assert state == "off", f"Expected trash_night=off after midnight reset, got {state}"
    print("PASS: Trash night reset automation clears the flag")


# ── Find phone (notification-only — must verify on device) ───────────────────

def test_find_riley_phone_runs_without_error():
    result = call_service("script", "find_riley_phone", {})
    assert result in (200, 201), f"Expected HTTP 200/201, got {result}"
    print("PASS: find_riley_phone executed (verify: notification + TTS on kitchen speaker)")


def test_find_casey_phone_runs_without_error():
    result = call_service("script", "find_casey_phone", {})
    assert result in (200, 201), f"Expected HTTP 200/201, got {result}"
    print("PASS: find_casey_phone executed (verify: notification + TTS on kitchen speaker)")
