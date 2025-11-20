#!/bin/bash
# D-REAM OS Scheduler Stress Workload
# Heavy context switching load

DURATION=${1:-60}

# Use stress-ng context stressor
stress-ng --context 0 --timeout ${DURATION}s --metrics-brief --yaml /tmp/stress_ng_scheduler_$$.yaml >/dev/null 2>&1

# Parse context switches
if [ -f /tmp/stress_ng_scheduler_$$.yaml ]; then
    switches=$(grep -m1 "bogo-ops-per-second-real-time:" /tmp/stress_ng_scheduler_$$.yaml | awk '{print $2}')
    rm -f /tmp/stress_ng_scheduler_$$.yaml
    echo "${switches:-0}"
else
    echo "0"
fi
