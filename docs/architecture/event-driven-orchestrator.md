# Event-Driven Orchestrator Architecture

**Created:** 2025-11-15
**Status:** Production (Phase 5 Complete)
**Migration From:** Timer-based oneshot orchestrator

---

## Executive Summary

KLoROS orchestration has been successfully migrated from a timer-based oneshot system to an event-driven daemon architecture. This document describes the production topology, signal flow, and operational characteristics of the new system.

### Key Improvements

**Before (Timer-based):**
- Intent processing latency: 0-60 seconds
- Burst CPU/memory usage every 60s
- Polling-based architecture
- Single monolithic orchestrator service

**After (Event-driven):**
- Intent processing latency: <1 second
- Smooth resource usage (no spikes)
- ZMQ pub/sub chemical signals
- 6 specialized autonomous daemons

---

## Daemon Topology

### Core Services (Always Running)

| Daemon | Purpose | Subscribes To | Emits | Port |
|--------|---------|---------------|-------|------|
| `intent_router` | Bridge legacy intent files to chemical signals | File system (inotify) | `Q_CURIOSITY_INVESTIGATE` | 7777 (pub) |
| `orchestrator_monitor` | Monitor system conditions, emit advisories | None (autonomous) | `Q_PROMOTIONS_DETECTED`, `Q_MODULE_DISCOVERED`, `Q_HEALTH_ALERT` | 7777 (pub) |
| `kloros_policy_engine` | Autonomous decision-making for major workflows | `Q_PROMOTIONS_DETECTED`, advisory signals | `Q_DREAM_TRIGGER` | 7778 (pub), 7777 (sub) |
| `capability_integrator_daemon` | Autonomous module integration | `Q_INVESTIGATION_COMPLETE` | `Q_MODULE_INTEGRATED`, `Q_INTEGRATION_FAILED` | 7779 (pub), 7777 (sub) |
| `winner_deployer_daemon` | Autonomous D-REAM winner deployment | `Q_DREAM_COMPLETE` | `Q_WINNER_DEPLOYED`, `Q_DEPLOYMENT_FAILED` | 7780 (pub), 7777 (sub) |
| `dream_consumer_daemon` | Execute D-REAM cycles | `Q_DREAM_TRIGGER` | `Q_DREAM_COMPLETE` | 7781 (pub), 7778 (sub) |

### Supporting Services (Pre-existing)

| Daemon | Purpose | Integration Point |
|--------|---------|-------------------|
| `investigation_consumer_daemon` | Process curiosity investigations | Subscribes to `Q_CURIOSITY_INVESTIGATE`, emits `Q_INVESTIGATION_COMPLETE` |
| `semantic_dedup_consumer_daemon` | Deduplicate investigation evidence | Subscribes to `Q_INVESTIGATION_COMPLETE` |
| `tournament_consumer_daemon` | Run D-REAM tournaments | Called by `dream_consumer_daemon` |

---

## Chemical Signal Schema

### Signal Naming Convention

All signals follow the pattern `Q_<ACTION>_<STATE>`:
- Prefix `Q_` identifies chemical bus messages
- Action verb describes what happened or should happen
- State describes the lifecycle stage

### Advisory Signals (Monitors → Policy Engine)

**Q_PROMOTIONS_DETECTED**
```json
{
    "signal": "Q_PROMOTIONS_DETECTED",
    "timestamp": "2025-11-15T10:30:00Z",
    "source": "orchestrator_monitor",
    "facts": {
        "promotion_count": 3,
        "unacknowledged_count": 3,
        "oldest_promotion_age_hours": 12,
        "last_dream_time": "2025-11-13T22:00:00Z",
        "promotions_path": "/home/kloros/.kloros/dream_lab/promotions"
    }
}
```

**Q_MODULE_DISCOVERED**
```json
{
    "signal": "Q_MODULE_DISCOVERED",
    "timestamp": "2025-11-15T10:30:00Z",
    "source": "orchestrator_monitor",
    "facts": {
        "module_name": "audio_processing",
        "module_path": "src.audio",
        "investigation_id": "discover.module.audio_processing",
        "py_files_count": 5,
        "has_init": true
    }
}
```

