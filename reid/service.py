#!/usr/bin/env python3
"""
Re-ID Clustering Service
Street camera (CX810) → InsightFace face embeddings + EasyOCR vehicle text
→ FAISS cluster matching → MQTT publish to HA

MQTT topics published:
  reid/clusters/person/{id}/count
  reid/clusters/person/{id}/last_seen
  reid/vehicle/code_enforcement/last_seen
  reid/vehicle/code_enforcement/count
"""

import cv2
import json
import logging
import os
import time
from datetime import datetime

import numpy as np
import paho.mqtt.client as mqtt
from insightface.app import FaceAnalysis

from clusters import ClusterDB
from ocr import VehicleOCR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
RTSP_URL      = os.environ["RTSP_URL"]
MQTT_HOST     = os.environ.get("MQTT_HOST", "192.168.68.3")
MQTT_PORT     = int(os.environ.get("MQTT_PORT", 1883))
MQTT_USER     = os.environ.get("MQTT_USER", "addons")
MQTT_PASSWORD = os.environ["MQTT_PASSWORD"]
DB_PATH       = os.environ.get("DB_PATH", "/data/clusters.db")
THRESHOLD     = float(os.environ.get("FAISS_THRESHOLD", "0.6"))

# How often to sample frames (seconds) — 1 frame/sec is enough for street RE-ID
SAMPLE_INTERVAL = 1.0
# Minimum seconds between Code Enforcement alerts
CE_COOLDOWN = 300


class ReidService:
    def __init__(self):
        log.info("Initializing InsightFace (buffalo_l ArcFace)...")
        self.face_app = FaceAnalysis(name="buffalo_l")
        self.face_app.prepare(ctx_id=-1)  # CPU

        self.ocr = VehicleOCR()
        self.db = ClusterDB(DB_PATH, threshold=THRESHOLD)
        self.mqttc = self._connect_mqtt()
        self._ce_last_alert = 0.0

    def _connect_mqtt(self) -> mqtt.Client:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="reid-service")
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()
        log.info("MQTT connected to %s:%d", MQTT_HOST, MQTT_PORT)
        return client

    def _publish(self, topic: str, payload: dict):
        self.mqttc.publish(topic, json.dumps(payload), retain=True)

    def _process_frame(self, frame: np.ndarray):
        now = time.time()

        # ── Face detection + clustering ────────────────────────────────────────
        faces = self.face_app.get(frame)
        for face in faces:
            if face.embedding is None:
                continue
            result = self.db.match_or_create("person", face.embedding)
            cid = result["cluster_id"]
            self._publish(f"reid/clusters/person/{cid}/count", {"count": result["count"]})
            self._publish(f"reid/clusters/person/{cid}/last_seen", {
                "last_seen": datetime.utcnow().isoformat(),
                "new_cluster": result["new"],
            })
            if result["new"]:
                log.info("New person cluster #%d", cid)
            else:
                log.debug("Person cluster #%d — sighting %d (score %.2f)", cid, result["count"], result["score"])

        # ── Code Enforcement OCR scan ──────────────────────────────────────────
        if now - self._ce_last_alert > CE_COOLDOWN:
            if self.ocr.scan(frame):
                self._ce_last_alert = now
                result = self.db.match_or_create("vehicle", np.zeros(512), label="code_enforcement")
                self._publish("reid/vehicle/code_enforcement/last_seen", {
                    "last_seen": datetime.utcnow().isoformat(),
                    "count": result["count"],
                })
                self._publish("reid/vehicle/code_enforcement/count", {"count": result["count"]})
                log.info("Code Enforcement vehicle — sighting #%d", result["count"])

    def run(self):
        log.info("Opening RTSP stream: %s", RTSP_URL)
        # RTSP-over-TCP for CX810 stability
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
        cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            log.error("Failed to open stream — check RTSP_URL and camera connectivity")
            return

        last_sample = 0.0
        consecutive_failures = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                consecutive_failures += 1
                log.warning("Frame read failed (%d consecutive)", consecutive_failures)
                if consecutive_failures > 30:
                    log.error("Too many failures — reconnecting...")
                    cap.release()
                    time.sleep(5)
                    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
                    consecutive_failures = 0
                continue

            consecutive_failures = 0
            now = time.time()
            if now - last_sample < SAMPLE_INTERVAL:
                continue

            last_sample = now
            try:
                self._process_frame(frame)
            except Exception as e:
                log.exception("Frame processing error: %s", e)


if __name__ == "__main__":
    ReidService().run()
