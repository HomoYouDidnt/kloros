#!/bin/bash
# D-REAM Power/Thermal Idle Workload
# Minimal power draw - just sensor monitoring

DURATION=${1:-20}

samples=0
start=$SECONDS

while [ $((SECONDS - start)) -lt $DURATION ]; do
    # Read power/thermal sensors
    sensors >/dev/null 2>&1 && samples=$((samples + 1))
    sleep 1
done

# Return samples per second
echo "scale=2; $samples / $DURATION" | bc
