# ChemBus Scheduler Migration Guide

**Migration Status**: Phase 1 - Reconnaissance Complete
**Created**: 2025-11-17
**Purpose**: Document migration from hardcoded timer loops to ChemBus-based event-driven scheduling

## Overview

KLoROS currently uses individual timer loops in each daemon (`while True: time.sleep(N)`). This creates:
- **Distributed timing logic**: Each daemon has its own polling loop
- **Hidden coordination**: Timing relationships not visible on ChemBus
- **Fixed intervals**: Cannot adapt to system load or conditions
- **Debug complexity**: Must check logs of each daemon to see when things fire

The target architecture centralizes scheduling through ChemBus, making all timing **observable**, **adaptive**, and **event-driven**.

## Current State: Hardcoded Timer Loops

### Daemon Inventory

| Daemon | File | Interval | Purpose | ChemBus Integration |
|--------|------|----------|---------|---------------------|
| **introspection** | `introspection_daemon.py:364` | 5s | Proactive capability scanning | ✅ Emits signals |
| **curiosity_core_consumer** | `curiosity_core_consumer_daemon.py:240` | 60s | Proactive question generation | ✅ Emits signals |
| **action_consumer** | `action_consumer_daemon.py` | 300s (5min) | Action processing | ⚠️ Partial |
| **investigation_consumer** | `investigation_consumer_daemon.py` | 300s (5min) | Investigation processing | ⚠️ Partial |
| **shadow** | `shadow_daemon.py` | 60s | D-REAM shadow evaluation | ⚠️ Partial |
| **tournament_consumer** | `tournament_consumer_daemon.py` | 15s | Tournament evaluation | ⚠️ Partial |
| **semantic_dedup_consumer** | `semantic_dedup_consumer_daemon.py` | 5s | Deduplication processing | ⚠️ Partial |
| **ledger_writer** | `ledger_writer_daemon.py` | 1s | Observability ledger writes | ✅ Event-driven |
| **chembus_historian** | `chembus_historian_daemon.py` | 1s (+ backoff) | ChemBus history archival | ✅ Event-driven |
| **decay** | `decay_daemon.py` | Variable | Memory decay processing | ❓ Unknown |

### Timing Pattern Analysis

**High-Frequency (1-5s intervals)**:
- Introspection: 5s proactive scanning
- Semantic dedup: 5s batch processing
- Ledger writer: 1s polling (event-driven subscriber)
- ChemBus historian: 1s polling (event-driven subscriber)

**Medium-Frequency (15-60s intervals)**:
- Curiosity core: 60s proactive generation
- Shadow daemon: 60s D-REAM evaluation
- Tournament: 15s batch processing

**Low-Frequency (5min intervals)**:
- Action consumer: 300s queue processing
- Investigation consumer: 300s investigation processing

## Target Architecture: ChemBus Scheduler

### Core Components

#### 1. Central Scheduler Daemon

**File**: `kloros/orchestration/scheduler_daemon.py` (NEW)

**Responsibilities**:
- Emit periodic trigger signals on configurable intervals
- Adapt intervals based on system load (affective state)
- Maintain observable schedule via ChemBus
- Support signal: `Q_SCHEDULE_TICK`

**Configuration**:
```python
SCHEDULE_CONFIG = {
    "introspection_scan": {
        "interval": 5.0,
        "signal": "Q_TRIGGER_INTROSPECTION",
        "ecosystem": "introspection",
        "adaptive": False  # Fixed interval
    },
    "curiosity_generation": {
        "interval": 60.0,
        "signal": "Q_TRIGGER_CURIOSITY",
        "ecosystem": "curiosity",
        "adaptive": True  # Can slow down under load
    },
    "action_processing": {
        "interval": 300.0,
        "signal": "Q_TRIGGER_ACTION_PROCESSING",
        "ecosystem": "queue_management",
        "adaptive": True
    },
    # ... etc
}
```

