# Blueprint Review — Smart Home Automation Recommendations

Source: *Person's Smart Home Blueprint* (YouTube summary)  
Cross-referenced against: current device inventory in HANDOFF.md, CLAUDE.md, entity map

---

## What You Already Have — Skip These Blueprint Items

These recommendations are either irrelevant (hardware you own) or not worth pursuing given your current stack.

| Blueprint Item | Why Skip |
|---|---|
| Beelink Mini S13 PC | HA Green is your server — same role, already running |
| Aeotec Z-Stick 10 Pro | ZBT-2 handles Zigbee already; Z-Wave only needed if you buy Z-Wave devices |
| HA Connect ZWA2 (Long Range) | Not recommended by the source anyway; no outbuilding |
| UniFi networking | Deco XE75 is solid; only worth replacing if you need managed PoE for cameras |
| Lutron RA3/Caseta dimmers | You're fully committed to Hue smart bulbs — adding a second lighting protocol isn't worth it |
| Smart dimmers + dumb bulbs approach | Too late; Hue is invested and working |
| E-paper Boox displays | MagicMirror project covers this use case; start there |
| FlightRadar24 add-on | Fills the HA database fast; novelty only |
| Cafe Flow Editor | You have Node-RED for advanced flows |
| Z-Wave JS UI | Not applicable without Z-Wave hardware |

---

## Automations You Can Build TODAY — No New Hardware

These all work with your current device inventory.

### 1. Washer / Dryer Done Alert
**What:** Push notification to your phone when a cycle finishes.  
**How:** You already have SmartThings vibration sensors on both the washer and dryer frames. When vibration has been active for >5 min and then stops, the cycle is done. No smart plug needed.  
**Build it:** `binary_sensor.vibration_sensor_1_vibration` / `binary_sensor.vibration_sensor_2_vibration` → active for 5 min → stops → notify.

### 2. Internet Outage Warning
**What:** Any Hue light turns red (or a notification fires) when internet drops.  
**How:** Add HA's built-in `ping` integration pointing at 8.8.8.8. When ping fails, trigger a light color or notification.  
**Build it:** Settings → Devices & Services → Add Integration → Ping (ICMP) → automate on `binary_sensor.ping_google_dns` going unavailable.

### 3. Automatic Away Mode (Phone Presence)
**What:** When you leave home, Ecobee goes to away setback, all lights turn off, front door locks.  
**How:** Install the HA companion app on your iPhone. It creates a `device_tracker.your_phone` entity with GPS zone data. When phone leaves the "Home" zone → fire away routine.  
**Build it:** Native HA automation trigger: zone → left → "Home" zone.

### 4. Arriving Home Routine
**What:** Lights on in entry areas, Ecobee switches back to comfort before you walk in.  
**How:** Reverse of above — companion app zone enters "Home".

### 5. Smart HVAC — "Cool Down?" Prompt
**What:** Google speaker asks if you want to cool down when you walk into the bedroom.  
**How:** Bedroom motion sensor (`binary_sensor.bedroom_motion_sensor_occupancy`) triggers a Google speaker TTS question via HA voice assist or a script. Ecobee is already integrated.  
**Enhancement:** Pair with Ecobee's own occupancy sensor for a more reliable trigger.

