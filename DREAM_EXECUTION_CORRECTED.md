# D-REAM Execution Model - CORRECTED

**Date:** 2025-10-27  
**Status:** Architecture clarified and corrected

---

## Core Principle

**D-REAM runs continuously with back-to-back tournaments, no artificial delays.**

Sequential execution through all domains, natural pacing from tournament duration, maximum efficiency with zero dead time.

---

## Correct Execution Flow

```python
while True:
    # Check for PHASE window
    if is_phase_window():  # 3-7 AM
        sleep_until_phase_ends()
        # When PHASE completes, resume immediately
    
    # Run all enabled experiments sequentially
    for experiment in enabled_experiments:
        run_tournament(experiment)
        # ↑ Takes as long as it takes
        # ↓ Immediately proceed to next
    
    # Cycle complete, immediately loop back
    # NO sleep
    # NO gaps
    # NO overlaps
```

---

## Execution Characteristics

### Sequential Processing
- Tournament N **completes fully** before Tournament N+1 starts
- Only **one tournament active** at a time
- No process overlaps or race conditions

### Domain-Agnostic Duration
- Conversation domain takes 5 minutes? Fine.
- RAG domain takes 20 minutes? Fine.
- System Health takes 2 minutes? Fine.
- **Each tournament takes as long as it needs**

### Zero Dead Time
- As soon as tournament finishes → immediately start next
- No artificial delays between cycles
- No gaps where system sits idle
- Maximum throughput naturally achieved

### Natural Pacing
- Tournament execution time provides pacing
- If all domains quick → fast cycles
- If domains slow → slower cycles
- System self-regulates based on workload

---

## What Was Wrong

### ❌ Fixed Sleep Argument
```bash
--sleep-between-cycles 180  # 3 minutes of DEAD TIME
```

**Problem:**
- Cycle finishes at 10:05:00
- System waits until 10:08:00 to start next cycle
- **3 minutes wasted** doing nothing
- Multiplied across 24 hours = hours of lost productivity

### ❌ "Adaptive" Timer Complexity
I was overthinking this with ideas like:
- Sleep based on fitness convergence
- Sleep based on recent tournament duration
- Complex heuristics and timing logic

**Reality:** None of this is needed. Just run continuously.

---

## Correct Configuration

### D-REAM Service
```ini
[Service]
Type=simple
User=kloros
Group=kloros
WorkingDirectory=/home/kloros
Environment="PYTHONPATH=/home/kloros:/home/kloros/src"
Restart=always

ExecStart=/home/kloros/.venv/bin/python3 -m src.dream.runner \
  --config /home/kloros/src/dream/config/dream.yaml \
  --logdir /home/kloros/logs/dream \
  --epochs-per-cycle 4 \
  --max-parallel 2

# NO --sleep-between-cycles argument
# Continuous execution, zero artificial delays
```

### Execution Timeline Example
```
10:00:00 - Start Cycle 1
10:00:05 - Conversation tournament (5 min)
10:05:05 - RAG tournament (20 min)
10:25:05 - System Health tournament (2 min)
10:27:05 - TTS tournament (3 min)
10:30:05 - Cycle 1 complete
10:30:05 - Start Cycle 2 immediately ← No gap!
10:30:10 - Conversation tournament...
...
02:59:55 - Current tournament completes
03:00:00 - PHASE window detected
03:00:00 - Sleep until PHASE ends
07:00:00 - PHASE window ends
07:00:00 - Resume D-REAM immediately
```

---

## PHASE Integration

### PHASE Window (3-7 AM)
- D-REAM detects PHASE window
- Completes current tournament (no mid-evaluation interruption)
- Pauses evolutionary loop
- Sleeps in 60-second chunks (allows clean shutdown)

### PHASE Execution
- Triggered by systemd timer at 3:00 AM
- Runs comprehensive QTIME tests across all SPICA domains
- Expected duration: 1-4 hours
- Writes completion signal when done

### D-REAM Resume
- Currently: waits until 7 AM regardless
- **Future enhancement**: detect completion signal, resume early
- When resumed: immediately continues tournaments

---

## Still Required: SPICA Architecture

**Critical:** All domains must be SPICA derivatives before re-enabling.

### Current State (Wrong)
```python
# Standalone domain classes
class ConversationDomain:
    def evaluate(...): ...

class RAGDomain:
    def evaluate(...): ...
```

### Required State
```python
# SPICA base template
class Spica:
    """Foundational template with state, telemetry, manifest, lineage."""
    def __init__(self, config): ...
    def spawn_instance(self): ...
    def record_telemetry(self): ...

# Domains inherit from SPICA
class SpicaConversation(Spica):
    def evaluate(...): ...

class SpicaRAG(Spica):
    def evaluate(...): ...
```

**Why:** Ensures structural compatibility, consistent telemetry, reproducibility.

---

## Implementation Checklist

### 1. ✅ Architecture Documented
- Continuous back-to-back execution model
- SPICA as foundational template
- No artificial delays

### 2. ⬜ Update D-REAM Service
- Remove `--sleep-between-cycles` from ExecStart
- Verify continuous execution in code (already implemented)
- Test that tournaments run sequentially

### 3. ⬜ SPICA Base Class
- Create `/home/kloros/src/spica/base.py`
- Define template methods: state, telemetry, manifest, lineage
- Document interface contract

### 4. ⬜ Migrate Domains to SPICA Derivatives
- Conversation → SpicaConversation(Spica)
- RAG → SpicaRAG(Spica)
- SystemHealth → SpicaSystemHealth(Spica)
- TTS → SpicaTTS(Spica)
- MCP → SpicaMCP(Spica)
- Planning → SpicaPlanning(Spica)
- CodeRepair → SpicaCodeRepair(Spica)
- BugInjector → SpicaBugInjector(Spica)

### 5. ⬜ Update D-REAM Runner
- Ensure spawns SPICA instances, not bare domains
- Verify telemetry reads from SPICA schema

### 6. ⬜ Update PHASE Tests
- Ensure all tests operate on SPICA derivatives
- Verify QTIME replicas work with SPICA instances

### 7. ⬜ CI Enforcement
- Add pytest plugin to block non-SPICA tests
- Fail builds if domains bypass SPICA template

### 8. ⬜ Re-enable Services
- Start dream.service (continuous D-REAM)
- Enable PHASE timer (3 AM nightly)
- Monitor logs for correct execution

---

## Testing Plan

### 1. Sequential Execution Test
- Enable dream.service
- Monitor logs for 1 hour
- Verify tournaments run back-to-back with no gaps
- Check timestamps show immediate progression

### 2. PHASE Pause Test
- Manually set time to 2:59 AM (or wait for actual PHASE)
- Verify D-REAM completes current tournament then pauses
- Verify logs show "PHASE window active, sleeping"
- Verify resumes at 7:00 AM

### 3. SPICA Enforcement Test
- Attempt to run test with non-SPICA domain
- Verify error/failure
- Verify all active tests use SPICA derivatives

---

## Summary

**D-REAM Execution:**
- Continuous, back-to-back tournaments
- Sequential processing (no overlaps)
- Zero artificial delays
- Natural pacing from workload
- Pauses only during PHASE window (3-7 AM)

**Before Re-enabling:**
- SPICA base class must exist
- All domains must inherit from SPICA
- D-REAM service updated (remove sleep argument)
- CI enforcement in place

**Current Status:** All services disabled until SPICA migration complete.
