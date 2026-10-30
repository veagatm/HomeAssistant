# Frigate stack (Mac Mini M1)

Mirror of `~/frigate` on the Mac Mini, pulled by `tools/sync.py`. Edit the files there, not
here, then re-sync. The full design history (and the abandoned CompreFace/Double Take pipeline)
is in [`../cameras/plan.md`](../cameras/plan.md).

## Runtime

```
Reolink cameras ──RTSP──▶ Frigate (Docker on Colima, CPU detector, 6 CPU / 10 GB VM)
  front     CX810            │  detect on sub-stream, record main stream
  backyard  RLC-1212A        │  face recognition (built-in), zones, masks
  front_floodlight  Duo      ▼
                       MQTT  frigate/events ──▶ Mosquitto on HA Green ──▶ HA Frigate integration
                             │                                             (cameras, sensors, alerts)
                             ├──▶ code-enforcement            OCR on street-zone cars → MQTT alert
                             ├──▶ code-enforcement-floodlight  same image, second camera/zone
                             ├──▶ bird-tracker                 feeder visits → SQLite → daily stats
                             └──▶ vehicle-dashboard (:8501)    Streamlit review of OCR detections
```

| Service | Port | Notes |
|---|---|---|
| `frigate` | 5050 (UI; 5000 is taken by macOS AirPlay), 8554 RTSP restream, 8555 WebRTC | `config/config.yml` |
| `code-enforcement`, `code-enforcement-floodlight` | — | share one SQLite volume; MQTT client IDs must differ or they kick each other offline |
| `vehicle-dashboard` | 8501 | reads the code-enforcement DB |
| `bird-tracker` | — | watches the `bird_feeder` zone on `backyard` |
| `reid-service` (`../reid`) | — | street-camera re-ID; crash-loops until that camera exists |

## Boot & config push

- `autostart.sh` (login): waits for the external media drive, starts Colima, then
  `docker compose up -d`.
- `start-frigate.sh` (`com.frigate.startup` LaunchAgent, at login and every 5 min) brings Frigate
  up if it's down and **pipes `config.yml` into the container**. Colima's virtiofs mount can serve
  a stale copy of host-edited files on a fresh VM, so the config is pushed rather than trusted to
  the bind mount.

## Credentials

Nothing secret is in these files. `docker-compose.yml` maps `.env` values (see `.env.example`)
into `FRIGATE_*` variables, which `config.yml` references as `{FRIGATE_FRONT_PASS}` etc. The
real `.env` stays on the Mac Mini and is gitignored.

## Tuning notes worth knowing

- Masks and zones carry dated comments explaining each change: static bins, a parked trailer and
  a tree base misread as people or cars. Read those before redrawing anything.
- `front_floodlight` is a dual-lens panoramic (7680×2160 main, 1536×432 detect); coordinates
  from `front` don't transfer.
- `preset-rtsp-restream` (forced TCP) is required for CX810 stream stability.