#### 2. Daemon Refactor Pattern

**Before (Timer-Based)**:
```python
def run(self):
    while self.running:
        wait_for_normal_mode()
        
        now = time.time()
        if now - self.last_scan_ts >= self.scan_interval:
            self._run_scan_cycle()
            self.last_scan_ts = now
        
        time.sleep(1)  # Polling loop
```

**After (Event-Driven)**:
```python
def __init__(self):
    # Subscribe to schedule trigger
    self.trigger_sub = ChemSub(
        topic="Q_TRIGGER_INTROSPECTION",
        on_json=self._on_trigger,
        zooid_name="introspection_daemon",
        niche="introspection"
    )

def _on_trigger(self, msg: Dict[str, Any]):
    """React to scheduler trigger signal."""
    self._run_scan_cycle()

def run(self):
    while self.running:
        wait_for_normal_mode()
        time.sleep(1)  # Keep-alive loop only
```

### New ChemBus Signals

| Signal | Purpose | Interval | Emitted By | Subscribed By |
|--------|---------|----------|------------|---------------|
| `Q_TRIGGER_INTROSPECTION` | Trigger introspection scan | 5s | scheduler_daemon | introspection_daemon |
| `Q_TRIGGER_CURIOSITY` | Trigger question generation | 60s | scheduler_daemon | curiosity_core_consumer |
| `Q_TRIGGER_ACTION_PROCESSING` | Trigger action queue processing | 300s | scheduler_daemon | action_consumer |
| `Q_TRIGGER_INVESTIGATION` | Trigger investigation processing | 300s | scheduler_daemon | investigation_consumer |
| `Q_TRIGGER_SHADOW_EVAL` | Trigger D-REAM shadow eval | 60s | scheduler_daemon | shadow_daemon |
| `Q_TRIGGER_TOURNAMENT` | Trigger tournament evaluation | 15s | scheduler_daemon | tournament_consumer |
| `Q_TRIGGER_SEMANTIC_DEDUP` | Trigger deduplication batch | 5s | scheduler_daemon | semantic_dedup_consumer |
| `Q_SCHEDULE_TICK` | Heartbeat signal (internal) | 1s | scheduler_daemon | (monitoring) |

### Adaptive Scheduling

**Affective State Integration**:

The scheduler subscribes to affective state signals and adjusts intervals:

```python
def _on_affect_signal(self, msg: Dict[str, Any]):
    """Adjust schedule based on affective state."""
    signal_type = msg.get("signal")
    
    if signal_type == "AFFECT_CRITICAL_FATIGUE":
        # Slow down non-critical tasks
        self._adjust_interval("curiosity_generation", 0.5)  # 2x slower
        self._adjust_interval("action_processing", 0.5)
        logger.info("[scheduler] Slowed schedule due to critical fatigue")
    
    elif signal_type == "AFFECT_WELLBEING_HIGH":
        # Speed up exploration
        self._adjust_interval("curiosity_generation", 1.5)  # 1.5x faster
        logger.info("[scheduler] Accelerated schedule due to high wellbeing")
```

## Migration Strategy

### Phase 1: Reconnaissance ✅

- [x] Identify all daemons with hardcoded timer loops
- [x] Document current intervals and purposes
- [x] Design ChemBus scheduler architecture
- [x] Create this migration guide

### Phase 2: Create Scheduler Daemon 📋

**Tasks**:
1. Create `scheduler_daemon.py` with configurable intervals
2. Implement signal emission for each trigger type
3. Add affective state subscription for adaptive scheduling
4. Create systemd service `kloros-scheduler.service`
5. Test scheduler in isolation (emit signals, verify timing)

**Deliverables**:
- `kloros/orchestration/scheduler_daemon.py`
- `config/scheduler_config.toml` (optional external config)
- systemd service file
- Unit tests for timing accuracy

### Phase 3: Refactor Daemons (Incremental) 📋

**Migration Order** (by risk/complexity):

