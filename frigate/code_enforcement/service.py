#!/usr/bin/env python3
"""
Code Enforcement Detector
Watches frigate/events for cars in road_zone, runs EasyOCR on the Frigate snapshot,
and publishes an MQTT alert when "code enforcement" text is found.

All car detections are logged to SQLite regardless of OCR result so you can
review missed reads and tune keywords over time.
"""

import io
import json
import logging
import os
import re
import sqlite3
from datetime import date, datetime, timezone

import paho.mqtt.client as mqtt
import requests
from PIL import Image, ImageEnhance, ImageFilter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ce-detector")

MQTT_HOST      = os.getenv("MQTT_HOST", "192.168.68.3")
MQTT_PORT      = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER      = os.getenv("MQTT_USER", "addons")
MQTT_PASSWORD  = os.getenv("MQTT_PASSWORD", "")
DB_PATH        = os.getenv("DB_PATH", "/data/code_enforcement.db")
FRIGATE_URL    = os.getenv("FRIGATE_URL", "http://192.168.68.142:5050")
# Used only for push-notification image URLs (must be reachable from a phone on
# cellular, away from home) — FRIGATE_URL above stays LAN-only since it's also used
# for the OCR service's own image fetches, which should stay fast/local.
NOTIFICATION_BASE_URL = os.getenv("NOTIFICATION_BASE_URL", "https://ha.example.net/api/frigate/notifications")
CAMERA         = os.getenv("FRIGATE_CAMERA", "front")
ZONE           = os.getenv("FRIGATE_ZONE", "road_zone")
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "ce-detector")
MODEL_DIR      = os.getenv("MODEL_DIR", "/data/easyocr_models")
THUMB_DIR      = os.getenv("THUMB_DIR", "/data/thumbnails")
# Hamming distance threshold for known-vehicle matching (0–64; lower = stricter)
PHASH_THRESHOLD = int(os.getenv("PHASH_THRESHOLD", "12"))

# Lazy-loaded — initialized on first car detection so the container starts fast
_reader = None

# Known fleet vehicle keyword sets — order matters (most specific first)
VEHICLE_CATEGORIES = [
    {
        "name":     "code_enforcement",
        "label":    "Code Enforcement",
        "keywords": ["code enforcement", "code enf", "code enfo"],
        "split":    [("code", "enforcement")],
        "fuzzy":    r"c[o0][d][e3].{0,4}en[f]",
        "topic":    "code_enforcement/alert",
    },
    {
        "name":     "usps",
        "label":    "USPS",
        "keywords": ["usps", "postal service", "we deliver for you", "we deliver for yo", "usps.com"],
        "split":    [],
        "fuzzy":    r"u\.?s\.?p\.?s",
        "topic":    "vehicles/usps",
    },
    {
        "name":     "fedex",
        "label":    "FedEx",
        "keywords": ["fedex", "federal express"],
        "split":    [("federal", "express")],
        "fuzzy":    r"fe[d]e[x]",
        "topic":    "vehicles/fedex",
    },
    {
        "name":     "ups",
        "label":    "UPS",
        "keywords": ["united parcel", "ups.com"],
        "split":    [],
        "fuzzy":    None,
        "topic":    "vehicles/ups",
    },
    {
        "name":     "amazon",
        "label":    "Amazon",
        "keywords": ["amazon", "amzn"],
        "split":    [],
        "fuzzy":    None,
        "topic":    "vehicles/amazon",
    },
]


def get_reader():
    global _reader
    if _reader is None:
        import easyocr
        log.info("Loading EasyOCR English model (first run may take ~60s to download)...")
        _reader = easyocr.Reader(["en"], gpu=False, model_storage_directory=MODEL_DIR)
        log.info("EasyOCR ready")
    return _reader


# ── Database ──────────────────────────────────────────────────────────────────

