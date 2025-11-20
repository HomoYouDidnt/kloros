#!/bin/bash
# D-REAM Memory Idle Workload
# Minimal memory activity - just allocation/deallocation

DURATION=${1:-20}

stress-ng \
    --vm 1 \
    --vm-bytes 256M \
    --vm-method all \
    --timeout ${DURATION}s \
    --metrics-brief \
    --yaml /tmp/stress_ng_output.yaml

# Parse throughput
if [ -f /tmp/stress_ng_output.yaml ]; then
    grep -m1 "bogo-ops-per-second-real-time:" /tmp/stress_ng_output.yaml | \
        awk '{print $2}'
else
    echo "0"
fi
