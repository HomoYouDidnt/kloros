#!/bin/bash
# D-REAM Storage Idle Workload
# Minimal I/O - just metadata operations

DURATION=${1:-20}
TMPDIR=${TMPDIR:-/tmp}
TEST_FILE="$TMPDIR/dream_storage_idle_$$"

ops=0
start=$SECONDS

while [ $((SECONDS - start)) -lt $DURATION ]; do
    # Light metadata operations
    touch "$TEST_FILE" 2>/dev/null
    stat "$TEST_FILE" >/dev/null 2>&1
    rm -f "$TEST_FILE" 2>/dev/null
    ops=$((ops + 1))
    sleep 0.5
done

# Return ops per second
echo "scale=2; $ops / $DURATION" | bc
