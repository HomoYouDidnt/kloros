#!/bin/bash
# D-REAM CPU Mixed Workload
# Combines compute, memory, and context switching stressors

DURATION=${1:-90}

# Run stress-ng with mixed stressors
stress-ng \
    --cpu 0 \
    --vm 2 \
    --vm-bytes 1G \
    --context 4 \
    --timeout ${DURATION}s \
    --metrics-brief \
    --yaml /tmp/stress_ng_output.yaml

# Parse throughput from output
if [ -f /tmp/stress_ng_output.yaml ]; then
    # Extract bogo-ops-per-second-real-time from the first stressor
    grep -m1 "bogo-ops-per-second-real-time:" /tmp/stress_ng_output.yaml | \
        awk '{print $2}'
else
    echo "0"
fi
