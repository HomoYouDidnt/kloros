# D-REAM and PHASE Execution Model

**Date:** 2025-10-27  
**Status:** Architecture clarified, implementation in progress

---

## Execution Flow

### D-REAM (Continuous Evolutionary Loop)

**Purpose:** Continuous evolutionary experimentation across domains

**Behavior:**
1. Runs sequentially through SPICA-derived domain instances
2. Generates candidate variants from current search space
3. Evaluates candidates via quick tournaments
4. Promotes winners based on fitness
5. Adapts search space based on performance
6. Uses **adaptive timer** (not fixed intervals) based on:
   - Tournament duration
   - Fitness convergence rate
   - Resource availability
   - Recent success rate

**Pause Condition:**
- Detects PHASE window (scheduled deep evaluation time)
- Completes current tournament (no mid-evaluation interruption)
- **PAUSES** evolutionary loop
- Waits for PHASE completion signal

### PHASE (Deep Evaluation - Hyperbolic Time Chamber)

**Purpose:** Comprehensive, high-fidelity evaluation with QTIME replicas

**Behavior:**
1. Triggered at scheduled time (e.g., 3:00 AM)
2. Runs exhaustive tests across all SPICA-derived domains
3. Uses QTIME replicas (epochs × slices × replicas) for statistical rigor
4. Generates detailed metrics, fitness data, insights
5. **Collapses results** back into the system:
   - Updates fitness baselines
   - Provides new metrics for D-REAM's next cycle
   - Identifies promising search space regions
   - Flags underperforming variants
6. Signals completion to D-REAM

**Current Schedule:** 3:00 AM - 7:00 AM (4-hour window)

### D-REAM Resumes

**After PHASE completes:**
1. D-REAM receives completion signal
2. Ingests new PHASE metrics/fitness data
3. Updates search space based on PHASE insights
4. Resumes evolutionary loop with enriched context

---

## Current Implementation Status

### ✅ Already Implemented
- **D-REAM pause/resume** (`is_phase_window()`, `sleep_until_phase_ends()`)
- **PHASE window detection** (3-7 AM hardcoded)
- **Sleep in 60-second chunks** (allows clean shutdown)
- **Sequential domain execution** (D-REAM iterates through experiments)

### ❌ Missing / Needs Fixing
- **Adaptive timer** (currently uses `--sleep-between-cycles` fixed argument)
- **PHASE completion signaling** (D-REAM just waits until 7 AM, doesn't check for actual completion)
- **Result collapse integration** (no code to ingest PHASE metrics into D-REAM)
- **SPICA architecture enforcement** (domains not derived from SPICA template)
- **phase-heuristics.timer removed** (was incorrectly set to 10-minute intervals)

---

## Correct Timer Architecture

### D-REAM Service (Continuous)
```ini
[Service]
Type=simple
Restart=always
ExecStart=/home/kloros/.venv/bin/python3 -m src.dream.runner \
  --config /home/kloros/src/dream/config/dream.yaml \
  --logdir /home/kloros/logs/dream \
  --epochs-per-cycle 4 \
  --max-parallel 2
  # NO --sleep-between-cycles (adaptive internally)
```

**Behavior:**
- Runs continuously (not on timer)
- Self-regulates with adaptive timing
- Pauses when detecting PHASE window
- Resumes after PHASE completes

### PHASE Timer (Scheduled Deep Evaluation)
```ini
[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true
```

**Behavior:**
- Triggers at 3:00 AM
- Runs comprehensive QTIME tests
- Expected duration: 1-4 hours
- Writes completion signal when done

### ❌ WRONG: phase-heuristics.timer
```ini
[Timer]
OnUnitActiveSec=10min  # ← WRONG: treats PHASE as monitoring service
```

**Why wrong:**
- PHASE is not a monitoring/heuristics service
- PHASE is a scheduled deep evaluation event
- 10-minute intervals would constantly interrupt D-REAM

---

## Implementation Requirements

### 1. Adaptive D-REAM Timer
- Remove `--sleep-between-cycles` fixed argument
- Implement adaptive timing based on:
  - Recent tournament durations (rolling average)
  - Fitness improvement rate (longer pause if converging)
  - Resource utilization (shorter pause if underutilized)
  - Time until next PHASE (scale down as PHASE approaches)

### 2. PHASE Completion Signal
- PHASE writes completion flag: `/tmp/phase_complete_<timestamp>`
- D-REAM checks for flag every 60 seconds during sleep
- When flag detected:
  - Load PHASE results from `/home/kloros/out/test_runs/latest/`
  - Ingest metrics into fitness history
  - Update search space adaptation
  - Resume evolutionary loop

### 3. Result Collapse Integration
- PHASE results format: `phase_results.json`
  ```json
  {
    "timestamp": 1730000000,
    "domains_tested": ["conversation", "rag", "system_health"],
    "metrics": {
      "domain": {"fitness": 0.85, "insights": [...]}
    },
    "promoted_variants": [...],
    "search_space_recommendations": {...}
  }
  ```
- D-REAM ingestion:
  - Update `_fitness_hist` with PHASE baseline
  - Adapt search space from recommendations
  - Log integration event to `.jsonl`

### 4. SPICA Architecture Enforcement
- All domain tests must instantiate SPICA derivatives
- D-REAM spawns `Spica<Domain>` instances, not bare domains
- PHASE evaluates SPICA-derived instances only
- CI gate: fail if non-SPICA tests detected

---

## Files to Modify

1. **`/home/kloros/src/dream/runner/__main__.py`**
   - Implement adaptive timer logic
   - Add PHASE completion detection
   - Add result collapse integration

2. **`/home/kloros/src/phase/runner.py`** (or equivalent)
   - Write completion signal at end
   - Output standardized `phase_results.json`

3. **`/etc/systemd/system/dream.service`**
   - Remove `--sleep-between-cycles` argument
   - Ensure `Restart=always` for continuous operation

4. **`/etc/systemd/system/phase-nightly.timer`** (rename from spica-phase-test.timer)
   - Keep 3:00 AM schedule
   - Update description to reflect "nightly deep evaluation"

5. **`/home/kloros/src/spica/base.py`** (create)
   - SPICA base class template
   - Domain derivatives inherit from this

---

## Testing Plan

1. **Adaptive Timer Test**
   - Run D-REAM for 2 hours
   - Verify sleep intervals adapt based on performance
   - Check logs for timing decisions

2. **Pause/Resume Test**
   - Manually trigger PHASE window (set time to 2:59 AM)
   - Verify D-REAM pauses at cycle boundary
   - Create fake completion signal
   - Verify D-REAM resumes before 7 AM

3. **Result Collapse Test**
   - Run PHASE with known results
   - Verify D-REAM ingests metrics correctly
   - Check search space adaptation applied

4. **SPICA Enforcement Test**
   - Attempt to run non-SPICA domain
   - Verify CI gate blocks execution
   - Verify all domains inherit from SPICA

---

## Next Steps (Priority Order)

1. ✅ **Disable incorrect timers** (already done)
2. ⏳ **Document architecture** (this document)
3. ⬜ **Implement adaptive timer** in D-REAM
4. ⬜ **Add PHASE completion signaling**
5. ⬜ **Implement result collapse integration**
6. ⬜ **Create SPICA base class**
7. ⬜ **Migrate domains to SPICA derivatives**
8. ⬜ **Add CI enforcement**
9. ⬜ **Re-enable D-REAM service** (continuous)
10. ⬜ **Re-enable PHASE timer** (3 AM nightly)

---

**Status:** All tests currently disabled. Do not re-enable until SPICA migration and adaptive timer implementation complete.
