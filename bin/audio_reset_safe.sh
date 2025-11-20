#!/usr/bin/env bash
# Safe audio state reset for KLoROS
# Only restarts PipeWire when no processes are holding /dev/snd/*

set -euo pipefail

echo "=== KLoROS Safe Audio Reset ==="

# Check if any processes are using audio devices
if lsof -nP /dev/snd/* 2>/dev/null | grep -q . ; then
    echo "❌ Audio devices busy; not restarting PipeWire."
    echo "Active audio processes:"
    lsof -nP /dev/snd/* 2>/dev/null
    exit 1
fi

echo "✅ Audio devices idle - safe to restart PipeWire"

# Ensure we're operating as kloros user with correct runtime dir
if [ "$(id -u)" != "1001" ]; then
    echo "❌ Must run as kloros user (UID 1001)"
    exit 1
fi

export XDG_RUNTIME_DIR="/run/user/1001"

if [ ! -w "$XDG_RUNTIME_DIR" ]; then
    echo "❌ Runtime directory not writable: $XDG_RUNTIME_DIR"
    exit 1
fi

echo "✅ Environment validated - restarting PipeWire services"

# Restart PipeWire stack
systemctl --user restart wireplumber pipewire pipewire-pulse

# Wait for services to come up
sleep 2

# Verify connection
if pactl info > /dev/null 2>&1; then
    echo "✅ PipeWire restart successful - audio ready"
    pactl info | head -8
else
    echo "❌ PipeWire restart failed - connection refused"
    exit 1
fi

echo "=== Audio Reset Complete ==="
