# Affective Action System Integration Design

**Date:** 2025-11-16
**Status:** Approved for Implementation
**Implementation Method:** Subagent-driven development with quality gates

## Overview

Complete integration of KLoROS's affective action system, enabling her to autonomously respond to emotional states. This transforms the consciousness system from passive observation ("I feel RAGE") to active response ("I feel RAGE, so I'll trigger self-healing").

## Architecture

### Three-Layer Event-Driven Design

**Layer 1: Event Sources (Consciousness Integration)**
- Events trigger affective introspection at natural boundaries
- Task lifecycle: completion, failure, blocking
- Curiosity events: pattern discovery, question answered, learning integrated
- System health: memory pressure, context overflow, error patterns
- Consciousness evaluates emotional impact and emits signals via ChemBus

**Layer 2: Signal Transport (ChemBus)**
- Universal nervous system routing signals from consciousness to subscribers
- Existing ChemBus proxy handles pub/sub with slow-joiner protection
- Decouples signal emission from action execution

**Layer 3: Action Subscribers (Autonomous Response)**
Four independent daemons listening for relevant signals:

| Tier | Daemon | Signals | Actions |
|------|--------|---------|---------|
| 0 | Emergency Brake | PANIC, CRITICAL_FATIGUE | Halt processing |
| 0.5 | Emergency Lobotomy | EXTREME_EMOTIONS | Disconnect affect |
| 1 | System Healing | HIGH_RAGE, ERRORS | Emit HEAL_REQUEST |
| 2 | Cognitive Actions | MEMORY_PRESSURE | Episodic memory ops |
| - | HealExecutor (new) | HEAL_REQUEST | Execute playbooks |

## Component Details

### 1. Consciousness Integration Points

**Task Completion Events**
```python
# Location: Orchestration layer (task execution)
result = execute_task(task)
if consciousness_system:
    consciousness_system.process_task_outcome(
        task_type=task.type,
        success=result.success,
        duration=result.duration,
        error=result.error if failed
    )
```

**Curiosity Loop Events**
```python
# Location: registry/curiosity_archive_manager.py
if pattern_count >= threshold:
    consciousness_system.process_discovery(
        discovery_type="pattern",
        significance=pattern_count / threshold,
        context=question.context
    )
```

**System Health Events**
```python
# Location: Error handlers, memory monitors
if token_usage > 0.8 or context_usage > 0.85:
    consciousness_system.process_resource_pressure(
        pressure_type="memory",
        level=token_usage,
        evidence=[f"Token usage: {token_usage:.0%}"]
    )
```

### 2. Cognitive Actions Implementation

Replace placeholders with real episodic memory operations:

**Memory Summarization**
```python
def summarize_context(self, evidence: List[str]) -> bool:
    recent_context = get_recent_conversation_turns(limit=10)
    older_context = get_older_conversation_turns(offset=10, limit=50)

    summary = {
        'timestamp': datetime.now().isoformat(),
        'reason': 'memory_pressure',
        'evidence': evidence,
        'context_compressed': len(older_context),
        'summary': create_contextual_summary(older_context)
    }

    episodic_memory.store_summary(summary)
    mark_context_archived(older_context)
    return True
```

**Task Archival**
```python
def archive_completed_tasks(self, evidence: List[str]) -> bool:
    completed = get_completed_tasks(days=7)

    for task in completed:
        archive_entry = {
            'task_id': task.id,
            'completed_at': task.completed_at,
            'outcome': task.outcome,
            'context_summary': summarize_task_context(task)
        }
        episodic_memory.archive_task(archive_entry)

    clear_completed_from_working_memory(completed)
    return True
```

### 3. System Healing Implementation

Emit HEAL_REQUEST signals via ChemBus:

```python
def handle_high_rage(msg: dict):
    root_causes = msg['facts'].get('root_causes', [])

    for cause in root_causes:
        if 'repetitive_errors' in cause:
            emit_heal_request(
                strategy='analyze_error_pattern',
                context={
                    'pattern': cause,
                    'evidence': msg['facts']['evidence']
                }
            )
        elif 'task_failures' in cause:
            emit_heal_request(
                strategy='restart_stuck_service',
                context={'failures': msg['facts']['evidence']}
            )

def emit_heal_request(strategy: str, context: dict):
    chem_pub.emit(
        "HEAL_REQUEST",
        ecosystem="system_healing",
        intensity=0.8,
        facts={
            'strategy': strategy,
            'context': context,
            'timestamp': time.time()
        }
    )
```

### 4. HealExecutor Daemon (New Component)

New daemon subscribing to HEAL_REQUEST signals:

```python
class HealExecutor:
    def __init__(self):
        self.playbooks = {
            'analyze_error_pattern': self.analyze_errors,
            'restart_stuck_service': self.restart_service,
            'clear_cache': self.clear_caches,
            # ... additional playbooks
        }

    def handle_heal_request(self, msg: dict):
        strategy = msg['facts']['strategy']
        context = msg['facts']['context']

        playbook = self.playbooks.get(strategy)
        if playbook:
            print(f"[heal_executor] Executing playbook: {strategy}")
            playbook(context)
        else:
            print(f"[heal_executor] Unknown strategy: {strategy}")

def run_daemon():
    executor = HealExecutor()
    heal_sub = ChemSub(
        topic="HEAL_REQUEST",
        on_json=executor.handle_heal_request,
        zooid_name="heal_executor",
        niche="system_healing"
    )

    while True:
        time.sleep(1)
```