1. **Start with ledger_writer** (already event-driven, easiest)
2. **introspection_daemon** (well-isolated, high-frequency)
3. **semantic_dedup_consumer** (simple, high-frequency)
4. **curiosity_core_consumer** (medium complexity, medium-frequency)
5. **shadow_daemon** (D-REAM interaction, medium-frequency)
6. **tournament_consumer** (tournament logic, medium-frequency)
7. **action_consumer** (queue management, low-frequency)
8. **investigation_consumer** (complex, low-frequency)

**Per-Daemon Refactor Process**:
1. Add `ChemSub` subscription to trigger signal
2. Move timer logic to `_on_trigger()` callback
3. Remove `if now - last_ts >= interval` logic
4. Keep minimal `while True: time.sleep(1)` keep-alive loop
5. Test signal-driven execution matches old timing
6. Monitor for regressions (missed cycles, timing drift)

### Phase 4: Adaptive Scheduling (Optional) 📋

**Add Intelligence**:
- Affective state-based interval adjustment
- Load-based backpressure (slow down if queue is full)
- Priority-based scheduling (critical signals get faster intervals)
- Jitter to prevent thundering herd (slight randomization)

### Phase 5: Deprecate Timer Loops 📋

**Cleanup**:
1. Remove all `time.sleep(interval)` logic from daemons
2. Verify all timing comes from scheduler
3. Remove `scan_interval`, `proactive_interval` parameters
4. Update documentation

## Benefits of ChemBus Scheduling

### Observability

**Before**: Must check each daemon's logs to see when things fire
```
# introspection logs
[16:30:05] Starting scan cycle #1234

# curiosity_core logs
[16:31:00] Proactive question generation triggered
```

**After**: All timing visible on ChemBus
```
# Single ChemBus stream shows all coordination
[16:30:05] Q_TRIGGER_INTROSPECTION emitted
[16:30:05] introspection_daemon received trigger
[16:31:00] Q_TRIGGER_CURIOSITY emitted
[16:31:00] curiosity_core_consumer received trigger
```

### Adaptivity

**Current**: Fixed intervals regardless of system state
- Introspection scans every 5s even during critical fatigue
- Curiosity generates questions every 60s even when overloaded

**With Scheduler**: Dynamic adjustment based on affective state
- Critical fatigue → Slow down non-critical tasks
- High wellbeing → Accelerate exploration
- Memory pressure → Reduce question generation frequency

### Coordination

**Current**: Implicit timing relationships
- Investigation consumer runs every 5 minutes
- Action consumer also runs every 5 minutes
- No guarantee they don't fire at same time (resource spike)

**With Scheduler**: Explicit coordination
- Stagger intervals to prevent resource spikes
- Synchronize related tasks (e.g., scan → generate → process)
- Add jitter to prevent thundering herd

### Testing

**Current**: Must run daemons for minutes to test timing
```bash
# Start daemon, wait 60 seconds, check if it fired
python -m src.kloros.orchestration.curiosity_core_consumer_daemon
# ... wait ... 
# Check logs to verify timing
```

**With Scheduler**: Inject signals to test immediately
```python
# Test daemon's reaction to trigger signal without waiting
chem_pub.emit(signal="Q_TRIGGER_CURIOSITY", ecosystem="curiosity")
# Verify daemon reacted correctly (instant feedback)
```

## Code Locations

### Daemons to Refactor

| File | Timer Logic Location | Interval | Priority |
|------|---------------------|----------|----------|
| `introspection_daemon.py` | Line 364 | 5s | High (well-isolated) |
| `curiosity_core_consumer_daemon.py` | Line 240 | 60s | Medium |
| `action_consumer_daemon.py` | TBD | 300s | Low (complex) |
| `investigation_consumer_daemon.py` | TBD | 300s | Low (complex) |
| `shadow_daemon.py` | TBD | 60s | Medium |
| `tournament_consumer_daemon.py` | TBD | 15s | Medium |
| `semantic_dedup_consumer_daemon.py` | TBD | 5s | High (simple) |

