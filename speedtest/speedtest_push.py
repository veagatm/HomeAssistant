#!/usr/bin/env python3
"""
Internet speed test — runs on Mac Mini (hardwired) via launchd every hour.
Publishes results to HA over MQTT discovery, so entities appear automatically
with no configuration.yaml edits or HA restart needed.

Uses Cloudflare's public speed-test endpoints (speed.cloudflare.com) via
stdlib http.client directly — deliberately not a third-party CLI. The two
options tried first were both worse for an unattended hourly job:
  - speedtest-cli (open source): its "nearest server" list for this GFiber IP
    block only returns ~10 Canadian servers (GeoIP mismatch), which shifts
    between requests, and one candidate returned an obviously-bogus
    1800000ms ping sentinel.
  - Ookla's official CLI: Homebrew can't build it here (outdated Command
    Line Tools, no precompiled bottle for this OS build yet).
Cloudflare's anycast network always routes to the nearest healthy edge
(confirmed via /cdn-cgi/trace resolving to the Atlanta colo), so there's no
server list to pin or for to drift.
"""

import http.client
import json
import os
import sys
import time

import paho.mqtt.publish as publish

# Shared with HomeAssistant/tests/ha_client.py — update both if the broker
# password is ever rotated. Password is read from ~/.mqtt_pass (not committed)
# so it can rotate without touching this file.
MQTT_HOST = "192.168.68.3"
MQTT_PORT = 1883
MQTT_USER = "addons"
MQTT_PASS_FILE = os.path.expanduser("~/.mqtt_pass")


def get_mqtt_pass() -> str:
    with open(MQTT_PASS_FILE) as f:
        return f.read().strip()

STATE_TOPIC = "macmini/speedtest/state"
DISCOVERY_PREFIX = "homeassistant/sensor/mac_mini_speedtest"

CF_HOST = "speed.cloudflare.com"
DOWNLOAD_BYTES = 50_000_000
UPLOAD_BYTES = 20_000_000
LATENCY_SAMPLES = 5

DEVICE = {
    "identifiers": ["mac_mini_speedtest"],
    "name": "Mac Mini Speed Test",
    "manufacturer": "Cloudflare speed.cloudflare.com",
}

SENSORS = [
    {
        "key": "download",
        "object_id": "mac_mini_download_speed",
        "name": "Download Speed",
        "unit_of_measurement": "Mbit/s",
        "device_class": "data_rate",
        "value_template": "{{ value_json.download_mbps }}",
    },
    {
        "key": "upload",
        "object_id": "mac_mini_upload_speed",
        "name": "Upload Speed",
        "unit_of_measurement": "Mbit/s",
        "device_class": "data_rate",
        "value_template": "{{ value_json.upload_mbps }}",
    },
    {
        "key": "ping",
        "object_id": "mac_mini_speedtest_ping",
        "name": "Speedtest Ping",
        "unit_of_measurement": "ms",
        "value_template": "{{ value_json.ping_ms }}",
    },
]


def measure_latency(conn: http.client.HTTPSConnection) -> float:
    samples = []
    for _ in range(LATENCY_SAMPLES):
        start = time.perf_counter()
        conn.request("GET", "/__down?bytes=0")
        resp = conn.getresponse()
        resp.read()
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    return round(samples[len(samples) // 2], 1)  # median


def measure_download(conn: http.client.HTTPSConnection) -> float:
    start = time.perf_counter()
    conn.request("GET", f"/__down?bytes={DOWNLOAD_BYTES}")
    resp = conn.getresponse()
    total = 0
    while chunk := resp.read(1 << 16):
        total += len(chunk)
    elapsed = time.perf_counter() - start
    return round((total * 8) / elapsed / 1_000_000, 2)  # Mbps


def measure_upload(conn: http.client.HTTPSConnection) -> float:
    payload = os.urandom(UPLOAD_BYTES)
    start = time.perf_counter()
    conn.request(
        "POST",
        "/__up",
        body=payload,
        headers={"Content-Type": "application/octet-stream"},
    )
    resp = conn.getresponse()
    resp.read()
    elapsed = time.perf_counter() - start
    return round((len(payload) * 8) / elapsed / 1_000_000, 2)  # Mbps


def get_colo(conn: http.client.HTTPSConnection) -> str:
    conn.request("GET", "/cdn-cgi/trace")
    resp = conn.getresponse()
    body = resp.read().decode()
    for line in body.splitlines():
        if line.startswith("colo="):
            return line.split("=", 1)[1]
    return "unknown"


def run_speedtest() -> dict:
    conn = http.client.HTTPSConnection(CF_HOST, timeout=30)
    try:
        colo = get_colo(conn)
        ping_ms = measure_latency(conn)
        download_mbps = measure_download(conn)
        upload_mbps = measure_upload(conn)
    finally:
        conn.close()

    return {
        "download_mbps": download_mbps,
        "upload_mbps": upload_mbps,
        "ping_ms": ping_ms,
        "colo": colo,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def publish_discovery():
    for sensor in SENSORS:
        config = {
            "name": sensor["name"],
            "object_id": sensor["object_id"],
            "unique_id": f"macmini_speedtest_{sensor['key']}",
            "state_topic": STATE_TOPIC,
            "value_template": sensor["value_template"],
            "unit_of_measurement": sensor["unit_of_measurement"],
            "state_class": "measurement",
            "json_attributes_topic": STATE_TOPIC,
            "device": DEVICE,
        }
        if "device_class" in sensor:
            config["device_class"] = sensor["device_class"]

        publish.single(
            f"{DISCOVERY_PREFIX}_{sensor['key']}/config",
            payload=json.dumps(config),
            retain=True,
            hostname=MQTT_HOST,
            port=MQTT_PORT,
            auth={"username": MQTT_USER, "password": get_mqtt_pass()},
        )


def publish_state(result: dict):
    publish.single(
        STATE_TOPIC,
        payload=json.dumps(result),
        retain=True,
        hostname=MQTT_HOST,
        port=MQTT_PORT,
        auth={"username": MQTT_USER, "password": get_mqtt_pass()},
    )
    print(
        f"Published: down={result['download_mbps']}Mbps "
        f"up={result['upload_mbps']}Mbps ping={result['ping_ms']}ms "
        f"colo={result['colo']}"
    )


def main():
    try:
        result = run_speedtest()
    except Exception as e:
        print(f"speedtest failed: {e}", file=sys.stderr)
        sys.exit(1)

    publish_discovery()
    publish_state(result)


if __name__ == "__main__":
    main()
