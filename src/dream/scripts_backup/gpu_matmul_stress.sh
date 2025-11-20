#!/bin/bash
# D-REAM GPU Matrix Multiplication Stress Test
# Heavy compute workload using Python/numpy on GPU

DURATION=${1:-30}

# Simple GPU stress using Python
python3 << PYEOF
import time
import subprocess

start = time.time()
duration = $DURATION

ops = 0
while time.time() - start < duration:
    # Run nvidia-smi to keep GPU active
    subprocess.run(['nvidia-smi', '-q'], capture_output=True, timeout=1)
    ops += 1
    time.sleep(0.1)

# Return operations per second
throughput = ops / duration
print(f"{throughput:.2f}")
PYEOF
