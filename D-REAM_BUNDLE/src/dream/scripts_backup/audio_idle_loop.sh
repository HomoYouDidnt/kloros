#!/bin/bash
# D-REAM Audio Idle Workload
# Minimal audio activity - just monitor PipeWire status

DURATION=${1:-20}

start=$SECONDS
queries=0

while [ $((SECONDS - start)) -lt $DURATION ]; do
    # Light query of audio system
    pactl info >/dev/null 2>&1 && queries=$((queries + 1))
    sleep 0.5
done

# Return queries per second
echo "scale=2; $queries / $DURATION" | bc