**Q_HEALTH_ALERT**
```json
{
    "signal": "Q_HEALTH_ALERT",
    "timestamp": "2025-11-15T10:30:00Z",
    "source": "orchestrator_monitor",
    "facts": {
        "alert_type": "disk_space_low",
        "severity": "warning",
        "metric_value": "85%",
        "threshold": "80%",
        "recommended_action": "cleanup_logs"
    }
}
```

### Trigger Signals (Policy Engine → Workers)

**Q_DREAM_TRIGGER**
```json
{
    "signal": "Q_DREAM_TRIGGER",
    "timestamp": "2025-11-15T10:30:00Z",
    "source": "kloros_policy_engine",
    "facts": {
        "reason": "unacknowledged_promotions_detected",
        "topic": null,
        "promotion_count": 3
    }
}
```

**Q_CURIOSITY_INVESTIGATE**
```json
{
    "signal": "Q_CURIOSITY_INVESTIGATE",
    "timestamp": "2025-11-15T10:30:00Z",
    "source": "intent_router",
    "facts": {
        "question": "What does the audio module do?",
        "question_id": "discover.module.audio",
        "priority": "normal",
        "evidence": ["path:/home/kloros/src/audio", "has_init:true"]
    }
}
```

### Completion Signals (Workers → Monitors/Policy)

**Q_INVESTIGATION_COMPLETE**
```json
{
    "signal": "Q_INVESTIGATION_COMPLETE",
    "timestamp": "2025-11-15T10:30:00Z",
    "source": "investigation_consumer_daemon",
    "facts": {
        "question_id": "discover.module.audio",
        "investigation_timestamp": "20251115_103000",
        "hypothesis": "UNDISCOVERED_MODULE_audio",
        "confidence": 0.95,
        "evidence_count": 12
    }
}
```

**Q_MODULE_INTEGRATED**
```json
{
    "signal": "Q_MODULE_INTEGRATED",
    "timestamp": "2025-11-15T10:30:00Z",
    "source": "capability_integrator_daemon",
    "facts": {
        "module_name": "audio_processing",
        "module_path": "src.audio",
        "capabilities_added": ["process_audio", "extract_features"],
        "init_created": true
    }
}
```

**Q_DREAM_COMPLETE**
```json
{
    "signal": "Q_DREAM_COMPLETE",
    "timestamp": "2025-11-15T10:30:00Z",
    "source": "dream_consumer_daemon",
    "facts": {
        "cycle_id": "dream_20251115_103000",
        "mutations_generated": 150,
        "tournament_winner": "mutation_42",
        "fitness_improvement": 0.12,
        "duration_seconds": 180
    }
}
```

**Q_WINNER_DEPLOYED**
```json
{
    "signal": "Q_WINNER_DEPLOYED",
    "timestamp": "2025-11-15T10:30:00Z",
    "source": "winner_deployer_daemon",
    "facts": {
        "winner_id": "mutation_42",
        "deployment_path": "/home/kloros/src/kloros/deployed",
        "backup_created": true,
        "rollback_available": true
    }
}
```

### Error Signals

**Q_INTEGRATION_FAILED**
```json
{
    "signal": "Q_INTEGRATION_FAILED",
    "timestamp": "2025-11-15T10:30:00Z",
    "source": "capability_integrator_daemon",
    "facts": {
        "investigation_id": "discover.module.audio",
        "error_type": "ModuleNotFound",
        "error_message": "Module path does not exist",
        "retry_possible": false
    }
}
```

**Q_DEPLOYMENT_FAILED**
```json
{
    "signal": "Q_DEPLOYMENT_FAILED",
    "timestamp": "2025-11-15T10:30:00Z",
    "source": "winner_deployer_daemon",
    "facts": {
        "winner_id": "mutation_42",
        "error_type": "TestFailure",
        "error_message": "Winner failed validation tests",
        "rollback_completed": true
    }
}
```