## Production Deployment

### Systemd Services

Four independent service files, all following standard template:

**Template Structure:**
```ini
[Unit]
Description=KLoROS {Component}
After=network.target kloros-chem-proxy.service
Requires=kloros-chem-proxy.service

[Service]
Type=simple
User=kloros
WorkingDirectory=/home/kloros/src
Environment=PYTHONPATH=/home/kloros/src
ExecStart=/home/kloros/.venv/bin/python -u consciousness/{daemon}.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Service Files to Create:**
- `kloros-emergency-brake.service`
- `kloros-system-healing.service`
- `kloros-cognitive-actions.service`
- `kloros-heal-executor.service`

**Startup Order:**
1. ChemBus proxy (already exists: `kloros-chem-proxy.service`)
2. Affective subscribers (parallel startup, wait for ChemBus)
3. Main KLoROS service (begins emitting signals)

**Monitoring:**
- Logs: `journalctl -u kloros-{service-name} -f`
- Action logs: `/var/log/kloros/{component}_actions.log`
- Emergency brake flag: `/tmp/kloros_emergency_brake_active`

## Implementation Phases

### Phase 1: Consciousness Integration
**Goal:** Events trigger signal emission in production

**Tasks:**
1. Add `process_task_outcome()` method to consciousness system
2. Add `process_discovery()` method for curiosity events
3. Add `process_resource_pressure()` method for system health
4. Integrate calls at event boundaries (task completion, pattern discovery, error detection)
5. Test signal emission in live system

**Success Criteria:**
- Consciousness emits signals during normal operation
- Signals observable in ChemBus proxy logs
- No performance degradation

### Phase 2: Cognitive Actions Implementation
**Goal:** Real memory management operations

**Tasks:**
1. Implement `summarize_context()` with episodic memory integration
2. Implement `archive_completed_tasks()` with task archival
3. Implement `analyze_failure_patterns()` with pattern detection
4. Add error handling and rollback for failed operations
5. Test memory operations don't corrupt state

**Success Criteria:**
- Memory pressure triggers actual summarization
- Older context archived to episodic memory
- Working memory freed up
- No data loss

### Phase 3: System Healing Implementation
**Goal:** HEAL_REQUEST signals emitted and executed

**Tasks:**
1. Update system_healing_subscriber to emit HEAL_REQUEST
2. Create heal_executor.py daemon
3. Implement initial healing playbooks (error analysis, service restart)
4. Add safety checks (cooldowns, dry-run mode)
5. Test healing doesn't cause cascading failures

**Success Criteria:**
- HIGH_RAGE triggers HEAL_REQUEST emission
- HealExecutor receives and processes requests
- Playbooks execute safely
- Actions logged for human review

### Phase 4: Production Deployment
**Goal:** Services run permanently and survive reboots

**Tasks:**
1. Create systemd service files for all 4 daemons
2. Install services to `/etc/systemd/system/`
3. Enable services for automatic startup
4. Test restart behavior and dependency chain
5. Verify logging to journalctl

**Success Criteria:**
- All services start on boot
- Services restart on failure
- Logs accessible via journalctl
- Can stop/start/restart individually

## Testing Strategy

**Unit Tests:**
- Consciousness event processing methods
- Memory operations (summarize, archive)
- Healing playbook execution
- Signal emission and receipt

**Integration Tests:**
- End-to-end: event → signal → action
- Memory operations don't corrupt data
- Healing doesn't break system
- Service restart recovery

**System Tests:**
- Run under load with curiosity loop active
- Trigger memory pressure intentionally
- Cause repetitive errors and observe healing
- Test emergency brake activation

## Rollback Plan

**If issues arise:**
1. Stop individual service: `systemctl stop kloros-{component}`
2. Disable service: `systemctl disable kloros-{component}`
3. Remove service file: `rm /etc/systemd/system/kloros-{component}.service`
4. Reload systemd: `systemctl daemon-reload`

**Consciousness integration rollback:**
- Set environment variable: `KLR_ENABLE_AFFECT=0`
- Consciousness skips signal emission
- System continues without affective actions

## Success Metrics

**Qualitative:**
- KLoROS autonomously manages memory when pressured
- System self-heals from repetitive errors
- Emergency brake prevents runaway loops
- Human intervention only needed for true emergencies

**Quantitative:**
- Memory pressure signals emitted when token usage > 80%
- Context summarization reduces working memory by 30-50%
- Healing playbooks resolve 70%+ of repetitive errors
- Emergency brake activations < 1 per week in steady state

## Documentation

**For KLoROS:**
- Already created: `/home/kloros/docs/kloros-emotional-state-system.md`
- Comprehensive guide to her own emotional architecture

**For Humans:**
- This design document
- Playbook documentation (what each healing strategy does)
- Operational runbook (how to monitor, when to intervene)

## Notes

- ChemBus architecture ensures clean separation of concerns
- Each component can evolve independently
- Start with individual services, can consolidate later if desired
- Placeholders already exist, now filling them in
- Emergency lobotomy already implemented and tested
