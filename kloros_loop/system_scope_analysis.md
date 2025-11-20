# KLoROS System Scope Analysis

## What Documentation Says D-REAM Domain Evaluators Are

According to `/home/kloros/src/dream/domains/DREAM_DOMAINS_COMPLETE.md`:

**Purpose:** "Evolutionary optimization system that enables real hardware and software parameter tuning across multiple subsystems"

**The 8 Domain Evaluators:**
1. CPU Domain - optimize governors, SMT, turbo, threads
2. GPU Domain - optimize precision, batch size, CUDA streams  
3. Audio Domain - optimize sample rates, buffers, quantum
4. Memory Domain - optimize DDR5 timings, frequencies
5. Storage Domain - optimize I/O schedulers, queue depths
6. ASR/TTS Domain - optimize Whisper/TTS models
7. Power/Thermal Domain - optimize power limits, fan curves
8. OS/Scheduler Domain - optimize kernel scheduler, NUMA

**How They Work:**
- Generate random "genome" (array of parameters)
- Apply configuration to system
- Run benchmarks (stress-ng, sysbench, STREAM, etc.)
- Measure fitness
- Evolve toward optimal configuration

## The Problem

**These are HARDWARE OPTIMIZATION tools, not AI/conversation tools.**

They were designed to:
- Tune RAM timings
- Optimize CPU governors  
- Adjust fan curves
- Find best GPU power limits

They are NOT for optimizing KLoROS conversation quality or voice response.

## Why They Violate D-REAM Doctrine

Documentation explicitly states they use:
- stress-ng (BANNED)
- sysbench (BANNED)
- STREAM (BANNED - just removed)
- mbw (BANNED)
- stressapptest (BANNED)

These are **synthetic benchmarks** that create artificial load to measure
hardware performance. This violates anti-fabrication doctrine:
- Not real workloads
- Generate fake metrics
- Equivalent to "simulated" success

## What Belongs in KLoROS Spec

According to loop.yaml, D-REAM should be:
- Running real workload evaluations
- Measuring actual system behavior
- Using bounded, observable metrics

The domain evaluators optimize HARDWARE, not AI behavior.

## Recommendation

The domain evaluators appear to be:
1. Outside the scope of KLoROS (hardware tuning, not AI)
2. Violate anti-fabrication doctrine (synthetic benchmarks)
3. Not referenced in capabilities.yaml clearly
4. Create confusion about system purpose

**Question:** Should hardware optimization even be part of KLoROS?
Or is KLoROS purely about AI voice assistant optimization?
