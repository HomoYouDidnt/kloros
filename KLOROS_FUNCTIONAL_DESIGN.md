# KLoROS Functional Design Document

**Version:** 1.3
**Date:** October 29, 2025 (Updated: November 3, 2025)
**Status:** Complete - Autonomous Self-Healing + Service Health Monitoring + Dashboard Integration
**Purpose:** Comprehensive functional description of KLoROS operation, covering individual processes and integrated system behavior

---

## Table of Contents

1. [Document Overview](#1-document-overview)
2. [System Architecture Summary](#2-system-architecture-summary)
3. [Individual Process Architecture](#3-individual-process-architecture)
4. [Integration Architecture](#4-integration-architecture)
5. [Data Flow Patterns](#5-data-flow-patterns)
6. [State Management](#6-state-management)
7. [Operational Workflows](#7-operational-workflows)
8. [System Timing and Coordination](#8-system-timing-and-coordination)
9. [Error Handling and Recovery](#9-error-handling-and-recovery)
10. [Performance Characteristics](#10-performance-characteristics)

---

## 1. Document Overview

### Purpose

This document describes **HOW** KLoROS operates, both as individual processes and as an integrated system. Unlike the System Audit (which documents WHAT exists and WHERE), this Functional Design explains operational behavior, data flows, integration patterns, and system interactions.

### Audience

- System architects reviewing integration patterns
- Developers implementing new features or domains
- Operators understanding system behavior
- Quality engineers designing test scenarios

### Scope

**Covered:**
- Functional operation of each major process
- Inter-process communication and integration
- Data flow through the system
- State management and persistence
- Timing, coordination, and synchronization
- Error handling and recovery patterns

**Not Covered:**
- Implementation details (see source code)
- Deployment procedures (see System Audit)
- Configuration reference (see config files)
- Historical design decisions (see architecture docs)

---

## 2. System Architecture Summary

### System Type

**Hybrid Evolutionary Optimization System with Voice Interface**

KLoROS combines:
1. **Real-time Voice Interaction** - Continuous user interaction loop
2. **Evolutionary Optimization** - Population-based genetic algorithm (D-REAM)
3. **Temporal Dilation Testing - Quantized intensive evaluation (PHASE))
4. **Continuous Improvement** - Tool synthesis and meta-repair

### Core Design Pattern: "Hyperbolic Time Chamber"

```
┌─────────────────────────────────────────────────────────────┐
│                    KLoROS System Architecture                │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────┐         ┌──────────────────┐          │
│  │   Voice Loop     │         │  D-REAM Engine   │          │
│  │   (Real-time)    │         │  (Slow/Evol)     │          │
│  │                  │         │                  │          │
│  │ STT→LLM→TTS      │         │ Population-based │          │
│  │ VAD→RAG→Memory   │         │ Evolution        │          │
│  │                  │         │ Consumes PHASE    │          │
│  └────────┬─────────┘         └────────┬─────────┘          │
│           │                            │                     │
│           │ Context                    │ Results             │
│           ↓                            ↓                     │
│  ┌─────────────────────────────────────────────────┐        │
│  │         Memory & RAG Integration                │        │
│  │  ChromaDB Vector Store + SQLite Episodes        │        │
│  └─────────────────────────────────────────────────┘        │
│           ↑                            ↑                     │
│           │ Knowledge                  │ Metrics             │
│           │                            │                     │
│  ┌────────┴─────────┐         ┌───────┴──────────┐         │
│  │  Tool Evolution  │         │  PHASE Engine    │         │
│  │  (ToolGen/       │◄────────┤  (Fast/Temporal)     │         │
│  │   RepairLab)     │ Repairs │                  │         │
│  │                  │         │  Hyperbolic Time    │         │
│  │  Synthesis       │         │  Chamber Testing   │         │
│  │  + Meta-repair   │         │  Quantized Bursts      │         │
│  └──────────────────┘         └──────────────────┘         │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              SPICA Foundation Layer                   │   │
│  │  Uniform interface for all test instances            │   │
│  │  Telemetry • Manifest • Lineage • Lifecycle          │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Key Architectural Principles

1. **Dual-Timescale Optimization**
   - Fast loop (PHASE): Temporal dilation, quantized intensive testing bursts
   - Slow loop (D-REAM): Evolutionary optimization consuming PHASE results
   - Results feed back to guide search space adaptation

2. **Separation of Concerns**
   - Voice: User interaction (standalone, always running)
   - D-REAM: Evolution engine (can run independently)
   - PHASE: Test orchestration (scheduled, isolated)
   - SPICA: Instance foundation (uniform interface)

3. **Loose Coupling via Data**
   - Systems communicate through structured files (JSONL, JSON)
   - No direct RPC or tight coupling
   - Enables independent operation and evolution

4. **Progressive Enhancement**
   - Core voice loop operates standalone
   - RAG enhances with context
   - Memory adds personalization
   - Evolution improves over time

---

## 3. Individual Process Architecture

This section describes HOW each major process operates in isolation, before integration.

---

### 3.1 Voice Loop (`src/kloros_voice.py`)

**Purpose:** Real-time voice interaction with hybrid STT, LLM reasoning, and TTS synthesis

**Process Type:** Single-threaded event loop with subprocess management

**Operational Mode:** Continuous (always running)

#### Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      Voice Loop Process                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  [1] Initialization Phase                                         │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ • Load audio device (auto-detect CMTECK or use env var)   │  │
│  │ • Detect sample rate (typically 48kHz)                     │  │
│  │ • Initialize Vosk model (~/kloros_models/vosk/model)       │  │
│  │ • Initialize Whisper model (medium, GPU if available)      │  │
│  │ • Initialize Piper TTS subprocess                          │  │
│  │ • Connect to Ollama (localhost:11434)                      │  │
│  │ • Load RAG bundle (if available)                           │  │
│  │ • Initialize memory DB (SQLite)                            │  │
│  │ • Load capability registry (self-awareness)                │  │
│  │ • Initialize MCP integration (tool introspection)          │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [2] Wake Word Detection Loop (Continuous)                        │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                                                             │  │
│  │  Audio Capture (16kHz, mono, blocking)                     │  │
│  │         ↓                                                   │  │
│  │  Energy Gate (RMS > KLR_WAKE_RMS_MIN)                      │  │
│  │         ↓                                                   │  │
│  │  Vosk Recognition (wake grammar only)                      │  │
│  │         ↓                                                   │  │
│  │  Fuzzy Match ("kloros" + variants)                         │  │
│  │         ↓                                                   │  │
│  │  Confidence Gate (> KLR_WAKE_CONF_MIN)                     │  │
│  │         ↓                                                   │  │
│  │  ✓ Wake Detected → Play Acknowledgment → Enter Turn Mode  │  │
│  │         ↓                                                   │  │
│  │  ✗ No Match → Continue Loop                                │  │
│  │                                                             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [3] Turn Processing (On Wake)                                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                                                             │  │
│  │  [3a] Audio Capture & VAD                                  │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ • Capture audio (max 30 seconds, timeout protection) │ │  │
│  │  │ • Two-stage VAD:                                      │ │  │
│  │  │   - Stage A: dBFS energy gate (-28 dBFS threshold)   │ │  │
│  │  │   - Stage B: Silero probability (0.60 threshold)     │ │  │
│  │  │ • Segment detection (attack=80ms, release=600ms)     │ │  │
│  │  │ • Select primary segment (prefer first or longest)   │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [3b] Hybrid STT (Vosk-Whisper)                            │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ • Vosk: Fast transcription (50-200ms latency)        │ │  │
│  │  │ • Whisper: Parallel high-accuracy (GPU-accelerated)  │ │  │
│  │  │ • Similarity scoring (RapidFuzz)                     │ │  │
│  │  │ • Confidence-based selection:                        │ │  │
│  │  │   - High similarity (>0.75): Use Whisper if higher   │ │  │
│  │  │   - Low similarity: Prefer higher confidence         │ │  │
│  │  │ • Adaptive threshold adjustment (memory-based)       │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [3c] LLM Reasoning (Ollama)                               │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ • Build prompt:                                       │ │  │
│  │  │   - System persona (PERSONA_PROMPT)                  │ │  │
│  │  │   - Capability description (registry)                │ │  │
│  │  │   - RAG context (if available)                       │ │  │
│  │  │   - Memory context (episodic retrieval)              │ │  │
│  │  │   - User transcript                                  │ │  │
│  │  │ • Call Ollama generate API (streaming)               │ │  │
│  │  │ • Collect response chunks                            │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [3d] TTS Synthesis (Piper)                                │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ • Phoneme processing (eSpeak for "KLoROS")           │ │  │
│  │  │ • ONNX inference (local model)                       │ │  │
│  │  │ • WAV generation                                     │ │  │
│  │  │ • Audio playback (pw-play/PipeWire)                  │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [3e] Memory Logging                                       │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ • Log episodic memory (user + assistant turns)       │ │  │
│  │  │ • Update vector embeddings (ChromaDB)                │ │  │
│  │  │ • Store telemetry (JSONL)                            │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  Return to Wake Word Detection Loop                        │  │
│  │                                                             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
```

#### Turn Lifecycle Detail

**Function:** `run_turn()` in `src/core/turn.py`

**Input:** Audio samples (numpy array), sample rate, backends (STT/TTS), configuration

**Output:** `TurnSummary` (transcript, response, timings, VAD metrics)

**State:** Stateless (all context passed as parameters)

**Timing:**
- VAD: 50-100ms (segment detection)
- STT: 50-200ms (Vosk fast path) + 100-500ms (Whisper parallel)
- LLM: 500-2000ms (depends on model and response length)
- TTS: 100-300ms (synthesis) + playback time
- **Total turn: 1-3 seconds** (user perceives Vosk latency only)

#### Integration Points

**Inputs (from environment):**
- Audio hardware (microphone)
- Configuration (environment variables)
- RAG bundle (optional, file-based)
- Memory DB (optional, SQLite)

**Outputs (to persistence):**
- Memory events (SQLite: `~/.kloros/kloros_memory.db`)
- Vector embeddings (ChromaDB: `~/.kloros/chroma_data/`)
- Telemetry logs (JSONL: optional)

**External Dependencies:**
- Vosk model (file: `~/kloros_models/vosk/model`)
- Whisper model (downloaded on first use)
- Piper model (ONNX files)
- Ollama service (HTTP: `localhost:11434`)

#### Failure Modes

| Failure | Behavior | Recovery |
|---------|----------|----------|
| Microphone unavailable | Exit with error | Manual fix + restart |
| Vosk model missing | Exit with error | Download model + restart |
| Whisper fails | Use Vosk only | Log warning, continue |
| Ollama unavailable | Exit with error | Start Ollama + restart |
| Piper fails | Skip TTS | Log error, continue |
| RAG unavailable | Skip context | Log warning, continue |
| Memory DB locked | Skip persistence | Log warning, continue |

---

### 3.2 D-REAM Evolution Engine (`src/dream/runner/__main__.py`)

**Purpose:** Continuous population-based genetic algorithm for parameter optimization

**Process Type:** Multi-process with ProcessPoolExecutor

**Operational Mode:** Continuous with adaptive sleep (currently disabled, awaiting timer implementation)

#### Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                   D-REAM Evolution Engine                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  [1] Initialization                                               │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ • Load config (dream.yaml)                                 │  │
│  │ • Initialize search space (adaptive dimensions)            │  │
│  │ • Load experiment definitions (domains, evaluators)        │  │
│  │ • Initialize novelty archive (K-NN, k=15)                  │  │
│  │ • Create artifact directories                              │  │
│  │ • Initialize telemetry logging                             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [2] Generation Loop (Continuous)                                 │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                                                             │  │
│  │  [2a] Check PHASE Window (3-7 AM)                          │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ if current_time in [03:00, 07:00]:                   │ │  │
│  │  │     log("Entering PHASE window, sleeping...")        │ │  │
│  │  │     wait_for_phase_completion()  # Check for signal  │ │  │
│  │  │     ingest_phase_results()       # Awaiting impl     │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [2b] Population Generation                                │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ if generation == 0:                                   │ │  │
│  │  │     # Random initialization                           │ │  │
│  │  │     candidates = random_sample(search_space, N=24)   │ │  │
│  │  │ else:                                                 │ │  │
│  │  │     # Elite preservation (top 6)                     │ │  │
│  │  │     elites = select_top_k(prev_gen, k=6)             │ │  │
│  │  │                                                       │ │  │
│  │  │     # Tournament selection (remaining 18)            │ │  │
│  │  │     for i in range(18):                              │ │  │
│  │  │         parent1 = tournament_select(size=3)          │ │  │
│  │  │         parent2 = tournament_select(size=3)          │ │  │
│  │  │                                                       │ │  │
│  │  │         # Crossover (p=0.7)                          │ │  │
│  │  │         if random() < 0.7:                           │ │  │
│  │  │             child = crossover(parent1, parent2)      │ │  │
│  │  │         else:                                        │ │  │
│  │  │             child = parent1                          │ │  │
│  │  │                                                       │ │  │
│  │  │         # Mutation (p=0.15)                          │ │  │
│  │  │         if random() < 0.15:                          │ │  │
│  │  │             child = mutate(child, search_space)      │ │  │
│  │  │                                                       │ │  │
│  │  │         offspring.append(child)                      │ │  │
│  │  │                                                       │ │  │
│  │  │     candidates = elites + offspring                  │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [2c] Parallel Evaluation (ProcessPoolExecutor)            │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ with ProcessPoolExecutor(max_workers=4) as pool:     │ │  │
│  │  │     futures = []                                     │ │  │
│  │  │     for candidate in candidates:                     │ │  │
│  │  │         future = pool.submit(                        │ │  │
│  │  │             evaluate_candidate,                      │ │  │
│  │  │             candidate,                               │ │  │
│  │  │             evaluator,                               │ │  │
│  │  │             context                                  │ │  │
│  │  │         )                                            │ │  │
│  │  │         futures.append(future)                       │ │  │
│  │  │                                                       │ │  │
│  │  │     # Wait for completion (with timeout)            │ │  │
│  │  │     results = [f.result(timeout=600) for f in futures]│ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [2d] Fitness Calculation (Multi-Objective)                │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ for candidate, metrics in zip(candidates, results): │ │  │
│  │  │                                                       │ │  │
│  │  │     # 6-dimensional fitness                          │ │  │
│  │  │     performance = metrics['primary_metric']          │ │  │
│  │  │     stability = 1 - metrics['variance']              │ │  │
│  │  │     drawdown = 1 - metrics['max_degradation']        │ │  │
│  │  │     turnover = metrics['efficiency']                 │ │  │
│  │  │     correlation = 1 - metrics['baseline_correlation']│ │  │
│  │  │     risk = 1 - metrics['tail_risk']                  │ │  │
│  │  │                                                       │ │  │
│  │  │     # Hard constraints (infeasible if violated)      │ │  │
│  │  │     if drawdown > 0.6 or risk > 0.8:                 │ │  │
│  │  │         fitness = -inf                               │ │  │
│  │  │     else:                                            │ │  │
│  │  │         # Weighted sum                               │ │  │
│  │  │         fitness = (                                  │ │  │
│  │  │             0.40 * performance +                     │ │  │
│  │  │             0.20 * stability +                       │ │  │
│  │  │             0.15 * drawdown +                        │ │  │
│  │  │             0.10 * turnover +                        │ │  │
│  │  │             0.10 * correlation +                     │ │  │
│  │  │             0.05 * risk                              │ │  │
│  │  │         )                                            │ │  │
│  │  │                                                       │ │  │
│  │  │     candidate['fitness'] = fitness                   │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [2e] Novelty Archive Update                               │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ for candidate in candidates:                         │ │  │
│  │  │     # K-NN novelty score                             │ │  │
│  │  │     embedding = embed(candidate)                     │ │  │
│  │  │     neighbors = knn_search(archive, embedding, k=15) │ │  │
│  │  │     novelty = mean_distance(embedding, neighbors)    │ │  │
│  │  │     candidate['novelty'] = novelty                   │ │  │
│  │  │                                                       │ │  │
│  │  │ # Pareto selection (fitness + novelty)               │ │  │
│  │  │ pareto_front = non_dominated_sort(candidates)        │ │  │
│  │  │ archive.extend(pareto_front[:10])  # Keep top 10    │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [2f] Search Space Adaptation (Every 5 generations)        │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ if generation % 5 == 0:                              │ │  │
│  │  │     # Analyze fitness history                        │ │  │
│  │  │     stagnant_params = find_low_variance_params()     │ │  │
│  │  │     promising_params = find_high_fitness_regions()   │ │  │
│  │  │                                                       │ │  │
│  │  │     # Prune stagnant                                 │ │  │
│  │  │     for param in stagnant_params:                    │ │  │
│  │  │         if coverage[param] > 0.95:                   │ │  │
│  │  │             search_space[param] = narrow_range()     │ │  │
│  │  │                                                       │ │  │
│  │  │     # Expand promising                               │ │  │
│  │  │     for param in promising_params:                   │ │  │
│  │  │         search_space[param] = expand_range()         │ │  │
│  │  │                                                       │ │  │
│  │  │     log_space_adaptation()                           │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [2g] Promotion (Best of Generation)                       │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ best = max(candidates, key=lambda c: c['fitness'])   │ │  │
│  │  │                                                       │ │  │
│  │  │ if best['fitness'] > current_champion['fitness']:    │ │  │
│  │  │     # Write promotion                                │ │  │
│  │  │     write_json(                                      │ │  │
│  │  │         f"artifacts/dream/promotions/{gen}.json",    │ │  │
│  │  │         best                                         │ │  │
│  │  │     )                                                │ │  │
│  │  │     current_champion = best                          │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [2h] Telemetry & Logging                                  │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ write_jsonl(                                         │ │  │
│  │  │     f"artifacts/dream/{exp_name}.jsonl",             │ │  │
│  │  │     {                                                │ │  │
│  │  │         "generation": gen,                           │ │  │
│  │  │         "best_fitness": best['fitness'],             │ │  │
│  │  │         "mean_fitness": mean([c['fitness']]),        │ │  │
│  │  │         "novelty_diversity": std([c['novelty']]),    │ │  │
│  │  │         "search_space_size": cardinality(space)      │ │  │
│  │  │     }                                                │ │  │
│  │  │ )                                                    │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [2i] Adaptive Sleep (Awaiting Implementation)             │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ # Calculate sleep time based on convergence          │ │  │
│  │  │ fitness_delta = abs(best - prev_best)                │ │  │
│  │  │ if fitness_delta < 0.01:                             │ │  │
│  │  │     sleep_time = min(sleep_time * 1.5, MAX_SLEEP)    │ │  │
│  │  │ else:                                                │ │  │
│  │  │     sleep_time = BASE_SLEEP                          │ │  │
│  │  │                                                       │ │  │
│  │  │ sleep(sleep_time)  # Currently not implemented       │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  Loop to [2a] for next generation                          │  │
│  │                                                             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
```

#### Evolution Parameters

From `src/dream/config/dream.yaml`:

```yaml
population_size: 24           # Candidates per generation
elite_k: 6                    # Elite preservation count
tournament_size: 3            # Tournament selection size
mutation_rate: 0.15           # Mutation probability
crossover_rate: 0.7           # Crossover probability
novelty_k: 15                 # K-nearest neighbors for novelty
max_generations: 1000         # Hard stop (optional)
```

#### Evaluator Interface

**Contract:** All evaluators must provide:

```python
def evaluate(params: dict, context: dict) -> dict:
    """
    Args:
        params: Candidate parameters from search space
        context: Experiment metadata (name, generation, budget)

    Returns:
        {
            'primary_metric': float,      # Main performance metric
            'variance': float,            # Stability measure
            'max_degradation': float,     # Drawdown metric
            'efficiency': float,          # Turnover metric
            'baseline_correlation': float,# Correlation metric
            'tail_risk': float,           # Risk metric
            'metadata': dict              # Optional telemetry
        }
    """
```

**Supported Evaluator Types:**
1. Module-level function: `evaluate(params, context)`
2. Factory function: `create_evaluator() -> obj` with `obj.evaluate(params, context)`
3. Class instantiation: `MyEvaluator()` with `evaluate(params, context)` method

#### Integration Points

**Inputs:**
- Configuration (YAML: `src/dream/config/dream.yaml`)
- Experiment definitions (Python modules with evaluators)
- PHASE results (awaiting implementation: `/tmp/phase_complete_{timestamp}`)

**Outputs:**
- Promotions: `artifacts/dream/promotions/{gen}.json`
- Telemetry: `artifacts/dream/{exp_name}.jsonl`
- Domain-specific artifacts: `artifacts/dream/{domain}/`

**Synchronization:**
- PHASE window signal (awaiting: check for file `/tmp/phase_complete_*`)
- Adaptive sleep timer (awaiting implementation)

#### Direct-Build Mode (Oct 2025)

In addition to the continuous population-based tournament mode described above, D-REAM now supports **direct-build mode** for on-demand hypothesis validation. This mode is used by the autonomous self-healing system.

**Purpose:** Generate specific code or configurations in response to runtime failures, rather than exploring a search space.

**Triggering:** Direct-build mode is triggered by:
1. CuriosityCore detects ModuleNotFoundError or similar runtime exception
2. ExceptionMonitor generates CuriosityQuestion with `action_class=propose_fix`
3. Orchestrator routes question to D-REAM direct-build instead of tournament

**Direct-Build Flow:**

```
┌──────────────────────────────────────────────────────────────┐
│                    D-REAM Direct-Build Mode                  │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  [1] Receive CuriosityQuestion from Orchestrator             │
│      ├─ Question: "How do I generate X.py from patterns?"    │
│      ├─ Evidence: [similar_modules, error_context]           │
│      └─ Action: propose_fix                                  │
│      ↓                                                        │
│  [2] Spawn SPICA Instance for Direct-Build                   │
│      ├─ Instance ID: spica-{short_hash}                      │
│      ├─ Hypothesis: MISSING_MODULE_{module_name}             │
│      └─ Mode: direct_build (not tournament)                  │
│      ↓                                                        │
│  [3] ModuleGenerator Analyzes Templates                      │
│      ├─ Read similar modules from evidence                   │
│      ├─ Parse structure and patterns                         │
│      └─ Generate new module code                             │
│      ↓                                                        │
│  [4] Write Generated Module                                  │
│      ├─ Path: src/{package}/{module}.py                      │
│      ├─ Ownership: kloros:kloros                             │
│      └─ Permissions: 0644                                    │
│      ↓                                                        │
│  [5] Validate Import Works                                   │
│      ├─ python3 -c "import {module}"                         │
│      └─ Exit code 0 = success                                │
│      ↓                                                        │
│  [6] Mark Question as Processed                              │
│      └─ Update processed_questions.jsonl                     │
│                                                                │
└──────────────────────────────────────────────────────────────┘
```

**Key Differences from Tournament Mode:**

| Aspect | Tournament Mode | Direct-Build Mode |
|--------|----------------|-------------------|
| **Purpose** | Explore search space | Fix specific problem |
| **Generations** | Multiple (evolutionary) | Single (one-shot) |
| **Population** | 24 candidates | 1 solution |
| **Evaluation** | Fitness scoring | Binary pass/fail |
| **Output** | Promotions | Generated code |
| **Time** | Hours to days | Minutes |

**ModuleGenerator Integration:**

The `ModuleGenerator` class (`src/dream/config_tuning/module_generator.py`) implements template-based code generation:

```python
class ModuleGenerator:
    """Generates missing modules from existing templates."""

    def generate_spica_domain(
        self,
        target_path: Path,
        similar_modules: List[str]
    ) -> bool:
        """
        Generate module by analyzing existing patterns.

        Steps:
        1. Read similar modules (up to 3)
        2. Extract common patterns (imports, classes, functions)
        3. Generate new module following template
        4. Validate structure and syntax
        5. Write to target path
        """
```

**Current Capabilities:**
- Generate SPICA domain modules (e.g., `spica_domain.py`)
- Analyze existing `spica_*.py` patterns
- Create generic base classes for test infrastructure

**Future Capabilities:**
- Generate LLM client wrappers
- Generate PHASE test domains
- Generate tool synthesis modules
- Self-extend with new generator templates

#### Current Status

**Operational:** Fully implemented, tested, ready
**Deployment:** Disabled (`dream.service` inactive)
**Blocking Issues:**
1. Adaptive timer not implemented (intelligent sleep scaling)
2. PHASE completion signaling not implemented
3. Result collapse not implemented (ingest PHASE metrics)

---

### 3.3 PHASE Test Orchestration (`src/phase/run_all_domains.py`)

**Purpose:** Temporal dilation testing - "Hyperbolic Time Chamber" providing accelerated intensive evaluation

**Process Type:** Sequential domain execution (can parallelize domains)

**Operational Mode:** Quantized bursts (nightly 3:00 AM + heuristic controller every 10 min)

#### Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                   PHASE Test Orchestration                       │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  [1] Initialization                                               │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ • Generate epoch ID (timestamp-based)                      │  │
│  │ • Initialize LLM backend (Ollama)                          │  │
│  │ • Load domain configurations                               │  │
│  │ • Initialize result collectors                             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [2] Domain Execution Loop (Sequential)                           │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                                                             │  │
│  │  For each domain in [TTS, Conversation, RAG, CodeRepair,  │  │
│  │                       SystemHealth, MCP, Planning,          │  │
│  │                       ToolGen, Turns, BugInjector,          │  │
│  │                       RepairLab]:                           │  │
│  │                                                             │  │
│  │      [2a] Domain Instantiation                             │  │
│  │      ┌──────────────────────────────────────────────────┐ │  │
│  │      │ • Load domain config                             │ │  │
│  │      │ • Create SPICA instance (inherits from SpicaBase)│ │  │
│  │      │ • Initialize domain-specific test suite         │ │  │
│  │      │ • Prepare telemetry logger                      │ │  │
│  │      └──────────────────────────────────────────────────┘ │  │
│  │              ↓                                              │  │
│  │      [2b] Test Execution                                   │  │
│  │      ┌──────────────────────────────────────────────────┐ │  │
│  │      │ # Example: TTS Domain                            │ │  │
│  │      │ tests = [                                        │ │  │
│  │      │     ("latency", test_latency),                   │ │  │
│  │      │     ("quality", test_mos_score),                 │ │  │
│  │      │     ("throughput", test_throughput),             │ │  │
│  │      │     ("error_rate", test_error_handling),         │ │  │
│  │      │     ...  # 8-12 tests per domain                 │ │  │
│  │      │ ]                                                │ │  │
│  │      │                                                  │ │  │
│  │      │ for test_name, test_fn in tests:                │ │  │
│  │      │     result = test_fn(config)                    │ │  │
│  │      │     log_telemetry(test_name, result)            │ │  │
│  │      │     results.append(result)                      │ │  │
│  │      └──────────────────────────────────────────────────┘ │  │
│  │              ↓                                              │  │
│  │      [2c] Statistical Analysis                             │  │
│  │      ┌──────────────────────────────────────────────────┐ │  │
│  │      │ # Multi-replica testing (QTIME rigor)            │ │  │
│  │      │ for test in tests:                               │ │  │
│  │      │     replicas = run_replicas(test, n=5)          │ │  │
│  │      │     mean = np.mean(replicas)                     │ │  │
│  │      │     std = np.std(replicas)                       │ │  │
│  │      │     ci95 = confidence_interval(replicas, 0.95)   │ │  │
│  │      │                                                  │ │  │
│  │      │     test_result = {                              │ │  │
│  │      │         "mean": mean,                            │ │  │
│  │      │         "std": std,                              │ │  │
│  │      │         "ci95": ci95,                            │ │  │
│  │      │         "pass": mean > threshold                 │ │  │
│  │      │     }                                            │ │  │
│  │      └──────────────────────────────────────────────────┘ │  │
│  │              ↓                                              │  │
│  │      [2d] Domain Summary                                   │  │
│  │      ┌──────────────────────────────────────────────────┐ │  │
│  │      │ summary = {                                      │ │  │
│  │      │     "domain": domain_name,                       │ │  │
│  │      │     "total_tests": len(tests),                   │ │  │
│  │      │     "passed": sum(t['pass'] for t in tests),     │ │  │
│  │      │     "pass_rate": passed / total,                 │ │  │
│  │      │     "metrics": aggregate_metrics(),              │ │  │
│  │      │     "telemetry": get_telemetry_path()            │ │  │
│  │      │ }                                                │ │  │
│  │      └──────────────────────────────────────────────────┘ │  │
│  │              ↓                                              │  │
│  │      Log domain summary                                    │  │
│  │      Continue to next domain                               │  │
│  │                                                             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [3] Epoch Summary & Reporting                                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ epoch_report = {                                           │  │
│  │     "epoch_id": epoch_id,                                  │  │
│  │     "timestamp": now(),                                    │  │
│  │     "total_tests": sum(d['total_tests'] for d in domains),│  │
│  │     "total_passed": sum(d['passed'] for d in domains),    │  │
│  │     "overall_pass_rate": total_passed / total_tests,       │  │
│  │     "domain_results": [domain_summaries],                  │  │
│  │     "duration_seconds": elapsed_time                       │  │
│  │ }                                                           │  │
│  │                                                             │  │
│  │ write_jsonl("src/phase/phase_report.jsonl", epoch_report)  │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [4] Signal Completion (Awaiting Implementation)                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ # Write completion signal for D-REAM                       │  │
│  │ write_file(f"/tmp/phase_complete_{epoch_id}", epoch_report)│  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
```

#### Domain Test Structure

Each domain implements the SPICA interface:

```python
class DomainName(SpicaBase):
    def __init__(self, config: DomainConfig):
        super().__init__(
            domain_name="domain_name",
            variant_id="baseline",
            version="1.0"
        )
        self.config = config
        self.test_results = []

    def run_all_tests(self, epoch_id: str) -> List[TestResult]:
        """Execute all tests for this domain."""
        for test in self.test_suite:
            result = self._run_test(test)
            self.log_telemetry(test.name, result)
            self.test_results.append(result)
        return self.test_results

    def get_summary(self) -> dict:
        """Aggregate test results into summary."""
        return {
            "total_tests": len(self.test_results),
            "passed": sum(r.passed for r in self.test_results),
            "pass_rate": self._calculate_pass_rate(),
            "metrics": self._aggregate_metrics()
        }
```

#### 11 SPICA Test Domains

| Domain | KPIs | Focus | Typical Runtime |
|--------|------|-------|-----------------|
| **TTS** | 12 | Latency, quality (MOS), throughput, error rate | 15-20 min |
| **Turn Management** | 10 | VAD boundaries, echo suppression, barge-in | 10-15 min |
| **RAG** | 11 | Precision, recall, grounding, relevance | 20-25 min |
| **ToolGen** | 9 | Synthesis success, test coverage, repair strategies | 25-30 min |
| **Conversation** | 10 | Intent accuracy, latency, context retention | 15-20 min |
| **Code Repair** | 8 | Test pass rate, lint pass rate, bug fixes | 20-25 min |
| **Planning** | 9 | Accuracy, latency, token cost, efficiency | 10-15 min |
| **Bug Injector** | 7 | Fault injection, recovery testing | 10-15 min |
| **System Health** | 8 | Memory remediation, CPU efficiency, recovery | 10-15 min |
| **MCP** | 10 | Tool discovery, routing, policy compliance | 15-20 min |
| **RepairLab** | 8 | Meta-repair strategies, pattern evolution | 20-25 min |

**Total: ~100 KPIs, 3-4 hour window**

#### Integration Points

**Inputs:**
- Domain configurations (YAML: `src/phase/configs/*.yaml`)
- SPICA instances (Python classes in `src/phase/domains/spica_*.py`)
- LLM backend (Ollama for code repair, planning)
- Test datasets (various formats)

**Outputs:**
- Epoch report (JSONL: `src/phase/phase_report.jsonl`)
- Domain telemetry (JSONL: per-domain files)
- SPICA instance snapshots: `experiments/spica/instances/`
- Completion signal (awaiting: `/tmp/phase_complete_{epoch_id}`)

**Scheduling:**
- Systemd timer: `spica-phase-test.timer`
- Window: 3:00 AM - 7:00 AM
- Frequency: Nightly

#### Current Status

**Operational:** Fully implemented, timer enabled
**Deployment:** Inactive (waiting for D-REAM to be active)
**Blocking:** D-REAM must be running to consume results

---

### 3.4 SPICA Instance Lifecycle (`src/spica/base.py`)

**Purpose:** Uniform foundation template for all test instances with telemetry, manifest, and lineage

**Process Type:** Instantiated class (not standalone process)

**Operational Mode:** Created on-demand by D-REAM or PHASE

#### Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      SPICA Instance Lifecycle                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  [1] Instantiation (by D-REAM or PHASE)                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ instance = MyDomain(                                       │  │
│  │     domain_name="my_domain",                               │  │
│  │     variant_id="gen42_elite3",                             │  │
│  │     version="1.2.3",                                       │  │
│  │     parent_id="gen41_elite2",  # Optional                  │  │
│  │     generation=42,                                         │  │
│  │     config={...}                                           │  │
│  │ )                                                           │  │
│  │                                                             │  │
│  │ # SpicaBase.__init__ executes:                             │  │
│  │ #  - Generate spica_id (UUID-based)                        │  │
│  │ #  - Create telemetry logger                               │  │
│  │ #  - Initialize manifest                                   │  │
│  │ #  - Initialize lineage tracker                            │  │
│  │ #  - Set creation timestamp                                │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [2] Execution (Domain-Specific Logic)                            │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                                                             │  │
│  │  # Domain implements evaluation logic                      │  │
│  │  result = instance.evaluate(params)                        │  │
│  │                                                             │  │
│  │  # SpicaBase provides telemetry                            │  │
│  │  instance.log_telemetry(                                   │  │
│  │      event_type="test_executed",                           │  │
│  │      metrics={"latency_ms": 142, "accuracy": 0.95},        │  │
│  │      metadata={"test_name": "test_synthesis"}              │  │
│  │  )                                                          │  │
│  │                                                             │  │
│  │  # Creates SpicaTelemetryEvent:                            │  │
│  │  # {                                                       │  │
│  │  #     "timestamp": 1730140800.0,                          │  │
│  │  #     "trace_id": "abc123",                               │  │
│  │  #     "variant_id": "gen42_elite3",                       │  │
│  │  #     "domain": "my_domain",                              │  │
│  │  #     "event_type": "test_executed",                      │  │
│  │  #     "metrics": {...},                                   │  │
│  │  #     "metadata": {...}                                   │  │
│  │  # }                                                       │  │
│  │                                                             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [3] Manifest Creation (Snapshot State)                           │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ manifest = instance.create_manifest(                       │  │
│  │     mutations={"param_a": 0.5, "param_b": "value"}         │  │
│  │ )                                                           │  │
│  │                                                             │  │
│  │ # SpicaManifest:                                           │  │
│  │ # {                                                        │  │
│  │ #     "spica_id": "550e8400-e29b-41d4-a716-446655440000",  │  │
│  │ #     "version": "1.2.3",                                  │  │
│  │ #     "domain": "my_domain",                               │  │
│  │ #     "origin_commit": "a1b2c3d",                          │  │
│  │ #     "parent_id": "gen41_elite2",                         │  │
│  │ #     "generation": 42,                                    │  │
│  │ #     "mutations": {"param_a": 0.5, "param_b": "value"},   │  │
│  │ #     "created_at": 1730140800.0,                          │  │
│  │ #     "config": {...},                                     │  │
│  │ #     "manifest_hash": "sha256:..."  # Tamper detection    │  │
│  │ # }                                                        │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [4] Lineage Tracking (Evolutionary History)                      │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ lineage = instance.get_lineage()                           │  │
│  │                                                             │  │
│  │ # SpicaLineage:                                            │  │
│  │ # {                                                        │  │
│  │ #     "spica_id": "550e8400-e29b-41d4-a716-446655440000",  │  │
│  │ #     "parent_id": "gen41_elite2",                         │  │
│  │ #     "generation": 42,                                    │  │
│  │ #     "origin_commit": "a1b2c3d",                          │  │
│  │ #     "created_at": 1730140800.0,                          │  │
│  │ #     "mutations_applied": {"param_a": 0.5, ...},          │  │
│  │ #     "hmac": "hmac-sha256:..."  # Tamper evidence         │  │
│  │ # }                                                        │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [5] Instance Persistence (Snapshot System)                       │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ # Triggered by PHASE or D-REAM                             │  │
│  │ snapshot_dir = f"experiments/spica/instances/spica-{id}"   │  │
│  │                                                             │  │
│  │ write_json(                                                │  │
│  │     f"{snapshot_dir}/manifest.json",                       │  │
│  │     manifest.to_json()                                     │  │
│  │ )                                                           │  │
│  │                                                             │  │
│  │ write_json(                                                │  │
│  │     f"{snapshot_dir}/lineage.json",                        │  │
│  │     lineage.to_json()                                      │  │
│  │ )                                                           │  │
│  │                                                             │  │
│  │ copy_file(                                                 │  │
│  │     f"src/phase/domains/spica_{domain}.py",                │  │
│  │     f"{snapshot_dir}/source.py"                            │  │
│  │ )                                                           │  │
│  │                                                             │  │
│  │ # Retention: Keep 10 most recent snapshots                 │  │
│  │ prune_old_snapshots(keep=10)                               │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [6] Telemetry Aggregation                                        │  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ # All telemetry events written to JSONL                    │  │
│  │ telemetry_path = f"artifacts/dream/{domain}/{variant}.jsonl"│  │
│  │                                                             │  │
│  │ # Each event line:                                         │  │
│  │ # {"timestamp": ..., "trace_id": ..., "metrics": ...}      │  │
│  │                                                             │  │
│  │ # Can be aggregated by D-REAM for fitness calculation      │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
```

#### SPICA Benefits

**For Domain Developers:**
- Uniform interface (no boilerplate)
- Automatic telemetry logging
- Built-in manifest/lineage tracking
- Snapshot persistence handled

**For D-REAM:**
- Consistent evaluation interface
- Traceable evolutionary history
- Tamper-evident manifests (SHA256)
- Structured telemetry for fitness

**For PHASE:**
- Standardized test execution
- Cross-domain metrics comparison
- Snapshot retention for analysis

#### Integration with Evolution

```
D-REAM Generation N
   ↓
Creates 24 SPICA instances (with mutations)
   ↓
Evaluates each (parallel)
   ↓
Collects telemetry → Calculates fitness
   ↓
Selects best → Writes promotion
   ↓
Creates snapshot (top 10 variants)
   ↓
D-REAM Generation N+1 (inherit from best)
```

#### Retention Policy

- **Total instances:** 10 snapshots retained
- **Cleanup trigger:** When count > 10, delete oldest
- **Criteria:** Keep highest fitness + most recent
- **Location:** `experiments/spica/instances/`

---

### 3.5 RAG Pipeline (`src/simple_rag.py`)

**Purpose:** Hybrid retrieval-augmented generation for context-enhanced responses

**Process Type:** Library (imported by voice loop)

**Operational Mode:** On-demand (per voice turn)

#### Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         RAG Pipeline                             │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  [1] Initialization (One-time, at voice loop startup)             │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ rag = RAG(                                                 │  │
│  │     bundle_path="rag_data/rag_store.npz",                  │  │
│  │     verify_bundle_hash=True                                │  │
│  │ )                                                           │  │
│  │                                                             │  │
│  │ # Load precomputed embeddings + metadata                   │  │
│  │ #  - Documents: List[Dict] (title, text, source, ...)     │  │
│  │ #  - Embeddings: np.ndarray (N x D)                        │  │
│  │ #  - Faiss index: Optional (if available)                  │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [2] Query Processing (Per turn)                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                                                             │  │
│  │  user_query = "How does D-REAM evolution work?"            │  │
│  │                                                             │  │
│  │  [2a] Query Embedding                                      │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ # Use embedder callable (Ollama /api/embeddings)     │ │  │
│  │  │ query_embedding = embedder(user_query)               │ │  │
│  │  │ # Returns: np.ndarray (D,)                           │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [2b] Hybrid Search                                        │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ # Stage 1: BM25 keyword search (sparse)              │ │  │
│  │  │ bm25_scores = []                                     │ │  │
│  │  │ for doc in documents:                                │ │  │
│  │  │     score = bm25(user_query, doc['text'])            │ │  │
│  │  │     bm25_scores.append(score)                        │ │  │
│  │  │                                                      │ │  │
│  │  │ bm25_top_k = argsort(bm25_scores)[:top_k]            │ │  │
│  │  │                                                      │ │  │
│  │  │ # Stage 2: Vector similarity (dense)                │ │  │
│  │  │ if faiss_index:                                      │ │  │
│  │  │     # GPU-accelerated ANN search                    │ │  │
│  │  │     distances, indices = faiss_index.search(         │ │  │
│  │  │         query_embedding, k=top_k                     │ │  │
│  │  │     )                                                │ │  │
│  │  │ else:                                                │ │  │
│  │  │     # Numpy cosine similarity                       │ │  │
│  │  │     similarities = cosine_similarity(               │ │  │
│  │  │         query_embedding,                            │ │  │
│  │  │         embeddings                                  │ │  │
│  │  │     )                                               │ │  │
│  │  │     vector_top_k = argsort(similarities)[:top_k]    │ │  │
│  │  │                                                      │ │  │
│  │  │ # Stage 3: Reciprocal Rank Fusion (RRF)            │ │  │
│  │  │ # Combine BM25 + vector results                     │ │  │
│  │  │ rrf_scores = {}                                      │ │  │
│  │  │ for rank, idx in enumerate(bm25_top_k):             │ │  │
│  │  │     rrf_scores[idx] = rrf_scores.get(idx, 0)        │ │  │
│  │  │                      + 1 / (60 + rank)              │ │  │
│  │  │                                                      │ │  │
│  │  │ for rank, idx in enumerate(vector_top_k):           │ │  │
│  │  │     rrf_scores[idx] = rrf_scores.get(idx, 0)        │ │  │
│  │  │                      + 1 / (60 + rank)              │ │  │
│  │  │                                                      │ │  │
│  │  │ # Rerank by RRF score                               │ │  │
│  │  │ final_indices = sorted(                              │ │  │
│  │  │     rrf_scores.keys(),                               │ │  │
│  │  │     key=lambda i: rrf_scores[i],                     │ │  │
│  │  │     reverse=True                                     │ │  │
│  │  │ )[:top_k]                                            │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [2c] Context Assembly                                     │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ retrieved_docs = [documents[i] for i in final_indices]│ │  │
│  │  │                                                      │ │  │
│  │  │ context = ""                                         │ │  │
│  │  │ for rank, doc in enumerate(retrieved_docs):          │ │  │
│  │  │     context += f"[{rank+1}] {doc['title']}\n"       │ │  │
│  │  │     context += f"{doc['text']}\n"                    │ │  │
│  │  │     context += f"Source: {doc['source']}\n\n"        │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [2d] Prompt Construction                                  │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ prompt = f"""                                        │ │  │
│  │  │ You are KLoROS, a knowledgeable voice assistant.    │ │  │
│  │  │                                                      │ │  │
│  │  │ Use the following context to answer the question.   │ │  │
│  │  │ If the context doesn't contain relevant info, say so│ │  │
│  │  │                                                      │ │  │
│  │  │ Context:                                             │ │  │
│  │  │ {context}                                            │ │  │
│  │  │                                                      │ │  │
│  │  │ Question: {user_query}                               │ │  │
│  │  │                                                      │ │  │
│  │  │ Answer:                                              │ │  │
│  │  │ """                                                  │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [2e] LLM Generation                                       │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ response = ollama_generate(                          │ │  │
│  │  │     model="qwen2.5:14b-instruct-q4_0",               │ │  │
│  │  │     prompt=prompt                                    │ │  │
│  │  │ )                                                    │ │  │
│  │  │                                                      │ │  │
│  │  │ return response                                      │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │                                                             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [3] Optional: Self-RAG (Confidence Filtering)                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ # If enabled, check response grounding                     │  │
│  │ confidence = assess_grounding(response, context)            │  │
│  │                                                             │  │
│  │ if confidence < threshold:                                  │  │
│  │     # Trigger fallback: "I'm not confident, let me check..."│  │
│  │     response = fallback_response()                          │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
```

#### RAG Configuration

From `src/config/kloros.yaml`:

```yaml
rag:
  enabled: true
  bundle_path: "rag_data/rag_store.npz"
  verify_hash: true

  search:
    top_k: 5                    # Retrieve top 5 documents
    hybrid: true                # Enable BM25 + vector
    bm25_weight: 0.3            # BM25 contribution
    vector_weight: 0.7          # Vector contribution

  reranking:
    enabled: true               # Cross-encoder reranking
    model: "cross-encoder/ms-marco-MiniLM-L-6-v2"
    top_n: 3                    # Final documents after rerank

  self_rag:
    enabled: false              # Self-assessment (experimental)
    confidence_threshold: 0.7
```

#### Data Format

**Bundle Structure (NPZ):**
```
rag_store.npz:
  - embeddings: np.ndarray (N x D, float32)
  - metadata: List[Dict] serialized as JSON string
  - manifest_hash: SHA256 checksum
```

**Metadata Schema:**
```json
{
  "id": "doc_001",
  "title": "D-REAM Evolution Overview",
  "text": "D-REAM (Darwinian-RZero Evolution...",
  "source": "docs/ASTRAEA_SYSTEM_THESIS.md",
  "section": "Section 2",
  "tokens": 1234,
  "embedding_model": "nomic-embed-text",
  "created_at": "2025-10-28T12:00:00Z"
}
```

#### Integration with Voice Loop

```python
# In kloros_voice.py
def generate_response(user_text: str) -> str:
    # Check if RAG is available
    if self.rag is not None:
        # RAG-enhanced response
        response = self.rag.answer(
            question_text=user_text,
            embedder=self.embedder_fn,
            top_k=5,
            ollama_url='http://localhost:11434/api/generate',
            ollama_model='qwen2.5:14b-instruct-q4_0'
        )
    else:
        # Direct LLM (no context)
        response = ollama_generate(
            prompt=f"{PERSONA_PROMPT}\nUser: {user_text}\nAssistant:",
            model='qwen2.5:14b-instruct-q4_0'
        )

    return response
```

#### Performance Characteristics

- **Bundle load:** ~100-500ms (one-time, at startup)
- **Query embedding:** ~50-100ms (Ollama embeddings)
- **BM25 search:** ~10-20ms (Python implementation)
- **Vector search:** ~5-10ms (numpy) or ~1-3ms (Faiss GPU)
- **RRF fusion:** ~1-2ms
- **Total retrieval:** ~70-130ms
- **LLM generation:** 500-2000ms (dominates latency)

**Memory:**
- Bundle: ~50-200MB (depends on corpus size)
- Runtime: +100-300MB (loaded embeddings + Faiss index)

---

### 3.6 Tool Evolution System (ToolGen + RepairLab)

**Purpose:** Continuous tool synthesis and meta-repair with evolutionary pattern selection

**Process Type:** On-demand (triggered by D-REAM or direct invocation)

**Operational Mode:** Integrated with D-REAM evolution loop

#### Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                  Tool Evolution System                           │
│               (ToolGen → RepairLab → D-REAM)                     │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  [1] Tool Synthesis (ToolGen)                                     │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                                                             │  │
│  │  [1a] Requirement Analysis                                 │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ # Input: Natural language spec or detected need      │ │  │
│  │  │ requirement = "Create tool to calculate WER from ASR"│ │  │
│  │  │                                                       │ │  │
│  │  │ # Parse intent                                       │ │  │
│  │  │ intent = parse_requirement(requirement)              │ │  │
│  │  │ # {                                                  │ │  │
│  │  │ #     "function_name": "calculate_wer",              │ │  │
│  │  │ #     "inputs": ["reference: str", "hypothesis: str"]│ │  │
│  │  │ #     "output": "float (WER score)",                 │ │  │
│  │  │ #     "domain": "speech_metrics"                     │ │  │
│  │  │ # }                                                  │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [1b] Template Selection                                   │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ # Match intent to template library                   │ │  │
│  │  │ templates = search_templates(                        │ │  │
│  │  │     domain=intent['domain'],                         │ │  │
│  │  │     function_type="metric_calculation"               │ │  │
│  │  │ )                                                    │ │  │
│  │  │                                                      │ │  │
│  │  │ # Rank by similarity                                │ │  │
│  │  │ template = select_best(templates)                    │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [1c] Code Generation (LLM-based)                          │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ prompt = f"""                                        │ │  │
│  │  │ Generate Python code for: {requirement}              │ │  │
│  │  │                                                      │ │  │
│  │  │ Template:                                            │ │  │
│  │  │ {template}                                           │ │  │
│  │  │                                                      │ │  │
│  │  │ Requirements:                                        │ │  │
│  │  │ - Type hints for all parameters                     │ │  │
│  │  │ - Docstring with examples                           │ │  │
│  │  │ - Error handling                                    │ │  │
│  │  │ - Unit tests                                        │ │  │
│  │  │ """                                                 │ │  │
│  │  │                                                      │ │  │
│  │  │ code = llm_generate(prompt)                          │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [1d] Static Validation                                    │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ # Syntax check                                       │ │  │
│  │  │ ast_tree = ast.parse(code)                           │ │  │
│  │  │                                                      │ │  │
│  │  │ # Type check (mypy)                                 │ │  │
│  │  │ type_errors = run_mypy(code)                         │ │  │
│  │  │                                                      │ │  │
│  │  │ # Linting (ruff)                                    │ │  │
│  │  │ lint_issues = run_ruff(code)                         │ │  │
│  │  │                                                      │ │  │
│  │  │ # Security scan (bandit)                            │ │  │
│  │  │ security_issues = run_bandit(code)                   │ │  │
│  │  │                                                      │ │  │
│  │  │ if errors:                                           │ │  │
│  │  │     → Send to RepairLab                              │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [1e] Dynamic Validation                                   │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ # Run generated unit tests                           │ │  │
│  │  │ test_result = pytest.main(["-x", "generated_test.py"])│ │  │
│  │  │                                                      │ │  │
│  │  │ if test_result != 0:                                 │ │  │
│  │  │     → Send to RepairLab                              │ │  │
│  │  │ else:                                                │ │  │
│  │  │     → Accept tool, add to registry                  │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │                                                             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [2] Meta-Repair (RepairLab)                                      │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                                                             │  │
│  │  [2a] Failure Analysis                                     │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ failure = {                                          │ │  │
│  │  │     "code": code,                                    │ │  │
│  │  │     "error_type": "type_error",                      │ │  │
│  │  │     "error_msg": "Argument 1 has incompatible type..."│ │  │
│  │  │     "test_output": pytest_output,                    │ │  │
│  │  │     "attempt": 1                                     │ │  │
│  │  │ }                                                    │ │  │
│  │  │                                                      │ │  │
│  │  │ # Classify failure mode                              │ │  │
│  │  │ failure_class = classify(failure)                    │ │  │
│  │  │ # Examples: "type_mismatch", "missing_import",      │ │  │
│  │  │ #            "off_by_one", "edge_case"              │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [2b] Pattern Library Search                               │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ # Load successful repair patterns                    │ │  │
│  │  │ patterns = load_patterns(failure_class)              │ │  │
│  │  │                                                      │ │  │
│  │  │ # Rank by:                                          │ │  │
│  │  │ # 1. Historical success rate                        │ │  │
│  │  │ # 2. Similarity to current failure                  │ │  │
│  │  │ # 3. D-REAM fitness scores (if available)           │ │  │
│  │  │ pattern = tournament_select(patterns, k=3)           │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [2c] Repair Strategy Application                         │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ # Apply pattern-specific fix                        │ │  │
│  │  │ if pattern.name == "type_coercion":                  │ │  │
│  │  │     fixed_code = apply_type_hints(code, pattern)     │ │  │
│  │  │ elif pattern.name == "import_addition":              │ │  │
│  │  │     fixed_code = add_imports(code, pattern)          │ │  │
│  │  │ elif pattern.name == "boundary_fix":                 │ │  │
│  │  │     fixed_code = adjust_boundaries(code, pattern)    │ │  │
│  │  │ else:                                                │ │  │
│  │  │     # LLM-based generic repair                      │ │  │
│  │  │     fixed_code = llm_repair(code, failure, pattern)  │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [2d] Validation (Re-test)                                 │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ validation_result = validate_tool(fixed_code)        │ │  │
│  │  │                                                      │ │  │
│  │  │ if validation_result.passed:                         │ │  │
│  │  │     # Success: log pattern effectiveness            │ │  │
│  │  │     log_repair_success(pattern, failure)             │ │  │
│  │  │     return fixed_code                                │ │  │
│  │  │ else:                                                │ │  │
│  │  │     # Failure: try next pattern                     │ │  │
│  │  │     attempt += 1                                     │ │  │
│  │  │     if attempt < 3:                                  │ │  │
│  │  │         → Retry with different pattern               │ │  │
│  │  │     else:                                            │ │  │
│  │  │         → Quarantine (backoff strategy)              │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │                                                             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [3] Backoff & Quarantine                                         │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ # After 3 failed repair attempts:                          │  │
│  │                                                             │  │
│  │ quarantine_entry = {                                        │  │
│  │     "code_hash": sha256(code),                              │  │
│  │     "failure_count": 3,                                     │  │
│  │     "last_attempt": now(),                                  │  │
│  │     "error_summary": summarize_errors(),                    │  │
│  │     "backoff_until": now() + timedelta(hours=24)            │  │
│  │ }                                                            │  │
│  │                                                             │  │
│  │ write_json("artifacts/dream/quarantine.json", quarantine_entry)│  │
│  │                                                             │  │
│  │ # Prevents thrashing on unfixable tools                    │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [4] D-REAM Integration (Pattern Evolution)                       │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                                                             │  │
│  │  [4a] Pattern as Genome                                    │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ # Each repair pattern is a D-REAM candidate          │ │  │
│  │  │ pattern_genome = {                                   │ │  │
│  │  │     "pattern_id": "type_coercion_v3",                │ │  │
│  │  │     "strategy": "apply_type_hints",                  │ │  │
│  │  │     "params": {                                      │ │  │
│  │  │         "aggressive": 0.7,                           │ │  │
│  │  │         "inference_depth": 2                         │ │  │
│  │  │     }                                                │ │  │
│  │  │ }                                                    │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [4b] Fitness from Success Rate                            │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ # Metrics collected:                                 │ │  │
│  │  │ fitness = {                                          │ │  │
│  │  │     "success_rate": 0.85,  # 85% repair success     │ │  │
│  │  │     "avg_attempts": 1.2,   # Usually works first try│ │  │
│  │  │     "coverage": 0.6,       # Handles 60% of cases   │ │  │
│  │  │     "generalization": 0.7  # Works across domains   │ │  │
│  │  │ }                                                    │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │         ↓                                                   │  │
│  │  [4c] Tournament Selection                                 │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ # D-REAM evolves repair patterns                     │ │  │
│  │  │ # Tournament selects high-fitness patterns           │ │  │
│  │  │ # Mutation varies strategy parameters                │ │  │
│  │  │ # Crossover combines successful strategies           │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │                                                             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [5] TTL Cleanup (Weekly)                                         │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ # Monday 00:00: Clean stale artifacts                      │  │
│  │ for artifact in artifacts/dream/:                           │  │
│  │     age = now() - artifact.created_at                       │  │
│  │     if age > 7 days and not artifact.promoted:              │  │
│  │         delete(artifact)                                     │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
```

#### Integration Summary

```
User Need
   ↓
ToolGen (Synthesize)
   ↓
Validation
   ↓ (if fails)
RepairLab (Fix)
   ↓
Re-validate
   ↓ (if passes)
Register Tool
   ↓
PHASE Tests (Evaluate in real workload)
   ↓
D-REAM (Evolve repair patterns based on success)
   ↓
Improved RepairLab Patterns
   ↓
Better Future Repairs
```

This creates a **meta-learning loop** where the system improves its ability to fix itself over time.

---

## 4. Integration Architecture

This section describes HOW individual processes integrate and communicate.

---

### 4.1 Voice ↔ RAG ↔ Memory Integration

**Data Flow:**

```
User Speech
   ↓
VAD → STT (Vosk-Whisper)
   ↓
Transcript: "How does D-REAM work?"
   ↓
   ├─→ Memory: Episodic Retrieval
   │   └─→ Recent conversation context
   │
   ├─→ RAG: Semantic Retrieval
   │   ├─→ Embed query
   │   ├─→ Hybrid search (BM25 + vector)
   │   └─→ Top 5 documents
   │
   └─→ LLM Prompt Assembly
       ├─→ System persona
       ├─→ Capability description
       ├─→ Memory context
       ├─→ RAG context
       └─→ User query
           ↓
       Ollama Generate
           ↓
       Response: "D-REAM is a continuous..."
           ↓
       TTS (Piper)
           ↓
       Audio Playback
           ↓
       Memory Logging
       ├─→ Episodic: (user_turn, assistant_turn)
       └─→ Vector: Update embeddings
```

**Communication:**
- **In-process:** Direct function calls (Python imports)
- **State:** Stateless (context passed as parameters)
- **Persistence:** SQLite (memory), ChromaDB (vectors)

---

### 4.1.1 Conversation Context System (Updated Nov 1, 2025)

**Purpose:** Maintain conversation continuity, prevent repetition, track topics

**Architecture Changes:**

```
User Speech → STT
    ↓
Transcript + Topic Tracking (NEW)
    ↓
    ├─→ Topic Tracker: Extract keywords/entities
    │   └─→ Weight user input 1.5x (user sets topic)
    ↓
Memory: Episodic Retrieval (ENHANCED)
    ├─→ Retrieve last 20 events (was 3)
    ├─→ Filter by conversation_id
    ├─→ Within 24-hour window
    └─→ Return up to 2000 chars (was 500)
    ↓
Context Assembly (IMPROVED)
    ├─→ Topic summary: "[Conversation context: Topics: X, Y | Entities: A, B]"
    ├─→ Recent summaries (up to 5)
    ├─→ Recent turns with labels:
    │   - "User: [message]"
    │   - "KLoROS: [response]"
    └─→ Newline-separated, chronological
    ↓
LLM Generation
    ↓
Response + Repetition Check (NEW)
    ├─→ Compare to last 10 responses
    ├─→ Calculate similarity (0.0-1.0)
    ├─→ If >75% similar:
    │   - Log warning: "[memory] ⚠️ Repetition detected"
    │   - Store SYSTEM_NOTE event
    └─→ Add to response history
    ↓
Topic Tracking Update (NEW)
    └─→ Extract keywords from response
    ↓
Memory Logging
    └─→ Store with conversation_id
```

**Configuration:**

| Parameter | Old Value | New Value | Impact |
|-----------|-----------|-----------|--------|
| `KLR_MAX_CONTEXT_EVENTS` | 3 | 20 | 6-7x more context |
| `KLR_CONVERSATION_TIMEOUT` | 25s | 60s | Natural pauses OK |
| `KLR_MAX_CONVERSATION_TURNS` | 5 | 20 | Extended conversations |
| Context char limit | 500 | 2000 | 4x more context text |

**New Components:**

1. **RepetitionChecker** (`src/kloros_memory/repetition_prevention.py`)
   - Tracks last N responses (default: 10)
   - Calculates similarity using SequenceMatcher
   - Threshold: 0.75 (75% similarity triggers warning)
   - Logs SYSTEM_NOTE events for repetitions

2. **TopicTracker** (`src/kloros_memory/topic_tracker.py`)
   - Extracts keywords (filters stopwords, min 4 chars)
   - Detects named entities (capitalized words)
   - Maintains frequency counts
   - Weights user inputs 1.5x
   - Generates topic summaries

**Integration Points:**

```python
# MemoryEnhancedKLoROS initialization
self.repetition_checker = RepetitionChecker(
    similarity_threshold=0.75,
    history_size=10
)
self.topic_tracker = TopicTracker(max_keywords=50)

# On conversation start:
self.repetition_checker.clear()
self.topic_tracker.clear()

# On user input:
self.topic_tracker.add_text(user_message, is_user=True)

# On LLM response:
is_repetitive, similar, score = self.repetition_checker.is_repetitive(response)
if is_repetitive:
    # Log warning
self.repetition_checker.add_response(response)
self.topic_tracker.add_text(response, is_user=False)
```

**Performance:**
- Repetition check: O(n) where n=10, ~0.1ms
- Topic extraction: O(m) where m=words, ~0.5ms
- Context retrieval: 20 events vs 3, +2ms query time
- Total overhead: <5ms per turn (negligible)

**User Impact:**
- **Before:** "Context awareness so off I can't hold a proper conversation"
- **After:** 20-turn context window, repetition detection, topic awareness
- **Expected:** 6-7x improvement in conversation quality

---

### 4.2 D-REAM ↔ PHASE Synchronization

**Temporal Coordination:**

```
Timeline (24-hour cycle):

00:00 ─────────────────────────────────────────────────────────── 00:00
  │                                                                 │
  │   D-REAM Evolution (consuming PHASE results)                                  │
  │   ├─ Generation N                                              │
  │   ├─ Generation N+1                                            │
  │   ├─ Generation N+2                                            │
  │   │  ...                                                       │
  │   │                                                            │
03:00 ├─── PHASE Window Start ───────────────────────────         │
  │   │                                                     │      │
  │   │   [D-REAM sleeps]                                   │      │
  │   │                                                     │      │
  │   │   PHASE Execution:                                  │      │
  │   │   ├─ TTS Domain (15 min)                            │      │
  │   │   ├─ Conversation Domain (15 min)                   │      │
  │   │   ├─ RAG Domain (20 min)                            │      │
  │   │   ├─ ToolGen Domain (25 min)                        │      │
  │   │   ├─ CodeRepair Domain (20 min)                     │      │
  │   │   ├─ Planning Domain (10 min)                       │      │
  │   │   ├─ BugInjector Domain (10 min)                    │      │
  │   │   ├─ SystemHealth Domain (10 min)                   │      │
  │   │   ├─ MCP Domain (15 min)                            │      │
  │   │   ├─ Turns Domain (10 min)                          │      │
  │   │   └─ RepairLab Domain (20 min)                      │      │
  │   │                                                     │      │
07:00 ├─── PHASE Window End ────────────────────────────────      │
  │   │                                                            │
  │   │   Signal: /tmp/phase_complete_{timestamp}                 │
  │   │                                                            │
  │   D-REAM Resumes                                              │
  │   ├─ Ingest PHASE results                                     │
  │   ├─ Update fitness landscape                                 │
  │   ├─ Adapt search space                                       │
  │   └─ Continue evolution (Generation N+K)                      │
  │       ...                                                      │
  │                                                                │
00:00 ────────────────────────────────────────────────────────── 00:00
  (Next cycle)
```

**Synchronization Mechanism:**

1. **D-REAM checks time before each generation:**
   ```python
   current_hour = datetime.now().hour
   if 3 <= current_hour < 7:
       print("Entering PHASE window, sleeping...")
       while not phase_complete_signal_exists():
           sleep(60)  # Check every minute
       ingest_phase_results()
   ```

2. **PHASE writes completion signal:**
   ```python
   # At end of run_all_domains.py
   signal_path = f"/tmp/phase_complete_{epoch_id}"
   with open(signal_path, "w") as f:
       json.dump(epoch_report, f)
   ```

3. **D-REAM ingests results:**
   ```python
   def ingest_phase_results():
       signal_files = glob("/tmp/phase_complete_*")
       latest = max(signal_files, key=os.path.getctime)

       with open(latest) as f:
           phase_data = json.load(f)

       # Update fitness history with PHASE metrics
       for domain in phase_data['domain_results']:
           update_fitness_history(
               domain=domain['domain'],
               metrics=domain['metrics']
           )

       # Trigger search space adaptation
       adapt_search_space(phase_data)

       # Clean up signal
       os.remove(latest)
   ```

**Current Status:** Synchronization logic designed but **not implemented**. Requires:
1. Adaptive sleep timer in D-REAM
2. Signal file writing in PHASE
3. Result collapse function in D-REAM

---

### 4.3 PHASE ↔ SPICA Instance Integration

**Data Flow:**

```
PHASE Runner
   ↓
For each domain:
   ↓
   [1] Load domain config (YAML)
   ↓
   [2] Instantiate SPICA derivative
       ├─ Inherits from SpicaBase
       ├─ Domain-specific test logic
       └─ Telemetry infrastructure
   ↓
   [3] Execute tests (via SPICA interface)
       ├─ Test 1 → log_telemetry()
       ├─ Test 2 → log_telemetry()
       └─ Test N → log_telemetry()
   ↓
   [4] Collect results
       ├─ SPICA.get_summary()
       └─ Aggregate metrics
   ↓
   [5] Create snapshot
       ├─ Manifest (config + mutations)
       ├─ Lineage (evolutionary history)
       └─ Source code copy
   ↓
   [6] Write to phase_report.jsonl
       └─ Domain summary + metrics
```

**Uniform Interface:**

All domains expose identical methods:

```python
# Standard SPICA interface
class AnyDomain(SpicaBase):
    def run_all_tests(self, epoch_id: str) -> List[TestResult]:
        """Execute test suite."""

    def get_summary(self) -> dict:
        """Aggregate results."""

    def log_telemetry(self, event_type: str, metrics: dict) -> None:
        """Log structured event (inherited from SpicaBase)."""
```

PHASE runner treats all domains uniformly:

```python
for domain_class in DOMAINS:
    domain = domain_class(config)
    results = domain.run_all_tests(epoch_id)
    summary = domain.get_summary()
    domain_results.append(summary)
```

---

### 4.4 ToolGen ↔ RepairLab ↔ D-REAM Loop

**Meta-Learning Architecture:**

```
┌─────────────────────────────────────────────────────────┐
│              Tool Evolution Meta-Loop                   │
└─────────────────────────────────────────────────────────┘

[1] ToolGen synthesizes tool
       ↓
[2] Validation fails
       ↓
[3] RepairLab attempts repair (Pattern P1)
       ↓
       ├─ Success → Log: P1 successful for error_type_X
       │              ↓
       │              D-REAM fitness += 1 for P1
       │
       └─ Failure → Try Pattern P2
                    ↓
                    (Repeat up to 3 attempts)
                    ↓
                    All failed → Quarantine

[4] D-REAM Evolution Cycle:
    ├─ Patterns as genomes
    ├─ Fitness = success_rate × coverage × generalization
    ├─ Tournament selection
    ├─ Mutation (vary strategy params)
    └─ Crossover (combine successful strategies)

[5] Evolved patterns → RepairLab library update

[6] Future repairs benefit from evolution

Loop: Continuous improvement of repair capability
```

**Communication:**

1. **ToolGen → RepairLab:** Direct function call with failure context
   ```python
   fixed_code = repair_tool(
       code=generated_code,
       error=validation_error,
       context=synthesis_context
   )
   ```

2. **RepairLab → D-REAM:** File-based telemetry
   ```python
   write_jsonl("artifacts/dream/repairlab.jsonl", {
       "pattern_id": "type_coercion_v3",
       "success": True,
       "error_type": "type_mismatch",
       "attempts": 1
   })
   ```

3. **D-REAM → RepairLab:** Updated pattern library
   ```python
   # D-REAM promotes winning patterns
   write_json("repairlab/patterns/promoted.json", {
       "pattern_id": "type_coercion_v3",
       "strategy": {...},
       "fitness": 0.92
   })
   ```

---

### 4.5 System-Wide Telemetry Flow

**Telemetry Architecture:**

```
All Processes
   ↓
Emit JSONL events
   ↓
   ├─→ Voice: turn_complete, memory_logged
   ├─→ D-REAM: generation_complete, promotion, adaptation
   ├─→ PHASE: domain_tested, epoch_complete
   ├─→ SPICA: test_executed, telemetry_event
   └─→ ToolGen/RepairLab: tool_generated, repair_attempted
       ↓
   Aggregated in respective artifact directories:
       ├─ artifacts/dream/{exp_name}.jsonl
       ├─ src/phase/phase_report.jsonl
       ├─ artifacts/dream/repairlab.jsonl
       └─ Optional: Elasticsearch/Grafana for viz
```

**Telemetry Schema (Universal):**

```json
{
  "timestamp": 1730140800.0,
  "event_type": "test_executed",
  "component": "spica_tts",
  "trace_id": "abc123",
  "metrics": {
    "latency_ms": 142,
    "success": true
  },
  "metadata": {
    "domain": "tts",
    "variant_id": "gen42_elite3"
  }
}
```

---

## 5. Data Flow Patterns

### 5.1 Voice Turn Data Flow

```
[User] Microphone
   ↓ (PCM audio samples)
[Voice Loop] Audio capture
   ↓ (np.ndarray, 16kHz mono)
[VAD] Segment detection
   ↓ (primary segment)
[Hybrid STT] Vosk + Whisper
   ↓ (transcript: str)
   ├─→ [Memory] Episodic log (user_turn)
   └─→ [RAG] Query embedding
       ↓ (embedding: np.ndarray)
   [RAG] Hybrid search (BM25 + vector)
       ↓ (top_k documents)
   [LLM] Context assembly + generation
       ↓ (response: str)
   ├─→ [Memory] Episodic log (assistant_turn)
   └─→ [TTS] Piper synthesis
       ↓ (WAV audio)
   [Audio Playback] PipeWire
       ↓
[User] Speaker
```

**Data Transformations:**

- Audio (PCM) → Transcript (string) → Embedding (vector) → Documents (list) → Prompt (string) → Response (string) → Audio (WAV)

**State Updates:**

- Memory DB: INSERT episodes
- ChromaDB: INSERT/UPDATE embeddings
- Telemetry: APPEND JSONL event

---

### 5.2 D-REAM Evolution Data Flow

```
[Generation N]
   ↓
[Population Generator] 24 candidates
   ↓ (List[dict] with params)
[ProcessPoolExecutor] Parallel evaluation
   ↓ (List[metrics])
[Fitness Calculator] 6-dimensional scores
   ↓ (List[fitness])
[Novelty Archive] K-NN novelty scores
   ↓ (List[novelty])
[Selection] Elite + tournament
   ↓ (List[selected])
[Genetic Operators] Crossover + mutation
   ↓ (Next generation params)
[Promotion Writer] Best → artifacts/dream/promotions/
   ↓ (JSON file)
[Telemetry Logger] → artifacts/dream/{exp_name}.jsonl
   ↓ (JSONL event)
[Search Space Adapter] Update dimensions (every 5 gens)
   ↓
[Generation N+1]
```

**Data Persistence:**

- Promotions: JSON (one file per generation)
- Telemetry: JSONL (append-only log)
- Search space state: In-memory (process state)
- Novelty archive: In-memory (K-NN index)

---

### 5.3 PHASE Evaluation Data Flow

```
[Epoch Start] epoch_id = "phase_20251028_030000"
   ↓
[For each domain in Quantized Bursts]
   ↓
   [Domain Instantiation] SPICA derivative
       ↓
   [Test Execution] run_all_tests(epoch_id)
       ├─→ Test 1 → result
       ├─→ Test 2 → result
       └─→ Test N → result
           ↓
   [Telemetry] log_telemetry() per test
       └─→ JSONL: artifacts/dream/{domain}/telemetry.jsonl
           ↓
   [Statistical Analysis] Multi-replica aggregation
       └─→ mean, std, ci95 per test
           ↓
   [Domain Summary] Pass rate + metrics
       ↓
   [Snapshot] Create SPICA instance snapshot
       └─→ experiments/spica/instances/spica-{id}/
           ├─ manifest.json
           ├─ lineage.json
           └─ source.py
           ↓
[Epoch Summary] Aggregate all domains
   ↓
[Write Report] src/phase/phase_report.jsonl
   ↓
[Signal Completion] /tmp/phase_complete_{epoch_id}
```

**Data Outputs:**

- Phase report: JSONL (one line per epoch)
- Domain telemetry: JSONL (per-domain, append-only)
- SPICA snapshots: JSON + Python source (directory per instance)
- Completion signal: JSON (tmp file, consumed by D-REAM)

---

## 6. State Management

### 6.1 Persistent State (Survives Restart)

| State | Location | Format | Owner |
|-------|----------|--------|-------|
| **Memory Episodes** | `~/.kloros/kloros_memory.db` | SQLite | Voice Loop |
| **Vector Embeddings** | `~/.kloros/chroma_data/` | ChromaDB | Voice Loop |
| **RAG Bundle** | `rag_data/rag_store.npz` | NPZ | Voice Loop (read-only) |
| **D-REAM Promotions** | `artifacts/dream/promotions/` | JSON | D-REAM |
| **D-REAM Telemetry** | `artifacts/dream/{exp}.jsonl` | JSONL | D-REAM |
| **PHASE Reports** | `src/phase/phase_report.jsonl` | JSONL | PHASE |
| **SPICA Snapshots** | `experiments/spica/instances/` | JSON + Python | PHASE |
| **Tool Quarantine** | `artifacts/dream/quarantine.json` | JSON | RepairLab |
| **Config Files** | `src/config/*.yaml`, `src/dream/config/*.yaml` | YAML | All (read-only) |

### 6.2 Runtime State (Process Memory)

| State | Owner | Lifecycle | Recovery |
|-------|-------|-----------|----------|
| **Audio Backends** | Voice Loop | Process lifetime | Restart process |
| **LLM Connection** | Voice Loop | Process lifetime | Retry connection |
| **RAG Index** | Voice Loop | Process lifetime | Reload bundle |
| **D-REAM Population** | D-REAM | Generation | Restart from last promotion |
| **Novelty Archive** | D-REAM | Process lifetime | Rebuild from telemetry |
| **Search Space State** | D-REAM | Process lifetime | Reset to config default |
| **PHASE Test State** | PHASE | Epoch | Restart epoch |

### 6.3 State Consistency

**Voice Loop:**
- **Episode writes:** Atomic (SQLite transactions)
- **Vector updates:** Eventually consistent (ChromaDB)
- **Failure:** Worst case = last turn not logged (acceptable)

**D-REAM:**
- **Promotion writes:** Atomic (file write)
- **Telemetry writes:** Append-only (eventual consistency)
- **Failure:** Restart from last promotion, loss of current generation (acceptable)

**PHASE:**
- **Report writes:** Atomic (single line append)
- **Snapshot writes:** Atomic (directory creation)
- **Failure:** Restart epoch from beginning (acceptable, nightly schedule)

**No Distributed Transactions:** All systems use local file-based state with atomic writes. No complex distributed coordination required.

---

## 7. Operational Workflows

### 7.1 Normal Operation (All Systems Active)

```
Day N
00:00 ─┬─ Voice Loop (continuous)
       │  ├─ User interactions
       │  ├─ Memory logging
       │  └─ RAG context
       │
       ├─ D-REAM Evolution (continuous)
       │  ├─ Generation N
       │  ├─ Generation N+1
       │  ├─ Generation N+2
       │  │  ...
       │
03:00 ─┼─ PHASE Window Start
       │  ├─ D-REAM sleeps
       │  └─ PHASE executes (Quantized Bursts, 4 hours)
       │
07:00 ─┼─ PHASE Window End
       │  ├─ Signal: /tmp/phase_complete_*
       │  ├─ D-REAM wakes
       │  ├─ D-REAM ingests results
       │  ├─ Search space adapts
       │  └─ D-REAM resumes (Generation N+K)
       │
       ├─ Voice Loop (continuous)
       │
00:00 ─┴─ (Next day, repeat)
```

**Key Properties:**
- Voice Loop: **Always available** (user-facing)
- D-REAM: **Adaptive** (continuous evolutionary with PHASE window pause)
- PHASE: **Quantized bursts** (nightly 3 AM deep evaluation + 10-min heuristic controller)
- No downtime for users

### 7.2 Cold Start (System Boot)

```
[1] System Boot
    ↓
[2] Start kloros.service (Voice Loop)
    ├─ Load models (Vosk, Whisper, Piper)
    ├─ Connect to Ollama
    ├─ Load RAG bundle
    ├─ Initialize memory DB
    └─ Enter wake word detection
    ↓
[3] (Manual or timer) Start dream.service
    ├─ Load config
    ├─ Initialize search space
    ├─ Load last promotion (if exists)
    └─ Begin evolution
    ↓
[4] (Timer: 3 AM) Start phase-heuristics.timer
    └─ Triggers spica-phase-test.service
        ├─ Execute Quantized Bursts
        └─ Write phase_report.jsonl
    ↓
[5] All systems operational
```

**Startup Time:**
- Voice Loop: ~10-20 seconds (model loading)
- D-REAM: ~5 seconds (config loading)
- PHASE: ~3-4 hours (full test suite)

### 7.3 Graceful Shutdown

```
[1] Shutdown Signal (SIGTERM)
    ↓
[2] Voice Loop
    ├─ Finish current turn (if active)
    ├─ Flush memory DB
    ├─ Close audio devices
    └─ Exit
    ↓
[3] D-REAM
    ├─ Finish current generation (if active)
    ├─ Write final promotion
    ├─ Flush telemetry
    └─ Exit
    ↓
[4] PHASE
    ├─ Finish current domain (if active)
    ├─ Write partial epoch report
    └─ Exit
```

**Recovery:** All systems resume from last persistent state. No data loss (except in-flight operations).

### 7.4 Error Recovery

**Voice Loop Failures:**

| Error | Detection | Recovery |
|-------|-----------|----------|
| Ollama down | HTTP error | Log error, skip turn, continue |
| Whisper fails | Exception | Fall back to Vosk, continue |
| Memory DB locked | SQLite error | Skip logging, continue |
| TTS fails | Process error | Skip synthesis, continue |

**Philosophy:** Non-critical failures should not crash the voice loop. Always prioritize user availability.

**D-REAM Failures:**

| Error | Detection | Recovery |
|-------|-----------|----------|
| Evaluator crash | Exception in ProcessPoolExecutor | Mark candidate as infeasible, continue |
| Timeout | ProcessPoolExecutor timeout | Kill worker, mark infeasible |
| Config invalid | YAML parse error | Exit with error (requires fix) |

**Philosophy:** Generation failures are acceptable (population-based search is robust). Invalid config requires manual intervention.

**PHASE Failures:**

| Error | Detection | Recovery |
|-------|-----------|----------|
| Domain test fails | Exception | Log failure, continue to next domain |
| LLM unavailable | HTTP error | Skip LLM-dependent tests, continue |
| Timeout | Test timeout | Mark test as failed, continue |

**Philosophy:** Best-effort evaluation. Partial epoch reports are useful. Restart epoch next day if critical failure.

### 7.5 Autonomous Exception Recovery (Oct 2025)

**Purpose:** Automatically detect, analyze, and fix runtime failures without human intervention.

**Workflow:**

```
T+0s    Runtime Exception Occurs
        ├─ Example: ModuleNotFoundError: No module named 'src.phase.domains.spica_domain'
        ├─ Exception logged to systemd journal
        └─ System continues (graceful degradation)
        ↓
T+60s   Orchestrator Tick (next cycle)
        ├─ CuriosityCore.generate_questions_from_matrix() called
        ├─ ExceptionMonitor reads last 5 minutes of journalctl logs
        ├─ Parses exception: type=ModuleNotFoundError, module=spica_domain
        └─ Finds similar modules: [spica_system_health, spica_gpu_allocation, spica_rag]
        ↓
T+61s   CuriosityQuestion Generated
        ├─ ID: "codegen.src_phase_domains_spica_domain"
        ├─ Question: "How do I generate spica_domain.py from patterns?"
        ├─ Evidence: ["similar_modules:spica_system_health,spica_gpu_allocation,spica_rag"]
        ├─ Action: propose_fix (direct-build mode)
        ├─ Value: 0.9 (high priority - blocking tournament)
        └─ Cost: 0.4 (moderate - code generation)
        ↓
T+62s   Question Added to Curiosity Feed
        └─ Written to /home/kloros/.kloros/curiosity_feed.json
        ↓
T+120s  Orchestrator Tick (next cycle)
        ├─ Reads curiosity_feed.json
        ├─ Processes question through CuriosityProcessor
        ├─ Recognizes action_class=propose_fix → direct-build mode
        └─ Spawns SPICA instance: spica-8e8bece0
        ↓
T+180s  D-REAM Direct-Build Execution
        ├─ ModuleGenerator.generate_spica_domain() called
        ├─ Reads template modules: spica_system_health.py, spica_gpu_allocation.py
        ├─ Analyzes patterns: SPICADomain class, run_qtime_replicas(), etc.
        ├─ Generates code: /home/kloros/src/phase/domains/spica_domain.py
        └─ Validates: python3 -c "from src.phase.domains.spica_domain import SPICADomain"
        ↓
T+300s  Validation Success
        ├─ Import test passes
        ├─ Module marked as operational
        └─ Question marked as processed in processed_questions.jsonl
        ↓
T+360s  System Resumes Normal Operation
        ├─ Next orchestrator tick attempts tournament again
        ├─ Import succeeds
        ├─ Tournament completes successfully
        └─ 11 SPICA instances created

Total Time: ~6 minutes (exception → fix → validation)
```

**Key Components:**

1. **ExceptionMonitor** (`src/registry/curiosity_core.py:877-1305`)
   - Monitors multiple log sources for exceptions and conversation issues:
     * `/home/kloros/logs/orchestrator/*.jsonl` - System errors (3× threshold)
     * `/home/kloros/logs/dream/*.jsonl` - DREAM experiment errors (3× threshold)
     * `/home/kloros/.kloros/logs/kloros-YYYYMMDD.jsonl` - Chat issues (2× threshold)
   - Extracts: exception type, module name, context, conversation failures
   - Finds similar modules for template analysis
   - Generates CuriosityQuestion with evidence
   - **Thresholds:** 3 occurrences for system errors, 2 for user-facing chat issues

2. **ModuleDiscoveryMonitor** (`src/registry/curiosity_core.py:860-1056`) **[NEW: Oct 2025]**
   - **Proactively scans** `/home/kloros/src` for undiscovered modules
   - Compares against capability registry to find unregistered components
   - Evaluates modules based on:
     * Presence of `__init__.py` (+0.1 value)
     * Documentation (`README.md`) (+0.1 value)
     * File count (≥3 files: +0.1 value)
     * Recency (modified <30 days: +0.15 value)
   - Generates top 5 discoveries per cycle (sorted by value)
   - **Example discoveries:** tool_synthesis (25 files), brainmods, scholar, agentflow
   - Base value: 0.5, max value: 0.95
   - **Status:** Successfully discovered 56 undiscovered modules on first run

3. **MetricQualityMonitor** (`src/registry/curiosity_core.py:1059-1320`) **[NEW: Oct 2025]**
   - **Meta-cognition layer** detecting fake/placeholder metrics in D-REAM tournaments
   - Scans orchestrator logs for suspicious patterns:
     * All tournament candidates producing identical metrics
     * Placeholder values (0.95, 150ms, 300ms, 512MB, etc.)
     * Zero variance across candidates (no actual comparison)
   - Generates HIGH-PRIORITY questions (value: 0.95) when detecting wasted compute
   - **Example:** "I ran 5 investigations but all tournament candidates produced identical metrics. Why am I not actually comparing anything?"
   - Prevents infinite loops of meaningless experiments
   - **Status:** Detected fake metrics in 5 module discovery investigations

4. **CuriosityCore** (`src/registry/curiosity_core.py`)
   - Integrates ExceptionMonitor, TestResultMonitor, ModuleDiscoveryMonitor, and MetricQualityMonitor
   - Routes questions with action_class=propose_fix to direct-build
   - Prioritizes high-value questions (blocking failures and meta-cognition)
   - **Proactive mode:** Runs module discovery and quality checks every observation cycle

5. **TestResultMonitor** (`src/registry/curiosity_core.py:186-400`)
   - Monitors pytest JSON reports at `/home/kloros/logs/pytest_latest.json`
   - Detects test failures, collection errors, and systematic test issues
   - Generates individual questions for ≤3 failures
   - Generates aggregate "systemic issue" questions for >3 failures
   - High-priority questions (value: 0.85-0.90) for blocking test failures

6. **Orchestrator** (`src/kloros/orchestration/orchestrator.py`)
   - Runs every 60 seconds
   - Processes curiosity feed with stale data detection
   - Auto-regenerates feed if capability state is newer than feed
   - Spawns SPICA instances for direct-build
   - Tracks processed questions

5. **ModuleGenerator** (`src/dream/config_tuning/module_generator.py`)
   - Template-based code generation
   - Analyzes existing patterns
   - Generates syntactically correct code
   - Validates imports work

**Exception Types Handled:**

| Exception Type | Detection Pattern | Recovery Action | Threshold |
|---------------|-------------------|-----------------|-----------|
| ModuleNotFoundError | `No module named 'X'` | Generate module from templates | 3× |
| ImportError | `cannot import name 'Y' from 'X'` | Generate missing class/function | 3× |
| FileNotFoundError | `No such file: /path/to/Z` | Generate file from templates | 3× |
| AttributeError | `'X' has no attribute 'Y'` | Add missing attribute to class | 3× |
| Chat ERROR events | ERROR level in chat logs | Investigate conversation failures | 2× |
| Tool call failures | Failed tool invocations | Fix tool integration issues | 2× |
| Response errors | Error language in responses | Improve response quality | 2× |
| Test failures | Pytest JSON report failures | Fix failing tests or code | Individual |

**Performance Metrics:**

- **Detection Latency:** 0-60 seconds (orchestrator tick)
- **Question Generation:** <1 second
- **Code Generation:** 2-5 minutes (direct-build)
- **Validation:** <10 seconds
- **Total Time:** ~8-10 minutes (exception → fix)

**Success Criteria:**

✓ Import test passes
✓ Generated code follows existing patterns
✓ Next system operation succeeds
✓ No manual intervention required

**Failure Modes:**

- No similar modules found → action_class=find_substitute (search for package)
- Generation fails → question stays in feed, retried next tick
- Validation fails → error logged, requires human intervention
- Multiple exceptions → prioritized by value estimate

---

## 8. System Timing and Coordination

### 8.1 Voice Loop Timing (Real-time Constraints)

**Latency Budget:**

```
User stops speaking
   ↓ [+80ms] VAD release time
End of speech detected
   ↓ [+150ms] Vosk transcription (fast path)
Transcript available
   ↓ [+300ms] Whisper verification (parallel, user doesn't wait)
   ↓ [+50ms] RAG retrieval
   ↓ [+1500ms] LLM generation
Response ready
   ↓ [+200ms] TTS synthesis
   ↓ [+playback time] Audio playback
User hears response
```

**Total user-perceived latency:** ~2 seconds (Vosk path dominates)

**Optimization:** Whisper runs in parallel and only replaces Vosk result if:
- Significantly different (similarity < 0.75)
- Higher confidence
- Completes before LLM call

### 8.2 D-REAM Timing (Adaptive)

**Per-Generation Timing:**

```
Generation N start
   ↓ [+5-10s] Population generation (24 candidates)
   ↓ [+30-600s] Parallel evaluation (4 workers)
       └─ Depends on evaluator complexity
   ↓ [+1-2s] Fitness calculation
   ↓ [+1-2s] Novelty scoring
   ↓ [+1s] Selection + genetic operators
   ↓ [+1s] Promotion + telemetry write
Generation N+1 start
```

**Total per generation:** 1-10 minutes (evaluator-dependent)

**Adaptive Sleep (Awaiting Implementation):**
- If fitness improving: Short sleep (BASE_SLEEP = 30s)
- If fitness plateaued: Exponential backoff (up to MAX_SLEEP = 30 min)
- Always check PHASE window before starting generation

### 8.3 PHASE Timing (Scheduled)

**Epoch Duration:**

```
3:00 AM: Epoch start
   ↓ [+15-20 min] TTS Domain
   ↓ [+10-15 min] Turn Management
   ↓ [+20-25 min] RAG Domain
   ↓ [+25-30 min] ToolGen Domain
   ↓ [+15-20 min] Conversation Domain
   ↓ [+20-25 min] Code Repair Domain
   ↓ [+10-15 min] Planning Domain
   ↓ [+10-15 min] Bug Injector Domain
   ↓ [+10-15 min] System Health Domain
   ↓ [+15-20 min] MCP Domain
   ↓ [+20-25 min] RepairLab Domain
   ↓ [+5 min] Epoch summary + reporting
7:00 AM: Epoch complete (target)
```

**Total:** 3-4 hours (parallelization possible in future)

**Timer Configuration:**
```
OnCalendar=*-*-* 03:00:00
```

### 8.4 SPICA Instance Timing

**Instance Lifecycle:**

```
Instantiation: ~1ms (Python class creation)
Test execution: Varies (domain-specific)
Telemetry logging: ~1ms per event (JSONL append)
Manifest creation: ~5ms (JSON serialization + hash)
Snapshot write: ~10-50ms (file I/O)
```

**Retention Cleanup:** ~100ms (scan + delete, triggered after snapshot)

### 8.5 Orchestrator and Autonomous System Timing (Oct 2025)

**Orchestrator Tick Cycle:**

```
T+0s    Orchestrator Tick Start (systemd timer: every 60s)
   ↓ [+100ms] Read curiosity_feed.json
   ↓ [+50ms] Read processed_questions.jsonl
   ↓ [+200ms] Generate questions from CapabilityMatrix
       ├─ Check capability gaps
       ├─ Check performance degradation
       ├─ Check resource pressure
       └─ Check exception logs (ExceptionMonitor)
   ↓ [+500ms] ExceptionMonitor Execution
       ├─ Read JSONL logs (orchestrator, dream, chat)
       ├─ Parse exceptions and chat issues (regex patterns)
       ├─ Find similar modules (glob search)
       └─ Generate CuriosityQuestion objects
   ↓ [+100ms] Question Deduplication
       ├─ Check if already processed
       ├─ Merge similar questions
       └─ Priority sorting
   ↓ [+50ms] Intent Emission
       ├─ Route to D-REAM (direct-build or tournament)
       ├─ Spawn SPICA instances
       └─ Update processed_questions.jsonl
   ↓ [+50ms] Instance Pruning
       ├─ List SPICA instances
       ├─ Sort by creation time
       └─ Delete oldest if count > max (10)
T+60s   Next Tick Start (repeat)
```

**Total per tick:** ~1050ms (1.05 seconds)

**ExceptionMonitor Timing Breakdown:**

| Operation | Typical | Notes |
|-----------|---------|-------|
| JSONL file reading | 50-100ms | Reading orchestrator, dream, chat logs |
| Log parsing | 50-100ms | Regex pattern matching |
| Exception extraction | 10-20ms | Per exception found |
| Chat issue detection | 20-40ms | Scanning conversation logs |
| Similar module search | 50-100ms | Glob pattern matching |
| Question generation | 10-20ms | Per exception/issue |
| **Total** | 400-600ms | For 3-5 exceptions/issues |

**Exception Detection Latency:**

```
Exception occurs at T+0s
   ↓ [0-60s] Wait for next orchestrator tick
   ↓ [+0.5s] ExceptionMonitor detects and processes
   ↓ [+0.1s] Question added to feed
   ↓ [0-60s] Wait for next orchestrator tick
   ↓ [+0.5s] Question processed, SPICA spawned
   ↓ [2-5 min] Direct-build generates code
   ↓ [+10s] Validation

Total: 2-8 minutes (avg 5 minutes)
```

**Orchestrator Load Profile:**

| System State | Tick Duration | CPU % | Memory |
|--------------|---------------|-------|--------|
| Idle (no questions) | 100-200ms | <5% | 50 MB |
| Processing questions | 1-2s | 10-20% | 100 MB |
| Spawning instances | 2-5s | 20-40% | 200 MB |
| Max capacity (10 instances) | 5-10s | 40-60% | 512 MB |

**Resource Limits:**

- **Max SPICA instances:** 10 (oldest pruned)
- **Exception lookback:** 60 minutes
- **Orchestrator tick:** 60 seconds (systemd timer)
- **Memory limit:** 512 MB (OOM protection via systemd)

**Coordination with Other Systems:**

```
Orchestrator (60s ticks)
   ├─ Reads curiosity_feed.json (written by CuriosityCore)
   ├─ Spawns SPICA instances (consumed by D-REAM)
   └─ Updates processed_questions.jsonl (read next tick)

D-REAM (continuous, when spawned)
   └─ Direct-build mode: 2-5 minutes per hypothesis

PHASE (scheduled, 3-7 AM)
   └─ Tournament mode: 3-4 hours per epoch

Voice Loop (continuous)
   └─ No direct coupling with orchestrator
```

---

## 9. Error Handling and Recovery

### 9.1 Error Classification

**Category 1: Transient Errors** (retry acceptable)
- Network timeouts (Ollama, external APIs)
- File locks (SQLite busy)
- Resource exhaustion (temporary)

**Recovery:** Exponential backoff + retry (max 3 attempts)

**Category 2: Permanent Errors** (retry futile)
- Invalid configuration (YAML parse error)
- Missing dependencies (model file not found)
- Incompatible versions (API mismatch)

**Recovery:** Exit with error message (requires manual intervention)

**Category 3: Degraded Mode** (partial functionality acceptable)
- Whisper unavailable (use Vosk only)
- RAG unavailable (skip context)
- Memory DB unavailable (skip logging)

**Recovery:** Log warning, continue with degraded functionality

### 9.2 Self-Healing Infrastructure

**Voice Loop Self-Heal:**

```python
# Example: Ollama connection recovery
if not ollama_available():
    try_reconnect(max_attempts=3, backoff=exponential)
    if still_unavailable():
        log_error("Ollama unavailable, exiting")
        exit(1)  # Let systemd restart
```

**D-REAM Self-Heal:**

```python
# Example: Evaluator timeout recovery
try:
    result = evaluate_with_timeout(candidate, timeout=600)
except TimeoutError:
    log_warning(f"Candidate {candidate_id} timed out")
    result = {"fitness": -inf}  # Mark infeasible
    continue  # Don't crash, robust to individual failures
```

**PHASE Self-Heal:**

```python
# Example: Domain test failure recovery
for domain in domains:
    try:
        result = domain.run_all_tests(epoch_id)
        domain_results.append(result)
    except Exception as e:
        log_error(f"Domain {domain.name} failed: {e}")
        # Continue to next domain (best-effort evaluation)
        continue
```

**Autonomous Code Generation Self-Heal (Oct 2025):**

```python
# Example: ModuleNotFoundError autonomous recovery
try:
    from src.phase.domains.spica_domain import SPICADomain
except ModuleNotFoundError as e:
    # Exception logged to systemd journal
    log_error(f"ModuleNotFoundError: {e}")
    # Continue with degraded functionality (skip this domain)
    # ExceptionMonitor will detect on next orchestrator tick:
    #   1. Parse exception from journal (within 0-60s)
    #   2. Generate CuriosityQuestion with action=propose_fix
    #   3. Spawn SPICA direct-build instance
    #   4. ModuleGenerator creates missing module from templates
    #   5. Validation: import test passes
    #   6. Next system operation succeeds (2-8 minutes total)
    pass  # Graceful degradation
```

**Key Differences from Traditional Self-Heal:**

| Aspect | Traditional | Autonomous Code Gen |
|--------|-------------|---------------------|
| **Detection** | Immediate (exception handler) | Delayed (0-60s orchestrator tick) |
| **Recovery** | Retry/reconnect/fallback | Generate missing code |
| **Time** | Milliseconds to seconds | Minutes |
| **Scope** | Same process/session | Persistent (survives restart) |
| **Human intervention** | May be required | None required |

**Autonomous Recovery Capabilities:**

1. **Module Generation**
   - Detects: `ModuleNotFoundError: No module named 'X'`
   - Action: Generate X.py from similar module templates
   - Example: spica_domain.py generated from spica_system_health.py patterns

2. **Class Generation** (Future)
   - Detects: `ImportError: cannot import name 'Y' from 'X'`
   - Action: Add missing class/function to existing module
   - Example: Add missing method to existing domain class

3. **Configuration Generation** (Future)
   - Detects: `FileNotFoundError: No such file: /path/to/config.yaml`
   - Action: Generate config from default template
   - Example: Create missing SPICA manifest.json

4. **Dependency Resolution** (Future)
   - Detects: `ModuleNotFoundError` with no similar local modules
   - Action: Search PyPI, install package, or create wrapper
   - Example: Install missing python package via pip

5. **Chat Issue Detection** (Oct 2025)
   - Detects: ERROR events, tool failures, response errors in chat logs
   - Threshold: 2 occurrences in 60 minutes (aggressive for UX)
   - Action: Generate investigation questions for conversation failures
   - Example: "Why are tool calls failing in the chat interface?"

6. **Test Failure Monitoring** (Oct 2025)
   - Detects: Pytest failures from `/home/kloros/logs/pytest_latest.json`
   - Action: Generate fix questions (individual for ≤3, aggregate for >3)
   - Priority: High (value: 0.85-0.90) for blocking failures
   - Example: "How do I fix test_gpu_canary collection failures?"

7. **Stale Data Detection** (Oct 2025)
   - Detects: Curiosity feed older than capability state
   - Action: Auto-regenerate feed from updated capability assessments
   - Prevention: Avoids wasting compute on already-fixed problems
   - Example: Detecting that memory.chroma is fixed but feed still asks about it

8. **Proactive Module Discovery** (Oct 30, 2025)
   - Detects: Modules in `/home/kloros/src` not registered in capability registry
   - Action: Generate investigation questions for top 5 discoveries per cycle
   - Evaluation: File count, documentation, recency, __init__.py presence
   - Priority: Medium-High (value: 0.6-0.95) based on signals
   - Example: "Found undiscovered module 'tool_synthesis' with 25 Python files. What does it do?"
   - **Status:** Discovered 56 undiscovered modules including brainmods, scholar, agentflow

9. **Meta-Cognition for Fake Metrics** (Oct 30, 2025)
   - Detects: D-REAM tournaments producing identical/placeholder metrics across all candidates
   - Action: Generate HIGH-PRIORITY questions (value: 0.95) about evaluation quality
   - Patterns: All candidates score 0.95, identical latencies, zero variance
   - Prevention: Stops wasting compute on meaningless tournament iterations
   - Example: "I ran 5 investigations but all candidates produced identical metrics. Why am I not actually comparing anything?"
   - **Status:** Detected fake metrics in 5 module discovery tournaments

10. **File Permission Auto-Fix** (Oct 30, 2025)
    - Detects: Capability failures due to non-writable paths (mode 640/750)
    - Action: chmod 660/770 for databases, chmod 666 for logs
    - Scope: KLoROS-owned files in `.kloros/` and `/var/log/kloros/`
    - **Status:** Fixed 4 capability-blocking permission issues:
      * memory.db (640→660), chroma_data (750→770)
      * tools.db (750→660), structured.jsonl (644→666)
    - Result: 16/17 capabilities now online (was 12/17 before fix)

**Success Rate (Oct 2025):**
- ModuleNotFoundError: 100% (1/1 - spica_domain.py)
- Chat issue detection: Active (2× threshold, 60min window)
- Test failure monitoring: Active (pytest JSON integration)
- Stale data detection: Active (timestamp-based validation)
- Capability fixes: 4/4 (chroma, dream, introspection, dev_agent)
- ImportError: Not yet tested
- FileNotFoundError: Not yet tested
- Other exceptions: Manual intervention required

### 9.3 Failure Scenarios and Recovery

**Scenario 1: Ollama Crashes During Voice Turn**

```
Detection: HTTP connection error
Impact: Current turn fails
Recovery:
  1. Log error
  2. Speak: "I'm having trouble thinking right now"
  3. Return to wake word detection
  4. User restarts Ollama manually
  5. Next turn succeeds
```

**Scenario 2: D-REAM Worker Deadlock**

```
Detection: ProcessPoolExecutor timeout (600s)
Impact: One candidate evaluation fails
Recovery:
  1. Kill worker process
  2. Mark candidate as infeasible (fitness = -inf)
  3. Continue with remaining 23 candidates
  4. Generation completes successfully
```

**Scenario 3: PHASE Domain Test Infinite Loop**

```
Detection: Test timeout (per-test limit)
Impact: One test fails, domain partially evaluated
Recovery:
  1. Kill test process
  2. Mark test as failed
  3. Continue to next test
  4. Domain summary reflects partial results
  5. Epoch completes
```

**Scenario 4: Disk Full During Telemetry Write**

```
Detection: IOError on JSONL write
Impact: Telemetry event lost
Recovery:
  1. Log critical error
  2. Skip telemetry write (non-blocking)
  3. Continue operation
  4. Alert operator (external monitoring)
```

**Scenario 5: ModuleNotFoundError During Tournament (Oct 2025)**

```
Detection: ModuleNotFoundError logged to systemd journal
Impact: Tournament fails, domain skipped
Recovery:
  1. Exception logged (T+0s)
  2. ExceptionMonitor detects on next tick (T+0-60s)
  3. CuriosityQuestion generated with action=propose_fix
  4. Question added to curiosity_feed.json (T+61s)
  5. Orchestrator spawns SPICA direct-build (T+120s)
  6. ModuleGenerator analyzes similar modules
  7. New module generated from templates (T+180s)
  8. Import validation passes (T+190s)
  9. Question marked as processed
  10. Next tournament attempt succeeds (T+360s)

Total recovery time: 6 minutes
Human intervention: None required
Success rate: 100% (when similar modules exist)
```

**Real Example (Oct 29, 2025):**

```
22:36:03 - ModuleNotFoundError: No module named 'src.phase.domains.spica_domain'
22:57:56 - CuriosityQuestion generated: codegen.src_phase_domains_spica_domain
23:02:29 - SPICA instance spawned: spica-8e8bece0 (direct-build)
23:05:00 - Module generated: /home/kloros/src/phase/domains/spica_domain.py
23:07:40 - Tournament succeeded: 11 SPICA instances created
Total: 31 minutes (including orchestrator tick delays)
```

**Scenario 6: Orchestrator Timer Stops (Nov 3, 2025)**

```
Detection: Service health monitor detects inactive timer
Impact: No autonomous improvements, winner deployment paused
Recovery:
  1. ServiceHealthMonitor checks kloros-orchestrator.timer (every 60s potential check)
  2. Detects: inactive + enabled status
  3. Applies cooldown check (5 minutes since last restart)
  4. Restarts service: sudo systemctl restart kloros-orchestrator.timer
  5. Verifies: service becomes active
  6. Logs restart attempt to ~/.kloros/service_health.jsonl
  7. Orchestrator resumes 60s tick cycle
  8. Winner deployment and intent processing resume

Total recovery time: <1 minute (if check runs immediately)
Maximum recovery time: 5-60 minutes (depends on monitoring interval)
Human intervention: None required (autonomous restart)
Success rate: 100% (unless system-wide issues)
```

**Real Example (Nov 3, 2025):**

```
Orchestrator stopped: Nov 1, 21:39 (reason unknown)
Manual detection: Nov 3, 10:40
Service re-enabled: check_my_health.py --heal
Status: ✓ ACTIVE - Ticking every 60 seconds
Processing: 14 winners, 5 intents, 17 curiosity questions
Note: Automated monitoring not yet integrated
```

---

## 10. Performance Characteristics

### 10.1 Latency Profiles

| Operation | Typical | Best Case | Worst Case |
|-----------|---------|-----------|------------|
| **Voice Turn (user-perceived)** | 2s | 1s | 5s |
| - VAD detection | 100ms | 50ms | 500ms |
| - STT (Vosk) | 150ms | 50ms | 300ms |
| - STT (Whisper, parallel) | 400ms | 200ms | 1000ms |
| - RAG retrieval | 100ms | 50ms | 300ms |
| - LLM generation | 1500ms | 500ms | 3000ms |
| - TTS synthesis | 200ms | 100ms | 500ms |
| **D-REAM Generation** | 5min | 1min | 30min |
| - Candidate evaluation | 120s | 10s | 600s |
| - Fitness calculation | 1s | 0.5s | 5s |
| **PHASE Epoch** | 4h | 3h | 5h |
| - Domain execution | 15min | 10min | 30min |
| **SPICA Test** | 30s | 10s | 120s |

### 10.2 Throughput

| System | Throughput | Notes |
|--------|------------|-------|
| **Voice Loop** | ~0.3-0.5 turns/min | Conversational pace |
| **D-REAM** | 6-24 gens/hour | Evaluator-dependent |
| **PHASE** | 1 epoch/day | Scheduled |
| **SPICA Test** | ~100 tests/epoch | Across Quantized Bursts |

### 10.3 Resource Usage

**Voice Loop (Steady State):**
- CPU: 10-30% (1 core)
- Memory: 1-2GB (models loaded)
- GPU: 20-40% (Whisper inference, if available)
- Disk I/O: ~1 MB/min (telemetry + memory)

**D-REAM (Active):**
- CPU: 100% (4 cores, parallel evaluation)
- Memory: 2-4GB (population + workers)
- GPU: 0-80% (evaluator-dependent)
- Disk I/O: ~10 MB/gen (promotions + telemetry)

**PHASE (Active):**
- CPU: 50-100% (1-2 cores)
- Memory: 2-4GB (test execution)
- GPU: 0-80% (domain-dependent)
- Disk I/O: ~500 MB/epoch (reports + snapshots)

### 10.4 Scalability Characteristics

**Voice Loop:**
- **Vertical:** Scales with CPU/GPU (faster inference)
- **Horizontal:** Not applicable (single user, single instance)
- **Bottleneck:** LLM generation (Ollama model size)

**D-REAM:**
- **Vertical:** Scales with CPU cores (parallel evaluation)
- **Horizontal:** Not implemented (could distribute workers)
- **Bottleneck:** Evaluator complexity

**PHASE:**
- **Vertical:** Scales with CPU/GPU (faster test execution)
- **Horizontal:** Could parallelize domains (11-way parallelism possible)
- **Bottleneck:** Sequential domain execution

---

## Conclusion

This Functional Design Document provides a comprehensive view of HOW KLoROS operates, both as individual processes and as an integrated system. Key takeaways:

### Individual Processes
1. **Voice Loop:** Real-time interaction with hybrid STT, RAG-enhanced reasoning, and memory integration
2. **D-REAM:** Continuous population-based evolution with adaptive timing and multi-objective fitness
3. **PHASE:** Scheduled deep evaluation with 11 SPICA-derived domains and statistical rigor
4. **SPICA:** Uniform foundation template providing telemetry, manifest, and lineage for all instances
5. **RAG:** Hybrid retrieval (BM25 + vector) with reciprocal rank fusion and optional reranking
6. **Tool Evolution:** Meta-learning loop (ToolGen → RepairLab → D-REAM) for continuous improvement

### Integration Patterns
- **Voice ↔ RAG ↔ Memory:** In-process, context-enhanced responses
- **D-REAM ↔ PHASE:** File-based synchronization with temporal coordination (Chamber Testing)
- **PHASE ↔ SPICA:** Uniform interface for cross-domain testing
- **ToolGen ↔ RepairLab ↔ D-REAM:** Meta-learning for self-improvement

### Operational Characteristics
- **Dual-timescale optimization:** Fast PHASE loop (temporal dilation testing) + slow D-REAM loop (evolutionary optimization)
- **Loose coupling:** File-based communication, no distributed transactions
- **Progressive degradation:** Non-critical failures don't crash the system
- **Adaptive behavior:** Search space adapts based on fitness history

### Current Implementation Status
- **Production Ready:** Voice loop, SPICA framework, tool evolution, telemetry
- **Awaiting Deployment:** D-REAM (disabled, awaiting adaptive timer + PHASE integration)
- **Future Enhancement:** PHASE parallelization, distributed D-REAM workers, advanced self-healing

---

**Document Version:** 1.0
**Date:** October 28, 2025
**Status:** Complete and verified against source code and System Audit documentation
**Next Review:** When architectural changes occur or new subsystems are added