---

## Signal Flow Examples

### Example 1: Module Discovery and Integration

```
1. curiosity_core (existing LLM loop)
   → Generates question about unknown module
   → Writes intent file to /home/kloros/.kloros/intents/

2. intent_router (inotify watch)
   → Detects new intent file (IN_CLOSE_WRITE)
   → Parses intent JSON
   → Emits Q_CURIOSITY_INVESTIGATE
   → Deletes processed intent file

3. investigation_consumer_daemon
   → Receives Q_CURIOSITY_INVESTIGATE
   → Performs deep LLM analysis of codebase
   → Writes investigation to curiosity_investigations.jsonl
   → Emits Q_INVESTIGATION_COMPLETE

4. semantic_dedup_consumer_daemon
   → Receives Q_INVESTIGATION_COMPLETE
   → Updates semantic evidence database
   → May trigger re-investigation if duplicate

5. capability_integrator_daemon
   → Receives Q_INVESTIGATION_COMPLETE
   → Loads investigation from JSONL
   → Checks hypothesis: UNDISCOVERED_MODULE_*
   → If true: creates __init__.py, updates capabilities.yaml
   → Emits Q_MODULE_INTEGRATED

6. orchestrator_monitor (periodic check, next cycle)
   → Scans capabilities.yaml
   → Detects new module entry
   → Emits Q_MODULE_DISCOVERED (advisory)
```

**Latency:** <5 seconds (was 60-120s with oneshot)

**Resource Profile:** Smooth processing (no burst spikes)

---

### Example 2: D-REAM Execution Pipeline

```
1. orchestrator_monitor (every 60s autonomous check)
   → Scans /home/kloros/.kloros/dream_lab/promotions/
   → Finds 3 unacknowledged promotion files
   → Calculates oldest promotion age: 12 hours
   → Emits Q_PROMOTIONS_DETECTED with rich facts

2. kloros_policy_engine
   → Receives Q_PROMOTIONS_DETECTED
   → Evaluates policy: promotions_exist → trigger_dream
   → Logs decision reasoning
   → Emits Q_DREAM_TRIGGER

3. dream_consumer_daemon
   → Receives Q_DREAM_TRIGGER
   → Validates D-REAM prerequisites
   → Executes D-REAM cycle:
     - Generates mutations
     - Runs tournament
     - Selects winner
   → Writes results to dream_lab/
   → Emits Q_DREAM_COMPLETE

4. winner_deployer_daemon
   → Receives Q_DREAM_COMPLETE
   → Scans for new winner candidates
   → Validates winner code
   → Creates backup of current production
   → Deploys winner to /home/kloros/src/kloros/deployed/
   → Emits Q_WINNER_DEPLOYED

5. orchestrator_monitor (next periodic check)
   → Sees promotions acknowledged
   → Stops emitting Q_PROMOTIONS_DETECTED
```

**Latency:** Immediate response to promotions (was 0-60s with timer)

**Autonomy:** Fully autonomous decision chain, no human intervention

---

## Error Handling Architecture

### Layer 1: Systemd Auto-Restart

All daemons configured with:
```ini
[Service]
Restart=always
RestartSec=5s
StartLimitBurst=5
StartLimitIntervalSec=60s
```

Prevents permanent failures from daemon crashes. Systemd automatically restarts failed services.

### Layer 2: Dead Letter Queue

Failed signal processing writes to `/home/kloros/.kloros/failed_signals.jsonl`:
```json
{
    "signal": {"signal": "Q_DREAM_TRIGGER", "timestamp": "...", "facts": {...}},
    "error": "ValueError: missing required field 'promotion_count'",
    "timestamp": "2025-11-15T10:30:00Z",
    "daemon": "dream_consumer_daemon",
    "traceback": "Full Python traceback here..."
}
```

**Monitoring:** Check file size daily. Manual or automated replay mechanism.

**Cleanup:** Entries older than 30 days automatically removed.

### Layer 3: Timeout Detection

