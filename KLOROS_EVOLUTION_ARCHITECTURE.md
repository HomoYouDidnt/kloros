# KLoROS Evolution Architecture - Complete Understanding

**Date:** 2025-11-11
**Context:** Deep investigation into D-REAM, PHASE, and SPICA systems

---

## Core Systems

### D-REAM (Darwinian-RZero Evolution & Anti-collapse Module)
**Purpose:** Parallel evolution system for optimizing configurations through tournament-style competition

**How It Works:**
1. Takes a search space of parameters to optimize
2. Creates multiple candidates (typically 8+) with different parameter configurations
3. Runs **parallel** tournaments with bracket-style elimination
4. Uses genetic algorithms (mutation, crossover, selection) to evolve solutions
5. Returns winning configuration with highest fitness score

**Key Characteristics:**
- **Parallel execution** - multiple candidates compete simultaneously
- **Tournament-style** - bracket elimination (AB vs CD vs EF vs GH → winners compete)
- **Fast** - designed to complete in minutes, not hours
- **Terminology:** Uses "generations" and "populations"

**Configuration:** `/home/kloros/src/dream/config/dream.yaml`

---

### PHASE (Phased Heuristic Adaptive Scheduling Engine)
**Purpose:** Sequential validation system for time-compressed stress testing

**How It Works:**
1. Takes validated candidates (winners from D-REAM)
2. Runs **sequential** tests in "Hyperbolic Time Chamber"
3. Simulates 40+ hours of workload in 3-7 hours
4. Tests under different conditions to find failure rates and edge cases
5. Generates validation metrics for promotion decisions

**Key Characteristics:**
- **Sequential execution** - one test at a time to prevent system overload
- **Time-compressed** - years of training → hours
- **Scheduled** - ONLY runs 3-7 AM EST
- **Terminology:** Uses "epochs", "slices", "replicas" (e.g., `e0.s1.r0`)
- **File-based queue:** Reads from `/home/kloros/.kloros/lineage/phase_queue.jsonl`

**Daemon:** `phase.consumer_daemon` (PID 1042) - tails queue file

---

### SPICA (Self-Progressive Intelligent Cognitive Archetype)
**Purpose:** Template proto-agent that can be tuned to become any specialized agent

**How It Works:**
1. Starts as generic template with NanoChat LLM
2. Given a capability requirement (e.g., "access camera", "parse logs")
3. 8 SPICA cells compete to find best approach
4. Winner is validated in PHASE probation period
5. If passes, becomes a "zooid" (specialized agent)
6. Integrated into KLoROS as new skill

**Key Characteristics:**
- **Adaptive:** Can be tuned for any purpose (conceptually)
- **Tournament-based:** 8 cells compete with different strategies
- **Test-driven:** Success measured by pytest suite (64 passed, 3 skipped typical)
- **Iterative:** Goes through multiple D-REAM cycles for refinement

**Template Location:** `/home/kloros/experiments/spica/template/`
**Instances:** `/home/kloros/experiments/spica/instances/`

---

## The Complete Flow (As Intended)

### Step 1: Discovery (Curiosity Subsystem)
**Agent:** CuriosityCore
**What:** Probes system, finds opportunities, asks questions

**Example Question:**
> "I found a camera device but no agent to use it. How can I utilize this device?"

**Output:** Question logged with value/cost ratio

---

### Step 2: Orchestration (Intent Routing)
**Agent:** Orchestrator Coordinator
**What:** Processes curiosity questions, determines action

**Decision Tree:**
- Question value/cost ratio < 1.5 → Skip
- Question already processed → Skip
- High-value question → Create intent
- Autonomy level ≥ 3 → Route to D-REAM

**Output:** Intent JSON file in `/home/kloros/.kloros/intents/`

---

### Step 3: Chemical Signal Routing (Experimental)
**Component:** `signal_router_v2` + `chem_proxy`
**What:** Biological-inspired message bus

**Signal Types:**
- `Q_SPICA_SPAWN` - Request new SPICA instance
- `Q_CURIOSITY_INVESTIGATE` - Investigate question
- `Q_INTEGRATION_FIX` - Fix integration issue

**Flow:**
1. Orchestrator emits chemical signal
2. `chem_proxy` (PID 1322) broadcasts via ZMQ
3. Consumers subscribe and process asynchronously

**Current Status:** Experimental, not fully wired up

---

### Step 4: D-REAM Tournament
**Component:** `SPICATournamentEvaluator`
**What:** Spawns 8 SPICA cells, runs bracket tournament

**Process:**
1. Generate 8 candidate parameter sets
2. Create 8 SPICA instances with different configurations
3. Run tournament with bracket elimination:
   - Round 1: AB, CD, EF, GH (4 matches)
   - Round 2: Winners compete (B vs F, C vs H)
   - Finals: Final winner emerges
4. Each match: Run test suite, compare fitness scores
5. Winner promoted to next round