def init_db(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp           TEXT NOT NULL,
            date                TEXT NOT NULL,
            event_id            TEXT,
            category            TEXT,
            is_code_enforcement INTEGER DEFAULT 0,
            matched_text        TEXT,
            all_ocr_text        TEXT,
            car_confidence      REAL,
            snapshot_url        TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS known_vehicles (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            phash        TEXT NOT NULL,
            event_id     TEXT,
            created_at   TEXT NOT NULL
        )
    """)
    # column migrations
    for col in ["category TEXT", "user_category TEXT", "reviewed INTEGER DEFAULT 0"]:
        try:
            conn.execute(f"ALTER TABLE detections ADD COLUMN {col}")
        except Exception:
            pass
    conn.execute("CREATE INDEX IF NOT EXISTS idx_date     ON detections(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ce       ON detections(is_code_enforcement)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON detections(category)")
    conn.commit()
    return conn


def today_ce_count(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM detections WHERE date=? AND is_code_enforcement=1",
        (date.today().isoformat(),)
    ).fetchone()[0]


def total_ce_count(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM detections WHERE is_code_enforcement=1"
    ).fetchone()[0]


# ── Known-vehicle matching ────────────────────────────────────────────────────

def is_known_vehicle(conn, img) -> bool:
    """Return True if img's pHash is within PHASH_THRESHOLD of any stored known vehicle."""
    import imagehash
    rows = conn.execute("SELECT phash FROM known_vehicles").fetchall()
    if not rows:
        return False
    h = imagehash.phash(img)
    for (stored,) in rows:
        try:
            if h - imagehash.hex_to_hash(stored) <= PHASH_THRESHOLD:
                return True
        except Exception:
            continue
    return False


# ── Image / OCR ───────────────────────────────────────────────────────────────

def fetch_snapshot(event_id):
    """
    Fetch the full-frame thumbnail from Frigate and save a local copy to THUMB_DIR.
    Using /thumbnail.jpg (no burned-in bbox overlays) instead of /snapshot.jpg.
    The local copy persists independently of Frigate's event retention.
    """
    url = f"{FRIGATE_URL}/api/events/{event_id}/thumbnail.jpg"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        raw = resp.content
        # Save a local copy before Frigate prunes the event
        os.makedirs(THUMB_DIR, exist_ok=True)
        local_path = os.path.join(THUMB_DIR, f"{event_id}.jpg")
        with open(local_path, "wb") as f:
            f.write(raw)
        return Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:
        log.error(f"Thumbnail fetch failed for {event_id}: {e}")
        return None


def mask_overlay_regions(img):
    """
    Black-out the Reolink timestamp (top strip) and watermark (bottom-right corner)
    so OCR doesn't waste time reading burned-in camera text.
    Fractions are tuned to the front camera's 640×360 layout scaled to any height.
    """
    from PIL import ImageDraw
    w, h = img.size
    draw = ImageDraw.Draw(img)
    # Top bar — timestamp ("06/16/2026 11:00:30 am TUE")
    draw.rectangle([0, 0, w, int(h * 0.10)], fill="black")
    # Bottom-right — "Front Yard" watermark
    draw.rectangle([int(w * 0.55), int(h * 0.88), w, h], fill="black")
    return img


def preprocess(img):
    """Mask overlays, upscale, then enhance contrast + sharpness for OCR."""
    img = mask_overlay_regions(img)
    w, h = img.size
    # Only upscale if the image is still small (Frigate may already serve 1080p)
    if h < 720:
        img = img.resize((w * 2, h * 2), Image.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.8)
    img = ImageEnhance.Sharpness(img).enhance(2.0)
    img = img.filter(ImageFilter.DETAIL)
    return img


def run_ocr(img):
    import numpy as np
    results = get_reader().readtext(np.array(img), detail=1, paragraph=False)
    for bbox, text, conf in results:
        log.info(f'  OCR: "{text}" ({conf:.2f})')
    return results


def classify_vehicle(ocr_results):
    """
    Match OCR text against all known vehicle categories.
    Returns (category_name_or_None, matched_phrase).
    Code enforcement is checked first since it's the priority alert.
    """
    blocks = [text for _, text, _ in ocr_results]
    combined = " ".join(blocks).lower()
    clean   = re.sub(r"[^a-z0-9\s\.]", " ", combined)
    words   = clean.split()

    for cat in VEHICLE_CATEGORIES:
        # Exact keyword in combined text
        for kw in cat["keywords"]:
            if kw in clean:
                return cat["name"], kw

        # Split-word match (e.g. "code" on one line, "enforcement" on another)
        for w1, w2 in cat.get("split", []):
            if w1 in words and w2 in words:
                return cat["name"], f"{w1} + {w2} (split)"

        # Fuzzy regex for common OCR substitutions
        if cat.get("fuzzy") and re.search(cat["fuzzy"], clean):
            return cat["name"], f"fuzzy: {combined[:60]}"

    return None, None


# ── MQTT ─────────────────────────────────────────────────────────────────────

def publish(client, conn, category, matched_text, all_text, car_confidence, event_id, snapshot_url):
    now = datetime.now(timezone.utc).isoformat()

    # Always log every car detection
    client.publish("vehicles/car_seen", json.dumps({
        "event_id":    event_id,
        "category":    category,
        "matched_text": matched_text,
        "all_ocr_text": all_text[:300],
        "snapshot_url": snapshot_url,
        "timestamp":   now,
    }))

    if category:
        cat_def = next((c for c in VEHICLE_CATEGORIES if c["name"] == category), None)
        label   = cat_def["label"] if cat_def else category
        topic   = cat_def["topic"] if cat_def else f"vehicles/{category}"

        count_today = today_ce_count(conn) if category == "code_enforcement" else 0
        count_total = total_ce_count(conn) if category == "code_enforcement" else 0

        payload = {
            "event_id":     event_id,
            "category":     category,
            "label":        label,
            "matched_text": matched_text,
            "snapshot_url": f"{NOTIFICATION_BASE_URL}/{event_id}/snapshot.jpg",
            "timestamp":    now,
            "today_count":  count_today,
            "total_count":  count_total,
        }
        client.publish(topic, json.dumps(payload))

        if category == "code_enforcement":
            client.publish("code_enforcement/last_seen",   now,              retain=True)
            client.publish("code_enforcement/today_count", str(count_today), retain=True)
            client.publish("code_enforcement/total_count", str(count_total), retain=True)
            log.warning(f"CODE ENFORCEMENT DETECTED — matched: '{matched_text}'")
        else:
            log.info(f"Vehicle classified as {label} — matched: '{matched_text}'")


# ── Event handler ─────────────────────────────────────────────────────────────

def on_message(client, userdata, msg):
    conn = userdata["conn"]
    try:
        payload = json.loads(msg.payload)
    except Exception:
        return

    if payload.get("type") != "end":
        return

    after = payload.get("after", {})
    if after.get("camera") != CAMERA or after.get("label") != "car":
        return
    if ZONE not in after.get("current_zones", []):
        return

    event_id       = after.get("id", "")
    car_confidence = after.get("top_score", 0)
    snapshot_url   = f"{FRIGATE_URL}/api/events/{event_id}/snapshot.jpg"

    log.info(f"Car in {ZONE} — event_id={event_id} conf={car_confidence:.2f}")

    img = fetch_snapshot(event_id)
    if img is None:
        return

    # Check known vehicles BEFORE running expensive OCR
    if is_known_vehicle(conn, img):
        log.info(f"Known vehicle matched — skipping OCR (event_id={event_id})")
        conn.execute(
            """INSERT INTO detections
               (timestamp, date, event_id, category, is_code_enforcement,
                matched_text, all_ocr_text, car_confidence, snapshot_url)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (datetime.now(timezone.utc).isoformat(), date.today().isoformat(),
             event_id, "my_vehicle", 0, "phash-match", "", car_confidence, snapshot_url)
        )
        conn.commit()
        client.publish("vehicles/my_vehicle", json.dumps({
            "event_id": event_id, "category": "my_vehicle",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))
        return

    img         = preprocess(img)
    ocr_results         = run_ocr(img)
    all_text            = " | ".join(text for _, text, _ in ocr_results)
    category, matched_text = classify_vehicle(ocr_results)
    is_ce               = category == "code_enforcement"

    conn.execute(
        """INSERT INTO detections
           (timestamp, date, event_id, category, is_code_enforcement, matched_text, all_ocr_text, car_confidence, snapshot_url)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (datetime.now(timezone.utc).isoformat(), date.today().isoformat(),
         event_id, category, int(is_ce), matched_text, all_text, car_confidence, snapshot_url)
    )
    conn.commit()

    publish(client, conn, category, matched_text, all_text, car_confidence, event_id, snapshot_url)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        log.info(f"Connected to MQTT {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe("frigate/events")
    else:
        log.error(f"MQTT connect failed rc={rc}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    conn = init_db(DB_PATH)
    log.info(f"DB at {DB_PATH} — watching {CAMERA}/{ZONE} on {FRIGATE_URL}")

    client = mqtt.Client(client_id=MQTT_CLIENT_ID, userdata={"conn": conn})
    if MQTT_PASSWORD:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_forever()


if __name__ == "__main__":
    main()