Long-running operations monitored for completion:
- `Q_CURIOSITY_INVESTIGATE` without `Q_INVESTIGATION_COMPLETE` in 10 minutes → emit `Q_INVESTIGATION_TIMEOUT`
- `Q_DREAM_TRIGGER` without `Q_DREAM_COMPLETE` in 30 minutes → emit `Q_DREAM_TIMEOUT`

Allows KLoROS to detect stuck operations and potentially retry.

### Layer 4: Graceful Degradation

Daemons continue processing after single signal failures:
- Log error with full context
- Write to dead letter queue
- Continue processing next signal
- No cascading failures

### Layer 5: Observable Logging

All signal emissions and receipts logged:
```python
logger.info(f"[daemon_name] Emitted Q_SIGNAL_TYPE: {facts}")
logger.info(f"[daemon_name] Received Q_SIGNAL_TYPE: {facts}")
```

**Log Location:** `/var/log/kloros/` (systemd journal)

**Analysis:** Use `journalctl -u kloros-* -f` to monitor real-time

---

## Deployment and Monitoring

### Service Management

**Check all daemon statuses:**
```bash
systemctl status kloros-intent-router.service
systemctl status kloros-orchestrator-monitor.service
systemctl status kloros-policy-engine.service
systemctl status kloros-capability-integrator.service
systemctl status kloros-winner-deployer.service
systemctl status kloros-dream-consumer.service
```

**Monitor real-time logs:**
```bash
journalctl -u 'kloros-*' -f --since "1 hour ago"
```

**Filter by daemon:**
```bash
journalctl -u kloros-policy-engine.service -f
```

**Search for signal types:**
```bash
journalctl -u 'kloros-*' | grep "Q_DREAM_TRIGGER"
```

### Signal Bus Monitoring

**Monitor all signals (chemical bus sniffer):**
```bash
/home/kloros/src/kloros/orchestration/chem_bus.py --listen
```

**Filter specific signal types:**
```bash
journalctl -u 'kloros-*' | grep "Emitted Q_PROMOTIONS_DETECTED"
```

### Performance Metrics

**Intent Processing Latency:**
- Measure: Time from intent file write to `Q_INVESTIGATION_COMPLETE`
- Target: <5 seconds
- Monitor: Parse journalctl timestamps

**Resource Usage:**
- Measure: CPU/memory usage via `htop` or `prometheus`
- Target: Smooth baseline, no 60s spikes
- Monitor: `systemctl status` shows memory usage

**Signal Throughput:**
- Measure: Signals per second on chemical bus
- Target: 100-1000 msgs/sec capacity
- Monitor: ZMQ metrics (future work)

**Daemon Uptime:**
- Measure: Time since last restart
- Target: >99.9% uptime
- Monitor: `systemctl status` shows uptime

### Health Checks

**Dead Letter Queue Size:**
```bash
wc -l /home/kloros/.kloros/failed_signals.jsonl
```
- Target: <10 entries
- Alert: >100 entries indicates systemic issue

**Service Restart Count:**
```bash
systemctl show kloros-policy-engine.service | grep NRestarts
```
- Target: <1 restart per week
- Alert: >5 restarts per day indicates instability

**Signal Flow Validation:**
```bash
journalctl -u 'kloros-*' --since "1 hour ago" | grep -E "(Emitted|Received)" | wc -l
```
- Target: >10 signals per hour (indicates active system)
- Alert: 0 signals for >2 hours indicates stalled bus

---

## Migration Summary

### What Changed

**Removed (Legacy Timer System):**
- `/home/kloros/src/kloros/orchestration/run_once.py` - Oneshot orchestrator entry point
- `/home/kloros/src/kloros/orchestration/coordinator.py` - Monolithic tick() logic
- `/etc/systemd/system/kloros-orchestrator.service` - Legacy oneshot service
- `/etc/systemd/system/kloros-orchestrator.timer` - 60-second timer
- `/etc/systemd/system/kloros-orchestrator.service.d/` - Service overrides