### New Files

| File | Purpose | Status |
|------|---------|--------|
| `kloros/orchestration/scheduler_daemon.py` | Central scheduler | ❌ To be created |
| `config/scheduler_config.toml` | Schedule configuration | ❌ Optional |
| `kloros-scheduler.service` | Systemd service | ❌ To be created |

## Testing Checklist

- [ ] Scheduler emits signals at correct intervals
- [ ] Scheduler responds to affective state changes
- [ ] Daemons react to trigger signals correctly
- [ ] No timing drift over long runs (hours)
- [ ] No missed cycles under load
- [ ] Graceful degradation if scheduler fails
- [ ] Observable schedule via ChemBus monitoring
- [ ] Scheduler respects maintenance mode
- [ ] Signal storms prevented (backpressure)
- [ ] All daemons converted from timer loops
- [ ] Performance impact measured (should be negligible)

## Risks & Mitigation

### Risk: Single Point of Failure

**Issue**: If scheduler daemon crashes, all timing stops

**Mitigation**:
- Systemd auto-restart for scheduler daemon
- Daemons fall back to local timer if no signals for 2x interval
- Monitor scheduler health via `Q_SCHEDULE_TICK` heartbeat

### Risk: Signal Storm

**Issue**: Scheduler might flood ChemBus with signals

**Mitigation**:
- Rate limiting in ChemPub (already exists)
- Backpressure detection (monitor queue depths)
- Adaptive slowdown if subscribers lag

### Risk: Timing Drift

**Issue**: Event-driven timing might drift from clock time

**Mitigation**:
- Scheduler uses wall-clock time (not delta accumulation)
- Periodic clock synchronization
- Monitoring for interval deviation

### Risk: Migration Regression

**Issue**: Converting daemons might break timing

**Mitigation**:
- Migrate one daemon at a time
- A/B test: Run old timer + new signal side-by-side
- Monitor for missed cycles or timing changes

### Risk: Complexity Increase

**Issue**: Adds another daemon to manage

**Mitigation**:
- Scheduler is simple (just emit signals on timers)
- Benefits (observability, adaptivity) outweigh cost
- Centralized scheduling easier to debug than distributed timers

## Decision: Proceed or Wait?

### Arguments for Proceeding

- Aligns with ChemBus-first architecture
- Makes timing observable and debuggable
- Enables adaptive scheduling (affective state integration)
- Simplifies daemon code (less timing logic)
- Better testability (inject signals)

### Arguments for Waiting

- Current system is stable
- Timer loops are simple and predictable
- Adds complexity (new daemon, new failure mode)
- No urgent pain point being solved
- Other migrations (intents → signals) just completed

### Recommendation

**WAIT** - Let system run stable for 1-2 weeks after intent migration

Reasons:
1. Just completed major migration (intent files → ChemBus signals)
2. No urgent timing-related issues
3. Current timer loops work reliably
4. Prefer stability before next architectural change
5. Can revisit when adaptive scheduling becomes necessary

This is a **Phase 2** migration - valuable but not urgent.

## Next Steps (When Ready)

1. Create `scheduler_daemon.py` prototype
2. Test with single daemon (introspection)
3. Run parallel for 48h (old timer + new signal)
4. Compare timing accuracy, resource usage
5. If successful, proceed with full migration
6. If issues, document learnings and defer

## References

- **CHEMBUS_INTENT_MIGRATION.md**: Completed intent → signal migration
- **CHEM_PROXY_MIGRATION.md**: ChemBus proxy consolidation
- **chem_bus_v2.py**: ChemSub/ChemPub wrapper classes
- **affective_signals.py**: Affective state → signal mapping

---

Last Updated: 2025-11-17
Author: Claude (claude-sonnet-4-5-20250929)
Status: Phase 1 Complete - Reconnaissance Done, Awaiting Decision
