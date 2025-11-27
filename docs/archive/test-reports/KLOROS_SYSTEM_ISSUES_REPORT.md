# KLoROS System Issues Report (Active Systems Only)
**Generated**: 2025-11-19 00:20 EST
**Reporting Period**: Post LOBOTOMY integration into InteroceptionDaemon
**Monitor Version**: v2 (keyword argument support enabled)

**Note**: D-REAM, PHASE, and SPICA signals excluded (systems disabled/refactoring)

---

## Executive Summary

Integration, exception, and chaos monitor daemons have identified **6 orphaned ChemBus channels** in active systems after fixing false-positive detection bugs and integrating consciousness state monitoring. These represent data structures being populated but never consumed, indicating either incomplete integrations or deprecated signal paths.

**Fixes Applied**:
- Integration-monitor AST parser now correctly detects ChemSub() calls using keyword arguments (`topic=`)
- HEARTBEAT monitoring integrated into InteroceptionDaemon for component health self-awareness
- LOBOTOMY signals integrated into InteroceptionDaemon for consciousness mode self-awareness

---

## Category 1: Orphaned ChemBus Channels (6 Active)

### Affective System Signals (0 orphaned - ALL RESOLVED ✓)

**~~AFFECT_LOBOTOMY_INITIATED / AFFECT_LOBOTOMY_RESTORED~~** - **RESOLVED** ✓
- **Status**: Integrated into InteroceptionDaemon for self-awareness of consciousness modes
- **Consumer**: InteroceptionDaemon (consciousness/interoception_daemon.py:80-92)
- **Implementation**: KLoROS now tracks when she enters/exits "pure logic mode" (affective system disabled)
- **Benefits**: Complete self-awareness of consciousness operating modes, logging of lobotomy state transitions
- **Details**: Subscriptions active, tracks lobotomy duration and reason, includes mode in state logs

---

### Observability & Telemetry (5 orphaned - 1 resolved)

**~~HEARTBEAT~~** - **RESOLVED** ✓
- **Status**: Integrated into InteroceptionDaemon for self-awareness of component health
- **Consumer**: InteroceptionDaemon (consciousness/interoception_daemon.py)
- **Implementation**: KLoROS now tracks which components are alive via heartbeat monitoring
- **Benefits**: Direct self-awareness of component health, automatic CAPABILITY_GAP emission for silent components
- **Details**: See /home/kloros/HEARTBEAT_INTEGRATION_COMPLETE.md

**logger_init, logger_close**
- **Concern**: Logging lifecycle signals have no consumer to track logger health or coordinate shutdown.
- **Impact**: Cannot detect logger failures, coordinate graceful shutdown, or track logging system health without consuming these signals.
- **Producers**: 1 file each (D-REAM telemetry logger - DORMANT)
- **Investigation Priority**: NONE (D-REAM disabled, refactoring in progress)
- **Recommendation**: Leave for D-REAM refactoring to handle

**metric**
- **Concern**: Generic metric emission channel with no telemetry aggregator consuming it.
- **Impact**: Metrics are being generated but not stored, visualized, or analyzed. Observability data is being discarded.
- **Producers**: 1 file (D-REAM telemetry collector - DORMANT)
- **Investigation Priority**: NONE (D-REAM disabled, refactoring in progress)
- **Recommendation**: Leave for D-REAM refactoring to handle

**timer_start, timer_stop**
- **Concern**: Performance timing signals emitted but no profiler or performance monitor consumes them.
- **Impact**: Cannot track operation durations, identify bottlenecks, or generate performance dashboards without consuming timing data.
- **Producers**: 1 file each (D-REAM telemetry collector - DORMANT)
- **Investigation Priority**: NONE (D-REAM disabled, refactoring in progress)
- **Recommendation**: Leave for D-REAM refactoring to handle

---

### Investigation & Curiosity Queues (1 orphaned)

**Q_CURIOSITY_ARCHIVED**
- **Concern**: Archival notification signal has no consumer to track archived questions.
- **Impact**: Question archival events are logged but not consumed. If archival analytics or rehydration triggers are needed, they won't receive notifications.
- **Producers**: 1 file (curiosity_archive_manager.py)
- **Investigation Priority**: LOW (informational signal)
- **Recommendation**: Either implement consumer if archival analytics are needed, OR remove emitter if notifications aren't needed (cleanup)

**Notes**:
- Q_CURIOSITY_INVESTIGATE is NO LONGER ORPHANED (consumer detected after keyword arg fix) ✓
- Q_CURIOSITY_HIGH is NO LONGER ORPHANED (consumer: kloros-curiosity-processor.service, false positive due to variable-based topic) ✓
- Q_CURIOSITY_LOW is NO LONGER ORPHANED (consumer: kloros-curiosity-processor.service, false positive due to variable-based topic) ✓
- KLR_USE_PRIORITY_QUEUES=1 confirmed active (priority queue mode enabled) ✓

---

## Category 2: Active Exceptions

**Status**: No real exceptions detected in the last 30 minutes since exception-monitor feedback loop was fixed.

