# Dashboard Design Ideas & Mockups

## Design feedback process
Review the ASCII mockups below. For each view, mark your preference with a `>` or just add comments inline. Once you've marked up what you want, I'll implement only those views and deploy.

**Phone-first constraints applied throughout:**
- 2-column max for horizontal stacks (3-col is too narrow on phone)
- Most-used controls at top
- Scroll is fine — but keep the "at a glance" content above the fold

---

## VIEW 1: Home

### CURRENT layout
```
┌─────────────────────────────┐
│ [Riley] [Casey] [Away] [Zzz]│  ← chips row
│ [Internet]                  │
├─────────────────────────────┤
│      THERMOSTAT             │  ← full-width ecobee
│      72°F / Cool            │
├─────────────────────────────┤
│ [LR Light] [Kitchen] [Bed]  │  ← 3-col (narrow on phone)
├─────────────────────────────┤
│  [Hallway]    [Foyer]       │
│  [Office]                   │
├─────────────────────────────┤
│      Quick Actions          │
│ [Good Night] [Set Trash]    │
│ [Find Riley] [Find Casey]   │
└─────────────────────────────┘
Fold is roughly here on a phone
```

### ALT A — Compact, most-used above the fold
```
┌─────────────────────────────┐
│ [Riley][Casey][Away][Zzz][↗]│  ← chips row (all on one line)
├─────────────────────────────┤
│      THERMOSTAT (compact)   │  ← keep, but consider simple-thermostat
│      72°F  Heat/Cool        │
├─────────────────────────────┤
│ [🌙 Good Night] [🗑 Trash]  │  ← quick actions moved up, 2-col
├─────────────────────────────┤
│ [LR Light ██░]  [Kitchen ██]│  ← 2-col light cards w/ brightness slider
│ [Bedroom ████]  [Office  ░░]│
├─────────────────────────────┤  ← FOLD (most-used above here)
│ [Hallway]       [Foyer]     │
│ [Find Riley]    [Find Casey]│
└─────────────────────────────┘
```

### ALT B — Status-first, minimal actions
```
┌─────────────────────────────┐
│ [Riley: Home] [Casey: Away] │  ← person chips (bigger, descriptive)
│ [🏠 Home] [☀️ Awake] [↗ Online]│
├─────────────────────────────┤
│ 72°F ── setpoint 74°F ──    │  ← minimal climate row
│ [▼] mode: cool              │
├─────────────────────────────┤
│  Living Room ████████░ on   │  ← light summary with state text
│  Kitchen     ░░░░░░░░░ off  │
│  Bedroom     ██████░░░ on   │
├─────────────────────────────┤  ← FOLD
│ [🌙 Good Night] [🗑 Trash]  │
│ [📍 Find Riley] [📍 Casey]  │
└─────────────────────────────┘
```

**Your pick / notes:**
> B

---

## VIEW 2: Rooms

### CURRENT layout
```
┌─────────────────────────────┐
│ Living Room  · 450 lux      │  ← title with lux
│ [Room Group] [Lamp]         │  ← 2-col lights
│ [Front L]  [Front R][Back L]│  ← 3-col (too narrow on phone)
│ [TV Strip] [Roku]           │
│                             │
│ Bedroom  · 120 lux          │
│ [Room Group] [Floor Lamp]   │
│ [Ceil 1] [Ceil 2] [Tall L]  │  ← 3-col
│ [Relax][Bright][Movie][Dung]│  ← 4-col (way too narrow)
│ [Bedroom TV]                │
│ [Manual Mode]               │
│                             │
│ Kitchen  · 800 lux          │
│ ... (continues scrolling)   │
└─────────────────────────────┘
Lots of scrolling, 3-4 col stacks too narrow on phone
```

### ALT A — Bubble Card grid (RECOMMENDED for phone)
```
┌─────────────────────────────┐
│   Rooms                     │
│ ┌──────────┐ ┌──────────┐   │
│ │ 🛋 Living │ │ 🛏 Bedroom│  ← tap opens popup
│ │  Room    │ │          │   │
│ │  ON ████ │ │  ON ████ │   │
│ └──────────┘ └──────────┘   │
│ ┌──────────┐ ┌──────────┐   │
│ │ 🍳 Kitchen│ │🚪Hallway │   │
│ │  OFF     │ │  OFF     │   │
│ └──────────┘ └──────────┘   │
│ ┌──────────┐ ┌──────────┐   │
│ │ 🏢 Office │ │🌿 Porch  │   │
│ │  OFF     │ │  OFF     │   │
│ └──────────┘ └──────────┘   │
└─────────────────────────────┘

Tap "Living Room" → popup fills screen:
┌─────────────────────────────┐
│ ✕  Living Room              │
│ ┌───────────────────────┐   │
│ │  Room Group  ████░ ON │   │
│ │  Lamp        ██░░░ ON │   │
│ │  Front Left  ████░ ON │   │
│ │  Front Right ████░ ON │   │
│ │  Back Left   ████░ ON │   │
│ │  TV Strip    ██░░░ ON │   │
│ └───────────────────────┘   │
│ ┌─────────┐                 │
│ │  Roku   │ Playing: Netflix│
│ └─────────┘                 │
└─────────────────────────────┘
```

