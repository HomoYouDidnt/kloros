#!/bin/bash
# D-REAM Power/Thermal Normal Workload
# Typical system load with power monitoring

DURATION=${1:-30}

# Light CPU load + power measurement
start=$SECONDS
measurements=0

while [ $((SECONDS - start)) -lt $DURATION ]; do
    # Light stress + measure power
    stress-ng --cpu 2 --timeout 2s >/dev/null 2>&1 &
    stress_pid=$!
    
    # Monitor power during load
    if command -v sensors >/dev/null 2>&1; then
        sensors | grep -E "power|Watt" >/dev/null 2>&1
        measurements=$((measurements + 1))
    fi
    
    wait $stress_pid 2>/dev/null
    sleep 1
done

# Return measurements per second
echo "scale=3; $measurements / $DURATION" | bc
