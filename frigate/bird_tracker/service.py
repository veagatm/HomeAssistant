#!/usr/bin/env python3
"""
Bird Tracker — listens to frigate/events MQTT, logs bird sightings to SQLite,
and publishes daily stats + alerts back to MQTT for HA dashboard consumption.
"""

import json
import sqlite3
import os
import logging
from datetime import datetime, date, timezone

import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('bird-tracker')

MQTT_HOST     = os.getenv('MQTT_HOST', '192.168.68.3')
MQTT_PORT     = int(os.getenv('MQTT_PORT', '1883'))
MQTT_USER     = os.getenv('MQTT_USER', 'addons')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD', '')
DB_PATH       = os.getenv('DB_PATH', '/data/birds.db')
CAMERA        = os.getenv('FRIGATE_CAMERA', 'backyard')
ZONE          = os.getenv('FRIGATE_ZONE', 'bird_feeder')
FRIGATE_URL   = os.getenv('FRIGATE_URL', 'http://192.168.68.142:5050')


# ── Database ──────────────────────────────────────────────────────────────────

def init_db(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sightings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT NOT NULL,
            date         TEXT NOT NULL,
            species      TEXT NOT NULL,
            confidence   REAL,
            event_id     TEXT,
            snapshot_url TEXT
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_date    ON sightings(date)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_species ON sightings(species)')
    conn.commit()
    return conn


def is_first_ever(conn, species):
    return conn.execute(
        'SELECT COUNT(*) FROM sightings WHERE species=?', (species,)
    ).fetchone()[0] == 0


def is_first_today(conn, species):
    today = date.today().isoformat()
    return conn.execute(
        'SELECT COUNT(*) FROM sightings WHERE species=? AND date=?', (species, today)
    ).fetchone()[0] == 0


def today_stats(conn):
    today = date.today().isoformat()
    rows = conn.execute(
        'SELECT species, COUNT(*) FROM sightings WHERE date=? GROUP BY species ORDER BY COUNT(*) DESC',
        (today,)
    ).fetchall()
    species_list = [{'species': r[0], 'count': r[1]} for r in rows]
    total  = sum(r['count'] for r in species_list)
    unique = len(species_list)
    return total, unique, species_list


def lifetime_unique(conn):
    return conn.execute('SELECT COUNT(DISTINCT species) FROM sightings').fetchone()[0]


# ── MQTT publishing ───────────────────────────────────────────────────────────

def publish_stats(client, conn, species, snapshot_url):
    total, unique, species_list = today_stats(conn)
    lifetime = lifetime_unique(conn)

    client.publish('birds/today/total',   str(total),                  retain=True)
    client.publish('birds/today/unique',  str(unique),                 retain=True)
    client.publish('birds/today/list',    json.dumps(species_list),    retain=True)
    client.publish('birds/last/species',  species,                     retain=True)
    client.publish('birds/last/time',     datetime.now(timezone.utc).isoformat(), retain=True)
    client.publish('birds/lifetime/unique', str(lifetime),             retain=True)

    log.info(f'Stats published — today: {total} sightings / {unique} species | lifetime: {lifetime} species')


# ── Event handler ─────────────────────────────────────────────────────────────

def on_message(client, userdata, msg):
    conn = userdata['conn']
    try:
        payload = json.loads(msg.payload)
    except Exception:
        return

    if payload.get('type') != 'end':
        return

    after = payload.get('after', {})
    if after.get('camera') != CAMERA or after.get('label') != 'bird':
        return
    if ZONE not in after.get('current_zones', []):
        return

    species    = after.get('sub_label') or 'Unknown Bird'
    event_id   = after.get('id', '')
    data       = after.get('data') or {}
    confidence = data.get('top_score', 0) if isinstance(data, dict) else 0
    now        = datetime.now(timezone.utc)
    snapshot_url = f'{FRIGATE_URL}/api/events/{event_id}/snapshot.jpg'

    first_ever  = is_first_ever(conn, species)
    first_today = is_first_today(conn, species)

    conn.execute(
        'INSERT INTO sightings (timestamp, date, species, confidence, event_id, snapshot_url) VALUES (?,?,?,?,?,?)',
        (now.isoformat(), date.today().isoformat(), species, confidence, event_id, snapshot_url)
    )
    conn.commit()

    log.info(f'Logged: {species} conf={confidence:.2f} first_ever={first_ever} first_today={first_today}')

    publish_stats(client, conn, species, snapshot_url)

    # Alert: brand-new species never seen before
    if first_ever:
        client.publish('birds/alert/new_species', json.dumps({
            'species':      species,
            'confidence':   round(confidence, 3),
            'snapshot_url': snapshot_url,
            'timestamp':    now.isoformat(),
        }))
        log.info(f'NEW SPECIES ALERT: {species}')

    # Alert: first time today (quieter, for dashboard freshness)
    if first_today:
        client.publish('birds/alert/first_today', json.dumps({
            'species':      species,
            'snapshot_url': snapshot_url,
        }))


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        log.info(f'Connected to MQTT {MQTT_HOST}:{MQTT_PORT}')
        client.subscribe('frigate/events')
    else:
        log.error(f'MQTT connect failed rc={rc}')


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    conn = init_db(DB_PATH)
    log.info(f'DB ready at {DB_PATH} — watching {CAMERA}/{ZONE}')

    client = mqtt.Client(client_id='bird-tracker', userdata={'conn': conn})
    if MQTT_PASSWORD:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_forever()


if __name__ == '__main__':
    main()
