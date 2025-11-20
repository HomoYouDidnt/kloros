#!/usr/bin/env bash
# Safe kill for CUDA processes - ensures VRAM drains properly
set -euo pipefail

PID="${1:?PID required}"
GPU="${2:-0}"

echo "=== Safe Kill for PID $PID ==="

# Check if process exists
if ! kill -0 "$PID" 2>/dev/null; then
    echo "✅ Process $PID already dead"
    exit 0
fi

echo "📋 Process info:"
ps -p "$PID" -o pid,ppid,user,command --no-headers || echo "Process info unavailable"

# Graceful termination first
echo "🛑 Sending SIGTERM to $PID..."
kill -TERM "$PID" 2>/dev/null || true

# Wait for process exit (up to 9 seconds)
echo "⏳ Waiting for process exit..."
for i in {1..30}; do
    if ! kill -0 "$PID" 2>/dev/null; then 
        echo "✅ Process exited gracefully"
        break
    fi
    sleep 0.3
done

# Wait for CUDA context to vanish (up to 10 seconds)
has_ctx() {
    nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -q "^$PID$"
}

if has_ctx; then
    echo "⏳ Waiting for CUDA context to release..."
    for i in {1..40}; do
        has_ctx || break
        sleep 0.25
    done
    
    if has_ctx; then
        echo "⚠️  CUDA context still held after 10s"
    else
        echo "✅ CUDA context released"
    fi
fi

# Last resort SIGKILL
if kill -0 "$PID" 2>/dev/null; then 
    echo "💀 Force killing $PID..."
    kill -KILL "$PID" || true
fi

echo "=== Safe Kill Complete ==="