### 6. Bed Occupancy / Sleep Mode
**What:** Trigger a "sleep" scene (lights off, Ecobee to sleep mode) when someone gets into bed.  
**How:** SmartThings vibration sensor on the bed frame (`zigbee2mqtt/vibration sensor 3`) detects settling-in movement. Not perfect (can't distinguish sleep from sitting on bed) but works for a time-windowed automation after 9 PM.

### 7. Good Morning Routine
**What:** Gradually brighten bedroom lights when you get up.  
**How:** Bed frame vibration sensor detects departure + time window (6–9 AM) → bedroom Hue lights slowly ramp to a warm scene.

### 8. Find My Phone
**What:** Voice command to a Google speaker plays an audible ping on your phone.  
**How:** HA companion app on iOS supports critical notifications and `notify.mobile_app_yourphone` can trigger a high-volume sound. Wire a Google speaker button press or a dashboard button to trigger it.

### 9. Trash Reminder (partial)
**What:** Kitchen speaker reminds you to take out the trash on trash night.  
**How:** Kitchen motion sensor detects you entering the kitchen. If it's trash night (an `input_boolean.trash_night` helper) and time is after 7 PM, Google speaker announces the reminder. Doesn't require a back-door contact sensor — just the motion sensor you already have.  
**Gap:** The blueprint version also checks that the door was already opened (confirmed trash taken out). That needs a contact sensor.

### 10. Memory Lights (approximate)
**What:** When you leave a room, lights turn off; if you return quickly, they restore to the same state.  
**How:** Motion sensors in living room, kitchen, bedroom, and hallway can fire a scene snapshot on "no motion for 5 min", then turn off. On motion return within 30 min, restore scene.  
**Gap:** PIR sensors stop detecting you if you're sitting still — mmwave fixes this (see Tier 1 below). Still useful for active-movement rooms like kitchen.

### 11. Doom Scrolling Prevention
**What:** iOS Shortcuts redirects to a reading app when social media is opened, if daily reading isn't done.  
**How:** Pure iOS Shortcuts + Apple Reminders — zero HA involvement needed.

---

## Top Equipment to Get

### Tier 1 — Buy These First (Highest Automation ROI)

#### 1. mmwave Presence Sensors — ~$35–60 each
**Why it's #1:** Your current PIR motion sensors go "inactive" the moment you stop moving. Every presence-based automation has a gap where the lights cut out while you're reading on the couch. mmwave fixes this by detecting breathing and micro-movements.

Recommended models (both are Zigbee, work directly with your Z2M setup):
- **Aqara FP1** (~$35) — zone-configurable, compact, well-supported in Z2M
- **Apollo MS1 / RO1** (~$55) — more zone granularity, HA community favorite

**Automations it unlocks:**
- Memory Lights (reliable — knows you're still there)
- Server Rack Lights (only on when you're standing right next to it)
- Nap Time Mode (detect actual sleep position in bedroom)
- HVAC presence per room
- "Office occupied" presence without checking your phone

**Priority rooms:** Office first (PIR gap is largest there), then living room, then bedroom.

---

#### 2. Zigbee Door/Window Contact Sensors — ~$10–15 each
**Why:** They unlock a family of conditional automations. Small, cheap, battery-lasts-years.

Recommended: **Aqara MCCGQ11LM** or **Sonoff SNZB-04** — both pair directly to Z2M.

**Automations they unlock:**
- **Back door left open while AC is running** (Ecobee already integrated — just need the sensor)
- **Trash Reminder with confirmation** (was door opened after 8 PM? Trash was taken out)
- **Nap Mode** (bedroom door closes → close shades + dim lights + sound machine)
- **Door open too long** alerts for front/back
- **August Lock pairing** — know when front door is opened independent of lock state

**Priority:** Back door first, then bedroom door.

---

#### 3. Zigbee Smart Plugs with Power Monitoring — ~$15–25 each
**Why:** Your existing Kasa HS103 plugs do NOT have power monitoring — they're on/off only. The LWHEM-2R tracks whole-home energy but not per-appliance. You need per-outlet monitoring for appliance-state automations.

Recommended: **Sonoff S31 Lite Zigbee** (power monitoring, Zigbee, pairs to Z2M).

**Automations they unlock:**
- **Dishwasher Status** — "Clean" dashboard button when dishwasher finishes
- **Charging Drawer Safety** — cut power if temps spike (pair with a cheap Zigbee temp sensor)
- **Appliance left on alerts** — space heater on after you leave, etc.

**Priority:** Dishwasher, then any device you want to monitor.

---

#### 4. Zigbee Water Leak Sensors — ~$10–15 each
**Why:** Low cost, high consequence if you skip them. Under-sink leaks are silent until there's serious damage.

Recommended: **Third Reality ZLD01-S** (has an onboard siren) or **Aqara SJCG12LM**.

**Automations they unlock:**
- Under-sink alerts (kitchen, bathrooms)
- **Dog Bowl Monitor** — Aqara sensor modified with two wires dropped into the bowl; alerts dashboard when bowl is dry (sensor triggers when *not* wet)

**Priority:** Kitchen under-sink, bathroom, washing machine area.

---

### Tier 2 — High Value, Slightly More Investment

#### 5. Robot Vacuum with HA Integration — ~$150–300
**Models with best HA support:** Roborock S5/S6 series, Dreame L10s.

**Automations it unlocks:**
- Auto-start when everyone leaves home (via phone presence detection)
- Maintenance alerts (dirty water tank, empty clean water — dashboard notification)
- "Don't vacuum" mode when someone is home in a specific room (mmwave sensor blocks room)
- Weekly schedule tied to your Google Calendar

---

#### 6. Pressure/Weight Mat (Imilab or Withings Sleep) — ~$60–100
**Why:** Your bed vibration sensor can detect someone getting in/out but not sustained occupancy (it goes quiet once you're still). A pressure mat is binary and reliable.

**Automations it unlocks:**
- Reliable sleep detection → trigger full sleep mode (Ecobee, lights, door lock)
- Auto-Arming "Home" alarm mode when in bed
- Morning routine trigger when pressure releases

---

#### 7. ESP32 + ESPresense for Room Presence — ~$15–30 per room
**Why:** If you install one ESP32 per room and flash ESPresense, it scans for your phone's Bluetooth and can pinpoint you to room-level accuracy. This is the budget alternative to mmwave for knowing *which room* you're in.

**Best use case:** "Find My Phone" room announcement, multi-room HVAC targeting, "Emergency — I'm in the bedroom" button.

**Caveat:** Requires a small DIY project. Start with mmwave (Tier 1) unless you enjoy tinkering.

---

### Tier 3 — Nice to Have, More Niche

#### 8. Smart Window Shades — ~$100–400 per window
**Options:**
- **IKEA Fyrtur** (~$100–130, Zigbee) — budget, pairs to Z2M
- **Hunter Douglas Powerview** — premium, hardwired option exists

**Automations:** Nap Mode, sun-angle countertop protection, morning gradual open.  
**Caveat:** High per-window cost adds up fast. Do one room first to validate the automation value.

#### 9. ESP32 + RFID Reader — ~$20–30 total
**Automates:** Scan a physical card → group Google speakers + set volume + start a Spotify playlist.  
**Why it's Tier 3:** Fun project but Google Home routines can mostly replicate this via voice. Worth building if you enjoy the tangible card interaction.

#### 10. Droplet Water Monitor — ~$200+
**What:** Ultrasonic clamp that measures water flow through the pipe with no plumbing cuts.  
**Automates:** Track daily water usage on dashboard, leak detection by abnormal flow patterns.  
**Caveat:** Expensive for a monitoring-only device. Water leak sensors (Tier 1 above) give you protection for a fraction of the cost. Consider this after you have leak sensors in place.

---

## Phone-as-Presence-Sensor: Alternatives to mmwave

The blueprint relies on mmwave for room-level presence. But before buying sensors, here's what you can get from your existing phone today:

| Presence Tier | Method | Cost | Reliability | What It Covers |
|---|---|---|---|---|
| Home/Away | HA companion app GPS | Free | Excellent | Away automations, Ecobee setback, lock/unlock |
| Room-level (basic) | PIR sensors already installed | Done | Good for motion, misses stillness | Kitchen, bedroom, living room, hallway |
| Room-level (better) | ESP32 + ESPresense BLE scanning | ~$15/room | Good | Any room with an ESP32 |
| Room-level (best) | mmwave sensor | ~$40/room | Excellent | Any room, including stationary occupancy |

**Practical starting point:** Before building any room-presence automation, install the HA companion app and set up Home/Away zone detection. That unlocks ~6 automations for free and you'll immediately feel the value. Then add mmwave sensors room by room.

**Office-specific gap:** Your current motion sensors cover living room, kitchen, bedroom, and hallway — but not the office. A single Zigbee PIR sensor (~$12, Aqara RTCGQ11LM) in the office fills the largest gap in your coverage without any ESP32 or mmwave investment.

---

## Suggested Phased Rollout

| Phase | Actions | New Hardware |
|---|---|---|
| **Phase 0 — Free wins** | Build washer/dryer done alerts, internet outage warning, away mode, good morning routine | None |
| **Phase 1 — Foundation sensors** | Back door contact sensor, kitchen/bathroom water leak sensors, office PIR sensor | ~$50–60 total |
| **Phase 2 — Appliance intelligence** | Smart plug with power monitoring on dishwasher, one more on a charging station | ~$40 |
| **Phase 3 — True presence** | mmwave sensor in office, then living room | ~$70–120 |
| **Phase 4 — Comfort** | Robot vacuum, bed pressure mat | ~$200–350 |
| **Phase 5 — Advanced** | Smart shades (one room), RFID reader, ESPresense room system | $100–400+ |

---

## Software to Add (No Hardware Required)

These are add-ons and integrations from the blueprint that add real value for free:

| Item | What It Does | How to Get |
|---|---|---|
| **Bubble Card** (HACS) | Pop-up subviews on dashboard to keep it clean | HACS → Frontend |
| **Atomic Calendar Revive** (HACS) | Family Google Calendar on dashboard | HACS → Frontend |
| **Chime TTS** (HACS) | Plays a chime before Google speaker TTS so it isn't jarring | HACS → Integration |
| **Kiosk Mode** (HACS) | Hide HA header/sidebar for tablet dashboards | HACS → Frontend |
| **Frosted Glass Theme** | iOS-style dashboard — use the "light" version only | HACS → Frontend |
| **Ping Integration** | Internet outage sensor — 8.8.8.8 monitor | Built-in, Settings → Integrations |
| **TP-Link Deco integration** | See which devices are online, presence detection via router | HACS (tplink-deco) |
