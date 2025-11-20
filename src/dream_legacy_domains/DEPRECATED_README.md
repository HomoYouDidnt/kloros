# DEPRECATED: Hardware Optimization Domain Evaluators

**Date**: 2025-10-20
**Status**: DEPRECATED - DO NOT USE

## Why Deprecated

These domain evaluators were part of a **misaligned implementation** of D-REAM that focused on hardware optimization (CPU governors, GPU settings, RAM timings, etc.) rather than the ASTRAEA-specified training data admission system.

## What Was Wrong

The original implementation:
- ❌ Used hardware benchmarks (stress-ng, sysbench, stressapptest) - BANNED utilities
- ❌ Optimized CPU/GPU/Memory/Storage/Power/Scheduler settings
- ❌ Had ZERO relation to training data admission, frozen judges, or KL divergence
- ❌ Created confusion by claiming to be "D-REAM" while doing hardware tuning

## The Correct D-REAM System

The **ASTRAEA-compliant D-REAM** training data admission system exists at:
- `/home/kloros/src/dream/admit.py` - Judge and admit with frozen evaluators
- `/home/kloros/src/dream/judges/frozen.py` - Frozen judges
- `/home/kloros/src/dream/mix.py` - 40% synthetic ratio enforcement
- `/home/kloros/src/dream/kl_anchor.py` - KL divergence personality preservation
- `/home/kloros/src/dream/diversity_metrics.py` - Diversity enforcement
- `/home/kloros/src/phase/hooks.py` - PHASE → D-REAM integration

## Deprecated Files

The following hardware optimization evaluators are **DEPRECATED**:
- `cpu_domain_evaluator.py` - CPU governor/SMT/affinity tuning
- `gpu_domain_evaluator.py` - GPU frequency/memory tuning
- `memory_domain_evaluator.py` - RAM timing/swappiness tuning
- `storage_domain_evaluator.py` - I/O scheduler/readahead tuning
- `power_thermal_domain_evaluator.py` - Power management tuning
- `os_scheduler_domain_evaluator.py` - Linux scheduler tuning

## Correct Domain Evaluators (Still Active)

These domain evaluators are **VALID** and aligned with ASTRAEA:
- `/home/kloros/src/dream/domains/conversation_domain_evaluator.py` - TTS quality
- `/home/kloros/src/dream/domains/asr_tts_domain_evaluator.py` - Speech recognition
- `/home/kloros/src/dream/domains/audio_domain_evaluator.py` - Audio processing
- `/home/kloros/src/dream/domains/rag_context_domain_evaluator.py` - RAG quality

These evaluate **KLoROS voice/reasoning quality**, not hardware.

## Do Not Use

If you need hardware optimization, use system configuration tools - not D-REAM.

D-REAM is a **training data admission system** with frozen judges and safety gates.
