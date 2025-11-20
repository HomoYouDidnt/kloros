#!/bin/bash
# D-REAM OS Scheduler Idle Workload
# Minimal scheduling activity

DURATION=${1:-20}

samples=0
start=$SECONDS

while [ $((SECONDS - start)) -lt $DURATION ]; do
    # Check scheduler stats
    cat /proc/schedstat >/dev/null 2>&1 && samples=$((samples + 1))
    sleep 0.5
done

# Return samples per second
echo "scale=2; $samples / $DURATION" | bc
