#!/bin/bash
# D-REAM GPU Mixed Workload
# Combines bursts and sustained load

DURATION=${1:-60}

python3 << 'PYEOF'
import time
import subprocess
import sys
import random

duration = int(sys.argv[1]) if len(sys.argv) > 1 else 60
start = time.time()
ops = 0

while time.time() - start < duration:
    # Random between quick query and sustained load
    if random.random() < 0.3:
        # Burst: quick queries
        subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu', 
                       '--format=csv,noheader'], capture_output=True, timeout=1)
        time.sleep(0.1)
    else:
        # Sustained: full query
        subprocess.run(['nvidia-smi', '-q'], capture_output=True, timeout=2)
        time.sleep(0.5)
    ops += 1

throughput = ops / duration
print(f"{throughput:.2f}")
PYEOF $DURATION
