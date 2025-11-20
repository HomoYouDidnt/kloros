#!/bin/bash
# D-REAM GPU Short Inference Bursts (Normal Load)
# Simulates typical inference workload

DURATION=${1:-30}

python3 << 'PYEOF'
import time
import subprocess
import sys

duration = int(sys.argv[1]) if len(sys.argv) > 1 else 30
start = time.time()
inferences = 0

while time.time() - start < duration:
    # Simulate inference by querying GPU state
    result = subprocess.run(
        ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used', 
         '--format=csv,noheader,nounits'],
        capture_output=True,
        text=True,
        timeout=2
    )
    if result.returncode == 0:
        inferences += 1
    time.sleep(0.5)  # Simulate inference gap

# Return inferences per second
throughput = inferences / duration
print(f"{throughput:.2f}")
PYEOF $DURATION