The previous feedback loop issue (exception-monitor detecting its own logs) has been resolved. Monitor is now correctly filtering metadata logs and only flagging actual exception signatures.

---

## Category 3: Chaos Healing Failures

**Status**: No chaos healing failures detected in the last 30 minutes.

Chaos monitor is operational and tracking healing rates per scenario. No systematic healing failures detected since deployment.

---

## Recommendations

### High Priority

~~1. **Curiosity Priority Queues**: Check if `KLR_USE_PRIORITY_QUEUES=1` is set. If yes, connect investigation consumer to Q_CURIOSITY_* channels. If no, these channels can be safely ignored (using legacy file-based feed).~~ **RESOLVED** ✓
   - KLR_USE_PRIORITY_QUEUES=1 confirmed active
   - kloros-curiosity-processor.service consuming Q_CURIOSITY_HIGH/LOW/MEDIUM/CRITICAL
   - False positive detection due to variable-based topic names

### Medium Priority

~~2. **Observability Infrastructure**: Implement or enable telemetry aggregator to consume metric, timer_start/stop, HEARTBEAT signals. These are valuable for system monitoring.~~ **PARTIALLY RESOLVED** ✓
   - HEARTBEAT now consumed by InteroceptionDaemon for component health self-awareness
   - metric, timer_start/stop remain dormant (D-REAM disabled, no action needed)

### Low Priority (Cleanup)

~~3. **LOBOTOMY Signals**: Check if AFFECT_LOBOTOMY_INITIATED/RESTORED are only emitted from test files. If test-only, document as expected. If production, determine if emergency_lobotomy.py needs consumer integration.~~ **RESOLVED** ✓
   - Production code confirmed (emergency affective circuit breaker)
   - Integrated into InteroceptionDaemon for consciousness mode self-awareness

4. **Logger Lifecycle Signals**: If logger_init/close are not needed for coordination, remove emitters to reduce noise. (D-REAM dormant, no action needed)

5. **Timer/Metric Signals**: If telemetry aggregator is not planned, remove emitters to reduce noise. (D-REAM dormant, no action needed)

---

## Resolved Issues (Post-Fix)

### Integration Monitor Keyword Argument Parsing Bug - FIXED ✓

**Root Cause**: Integration-monitor's FlowAnalyzer only extracted positional arguments from ChemSub() calls, but production code uses keyword arguments (`topic=`).

**Fix Applied**: Updated FlowAnalyzer.visit_Call() to parse keyword arguments (commit ec2bc59).

**Channels Resolved** (9 total):
1. AFFECT_HIGH_RAGE - Consumer: kloros-system-healing.service ✓
2. AFFECT_MEMORY_PRESSURE - Consumer: kloros-cognitive-actions.service ✓
3. AFFECT_RESOURCE_STRAIN - Consumer: both services ✓
4. AFFECT_CONTEXT_OVERFLOW - Consumer: kloros-cognitive-actions.service ✓
5. AFFECT_TASK_FAILURE_PATTERN - Consumer: kloros-cognitive-actions.service ✓
6. AFFECT_REPETITIVE_ERROR - Consumer: kloros-system-healing.service ✓
7. HEAL_REQUEST - Consumer: kloros-heal-executor.service ✓
8. OBSERVATION - Consumer found ✓
9. Q_CURIOSITY_INVESTIGATE - Consumer found ✓

**Impact**: Reduced active orphaned channels from 16 to 8 (50% reduction). All affective behavioral signals confirmed as properly consumed. Component health monitoring integrated into self-awareness.

**Services Confirmed Active**:
- kloros-system-healing.service (consuming AFFECT_HIGH_RAGE, AFFECT_RESOURCE_STRAIN, AFFECT_REPETITIVE_ERROR)
- kloros-cognitive-actions.service (consuming AFFECT_MEMORY_PRESSURE, AFFECT_CONTEXT_OVERFLOW, AFFECT_TASK_FAILURE_PATTERN, AFFECT_RESOURCE_STRAIN)

### Priority Queue Variable-Based Topic Detection - INVESTIGATED ✓

**Investigation**: Checked if KLR_USE_PRIORITY_QUEUES environment variable is enabled and if priority queues have consumers.

**Findings**:
- Environment variable: `KLR_USE_PRIORITY_QUEUES=1` (confirmed in running process)
- Consumer service: kloros-curiosity-processor.service (active, PID 934984)
- Priority queue mode: ENABLED and fully operational
- ChemBus activity: Confirmed Q_CURIOSITY_HIGH (68+ msgs), Q_CURIOSITY_LOW (191+ msgs) actively processed

**Root Cause of False Positive**: Integration-monitor's AST parser only detects literal string constants for topic parameters, not variables:

```python
# Detected ✓
ChemSub(topic="SIGNAL_NAME", ...)

# NOT Detected ✗ (curiosity_processor pattern)
signal_name = "Q_CURIOSITY_HIGH"
ChemSub(topic=signal_name, ...)
```

**Channels Resolved** (2 total):
- Q_CURIOSITY_HIGH - Consumer: kloros-curiosity-processor.service ✓
- Q_CURIOSITY_LOW - Consumer: kloros-curiosity-processor.service ✓