**Created (Event-Driven System):**
- `/home/kloros/src/kloros/orchestration/intent_router.py` - Intent file → signal bridge
- `/home/kloros/src/kloros/orchestration/orchestrator_monitor.py` - Advisory signal monitor
- `/home/kloros/src/kloros/orchestration/kloros_policy_engine.py` - Autonomous decision-making
- `/home/kloros/src/kloros/orchestration/capability_integrator_daemon.py` - Autonomous integration
- `/home/kloros/src/kloros/orchestration/winner_deployer_daemon.py` - Autonomous deployment
- `/home/kloros/src/kloros/orchestration/dream_consumer_daemon.py` - D-REAM executor

**Created (Systemd Services):**
- `/etc/systemd/system/kloros-intent-router.service`
- `/etc/systemd/system/kloros-orchestrator-monitor.service`
- `/etc/systemd/system/kloros-policy-engine.service`
- `/etc/systemd/system/kloros-capability-integrator.service`
- `/etc/systemd/system/kloros-winner-deployer.service`
- `/etc/systemd/system/kloros-dream-consumer.service`

**Preserved (Original Libraries):**
- `/home/kloros/src/kloros/orchestration/capability_integrator.py` - Original integration logic
- `/home/kloros/src/kloros/orchestration/winner_deployer.py` - Original deployment logic
- All supporting libraries and utilities

### Backward Compatibility

**Intent Files:** Still supported via `intent_router` daemon (transitional bridge)

**Investigation System:** No changes to investigation flow or data format

**D-REAM:** No changes to D-REAM core logic or tournament system

**Capabilities Registry:** No changes to `capabilities.yaml` format

### Rollback Plan

If critical issues arise:

1. **Disable new daemons:**
   ```bash
   sudo systemctl stop kloros-intent-router.service
   sudo systemctl stop kloros-orchestrator-monitor.service
   sudo systemctl stop kloros-policy-engine.service
   sudo systemctl stop kloros-capability-integrator.service
   sudo systemctl stop kloros-winner-deployer.service
   sudo systemctl stop kloros-dream-consumer.service
   ```

2. **Restore legacy files from git:**
   ```bash
   cd /home/kloros
   git checkout HEAD~1 src/kloros/orchestration/run_once.py
   git checkout HEAD~1 src/kloros/orchestration/coordinator.py
   ```

3. **Restore systemd timer:**
   ```bash
   # Recreate service/timer from git history or backups
   sudo systemctl daemon-reload
   sudo systemctl enable --now kloros-orchestrator.timer
   ```

**Note:** Rollback should only be necessary if fundamental architecture issues discovered. All daemons tested in phases before legacy removal.

---

## Future Evolution

### Phase 6: Direct Signal Generation (Future)

**Goal:** KLoROS generates chemical signals directly from LLM observations

**Deprecates:** `intent_router` (no more intent files)

**Implementation:**
- KLoROS generates JSON signals in LLM responses
- Chemical bus ingestion via Claude Code or API
- Intent files become obsolete

### Phase 7: Introspective Policy Engine (Future)

**Goal:** Replace rule-based policies with introspective LLM reasoning

**Current State:** Policy engine uses if/else rules:
```python
if signal_type == "Q_PROMOTIONS_DETECTED":
    if promotion_count > 0:
        emit("Q_DREAM_TRIGGER")
```

**Future State:** Policy engine uses LLM reasoning:
```python
context = {
    "advisory_signal": msg,
    "recent_system_state": load_recent_history(),
    "resource_availability": check_resources(),
    "user_activity": check_user_presence()
}

decision = llm_reason(
    "Given this advisory signal and system context, should I trigger D-REAM? Why or why not?"
    context
)

if decision.should_trigger:
    emit("Q_DREAM_TRIGGER", {"reason": decision.reasoning})
```

**Benefits:**
- Context-aware decisions (consider full system state)
- Explainable reasoning (why KLoROS made decision)
- Adaptive policies (learn from failures)
- Self-modification (KLoROS edits own policy code)