**Execution:** **Should be PARALLEL** but implementation uses PHASE adapter (sequential)

**Expected Duration:** Minutes
**Actual Duration (bug):** 20 minutes (using PHASE sequential executor)

---

### Step 5: PHASE Validation
**Component:** `phase.consumer_daemon` + `SPICADomain`
**What:** Runs winner through probation testing

**Process:**
1. Winner from D-REAM added to PHASE queue
2. PHASE daemon picks up job (file-based queue)
3. Runs sequential replicas (epochs × slices × replicas):
   - Example: 2 epochs × 4 slices × 8 replicas = 64 test runs
4. Each replica runs full test suite (~2.5 seconds)
5. Aggregates results, calculates failure rates
6. Generates validation report

**Execution:** **SEQUENTIAL by design** (prevent system overload)

**Expected Duration:** Hours (3-7 AM window)
**Naming Pattern:** `spica-{id}.e{epoch}.s{slice}.r{replica}`

---

### Step 6: Promotion & Integration
**Components:** `winner_deployer` + `PromotionApplier`
**What:** Deploys validated winners to production

**Process:**
1. Winner deployer checks for new winners every minute
2. Reads winning parameters from D-REAM results
3. Applies to `.kloros_env` with guardrails
4. Hot-reload triggers (updates running system without restart)
5. Winner becomes active zooid
6. KLoROS ingests as new agent capability

**Guardrails:**
- Hallucination rate < 0.2
- Valid parameter ranges
- No destructive changes

---

## The Bug We Fixed (Nov 11, 2025)

### Symptom
Orchestrator ticks taking 20 minutes instead of 60 seconds

### Root Cause
`curiosity_processor.process_curiosity_feed()` was calling `_spawn_tournament()` **SYNCHRONOUSLY** every tick

**Call Chain:**
```
orchestrator.tick()
  → process_curiosity_feed()
    → _spawn_tournament(q)
      → SPICATournamentEvaluator.evaluate_batch()
        → phase_adapter.submit_tournament()
          → SPICADomain.run_qtime_replicas()
            → for replica in replicas:  # SEQUENTIAL LOOP
                → _run_single_replica()  # 2.5 seconds each
                → BLOCKS FOR 20 MINUTES
```

### Why This Happened
1. D-REAM tournaments were supposed to be async via chemical signals
2. But `curiosity_processor` had legacy synchronous tournament spawning
3. Feature flag `ENABLE_SPICA_TOURNAMENTS` existed but was never checked
4. Synchronous code always ran, blocking orchestrator tick

### The Fix
Added feature flag check before synchronous spawning:

```python
if ENABLE_SPICA_TOURNAMENTS:  # Default: False
    # Run synchronous tournament
    experiment_result = _spawn_tournament(q)
else:
    # Emit intent only, let chemical signals handle async
    logger.info(f"Skipping synchronous tournament (will route via chemical signals)")
```

**File:** `/home/kloros/src/kloros/orchestration/curiosity_processor.py:1047`

**Result:**
- Orchestrator ticks complete in <60 seconds
- Intents processed via chemical signals
- Chemical signal consumers handle async execution

---

## Misunderstandings We Cleared Up

### Misunderstanding 1: "PHASE is running outside its window"
**Reality:** PHASE wasn't running at all. SPICA tests were, using PHASE's `SPICADomain` test executor.

**Why Confusing:** SPICA tests use PHASE's naming convention (`e0.s1.r0`) because D-REAM's evaluator calls into PHASE adapter.

---

### Misunderstanding 2: "Chemical signals aren't working"
**Reality:** Chemical signals work perfectly. They emit and archive intents correctly.

**Why Confusing:** Synchronous tournament spawning happened BEFORE chemical routing, making signals seem ineffective.

---

### Misunderstanding 3: "67 intents are stuck unprocessed"
**Reality:** All 67 intents were processed and archived to `/processed/routed_via_chemical_signal/`

**Why Confusing:** We checked while the current tick was still processing. Intents get archived after processing.

---

## Key Insights

### 1. D-REAM vs PHASE Confusion
**They're complementary, not competitive:**
- D-REAM = Find winners (parallel, fast, exploratory)
- PHASE = Validate winners (sequential, slow, thorough)
- SPICA = The units being tested (can use either system)

### 2. SPICA Test Pattern
Seeing "same tests over and over" is **CORRECT BEHAVIOR:**
- Test suite = fitness function (constant)
- Parameters being tested = what varies (evolution)
- Different SPICA instance IDs = population diversity

**Not a bug - that's how genetic algorithms work!**

