"""
Presence automation tests.

Uses set_state() to fake person locations and automation.trigger to bypass
the 5-minute 'for:' delay on the away-mode trigger. Conditions are still
evaluated (skip_condition=False) so sleep mode and snooze blocks are tested.

Side effects: turns off lights when arriving home automation fires.
All state changes are cleaned up in each test.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from ha_client import get_state, call_service, set_state, wait

AWAY_AUTO = "automation.presence_away_mode_both_gone_5_min"
ARRIVE_AUTO = "automation.presence_arriving_home_first_person_back"

RILEY = "person.riley_hollis"
CASEY = "person.cassandra_quinlan"

AWAY_FLAG = "input_boolean.away_mode_active"
SLEEP_FLAG = "input_boolean.sleep_mode_active"


def _reset():
    """Restore normal operating state."""
    call_service("input_boolean", "turn_off", {"entity_id": AWAY_FLAG})
    call_service("input_boolean", "turn_off", {"entity_id": SLEEP_FLAG})
    call_service("script", "clear_snooze", {"snooze_id": "away_mode"})
    call_service("script", "clear_snooze", {"snooze_id": "arriving_home"})
    set_state(RILEY, "home")
    set_state(CASEY, "home")
    wait(1)


def test_away_mode_activates_when_both_gone():
    _reset()
    set_state(RILEY, "not_home")
    set_state(CASEY, "not_home")
    wait(1)
    # skip_condition=False: automation checks that both persons are away
    call_service("automation", "trigger", {
        "entity_id": AWAY_AUTO,
        "skip_condition": False
    })
    wait(3)
    state = get_state(AWAY_FLAG)["state"]
    assert state == "on", f"Expected away_mode_active=on, got {state}"
    print("PASS: Away mode activates when both persons not_home")
    _reset()


def test_away_mode_blocked_by_sleep():
    _reset()
    call_service("input_boolean", "turn_on", {"entity_id": SLEEP_FLAG})
    set_state(RILEY, "not_home")
    set_state(CASEY, "not_home")
    wait(1)
    call_service("automation", "trigger", {
        "entity_id": AWAY_AUTO,
        "skip_condition": False
    })
    wait(3)
    state = get_state(AWAY_FLAG)["state"]
    assert state == "off", f"Expected away_mode to stay off during sleep, got {state}"
    print("PASS: Away mode blocked when sleep mode is active")
    _reset()


def test_away_mode_blocked_by_snooze():
    _reset()
    call_service("script", "snooze_automation", {
        "snooze_id": "away_mode",
        "duration_minutes": 30
    })
    set_state(RILEY, "not_home")
    set_state(CASEY, "not_home")
    wait(1)
    call_service("automation", "trigger", {
        "entity_id": AWAY_AUTO,
        "skip_condition": False
    })
    wait(3)
    state = get_state(AWAY_FLAG)["state"]
    assert state == "off", f"Expected away_mode blocked by snooze, got {state}"
    print("PASS: Away mode blocked when snoozed")
    _reset()


def test_away_mode_does_not_fire_if_someone_home():
    """Only one person is away — should not activate away mode."""
    _reset()
    set_state(RILEY, "not_home")
    set_state(CASEY, "home")
    wait(1)
    call_service("automation", "trigger", {
        "entity_id": AWAY_AUTO,
        "skip_condition": False
    })
    wait(3)
    state = get_state(AWAY_FLAG)["state"]
    assert state == "off", f"Expected away_mode off (Casey is home), got {state}"
    print("PASS: Away mode does not fire if one person is home")
    _reset()


def test_arriving_home_clears_away_mode():
    _reset()
    # Activate away mode first
    call_service("input_boolean", "turn_on", {"entity_id": AWAY_FLAG})
    set_state(RILEY, "home")
    wait(1)
    call_service("automation", "trigger", {
        "entity_id": ARRIVE_AUTO,
        "skip_condition": False
    })
    wait(3)
    state = get_state(AWAY_FLAG)["state"]
    assert state == "off", f"Expected away_mode=off after arriving, got {state}"
    print("PASS: Arriving home clears away mode")
    _reset()


def test_arriving_home_blocked_by_snooze():
    _reset()
    call_service("input_boolean", "turn_on", {"entity_id": AWAY_FLAG})
    call_service("script", "snooze_automation", {
        "snooze_id": "arriving_home",
        "duration_minutes": 30
    })
    set_state(RILEY, "home")
    wait(1)
    call_service("automation", "trigger", {
        "entity_id": ARRIVE_AUTO,
        "skip_condition": False
    })
    wait(3)
    state = get_state(AWAY_FLAG)["state"]
    assert state == "on", f"Expected away_mode to stay on (arriving snoozed), got {state}"
    print("PASS: Arriving home blocked when snoozed")
    _reset()
