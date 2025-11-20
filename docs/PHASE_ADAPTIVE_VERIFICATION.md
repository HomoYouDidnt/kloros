# PHASE Adaptive System Verification

## System Architecture

PHASE (Phased Heuristic Adaptive Scheduling Engine) is now a fully adaptive cognitive orchestrator with a closed-loop feedback system.

### Components

1. **Heuristic Controller** (`/home/kloros/src/heuristics/controller.py`)
   - Analyzes recent PHASE runs (24h lookback)
   - Computes signals: Yield (Y), Cost (C), Stability (S), Novelty (N), Promotion (P)
   - Applies UCB1 scoring for adaptive test selection
   - Determines phase type: LIGHT/DEEP/REM
   - Emits read-only hints.json every 10 minutes

2. **PHASE Orchestrator** (`/home/kloros/scripts/dream_overnight.sh`)
   - Reads hints.json at startup
   - Applies phase-specific strategies
   - Adjusts parallelism based on workers_hint
   - Writes observability summary.json on completion

3. **Systemd Timer** (`phase-heuristics.timer`)
   - Runs controller every 10 minutes
   - Generates fresh hints based on recent data
   - Logs to `/home/kloros/logs/heuristics_controller.log`

## Verification Steps

### 1. Controller Functionality ✓

**Verified:** Controller runs successfully and generates valid hints.json

### 2. Timer Scheduling ✓

**Verified:** Timer installed, enabled, and scheduled correctly (runs every 10 minutes)

### 3. Hints Integration ✓

**Verified:** All hints read and applied correctly

### 4. Phase Type Strategies ✓

#### LIGHT Mode
- **Trigger:** avg_cost > 60 minutes
- **Strategy:** Quick diagnostics (last_failed + promotion only)

#### DEEP Mode (Default)
- **Strategy:** All passes enabled
- **Use Case:** Full integration testing

#### REM Mode
- **Trigger:** novelty > 0.6 AND promotion_acceptance > 0.7
- **Strategy:** Comprehensive testing for D-REAM meta-learning

### 5. Signal Computation

- **Yield (Y):** failures_detected / runtime_hours
- **Cost (C):** avg_runtime_minutes / trial
- **Stability (S):** 1 - flake_rate
- **Novelty (N):** unique_failures / total_failures
- **Promotion (P):** candidates_accepted / evaluations_run

### 6. Observability

Each PHASE run writes: manifest.json, results.jsonl, metrics.jsonl, summary.json

## Status

**PHASE Adaptive System: OPERATIONAL**

System complete: 100% of specified functionality implemented and verified.
