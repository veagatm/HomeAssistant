#!/bin/bash
# Starts Frigate after Colima/Docker is ready and re-pushes config
# to work around Colima virtiofs caching on fresh VM start.
# Registered as com.frigate.startup LaunchAgent (runs at login + every 5 min).

DOCKER=/opt/homebrew/bin/docker
COMPOSE_DIR="/Users/homeuser/frigate"
LOG="/tmp/frigate-start.log"

echo "[$(date)] Frigate watchdog check" >> "$LOG"

# Wait for Docker socket to be available (Colima may not be ready at login)
for i in $(seq 1 30); do
    if "$DOCKER" info &>/dev/null; then
        break
    fi
    sleep 2
done

if ! "$DOCKER" info &>/dev/null; then
    echo "[$(date)] ERROR: Docker not available after 60s, skipping" >> "$LOG"
    exit 1
fi

# Bring Frigate up (idempotent — no-op if already running)
cd "$COMPOSE_DIR"
"$DOCKER" compose up -d frigate >> "$LOG" 2>&1

# If Frigate just started (not already running), push the config
sleep 8
if "$DOCKER" ps --filter name=^frigate$ --filter status=running -q | grep -q .; then
    cat "$COMPOSE_DIR/config/config.yml" | "$DOCKER" exec -i frigate tee /config/config.yaml > /dev/null \
        && echo "[$(date)] Config pushed OK" >> "$LOG" \
        || echo "[$(date)] WARNING: Config push failed" >> "$LOG"
fi

# Keep bird-tracker running alongside Frigate
"$DOCKER" compose up -d bird-tracker >> "$LOG" 2>&1
