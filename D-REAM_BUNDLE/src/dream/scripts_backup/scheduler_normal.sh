#!/bin/bash
# D-REAM OS Scheduler Normal Workload
# Typical multi-process activity

DURATION=${1:-30}

ops=0
start=$SECONDS

while [ $((SECONDS - start)) -lt $DURATION ]; do
    # Spawn light processes
    for i in {1..4}; do
        (sleep 0.1; echo $$) >/dev/null 2>&1 &
    done
    
    # Measure context switches
    cat /proc/stat | grep ^ctxt >/dev/null 2>&1
    ops=$((ops + 1))
    
    wait
    sleep 1
done

# Return ops per second
echo "scale=2; $ops / $DURATION" | bc
