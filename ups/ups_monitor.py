#!/usr/bin/env python3
"""
UPS monitor — runs on Mac Mini via launchd (KeepAlive), polls the CyberPower
CP1500AVRLCD3 every few seconds through macOS's own power-source reporting
(`pmset -g batt`, fed by the UPS's USB HID link), and publishes to HA over
MQTT discovery.

Why the Mac and not NUT on HA Green: the UPS's single USB port is plugged
into the Mac so PowerPanel Personal can shut the Mac down cleanly on low
battery. Moving USB to HA Green would lose that. macOS already exposes
"AC Power" vs "UPS Power" and charge %, which is all the outage alert needs.

Publishes on every change plus a heartbeat, and sets an MQTT last-will so
the entities go `unavailable` if this script or the Mac dies.
"""

import json
import os
import re
import subprocess
import sys
import time

import paho.mqtt.client as mqtt

# Shared with HomeAssistant/tests/ha_client.py — update both if the broker
# password is ever rotated. Password is read from ~/.mqtt_pass (not committed).
MQTT_HOST = "192.168.68.3"
MQTT_PORT = 1883
MQTT_USER = "addons"
MQTT_PASS_FILE = os.path.expanduser("~/.mqtt_pass")

STATE_TOPIC = "macmini/ups/state"
AVAIL_TOPIC = "macmini/ups/availability"

POLL_SECONDS = 5
HEARTBEAT_SECONDS = 60

DEVICE = {
    "identifiers": ["macmini_ups"],
    "name": "UPS",
    "manufacturer": "CyberPower",
    "model": "CP1500AVRLCD3",
}

ENTITIES = [
    (
        "binary_sensor",
        "on_battery",
        {
            "name": "On Battery",
            "object_id": "ups_on_battery",
            "value_template": "{{ 'ON' if value_json.on_battery else 'OFF' }}",
            "icon": "mdi:battery-alert",
        },
    ),
    (
        "sensor",
        "battery",
        {
            "name": "Battery",
            "object_id": "ups_battery",
            "value_template": "{{ value_json.battery_pct }}",
            "unit_of_measurement": "%",
            "device_class": "battery",
            "state_class": "measurement",
        },
    ),
]


def get_mqtt_pass() -> str:
    with open(MQTT_PASS_FILE) as f:
        return f.read().strip()


def read_ups():
    """Return {'on_battery': bool, 'battery_pct': int|None, 'present': bool}."""
    out = subprocess.run(
        ["/usr/bin/pmset", "-g", "batt"], capture_output=True, text=True, timeout=10
    ).stdout
    first = out.splitlines()[0] if out else ""
    pct = re.search(r"(\d+)%", out)
    return {
        "on_battery": "UPS Power" in first or "Battery Power" in first,
        "battery_pct": int(pct.group(1)) if pct else None,
        "present": "present: true" in out,
    }


def publish_discovery(client):
    for component, key, extra in ENTITIES:
        config = {
            "unique_id": f"macmini_ups_{key}",
            "state_topic": STATE_TOPIC,
            "availability_topic": AVAIL_TOPIC,
            "json_attributes_topic": STATE_TOPIC,
            "device": DEVICE,
            **extra,
        }
        client.publish(
            f"homeassistant/{component}/macmini_ups_{key}/config",
            json.dumps(config),
            retain=True,
        )


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        print(f"MQTT connect failed: {reason_code}", file=sys.stderr)
        return
    publish_discovery(client)
    client.publish(AVAIL_TOPIC, "online", retain=True)
    userdata["force"] = True  # republish state after (re)connect


def main():
    userdata = {"force": True}
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, client_id="macmini-ups", userdata=userdata
    )
    client.username_pw_set(MQTT_USER, get_mqtt_pass())
    client.will_set(AVAIL_TOPIC, "offline", retain=True)
    client.on_connect = on_connect
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()

    last, last_sent = None, 0.0
    while True:
        try:
            state = read_ups()
        except Exception as e:
            print(f"pmset read failed: {e}", file=sys.stderr)
            time.sleep(POLL_SECONDS)
            continue

        # A blank % read happens occasionally mid-transition; keep the last value.
        if state["battery_pct"] is None and last:
            state["battery_pct"] = last["battery_pct"]

        changed = last is None or state["on_battery"] != last["on_battery"] or \
            state["battery_pct"] != last["battery_pct"]
        if changed or userdata["force"] or time.time() - last_sent > HEARTBEAT_SECONDS:
            if client.is_connected():
                client.publish(STATE_TOPIC, json.dumps(state), retain=True)
                last_sent = time.time()
                userdata["force"] = False
                if changed:
                    print(f"{time.strftime('%F %T')} {state}", flush=True)
        last = state
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
