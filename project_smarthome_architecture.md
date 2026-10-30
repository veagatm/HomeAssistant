---
name: SmartHome Project Architecture
description: Full hardware inventory, protocol map, and planned HA architecture for the user's smart home build
type: project
originSessionId: cd6a7d13-ac56-4951-a977-b5a01ad5cff5
---
# SmartHome Project Architecture

Full Home Assistant build in progress. HA hardware unboxed but not yet configured as of 2026-05-07.

**Why:** Move off Google Home to local-first control, add network security (IoT VLAN), integrate energy monitoring, cameras (future), and MagicMirror.

**How to apply:** Reference this when continuing the build. Follow the installation sequence.

---

## Hardware Inventory

### Core Infrastructure
- **HA Green** — main HA server (HAOS)
- **HA Connect ZBT-2** — Zigbee + Thread/Matter USB (plugs into HA Green)
- Xfinity + Netgear CM1200 modem (gFiber arriving in 3-6 months — will replace modem with ONT)
- TP-Link Deco AXE5400 XE75 mesh system
- **Netgear GS308Ev4** — 8-port managed smart switch (supports 802.1Q VLANs)

### Lighting
- Philips Hue bridge + variety of Hue lights (currently in Google Home)
- Govee WiFi lights (have local LAN API — must enable in Govee app)

### Locks
- **August Smart Lock 3rd Gen Pro + Connect Hub** (WiFi/cloud — no local option, front door)
- **GJV Smart Lock** (Tuya/Smart Life, back door) — SKIP FOR NOW (Tuya integration doesn't support locks natively)

### Sensors
- Hue motion sensors (Zigbee)
- Samsung SmartThings motion sensors (Zigbee)
- Off-brand sensors (Zigbee — not yet configured)

### Smart Plugs
- TP-Link Kasa HS103P2 (local API, fully supported)
- BN-Link smart WiFi plugs (Tuya-based, LocalTuya via HACS)

### Energy Monitoring
- **Leviton Load Center** with **LWHEM-2R** energy monitor (WiFi/cloud — HACS integration: `rwoldberg/ldata-ha`)

### Voice / Display
- Google Nest Hub 10" (Matter bridge)
- Google Home speakers (multiple)
- Chromecasts
- MagicMirror on Raspberry Pi 3 B+ (companion project — keep separate)

### Cameras (future)
- Reolink cameras (not yet purchased/installed — local RTSP, native HA integration + Frigate)

### Other
- August smart lock bridge (included with lock above)
- Google Home speakers (will integrate via Google Cast in HA)

---

## Protocol Map

```
ZBT-2 (USB on HA Green)
├── Zigbee: Hue sensors, SmartThings sensors, off-brand sensors
└── Thread/Matter: Nest Hub 10" (Matter bridge)

Philips Hue Bridge (local API — keep bridge, don't migrate bulbs to ZBT-2)

WiFi (IoT VLAN):
├── Govee lights → Govee Light Local (HACS, local LAN)
├── Kasa HS103 plugs → TP-Link Kasa integration (local)
├── BN-Link plugs → LocalTuya (HACS, local)
├── August Lock → August integration (cloud, unavoidable)
├── Leviton LWHEM-2R → ldata-ha (HACS, cloud to my.leviton.com)
├── GJV Lock (back door) → SKIP (Tuya, no good HA lock support yet)
└── Reolink cameras (future) → Reolink integration (local RTSP) + Frigate NVR
```

No Z-Wave dongle needed (Leviton is WiFi, not Z-Wave).

---

## Add-on Stack (HA Green)

| Add-on | Purpose |
|---|---|
| Zigbee2MQTT | Zigbee coordinator using ZBT-2 |
| Mosquitto MQTT Broker | Message bus for Zigbee2MQTT |
| Node-RED | Visual automation builder |
| Frigate NVR | Local AI camera detection (Reolink, future) |
| HACS | Community integrations installer |
| File Editor | In-browser YAML editing |
| Tailscale | Remote access (zero open ports) |

---

## Network Security Architecture

```
Internet → CM1200 → Deco XE75 (router)
  ├── SSID: Main WiFi  → VLAN 10 (trusted: phones, PCs, HA Green)
  ├── SSID: IoT        → VLAN 20 (all IoT WiFi devices)
  └── Wired uplink → Netgear GS308Ev4
        ├── Port 1: Deco uplink (trunk VLAN 10+20)
        ├── Port 2: HA Green → VLAN 10
        ├── Port 3+: IoT wired devices → VLAN 20
```

Firewall: IoT VLAN reaches internet but NOT main VLAN, except HA Green (which polls IoT).
Note: Verify Deco XE75 VLAN tagging support on uplink port — may be limited to IoT SSID isolation only.

---

## Remote Access
- **Tailscale** (HA add-on) — primary remote access, zero open ports
- **NordVPN** — keep for outbound privacy; NOT used for HA remote access (wrong tool for that job)

---

## MagicMirror (Companion Project — separate repo)
- Keep MagicMirror on Pi3 B+ (do NOT run HA on it — 1GB RAM too limited)
- Add: MMM-HomeAssistant, MMM-iFrame (full HA dashboard), MMM-YouTube
- Bathroom audio: routed through HA → Google Cast to bathroom speaker
- Start this AFTER HA is stable

---

## Installation Sequence
1. Network first — IoT VLAN on GS308Ev4 + Deco IoT SSID
2. HA initial setup — HA Green onboarding
3. Add-ons — Zigbee2MQTT, Mosquitto, HACS, Tailscale, File Editor
4. Devices — Hue (local), Govee (local), Kasa (local), sensors (Zigbee2MQTT)
5. Cloud integrations — August, Leviton LWHEM (ldata-ha), Google Cast
6. Automations — Node-RED
7. Cameras — Frigate + Reolink (when hardware arrives)
8. MagicMirror — after HA is stable

---

## gFiber Transition Note
Arriving in 3-6 months. Replaces CM1200 (ONT-based, no modem). Deco WAN port repoints. Rest of architecture unchanged.
