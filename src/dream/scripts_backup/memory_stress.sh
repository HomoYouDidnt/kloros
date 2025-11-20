#!/bin/bash
# D-REAM Memory Stress Workload
# Heavy memory pressure - large allocations with intensive access patterns

DURATION=${1:-120}

stress-ng \
    --vm 8 \
    --vm-bytes 4G \
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