**Services Confirmed Active**:
- kloros-curiosity-processor.service (consuming Q_CURIOSITY_HIGH, Q_CURIOSITY_LOW, Q_CURIOSITY_MEDIUM, Q_CURIOSITY_CRITICAL)

**Detailed Report**: See `/home/kloros/KLR_USE_PRIORITY_QUEUES_STATUS.md`

### Heartbeat Integration - COMPLETE ✓

**Implementation**: Integrated HEARTBEAT monitoring directly into InteroceptionDaemon for self-awareness of component health.

**Architectural Decision**: Instead of creating a separate heartbeat-monitor daemon, integrated into InteroceptionDaemon because component liveness is part of internal perception / self-awareness.

**Changes Made**:
- Added ChemSub subscription to HEARTBEAT in InteroceptionDaemon
- Track last heartbeat timestamp per zooid (component_heartbeats dict)
- Check component liveness every 5 seconds
- Emit CAPABILITY_GAP when component silent > 30 seconds
- Log component recovery when silent component resumes
- Include component health in periodic state logs

**Benefits**:
- **Self-awareness**: KLoROS now knows which parts of herself are alive
- **Automatic failure detection**: Silent components trigger CAPABILITY_GAP
- **No new daemon**: Reused existing InteroceptionDaemon
- **Low overhead**: Passive heartbeat tracking

**Active Components Detected**:
- interoception_heartbeat_monitor
- investigation-consumer
- semantic-dedup
- introspection
- curiosity-processor
- [Multiple ChemSub subscribers]

**Channels Resolved** (1 total):
- HEARTBEAT - Consumer: InteroceptionDaemon ✓

**Detailed Report**: See `/home/kloros/HEARTBEAT_INTEGRATION_COMPLETE.md`

### LOBOTOMY Signal Integration - COMPLETE ✓

**Implementation**: Integrated AFFECT_LOBOTOMY_INITIATED and AFFECT_LOBOTOMY_RESTORED monitoring into InteroceptionDaemon for consciousness mode self-awareness.

**Architectural Decision**: Emergency lobotomy is a consciousness state change (affective system disabled/restored), making it part of interoception (internal perception of operating modes).

**Changes Made**:
- Added ChemSub subscriptions to AFFECT_LOBOTOMY_INITIATED and AFFECT_LOBOTOMY_RESTORED in InteroceptionDaemon
- Track lobotomy state (active boolean, initiated time, reason)
- Log lobotomy transitions (INITIATED with reason, RESTORED with duration)
- Include consciousness mode in periodic state logs (mode=normal vs mode=lobotomy)
- Added get_consciousness_mode_summary() method for introspection

**Benefits**:
- **Self-awareness**: KLoROS knows when she's in "pure logic mode" (affective processing disabled)
- **State transitions**: Logged when entering/exiting lobotomy mode with duration and reason
- **Interoception coherence**: Consciousness mode is part of internal state perception
- **Emergency visibility**: Can track when extreme affective states trigger circuit breaker

**Channels Resolved** (2 total):
- AFFECT_LOBOTOMY_INITIATED - Consumer: InteroceptionDaemon ✓
- AFFECT_LOBOTOMY_RESTORED - Consumer: InteroceptionDaemon ✓

**Files Modified**:
- `/home/kloros/src/consciousness/interoception_daemon.py` (lines 74-92, 116-148, 212-233, 473-485)

---

## Filtered Items (Not Included)

The following orphaned channels were detected but excluded from this report:

**D-REAM Evolution System** (8 signals): candidate_eval, fitness_calc, regime_eval, generation_start, generation_end, run_start, run_end, pareto_front
- **Reason**: D-REAM is disabled and being refactored. These are dormant code paths.

**Test Infrastructure** (1 signal): test_event
- **Reason**: Test-only infrastructure, not production concern.

---

## Methodology

This report was generated by analyzing streaming integration-monitor daemon logs. The daemon uses inotify-based file watching to incrementally parse Python source files and detect ChemBus signal producers/consumers. Orphaned queues are defined as channels with ≥1 producer but 0 consumers.

**Monitor Status**:
- integration-monitor: 20.7MB memory, 2600 files indexed (v2 with keyword argument support)
- exception-monitor: streaming journalctl (feedback loop fixed)
- chaos-monitor: tailing chaos_history.jsonl

All monitors are operational and emitting CAPABILITY_GAP signals in real-time.

**Active Systems Filter**: D-REAM, PHASE, and SPICA excluded per configuration.

**Changelog**:
- 2025-11-19 00:20 EST: LOBOTOMY signals integrated into InteroceptionDaemon - consciousness mode awareness complete (6 active orphans)
- 2025-11-18 23:50 EST: HEARTBEAT integrated into InteroceptionDaemon - component health awareness complete (8 active orphans)
- 2025-11-18 23:00 EST: Priority queue investigation complete - Q_CURIOSITY_HIGH/LOW resolved (9 active orphans)
- 2025-11-18 22:58 EST: Updated with integration-monitor keyword parsing fix results (11 active orphans)
- 2025-11-18 22:42 EST: Initial report with 16 orphaned channels (contains false positives)
