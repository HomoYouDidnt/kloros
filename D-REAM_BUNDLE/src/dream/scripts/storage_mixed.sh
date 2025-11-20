#!/bin/bash
# D-REAM Storage Mixed Workload
# Random read/write patterns with varying block sizes

DURATION=${1:-60}
TMPDIR=${TMPDIR:-/tmp}
TEST_FILE="$TMPDIR/dream_storage_mixed_$$"

# Use dd for real I/O operations
ops=0
start=$SECONDS
total_bytes=0

while [ $((SECONDS - start)) -lt $DURATION ]; do
    # Random block size (4K, 64K, 1M)
    block_sizes=(4 64 1024)
    bs=${block_sizes[$((RANDOM % 3))]}
    count=$((RANDOM % 10 + 1))
    
    # Write test
    dd if=/dev/zero of="$TEST_FILE" bs=${bs}k count=$count conv=fdatasync 2>/dev/null
    bytes_written=$((bs * count * 1024))
    total_bytes=$((total_bytes + bytes_written))
    
    # Read test
    dd if="$TEST_FILE" of=/dev/null bs=${bs}k 2>/dev/null
    total_bytes=$((total_bytes + bytes_written))
    
    ops=$((ops + 1))
    sleep 0.1
done

rm -f "$TEST_FILE"

# Return MB/s throughput
elapsed=$((SECONDS - start))
mb_total=$((total_bytes / 1024 / 1024))
echo "scale=2; $mb_total / $elapsed" | bc