### ALT B — Flat but 2-col only (no Bubble Card needed)
```
Same as current but:
- All 3-col stacks → 2-col (Front L + Front R on one row, Back L + TV Strip on next)
- 4-col Hue scenes → 2-col (2 rows of 2)
- No popup needed
- Still long scroll but cards are readable
```

**Your pick / notes:**
> A

---

## VIEW 5: Automations

### CURRENT layout
```
Endless scroll: Room switches → State flags → 12 toggle rows → 
15+ snooze sections (each with 3-4 buttons) — very long
```

### ALT A — Snoozed items bubble to top
```
┌─────────────────────────────┐
│  🔔 Active Snoozes          │  ← conditional: only shows when something snoozed
│  LR Motion  → clears 2:30p  │
│  [Clear LR] [Clear All]     │
├─────────────────────────────┤
│  Room Switches              │
│ [LR ✓] [Bed ✓] [Kitchen ✓] │
├─────────────────────────────┤
│  State Flags                │
│ [Sleep ✓] [Away ✓] [Trash]  │
├─────────────────────────────┤
│  Snooze Controls            │
│  ▶ Lighting        (tap→ expand)│
│  ▶ Routines        (tap→ expand)│
│  ▶ Alerts          (tap→ expand)│
└─────────────────────────────┘
(much shorter when nothing snoozed; snooze sections expand on demand)
```

### ALT B — Keep flat but collapse individual snooze rows
```
Same structure as current, but:
- Each snooze row: shows "active" or expiry time in subtitle
- Only the most-used options shown: 30min | Clear (drop 2hr + Until 7am rows to reduce clutter)
- Per-automation toggles stay as entities card (compact)
```

**Your pick / notes:**
> A

---

## Other ideas / notes

*Add anything here you want to try or change across any view*

---

---

### 1. Casting Lovelace Dashboards to Google Displays
To cast specific Lovelace dashboard views to supported Google devices with a screen (like a Google Nest Hub), you must meet a few technical prerequisites:
*   **HTTPS Requirement:** Your Home Assistant instance must be accessible externally via HTTPS. This is handled automatically if you use Home Assistant Cloud (Nabu Casa), otherwise, you must configure an external URL manually.
*   **Google Cast Integration:** Home Assistant will usually auto-detect your Cast devices, but you must ensure the Google Cast integration is fully configured.

**How to Cast a View:**
Instead of casting the whole system, you cast a specific "view" (an individual page within a dashboard). 
1.  **Locate your Paths:** Check your dashboard URL. The string directly following your IP/port is the **dashboard path** (e.g., `lovelace_demo`), and the final string is the **view path** (e.g., `home`). You can set a custom view path by clicking the pencil icon next to the view in "Edit Dashboard" and modifying the `URL` field.
2.  **Call the Service:** Navigate to **Developer Tools > Services** and select `cast.show_lovelace_view`. 
3.  **Provide Parameters:** You will need to input the `entity_id` of your target media player (ensure it has a screen, unlike a Nest Mini), the `dashboard_path`, and the `view_path`. Once called, the touch screen will allow you to control the entities directly from the display.

**Recommended Workarounds and Automations:**
*   **Voice Automation:** You can turn the `cast.show_lovelace_view` service call into a script, expose that script to Google Assistant, and trigger it via a voice routine (e.g., "Hey Google, cast lights").
*   **Crucial "Gotcha" - Closing Sessions:** A casting session remains open on the Google device. If you try to cast a *new* view while an old one is still active, the screen will hang on the Google logo. To fix this, it is highly recommended to create a script that calls the `media_player.turn_off` service targeting your cast entity. Expose this to Google Assistant and map it to a "stop casting" voice routine to clear the screen before initiating a new cast.
*   *(Note: Using this setup to auto-cast security camera feeds upon motion detection is explicitly **not recommended** at this time, as the streams often lag or fail to load entirely.)*

### 2. Creating an Interactive "Room Image" Lovelace Interface
You can create a highly visual dashboard where touching specific parts of a photograph of your actual room toggles the corresponding physical lights.

**Image Preparation:**
1.  Use image editing software like GIMP to create a base image of your room in grayscale (black and white) to represent all lights being turned off. 
2.  Create separate, isolated image overlays for each individual light in the room while turned on.
3.  In Home Assistant, use the File Editor to create a new folder named `www` and upload all your prepared images into it, then restart Home Assistant.

**Lovelace Configuration:**
1.  Add a **Picture Elements** card to your dashboard.
2.  Set the main image of the card to your base grayscale room image.
3.  Add an `image` element for your isolated light overlays. Link this element to your target entity (e.g., an MQTT switch) and use CSS positioning (`top: 50%`, `left: 50%`, `width: 100%`) so it perfectly overlaps the base image. Configure the `state_image` so this colored overlay only appears when the entity's state is "on". 
4.  Add a `state-icon` element linked to the exact same switch entity. Manually adjust the `top` and `left` percentages to position the clickable icon exactly over the physical light fixture in the photo, and set the `tap_action` to `toggle`. 