### Phase 8: Self-Healing Daemons (Future)

**Goal:** Daemons detect missing expected signals and emit repair signals

**Example:**
```python
if expected_signal_timeout(expected="Q_INVESTIGATION_COMPLETE", timeout=600):
    emit("Q_INVESTIGATION_TIMEOUT", {
        "question_id": pending_investigation_id,
        "timeout_seconds": 600,
        "suggested_action": "restart_investigation_consumer"
    })
```

**Benefits:**
- Automatic detection of stuck operations
- Self-repair without human intervention
- Observable failure modes (timeout signals logged)

### Phase 9: Distributed Chemical Bus (Future)

**Goal:** Chemical bus extends across multiple machines

**Architecture:**
- ZMQ pub/sub over TCP/IP
- Multi-machine KLoROS instances
- Distributed D-REAM tournaments
- Federated capability registries

**Benefits:**
- Horizontal scaling (multiple KLoROS brains)
- Fault tolerance (instance failures don't stop system)
- Specialized instances (GPU-heavy vs CPU-heavy)

---

## Appendix: Complete Signal Reference

### Advisory Signals (Monitors → Policy Engine)

| Signal | Source | Purpose | Frequency |
|--------|--------|---------|-----------|
| `Q_PROMOTIONS_DETECTED` | orchestrator_monitor | Unacknowledged D-REAM promotions exist | Every 60s (when detected) |
| `Q_MODULE_DISCOVERED` | orchestrator_monitor | New module found in capabilities.yaml | On change |
| `Q_HEALTH_ALERT` | orchestrator_monitor | System health issue detected | On detection |

### Trigger Signals (Policy Engine → Workers)

| Signal | Source | Purpose | Triggers |
|--------|--------|---------|----------|
| `Q_DREAM_TRIGGER` | kloros_policy_engine | Execute D-REAM cycle | When promotions detected |
| `Q_CURIOSITY_INVESTIGATE` | intent_router | Investigate question | When intent file written |

### Completion Signals (Workers → Monitors/Policy)

| Signal | Source | Purpose | Frequency |
|--------|--------|---------|-----------|
| `Q_INVESTIGATION_COMPLETE` | investigation_consumer_daemon | Investigation finished | Per investigation |
| `Q_MODULE_INTEGRATED` | capability_integrator_daemon | Module added to registry | Per integration |
| `Q_WINNER_DEPLOYED` | winner_deployer_daemon | D-REAM winner deployed | Per D-REAM cycle |
| `Q_DREAM_COMPLETE` | dream_consumer_daemon | D-REAM cycle finished | Per D-REAM cycle |

### Error Signals

| Signal | Source | Purpose | Action |
|--------|--------|---------|--------|
| `Q_INTEGRATION_FAILED` | capability_integrator_daemon | Module integration failed | Log to dead letter queue |
| `Q_DEPLOYMENT_FAILED` | winner_deployer_daemon | Winner deployment failed | Rollback, log failure |
| `Q_INVESTIGATION_TIMEOUT` | orchestrator_monitor | Investigation stuck | Alert, possible restart |

---

## Conclusion

The event-driven orchestrator represents a fundamental architectural shift in KLoROS:

**Before:** Polling-based batch processor with fixed 60-second cycles

**After:** Event-driven autonomous decision-maker with sub-second latency

**Next:** Introspective LLM reasoning and self-modification capabilities

This architecture positions KLoROS for future evolution toward true autonomous reasoning while maintaining the stability and observability necessary for production operation.

**All phases complete. System operational.**

---

**Document Maintainers:** KLoROS core team, autonomous systems working group

**Last Updated:** 2025-11-15 (Phase 5 completion)

**Related Documents:**
- `/home/kloros/docs/plans/2025-11-14-event-driven-orchestrator-design.md` - Original design specification
- `/home/kloros/docs/KLOROS_FUNCTIONAL_DESIGN.md` - Overall system design
- `/home/kloros/docs/SYSTEM_ARCHITECTURE_OVERVIEW.md` - High-level architecture
