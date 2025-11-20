#!/bin/bash
# D-REAM OS Scheduler Mixed Workload
# Variable process loads

DURATION=${1:-60}

cycles=0
start=$SECONDS

while [ $((SECONDS - start)) -lt $DURATION ]; do
    # Burst phase - many short processes
    for i in {1..10}; do
        (sleep 0.05) &
    done
    wait
    
    # Sustained phase - fewer longer processes
    for i in {1..3}; do
        (sleep 1) &
    done
    wait
    
    # Measure scheduling activity
    cat /proc/schedstat >/dev/null 2>&1
    cycles=$((cycles + 1))
    
    sleep 0.5
done

# Return cycles per second
echo "scale=2; $cycles / $DURATION" | bc
