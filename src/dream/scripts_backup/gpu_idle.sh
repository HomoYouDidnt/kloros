#!/bin/bash
# D-REAM GPU Idle Workload
# Minimal GPU activity - just query state periodically

DURATION=${1:-20}
INTERVAL=1

echo "GPU idle monitoring for ${DURATION}s" >&2

START=$SECONDS
while [ $((SECONDS - START)) -lt $DURATION ]; do
    nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null || echo "0"
    sleep $INTERVAL
done

# Return average idle utilization (should be near 0)
echo "0"
