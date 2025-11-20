# D-REAM Domain Evaluators

## Overview

Comprehensive system optimization framework for D-REAM that enables real hardware and software parameter tuning across multiple subsystems.

## Implemented Domains

### ✅ CPU Domain (`cpu_domain_evaluator.py`)
**Genome Knobs:**
- Core utilization (25-100% of cores)
- SMT enabled/disabled
- CPU governor selection (performance, schedutil, powersave)
- Thread count configuration
- Hugepages allocation
- EPP (Energy Performance Preference) if supported
- Turbo boost control

**Fitness Signals:**
- Throughput (ops/s) - weight: 0.4
- P95/P99 latency - weight: -0.2/-0.1
- Context switches - weight: -0.05
- Cache miss rate - weight: -0.1
- Watts per operation - weight: -0.15

**Safety Constraints:**
- CPU temp ≤ 90°C
- Package power ≤ 150W
- No thermal throttling
- CPU usage ≤ 95%

### ✅ GPU Domain (`gpu_domain_evaluator.py`)
**Genome Knobs:**
- Precision mode (fp32/fp16/int8)
- Batch size (1-32)
- CUDA streams (1-8)
- Context length (512-8192 tokens)
- Power limit (50-100% of max)
- Memory/GPU clock offsets
- CUDA graphs enabled/disabled

**Fitness Signals:**
- Tokens/s or iterations/s - weight: 0.4/0.2
- P95 latency - weight: -0.15
- SM occupancy - weight: 0.1
- VRAM headroom - weight: 0.05
- Joules per token - weight: -0.2

**Safety Constraints:**
- GPU temp ≤ 83°C
- Memory temp ≤ 95°C
- No ECC errors
- No VRAM OOM

### ✅ Audio Domain (`audio_domain_evaluator.py`)
**Genome Knobs:**
- Sample rate (22050-192000 Hz)
- Buffer size (64-4096 samples)
- Period size (32-1024 samples)
- Quantum (PipeWire)
- Resampler algorithm
- Thread priority
- Echo cancellation

**Fitness Signals:**
- Round-trip latency - weight: -0.4
- Xruns per hour - weight: -0.3
- SNR (dB) - weight: 0.15
- THD (%) - weight: -0.1

**Safety Constraints:**
- Xruns ≤ 6 per hour
- Audio CPU ≤ 30%
- RTL ≤ 50ms

## Usage

Run single domain optimization:
```bash
python3 /home/kloros/src/dream/domains/dream_domain_integration.py --domain cpu
```

Run as background service:
```bash
python3 /home/kloros/src/dream/domains/dream_domain_integration.py --daemon
```

## Results

Results stored in:
- `/home/kloros/src/dream/artifacts/domain_telemetry/`
- `/home/kloros/src/dream/artifacts/domain_results/`
