"""
Camera infrastructure tests.

Blink cameras are cloud-snapshot-only (supported_features=0, no streaming).
These tests verify entity health and automation state — they do NOT trigger
a Blink cloud capture (that uses battery and takes 15+ seconds to complete).

To manually force a snapshot refresh: python3 ha_client.py trigger_blink
Or trigger automation.system_blink_snapshot_refresh via Developer Tools.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import requests
from ha_client import get_state, call_service, _headers, _session, HA_URL, wait

CAMERA_ENTITIES = [
    "camera.driveway",
    "camera.rear_driveway",
    "camera.backyard",
    "camera.doorbell",
    "camera.g8v1_gh02_2503_3rh3",  # G8V1 living room cam
    "camera.tilt_camera",
]

MOTION_ALERT_AUTOMATIONS = [
    "Camera - Driveway Motion Alert",
    "Camera - Rear Driveway Motion Alert",
    "Camera - Backyard Motion Alert",
    "Camera - Doorbell Motion Alert",
    "Camera - Living Room Motion While Away",
    "Camera - Tilt Camera Motion While Away",
]


def _get_automation_by_alias(alias: str):
    r = _session.get(f"{HA_URL}/api/states", headers=_headers())
    r.raise_for_status()
    for s in r.json():
        if s["entity_id"].startswith("automation."):
            if s["attributes"].get("friendly_name") == alias:
                return s
    return None


def test_all_cameras_registered():
    """All Blink camera entities must exist in the HA registry."""
    missing, unavailable = [], []
    for entity_id in CAMERA_ENTITIES:
        try:
            s = get_state(entity_id)
            if s["state"] in ("unavailable", "unknown"):
                unavailable.append(entity_id)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                missing.append(entity_id)
            else:
                raise
    assert not missing, "Cameras NOT REGISTERED:\n  " + "\n  ".join(missing)
    if unavailable:
        print(f"WARN: {len(unavailable)} cameras unavailable (may be sleeping): {unavailable}")
    else:
        print(f"PASS: All {len(CAMERA_ENTITIES)} cameras registered and accessible")


def test_cameras_have_entity_picture():
    """Each camera must have an entity_picture attribute (what picture-entity uses)."""
    missing_picture = []
    for entity_id in CAMERA_ENTITIES:
        try:
            s = get_state(entity_id)
            if not s["attributes"].get("entity_picture"):
                missing_picture.append(entity_id)
        except requests.HTTPError:
            pass  # Caught in test_all_cameras_registered
    assert not missing_picture, (
        "Cameras missing entity_picture (dashboard card will be blank):\n  "
        + "\n  ".join(missing_picture)
    )
    print(f"PASS: All accessible cameras have entity_picture attribute")


def test_blink_refresh_automation_enabled():
    """System - Blink Snapshot Refresh must be enabled for fresh images."""
    s = _get_automation_by_alias("System - Blink Snapshot Refresh")
    assert s is not None, "automation 'System - Blink Snapshot Refresh' not found"
    assert s["state"] == "on", (
        f"Blink refresh automation is {s['state']} — images will go stale"
    )
    print("PASS: Blink snapshot refresh automation is enabled")


def test_motion_alert_automations_enabled():
    """All camera motion alert automations must be enabled."""
    disabled, missing = [], []
    for alias in MOTION_ALERT_AUTOMATIONS:
        s = _get_automation_by_alias(alias)
        if s is None:
            missing.append(alias)
        elif s["state"] != "on":
            disabled.append(f"{alias} ({s['state']})")
    assert not missing, "Motion alert automations NOT FOUND:\n  " + "\n  ".join(missing)
    assert not disabled, "Motion alert automations DISABLED:\n  " + "\n  ".join(disabled)
    print(f"PASS: All {len(MOTION_ALERT_AUTOMATIONS)} camera motion alert automations enabled")


def test_blink_refresh_can_be_triggered():
    """Trigger the Blink refresh automation and verify it runs without error.
    Does NOT wait for snapshot to arrive — just confirms the automation fires.
    """
    r = _session.get(f"{HA_URL}/api/states", headers=_headers())
    automations = {
        s["attributes"].get("friendly_name"): s["entity_id"]
        for s in r.json() if s["entity_id"].startswith("automation.")
    }
    entity_id = automations.get("System - Blink Snapshot Refresh")
    assert entity_id, "Cannot find Blink refresh automation entity_id"

    result = call_service("automation", "trigger", {"entity_id": entity_id})
    assert result in (200, 201), f"Expected HTTP 200/201, got {result}"
    print(
        "PASS: Blink refresh automation triggered "
        "(verify: camera.entity_picture URLs update after ~20s)"
    )
