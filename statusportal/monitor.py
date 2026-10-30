#!/usr/bin/env python3
"""
House Status Monitor — runs on Mac Mini via launchd every 60s.
Pings all local devices and POSTs status to the Cloudflare Worker.
"""

import json
import os
import socket
import subprocess
import time
import urllib.request
import urllib.error

WORKER_URL = "https://status.example.net/api/heartbeat"
API_KEY    = os.environ.get("HSP_API_KEY", "")  # set in launchd plist

DEVICES = [
    # group: "network" | "ha" | "service"
    {"name": "Internet",        "ip": "8.8.8.8",       "group": "network"},
    {"name": "Router (Deco)",   "ip": "192.168.68.1",  "group": "network"},
    {"name": "Netgear Switch",  "ip": "192.168.68.2",  "group": "network"},
    {"name": "HA Green",        "ip": "192.168.68.3",  "group": "ha",      "port": 8123},
    {"name": "Mac Mini",        "ip": "192.168.68.142","group": "service"},
    {"name": "Zigbee2MQTT",     "ip": "192.168.68.3",  "group": "service", "port": 8099},
    {"name": "Frigate NVR",     "ip": "192.168.68.142","group": "service", "port": 5000},
]


def ping(ip: str, timeout: int = 2) -> tuple[bool, float | None]:
    """ICMP ping. Returns (reachable, latency_ms)."""
    start = time.monotonic()
    result = subprocess.run(
        ["ping", "-c", "1", "-W", str(timeout * 1000), "-t", str(timeout), ip],
        capture_output=True,
    )
    elapsed = (time.monotonic() - start) * 1000
    return result.returncode == 0, round(elapsed, 1)


def port_open(ip: str, port: int, timeout: int = 3) -> tuple[bool, float | None]:
    """TCP port check. Returns (open, latency_ms)."""
    start = time.monotonic()
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            elapsed = (time.monotonic() - start) * 1000
            return True, round(elapsed, 1)
    except (OSError, socket.timeout):
        return False, None


def check_device(d: dict) -> dict:
    ip   = d["ip"]
    port = d.get("port")

    if port:
        online, latency = port_open(ip, port)
    else:
        online, latency = ping(ip)

    return {
        "name":       d["name"],
        "ip":         ip,
        "port":       port,
        "group":      d["group"],
        "online":     online,
        "latency_ms": latency if online else None,
    }


def push(devices: list[dict]) -> bool:
    payload = json.dumps({"devices": devices}).encode()
    req = urllib.request.Request(
        WORKER_URL,
        data=payload,
        headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.URLError as e:
        print(f"Push failed: {e}")
        return False


def main():
    statuses = [check_device(d) for d in DEVICES]
    ok = push(statuses)
    if not ok:
        print("Warning: failed to push status to worker")
    online = [d["name"] for d in statuses if d["online"]]
    offline = [d["name"] for d in statuses if not d["online"]]
    print(f"Pushed — online: {online or 'none'} | offline: {offline or 'none'}")


if __name__ == "__main__":
    main()
