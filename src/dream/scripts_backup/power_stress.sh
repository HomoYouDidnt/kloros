#!/bin/bash
# D-REAM Power/Thermal Stress Workload
# Maximum power draw test

DURATION=${1:-60}

# Heavy load + continuous power monitoring
start=$SECONDS
measurements=0

# Start sustained stress in background
stress-ng --cpu 0 --timeout ${DURATION}s >/dev/null 2>&1 &
stress_pid=$!

# Monitor power continuously
while [ $((SECONDS - start)) -lt $DURATION ] && kill -0 $stress_pid 2>/dev/null; do
    # Check thermal and power
    sensors 2>/dev/null | grep -qE "temp|power" && measurements=$((measurements + 1))
    sleep 0.5
done

# Cleanup
kill $stress_pid 2>/dev/null
wait $stress_pid 2>/dev/null

# Return measurements per second
echo "scale=2; $measurements / $DURATION" | bc
