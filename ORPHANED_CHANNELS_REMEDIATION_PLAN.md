# Orphaned ChemBus Channels - Remediation Plan
**Created**: 2025-11-18 22:45 EST
**Status**: Investigation Complete → Ready for Implementation

---

## Investigation Summary

Investigation of 16 orphaned channels revealed:
1. **FALSE POSITIVES** (10 channels) - Consumers exist but integration-monitor has AST parsing bug
2. **TRUE ORPHANS** (6 channels) - No consumers implemented

---

## Category 1: FALSE POSITIVES - Integration Monitor Bug

### Issue: Keyword Argument Parsing

**Root Cause**: Integration monitor's FlowAnalyzer only extracts positional arguments from ChemSub() calls, but production code uses keyword arguments:
```python
# Production code (NOT detected):
ChemSub(topic="AFFECT_HIGH_RAGE", on_json=handler, ...)

# What parser expects (positional):
ChemSub("AFFECT_HIGH_RAGE", handler, ...)
```

**False Positive Channels** (10 total):
1. AFFECT_HIGH_RAGE → kloros-system-healing.service (ACTIVE)
2. AFFECT_MEMORY_PRESSURE → kloros-cognitive-actions.service (ACTIVE)
3. AFFECT_LOBOTOMY_INITIATED → (investigate producer - may be test-only)
4. AFFECT_LOBOTOMY_RESTORED → (investigate producer - may be test-only)
5. AFFECT_RESOURCE_STRAIN → both services subscribe (ACTIVE)
6. AFFECT_CONTEXT_OVERFLOW → kloros-cognitive-actions.service (ACTIVE)
7. AFFECT_TASK_FAILURE_PATTERN → kloros-cognitive-actions.service (ACTIVE)
8. AFFECT_REPETITIVE_ERROR → kloros-system-healing.service (ACTIVE)
9. (need to verify remaining signals)

**Remediation**: Fix integration_monitor_daemon.py FlowAnalyzer to parse keyword arguments

---

## Category 2: TRUE ORPHANS - Missing Consumers

### Observability & Telemetry (6 orphaned)

**HEARTBEAT**
- **Status**: TRUE ORPHAN
- **Producers**: 2 files
- **Recommendation**: Implement health-monitor daemon or add to orchestrator-monitor
- **Priority**: Medium
- **Impact**: Cannot track component liveness without heartbeat consumer

**metric, timer_start, timer_stop**
- **Status**: TRUE ORPHAN
- **Producers**: 1 file each
- **Recommendation**: Either implement telemetry aggregator daemon OR remove emitters if not actively used
- **Priority**: Low (cleanup)
- **Impact**: Observability data discarded, but no active monitoring dashboard exists

**logger_init, logger_close**
- **Status**: TRUE ORPHAN
- **Producers**: 1 file each
- **Recommendation**: Remove emitters (logging lifecycle coordination not needed)
- **Priority**: Low (cleanup)
- **Impact**: None - these were experimental signals

---

### Curiosity Priority Queues (4 - STATUS UNCLEAR)

**Q_CURIOSITY_INVESTIGATE, Q_CURIOSITY_HIGH, Q_CURIOSITY_LOW, Q_CURIOSITY_ARCHIVED**
- **Status**: CONDITIONAL - depends on KLR_USE_PRIORITY_QUEUES environment variable
- **Investigation Needed**: Check if `KLR_USE_PRIORITY_QUEUES=1` is set
  - If YES → need to wire up investigation_consumer to these channels
  - If NO → these are dormant code paths, can be ignored (using legacy file-based feed)
- **Priority**: High (if env var enabled) / None (if disabled)

---

### Core System Signals (2 - INVESTIGATE)

**HEAL_REQUEST**
- **Status**: UNCLEAR - kloros-heal-executor service exists and running
- **Investigation Needed**: Check if heal-executor subscribes with correct topic name
- **Recommendation**: Audit heal executor subscription - may be channel name mismatch
- **Priority**: High
- **Impact**: Self-healing may be broken if heal executor isn't receiving requests

**OBSERVATION**
- **Status**: TRUE ORPHAN (likely)
- **Producers**: 1 file
- **Investigation Needed**: Check if streaming_observation_handler.py exists and what it subscribes to
- **Recommendation**: Either remove OBSERVATION emitter or fix handler subscription
- **Priority**: Medium

---

## Remediation Tasks

### Task 1: Fix Integration Monitor (IMMEDIATE)

**File**: `/home/kloros/src/kloros/monitors/integration_monitor_daemon.py`

