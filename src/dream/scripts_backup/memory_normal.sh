#!/bin/bash
# D-REAM Memory Normal Workload
# Typical memory operations - moderate allocation and access

DURATION=${1:-30}

stress-ng \
    --vm 2 \
    --vm-bytes 1G \
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
