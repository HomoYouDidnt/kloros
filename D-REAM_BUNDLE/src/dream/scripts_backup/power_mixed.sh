#!/bin/bash
# D-REAM Power/Thermal Mixed Workload
# Varying load patterns with thermal monitoring

DURATION=${1:-60}

start=$SECONDS
cycles=0

while [ $((SECONDS - start)) -lt $DURATION ]; do
    # Cycle: burst → idle → sustained
    
    # Burst (5s)
    stress-ng --cpu 0 --timeout 5s >/dev/null 2>&1 &
    burst_pid=$!
    sensors >/dev/null 2>&1
    wait $burst_pid 2>/dev/null
    
    # Idle (3s)
    sleep 3
    sensors >/dev/null 2>&1
    
    # Sustained (7s)
    stress-ng --cpu 4 --timeout 7s >/dev/null 2>&1 &
    sustained_pid=$!
    sensors >/dev/null 2>&1
    wait $sustained_pid 2>/dev/null
    
    cycles=$((cycles + 1))
done

# Return cycles per minute
echo "scale=2; $cycles * 60 / $DURATION" | bc