**Change**: Update FlowAnalyzer.visit_Call() to extract `topic=` keyword argument:

```python
# ChemSub() - consumer
elif (isinstance(node.func, ast.Name) and node.func.id == 'ChemSub'):
    signal = None

    # Try positional arg first
    if node.args:
        signal = self._extract_string_value(node.args[0])

    # Try keyword arg 'topic='
    if not signal:
        for keyword in node.keywords:
            if keyword.arg == 'topic':
                signal = self._extract_string_value(keyword.value)
                break

    if signal:
        self.flows.append({
            'type': 'consumer',
            'channel': signal,
            'file': str(self.file_path),
            'line': node.lineno
        })
```

**Expected Result**: After fix, affective signals (AFFECT_*) should no longer show as orphaned

---

### Task 2: Investigate LOBOTOMY Signals (LOW PRIORITY)

- Check if AFFECT_LOBOTOMY_INITIATED/RESTORED are only emitted from test files
- If test-only: document as expected
- If production: determine if emergency_lobotomy.py needs consumer integration

---

### Task 3: Check HEAL_REQUEST Channel (HIGH PRIORITY)

**Investigation**:
1. Check kloros-heal-executor.service logs for ChemSub topic
2. Verify it subscribes to "HEAL_REQUEST" (not "heal_request" or variant)
3. If mismatch found, fix either emitter or consumer to align

**Files to check**:
- Producer: `/home/kloros/src/consciousness/system_healing_subscriber.py:54`
- Consumer: Find heal executor daemon source

---

### Task 4: Check KLR_USE_PRIORITY_QUEUES (HIGH PRIORITY)

**Command**:
```bash
grep -r "KLR_USE_PRIORITY_QUEUES" /home/kloros/ --include="*.env" --include="*.service"
```

**Action**:
- If `KLR_USE_PRIORITY_QUEUES=1`: Wire up investigation consumer to Q_CURIOSITY_* channels
- If `KLR_USE_PRIORITY_QUEUES=0` or unset: Document these as dormant legacy code

---

### Task 5: OBSERVATION Channel (MEDIUM PRIORITY)

**Investigation**:
1. Find streaming_observation_handler.py
2. Check what ChemBus topic it subscribes to
3. Either fix topic mismatch or remove OBSERVATION emitter if deprecated

---

### Task 6: Telemetry Signals Cleanup (LOW PRIORITY)

**Signals**: metric, timer_start, timer_stop, logger_init, logger_close, HEARTBEAT

**Decision Tree**:
1. Is there an active telemetry dashboard or monitoring system?
   - YES → Implement telemetry aggregator daemon to consume these
   - NO → Remove emitters to reduce noise

2. For HEARTBEAT specifically:
   - If health monitoring is needed → add to orchestrator-monitor
   - If not needed → remove emitters

---

## Implementation Priority

### Phase 1 (IMMEDIATE - Today)
1. Fix integration-monitor keyword argument parsing
2. Restart integration-monitor and regenerate report to see real orphans

### Phase 2 (HIGH - This Week)
3. Investigate HEAL_REQUEST channel mismatch
4. Check KLR_USE_PRIORITY_QUEUES and handle Q_CURIOSITY_* channels
5. Investigate OBSERVATION channel

### Phase 3 (MEDIUM - Next Week)
6. Decide on telemetry infrastructure (implement aggregator vs cleanup)
7. Investigate LOBOTOMY signals

### Phase 4 (LOW - Backlog)
8. Clean up unused telemetry emitters if no monitoring system planned

---

## Success Criteria

1. Integration-monitor correctly detects active consumers
2. Orphaned channels report reduced from 16 to <6
3. All affective signals (AFFECT_*) confirmed as properly consumed
4. HEAL_REQUEST channel verified as working or fixed
5. Curiosity queue status clarified (active vs dormant)

---

## Notes

- **Discovery**: Integration-monitor AST parser had blind spot for keyword arguments
- **Good News**: Most "orphaned" affective signals actually have active consumers!
- **Services Confirmed Active**:
  - kloros-system-healing.service (consuming AFFECT_HIGH_RAGE, AFFECT_RESOURCE_STRAIN, AFFECT_REPETITIVE_ERROR)
  - kloros-cognitive-actions.service (consuming AFFECT_MEMORY_PRESSURE, AFFECT_CONTEXT_OVERFLOW, AFFECT_TASK_FAILURE_PATTERN, AFFECT_RESOURCE_STRAIN)
