#!/usr/bin/env bash
# Graceful process termination with CUDA cleanup
# Usage: ./graceful_kill.sh <PID> [GPU_ID]

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <PID> [GPU_ID]"
    exit 1
fi

PID="$1"
GPU="${2:-0}"

# Check if process exists
if ! kill -0 "$PID" 2>/dev/null; then
    echo "Process $PID not found or already terminated"
    exit 0
fi

echo "Gracefully terminating process $PID..."

# Send SIGTERM for graceful shutdown
kill -TERM "$PID" || true

# Wait for process to exit (up to 9 seconds)
for i in {1..30}; do
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "Process $PID terminated gracefully"
        break
    fi
    sleep 0.3
done

# Wait for VRAM to drain (up to 10 seconds)
echo "Waiting for GPU memory cleanup..."
for i in {1..40}; do
    USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i "$GPU" 2>/dev/null || echo 0)
    if [ "$USED" -lt 500 ]; then
        echo "GPU memory cleaned up (${USED}MB remaining)"
        break
    fi
    sleep 0.25
done

# Last resort - force kill if still running
if kill -0 "$PID" 2>/dev/null; then
    echo "Process $PID not responding, force killing..."
    kill -KILL "$PID" || true
    sleep 1
fi

echo "Termination complete"
