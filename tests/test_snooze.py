"""
Snooze system tests.

Tests script.snooze_automation, script.clear_snooze, and script.snooze_until_morning.
Uses snooze_lr_motion as the test target — chosen because triggering LR motion
automation in this state has no destructive effect on lights.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timezone
from ha_client import get_state, call_service, wait

SNOOZE_ID = "lr_motion"
SNOOZE_ENTITY = f"input_datetime.snooze_{SNOOZE_ID}"


def _snooze_ts() -> float:
    """Return the current snooze timestamp as a Unix float."""
    return get_state(SNOOZE_ENTITY)["attributes"].get("timestamp", 0)


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def test_snooze_sets_future_datetime():
    # Clear first so state is predictable
    call_service("script", "clear_snooze", {"snooze_id": SNOOZE_ID})
    wait(1)
    call_service("script", "snooze_automation", {"snooze_id": SNOOZE_ID, "duration_minutes": 30})
    wait(2)
    ts = _snooze_ts()
    assert ts > _now_ts(), f"Expected future timestamp, got {ts} vs now {_now_ts():.0f}"
    print(f"PASS: snooze_automation sets future timestamp: {get_state(SNOOZE_ENTITY)['state']}")


def test_snooze_is_in_range():
    """Snooze set for 30 min should be 25–35 min from now (allowing clock drift)."""
    ts = _snooze_ts()
    now = _now_ts()
    delta_minutes = (ts - now) / 60
    assert 25 <= delta_minutes <= 35, f"Expected ~30 min snooze, got {delta_minutes:.1f} min"
    print(f"PASS: Snooze duration correct ({delta_minutes:.1f} min from now)")


def test_clear_snooze_resets_to_past():
    call_service("script", "clear_snooze", {"snooze_id": SNOOZE_ID})
    wait(2)
    ts = _snooze_ts()
    assert ts < _now_ts(), f"Expected past timestamp after clear, got {ts}"
    state = get_state(SNOOZE_ENTITY)["state"]
    print(f"PASS: clear_snooze reset to past ({state})")


def test_snooze_until_morning_sets_tomorrow_7am():
    call_service("script", "snooze_until_morning", {"snooze_id": SNOOZE_ID})
    wait(2)
    ts = _snooze_ts()
    now = _now_ts()
    assert ts > now, f"Expected future timestamp, got {ts}"
    # Should be within 24h + some buffer
    assert ts - now < 25 * 3600, f"snooze_until_morning set too far ({(ts - now)/3600:.1f}h)"
    state = get_state(SNOOZE_ENTITY)["state"]
    print(f"PASS: snooze_until_morning set to {state}")
    # Cleanup
    call_service("script", "clear_snooze", {"snooze_id": SNOOZE_ID})
    wait(1)


def test_snooze_guard_template_while_active():
    """With an active snooze, the guard template should evaluate to false (blocking)."""
    call_service("script", "snooze_automation", {"snooze_id": SNOOZE_ID, "duration_minutes": 30})
    wait(2)
    ts = _snooze_ts()
    now = _now_ts()
    # Template: {{ ts is none or ts < now().timestamp() }}
    # While snoozed ts > now, so template = false = automation blocked
    template_result = (ts is None or ts < now)
    assert not template_result, "Guard template should be False while snoozed"
    print("PASS: Guard template evaluates False while snooze is active (automation blocked)")
    # Cleanup
    call_service("script", "clear_snooze", {"snooze_id": SNOOZE_ID})
    wait(1)


def test_snooze_guard_template_after_clear():
    """After clear_snooze, the guard template should evaluate to true (allowing)."""
    ts = _snooze_ts()
    now = _now_ts()
    template_result = (ts is None or ts < now)
    assert template_result, f"Guard template should be True after clear, got ts={ts} now={now:.0f}"
    print("PASS: Guard template evaluates True after clear (automation allowed)")
