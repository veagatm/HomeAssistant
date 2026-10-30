#!/bin/bash
export HOME=/Users/homeuser
export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin

LOG=/Users/homeuser/frigate/autostart.log
echo "$(date): Boot sequence started" >> "$LOG"

# If an external drive is configured, wait for it to mount (up to 60s)
MEDIA_PATH=$(grep -E '^FRIGATE_MEDIA_PATH=' /Users/homeuser/frigate/.env | cut -d= -f2)
if [[ "$MEDIA_PATH" == /Volumes/* ]]; then
    echo "$(date): Waiting for external drive at $MEDIA_PATH..." >> "$LOG"
    elapsed=0
    while [ ! -d "$MEDIA_PATH" ] && [ $elapsed -lt 60 ]; do
        sleep 3
        elapsed=$((elapsed + 3))
    done
    if [ ! -d "$MEDIA_PATH" ]; then
        echo "$(date): WARNING: External drive not found after 60s — creating fallback dir and continuing" >> "$LOG"
        mkdir -p "$MEDIA_PATH" 2>/dev/null || true
    else
        echo "$(date): External drive ready" >> "$LOG"
    fi
fi

# Start Colima if not already running
if /opt/homebrew/bin/colima status 2>/dev/null | grep -q "Running"; then
    echo "$(date): Colima already running" >> "$LOG"
else
    echo "$(date): Starting Colima..." >> "$LOG"
    /opt/homebrew/bin/colima start
fi

# Wait for Docker daemon to be ready
echo "$(date): Waiting for Docker daemon..." >> "$LOG"
until /opt/homebrew/bin/docker info > /dev/null 2>&1; do
    sleep 3
done

# Bring up the Frigate stack
echo "$(date): Starting Frigate stack..." >> "$LOG"
cd /Users/homeuser/frigate
/opt/homebrew/bin/docker compose up -d
echo "$(date): Done" >> "$LOG"