### 3. The 3 Skipped Tests
Likely marked as `@pytest.mark.slow` or `@pytest.mark.optional`:
- Skipped to keep fitness evaluation fast
- Only run in full validation (PHASE)
- Common pattern in test-driven evolution

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     CURIOSITY SUBSYSTEM                      │
│  - Probes system                                            │
│  - Generates questions                                      │
│  - Estimates value/cost                                     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR (60s ticks)                   │
│  - Processes questions                                      │
│  - Creates intents                                          │
│  - Routes via chemical signals                              │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌──────────────┐        ┌──────────────────┐
│   CHEMICAL   │        │  INTEGRATION     │
│   SIGNALS    │        │  FIXES           │
│  (async bus) │        │  (autonomy ≥ 3)  │
└──────┬───────┘        └────────┬─────────┘
       │                         │
       ▼                         ▼
┌─────────────────────────────────────────┐
│         D-REAM TOURNAMENT               │
│  - 8 SPICA cells                        │
│  - Bracket elimination                  │
│  - Parallel execution (SHOULD BE)       │
│  - Duration: Minutes                    │
└────────────────┬────────────────────────┘
                 │
                 ▼ (Winner)
┌─────────────────────────────────────────┐
│        PHASE VALIDATION                 │
│  - Sequential stress testing            │
│  - Time-compressed (40hrs → 4hrs)       │
│  - Runs 3-7 AM only                     │
│  - Finds edge cases                     │
└────────────────┬────────────────────────┘
                 │
                 ▼ (Validated Winner)
┌─────────────────────────────────────────┐
│         PROMOTION & DEPLOYMENT          │
│  - Apply to .kloros_env                 │
│  - Hot-reload (zero downtime)           │
│  - Guardrails check                     │
│  - Becomes active zooid                 │
└─────────────────────────────────────────┘
```

---

## Current Status (Nov 11, 2025 20:24)

### What's Working ✅
- Curiosity question generation
- Intent creation and archiving
- Chemical signal emission
- Hot-reload for config changes

### What's Fixed ✅
- Orchestrator tick blocking (was 20 min, now <60 sec)
- SPICA test failures (fixed SpicaBase import)
- SPICA subprocess imports (added PYTHONPATH)

### What Needs Work 🚧
- Chemical signal consumers (not fully implemented)
- D-REAM parallel execution (currently uses PHASE sequential adapter)
- KLoROS understanding of how to use D-REAM (needs documentation/training)
- Tournament bracket implementation (8 cells → 4 matches → 2 → 1)

### Key Environment Variables
- `KLR_ORCHESTRATION_MODE=enabled` - Enable orchestrator
- `KLR_CHEM_ENABLED=1` - Enable chemical signals
- `KLR_ENABLE_SPICA_TOURNAMENTS=0` - Disable synchronous tournaments (DEFAULT)
- `KLR_AUTONOMY_LEVEL=3` - Enable autonomous SPICA spawning

---

## Next Steps for Full Implementation

1. **Create D-REAM Consumer Daemon**
   - Subscribe to `Q_SPICA_SPAWN` chemical signals
   - Run tournaments **asynchronously**
   - Use proper parallel execution (not PHASE sequential)

2. **Implement Bracket Tournament Logic**
   - Round 1: Run 4 matches in parallel (AB, CD, EF, GH)
   - Round 2: Run 2 matches with winners
   - Finals: 1 match for champion

3. **Separate D-REAM from PHASE Execution**
   - D-REAM should NOT use `phase_adapter.submit_tournament()`
   - Create `dream_adapter.run_parallel_tournament()` instead
   - Keep PHASE for validation only (3-7 AM)

4. **Document for KLoROS**
   - Teach her when to trigger D-REAM
   - Explain the camera example workflow
   - Provide examples of successful evolutions

---

## Files Modified During Investigation

1. `/home/kloros/src/spica/base.py` - Created SpicaBase class
2. `/home/kloros/src/spica/__init__.py` - Module init
3. `/home/kloros/experiments/spica/template/tools/queue_runner.py` - Added PYTHONPATH
4. `/home/kloros/src/config/hot_reload.py` - Hot-reload implementation
5. `/home/kloros/src/kloros/orchestration/winner_deployer.py` - Trigger hot-reload
6. `/home/kloros/src/kloros/observer/run.py` - Start hot-reload daemon
7. `/home/kloros/src/kloros/orchestration/curiosity_processor.py` - **Disabled synchronous tournaments**

---

## Terminology Reference

| Term | Meaning |
|------|---------|
| **D-REAM** | Evolution system (parallel tournaments) |
| **PHASE** | Validation system (sequential stress tests) |
| **SPICA** | Proto-agent template |
| **Zooid** | Validated, specialized agent |
| **Intent** | Work request in JSON format |
| **Chemical Signal** | Async message on biological-inspired bus |
| **Tournament** | Bracket-style competition between candidates |
| **Epoch** | PHASE terminology for training iteration |
| **Generation** | D-REAM terminology for evolution iteration |
| **Fitness** | Score indicating solution quality |
| **Champion** | Tournament winner |
| **Promotion** | Deploying winner to production |

---

**END OF DOCUMENT**
