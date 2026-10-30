"""
HA test client — shared helpers for all test scripts.

Setup (once):
    pip3 install requests paho-mqtt
    echo "YOUR_LONG_LIVED_TOKEN" > ~/.ha_token
    echo "YOUR_MQTT_PASSWORD" > ~/.mqtt_pass

CLI usage:
    python3 ha_client.py get light.living_room
    python3 ha_client.py get media_player.roku_ultra
"""

import json
import os
import sys
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HA_URL = "http://192.168.68.3:8123"
MQTT_HOST = "192.168.68.3"
MQTT_PORT = 1883
MQTT_USER = "addons"
TOKEN_FILE = os.path.expanduser("~/.ha_token")
MQTT_PASS_FILE = os.path.expanduser("~/.mqtt_pass")

# Retry on connection errors — HA can be briefly busy during async automation runs
# (e.g. Blink cloud triggers). 3 retries with 2s backoff handles transient drops.
_retry = Retry(total=3, backoff_factor=2, status_forcelist=[502, 503, 504],
               allowed_methods=["GET", "POST"])
_session = requests.Session()
_session.mount("http://", HTTPAdapter(max_retries=_retry))


def get_token() -> str:
    with open(TOKEN_FILE) as f:
        return f.read().strip()


def get_mqtt_pass() -> str:
    with open(MQTT_PASS_FILE) as f:
        return f.read().strip()


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_token()}",
        "Content-Type": "application/json",
    }


def get_state(entity_id: str) -> dict:
    r = _session.get(f"{HA_URL}/api/states/{entity_id}", headers=_headers())
    r.raise_for_status()
    return r.json()


def call_service(domain: str, service: str, data: dict) -> int:
    r = _session.post(
        f"{HA_URL}/api/services/{domain}/{service}",
        headers=_headers(),
        json=data,
    )
    return r.status_code


def set_state(entity_id: str, state: str, attributes: dict = None) -> None:
    """Force-set an entity state for testing. HA REST allows this for any entity."""
    body = {"state": state}
    if attributes:
        body["attributes"] = attributes
    _session.post(f"{HA_URL}/api/states/{entity_id}", headers=_headers(), json=body)


def inject_mqtt(topic: str, payload) -> None:
    """Publish a fake MQTT message to simulate a sensor reading.

    payload may be a dict (JSON-serialized) or a plain string (sent as-is).
    """
    import paho.mqtt.publish as publish
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    publish.single(
        topic,
        payload=raw,
        hostname=MQTT_HOST,
        port=MQTT_PORT,
        auth={"username": MQTT_USER, "password": get_mqtt_pass()},
    )


def wait(seconds: float) -> None:
    time.sleep(seconds)


def light_brightness(entity_id: str) -> int:
    # HA stores brightness as None (not absent) when light is off
    return int(get_state(entity_id)["attributes"].get("brightness") or 0)


def light_rgb(entity_id: str) -> list:
    return get_state(entity_id)["attributes"].get("rgb_color", [])


def light_state(entity_id: str) -> str:
    return get_state(entity_id)["state"]


def media_state(entity_id: str) -> str:
    return get_state(entity_id)["state"]


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "get":
        s = get_state(sys.argv[2])
        print(f"state: {s['state']}")
        attrs = s.get("attributes", {})
        for key in ("friendly_name", "brightness", "color_temp", "rgb_color",
                    "source", "media_title", "is_volume_muted"):
            if key in attrs:
                print(f"  {key}: {attrs[key]}")
    else:
        print("Usage: python3 ha_client.py get <entity_id>")
