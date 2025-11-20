#!/bin/bash
# D-REAM GPU Matrix Multiplication Stress Test
# Heavy compute workload using real PyTorch matmul on GPU (bounded)

DURATION=${1:-30}

python3 << PYEOF
import time
import json
import sys

try:
    import torch
except ImportError:
    # Graceful fallback if PyTorch not available
    print(json.dumps({
        "error": "pytorch_unavailable",
        "functional": False,
        "throughput_gflops": 0.0
    }))
    sys.exit(0)

duration = $DURATION
matrix_size = 2048  # Bounded: 2048x2048 matrix (reasonable GPU load)
start = time.time()
ops = 0
total_flops = 0

# Check GPU availability
if not torch.cuda.is_available():
    print(json.dumps({
        "error": "cuda_unavailable",
        "functional": False,
        "throughput_gflops": 0.0
    }))
    sys.exit(0)

device = torch.device('cuda:0')

# Preallocate matrices (bounded memory)
try:
    A = torch.randn(matrix_size, matrix_size, device=device)
    B = torch.randn(matrix_size, matrix_size, device=device)
except RuntimeError as e:
    print(json.dumps({
        "error": "gpu_oom",
        "details": str(e),
        "functional": False,
        "throughput_gflops": 0.0
    }))
    sys.exit(0)

while time.time() - start < duration:
    try:
        # Real matrix multiplication on GPU
        C = torch.matmul(A, B)
        torch.cuda.synchronize()  # Wait for GPU to finish

        # Count FLOPs: 2 * N^3 for NxN matmul
        flops = 2 * (matrix_size ** 3)
        total_flops += flops
        ops += 1

        # Small gap to prevent thermal throttling (0.1s)
        time.sleep(0.1)
    except RuntimeError as e:
        # GPU error occurred
        print(json.dumps({
            "error": "gpu_runtime_error",
            "details": str(e),
            "functional": False,
            "ops_completed": ops,
            "throughput_gflops": 0.0
        }))
        sys.exit(1)

elapsed = time.time() - start

# Calculate throughput in GFLOPS
gflops = (total_flops / elapsed) / 1e9 if elapsed > 0 else 0.0

# Structured output
print(json.dumps({
    "throughput_gflops": round(gflops, 2),
    "ops_completed": ops,
    "matrix_size": matrix_size,
    "elapsed_seconds": round(elapsed, 2),
    "functional": ops > 0
}))
PYEOF
