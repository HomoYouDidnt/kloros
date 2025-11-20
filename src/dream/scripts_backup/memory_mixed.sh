#!/bin/bash
DURATION=${1:-90}
stress-ng --vm 4 --vm-bytes 2G --timeout ${DURATION}s --metrics-brief --yaml /tmp/stress_ng_output.yaml
grep -m1 "bogo-ops-per-second-real-time:" /tmp/stress_ng_output.yaml | awk '{print $2}' || echo "0"
