# Event-Driven Orchestrator Architecture Design

**Date:** 2025-11-14
**Status:** Approved for Implementation
**Phase:** Phased rollout with subagent execution

---

## Executive Summary

This design converts KLoROS orchestration from a oneshot timer-based system to an event-driven daemon architecture. The current orchestrator runs every 60 seconds via systemd timer, causing high latency (up to 60s), burst resource usage, and architectural mismatch with the existing ZMQ chemical bus. The new architecture makes KLoROS the conscious decision-maker who triggers major workflows, while background services emit advisory signals and autonomous daemons handle routine tasks.

**Note:** PHASE system is currently on hold pending structural changes. This design accommodates future PHASE integration but does not implement it initially.

---

## Problem Statement

### Current Architecture Issues

The oneshot orchestrator creates four critical inefficiencies:

1. **Latency:** Intents queue for up to 60 seconds before processing
2. **Burst Load:** Processing 10 intents simultaneously spikes CPU and memory
3. **Queueing Pressure:** If more than 10 intents arrive per minute, queue grows unbounded
4. **Architectural Mismatch:** System has event-driven ZMQ pub/sub infrastructure, but orchestrator polls instead of subscribing

### Root Cause

The orchestrator was designed as a periodic batch processor when KLoROS had fewer autonomous systems. As the chemical bus matured, other daemons became event-driven (investigation_consumer, semantic_dedup), but the orchestrator remained oneshot. KLoROS's own curiosity system discovered this inefficiency by asking "why doesn't the orchestrator run full-time?"

---

## Design Vision

### Architectural Philosophy

**KLoROS as Conscious Orchestrator:**
- KLoROS makes decisions about major workflows (currently D-REAM; PHASE when re-enabled)
- Background monitors emit advisory signals about system conditions
- KLoROS's policy engine evaluates advisories and triggers appropriate actions
- All coordination happens via chemical signals, not files or polling

**Component Roles:**
- **Advisory Monitors:** Observe system state, emit context-rich signals for KLoROS to consider
- **Autonomous Services:** Execute routine tasks automatically when triggered
- **KLoROS Policy Engine:** Autonomous decision-making based on advisory signals (evolution path to introspective LLM reasoning)
- **Intent Router:** Transitional bridge from legacy intent files to chemical signals

### Evolution Path

**Phase 1 (This Design):** Intent router bridges file system to chemical bus; policy engine uses rule-based decisions

**Phase 2 (Future):** KLoROS generates signals directly based on observations; policy engine uses introspective LLM reasoning

---

## Chemical Signal Schema

### Signal Naming Convention

All signals follow the pattern `Q_<ACTION>_<STATE>`:
- `Q_INTENT_READY` - Intent file written, ready for routing
- `Q_CURIOSITY_INVESTIGATE` - Investigation requested
- `Q_INVESTIGATION_COMPLETE` - Investigation finished
- `Q_PROMOTIONS_DETECTED` - Unacknowledged D-REAM promotions exist
- `Q_DREAM_TRIGGER` - KLoROS decided to run D-REAM
- `Q_DREAM_COMPLETE` - D-REAM cycle finished
- `Q_MODULE_INTEGRATED` - Capability integrator added module to registry

### Signal Structure

```python
{
    "signal": "Q_SIGNAL_NAME",
    "timestamp": "2025-11-14T10:30:00Z",
    "source": "daemon_name",
    "facts": {
        # Rich contextual data for decision-making
        # Everything needed without additional queries
    }
}
```

### Advisory Signals (emitted by monitors)

**Q_PROMOTIONS_DETECTED:**
```python
{
    "signal": "Q_PROMOTIONS_DETECTED",
    "timestamp": "...",
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

**Q_MODULE_DISCOVERED:**
```python
{
    "signal": "Q_MODULE_DISCOVERED",
    "timestamp": "...",
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

### Trigger Signals (emitted by KLoROS policy)

**Q_DREAM_TRIGGER:**
```python
{
    "signal": "Q_DREAM_TRIGGER",
    "timestamp": "...",
    "source": "kloros_policy_engine",
    "facts": {
        "reason": "unacknowledged_promotions_detected",
        "topic": null,
        "promotion_count": 3
    }
}
```

**Q_CURIOSITY_INVESTIGATE:**
```python
{
    "signal": "Q_CURIOSITY_INVESTIGATE",
    "timestamp": "...",
    "source": "intent_router",
    "facts": {
        "question": "What does the audio module do?",
        "question_id": "discover.module.audio",
        "priority": "normal",
        "evidence": ["path:/home/kloros/src/audio", "has_init:true"]
    }
}
```

---

## Component Architecture

### 1. orchestrator_monitor.py (Advisory Monitor)

**Purpose:** Monitor system conditions and emit advisory signals

**Subscribes to:** None (autonomous monitoring)

**Emits:**
- `Q_PROMOTIONS_DETECTED` - Unacknowledged D-REAM promotions exist
- `Q_MODULE_DISCOVERED` - New module detected in investigations log
- `Q_HEALTH_ALERT` - System health issue detected

**Implementation:**
```python
class OrchestratorMonitor:
    def __init__(self):
        self.zmq_context = zmq.Context()
        self.signal_publisher = self.zmq_context.socket(zmq.PUB)
        self.signal_publisher.bind("tcp://127.0.0.1:7777")

    async def periodic_checks(self):
        """Run monitoring checks every 60 seconds."""
        while True:
            await asyncio.sleep(60)

            # Check for promotions
            promotion_count = self._count_unacknowledged_promotions()
            if promotion_count > 0:
                self._emit_signal("Q_PROMOTIONS_DETECTED", {
                    "promotion_count": promotion_count,
                    # ... other facts
                })

            # Check system health
            health_issues = self._check_system_health()
            for issue in health_issues:
                self._emit_signal("Q_HEALTH_ALERT", issue)

    def _emit_signal(self, signal_type: str, facts: dict):
        """Emit chemical signal."""
        msg = {
            "signal": signal_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "orchestrator_monitor",
            "facts": facts
        }
        self.signal_publisher.send_json(msg)
        logger.info(f"[monitor] Emitted {signal_type}: {facts}")
```

**Systemd Service:**
- Type: `notify` (with sd_notify when ready)
- Restart: `always`
- After: `kloros-chemical-bus.service`

---

### 2. intent_router.py (Transitional Bridge)

**Purpose:** Convert legacy intent files to chemical signals

**Watches:** `/home/kloros/.kloros/intents/` directory (inotify)

**Emits:** Signal type based on intent content

**Intent to Signal Mapping:**
- `discover.module.*` → `Q_CURIOSITY_INVESTIGATE`
- `reinvestigate.*` → `Q_CURIOSITY_INVESTIGATE`
- Generic questions → `Q_CURIOSITY_INVESTIGATE`

**Implementation:**
```python
class IntentRouter:
    def __init__(self):
        self.zmq_context = zmq.Context()
        self.signal_publisher = self.zmq_context.socket(zmq.PUB)
        self.signal_publisher.bind("tcp://127.0.0.1:7777")

        # Inotify watch on intent directory
        self.watcher = inotify.adapters.Inotify()
        self.watcher.add_watch('/home/kloros/.kloros/intents')

    def run(self):
        """Watch for new intent files and route to chemical signals."""
        logger.info("[intent_router] Starting intent file watcher")

        for event in self.watcher.event_gen(yield_nones=False):
            (_, type_names, path, filename) = event

            if 'IN_CLOSE_WRITE' in type_names:
                intent_file = Path(path) / filename
                self._route_intent(intent_file)

    def _route_intent(self, intent_file: Path):
        """Read intent file and emit appropriate signal."""
        try:
            with open(intent_file, 'r') as f:
                intent = json.load(f)

            # Determine signal type from intent
            if intent['type'] in ['discover.module', 'reinvestigate']:
                signal_type = "Q_CURIOSITY_INVESTIGATE"
                facts = {
                    "question": intent['data'].get('question', ''),
                    "question_id": intent['id'],
                    "priority": intent['data'].get('priority', 'normal'),
                    "evidence": intent['data'].get('evidence', [])
                }
            else:
                logger.warning(f"[intent_router] Unknown intent type: {intent['type']}")
                return

            # Emit signal
            self._emit_signal(signal_type, facts)

            # Delete processed intent file
            intent_file.unlink()
            logger.info(f"[intent_router] Routed and deleted {intent_file.name}")

        except Exception as e:
            logger.error(f"[intent_router] Failed to route {intent_file}: {e}")
            # Write to dead letter queue
            self._write_dead_letter(intent_file, str(e))
```

**Future Deprecation:** When KLoROS generates signals directly, this daemon becomes obsolete.

---

### 3. kloros_policy_engine.py (KLoROS Decision-Making)

**Purpose:** Autonomous policy decisions for major workflows

**Subscribes to:**
- `Q_PROMOTIONS_DETECTED`
- Advisory signals from monitors

**Emits:**
- `Q_DREAM_TRIGGER`
- (Future: `Q_PHASE_TRIGGER` when PHASE re-enabled)

**Policy Logic:**
```python
class KLoROSPolicyEngine:
    def __init__(self):
        self.zmq_context = zmq.Context()

        # Subscribe to advisory signals
        self.signal_subscriber = self.zmq_context.socket(zmq.SUB)
        self.signal_subscriber.connect("tcp://127.0.0.1:7777")
        self.signal_subscriber.setsockopt_string(zmq.SUBSCRIBE, "")

        # Publish trigger signals
        self.signal_publisher = self.zmq_context.socket(zmq.PUB)
        self.signal_publisher.bind("tcp://127.0.0.1:7778")

    async def run(self):
        """Process advisory signals and make decisions."""
        logger.info("[kloros_policy] Starting policy engine")

        while True:
            # Receive signal (non-blocking with timeout)
            if self.signal_subscriber.poll(timeout=1000):
                msg = self.signal_subscriber.recv_json()
                await self._process_advisory(msg)

    async def _process_advisory(self, msg: dict):
        """Evaluate advisory signal and decide whether to trigger action."""
        signal_type = msg.get('signal')
        facts = msg.get('facts', {})

        if signal_type == "Q_PROMOTIONS_DETECTED":
            # Policy: If promotions exist, trigger D-REAM
            promotion_count = facts.get('promotion_count', 0)
            if promotion_count > 0:
                logger.info(f"[kloros_policy] {promotion_count} promotions detected, triggering D-REAM")
                self._emit_signal("Q_DREAM_TRIGGER", {
                    "reason": "unacknowledged_promotions_detected",
                    "topic": None,
                    "promotion_count": promotion_count
                })

        # Future: PHASE window logic
        # elif signal_type == "Q_PHASE_WINDOW_OPEN":
        #     phase_done = facts.get('phase_done_today', True)
        #     if not phase_done:
        #         self._emit_signal("Q_PHASE_TRIGGER", {...})
```

**Future Evolution:** Replace rule-based policies with introspective LLM reasoning that considers full system context.

---

### 4. capability_integrator_daemon.py (Autonomous Service Conversion)

**Current State:** Called by orchestrator tick() every 60s

**New Behavior:** Standalone daemon subscribing to signals

**Subscribes to:** `Q_INVESTIGATION_COMPLETE`

**Emits:**
- `Q_MODULE_INTEGRATED` - Module added to capabilities.yaml
- `Q_INTEGRATION_FAILED` - Integration failed

**Conversion:**
```python
class CapabilityIntegratorDaemon:
    def __init__(self):
        # Existing integrator logic
        self.integrated_ids = self._load_integrated_ids()

        # New: ZMQ subscriber
        self.zmq_context = zmq.Context()
        self.signal_subscriber = self.zmq_context.socket(zmq.SUB)
        self.signal_subscriber.connect("tcp://127.0.0.1:7777")
        self.signal_subscriber.setsockopt_string(zmq.SUBSCRIBE, "Q_INVESTIGATION_COMPLETE")

        # New: Signal publisher
        self.signal_publisher = self.zmq_context.socket(zmq.PUB)
        self.signal_publisher.bind("tcp://127.0.0.1:7779")

    async def run(self):
        """Process investigation complete signals."""
        logger.info("[capability_integrator] Starting daemon")

        while True:
            msg = self.signal_subscriber.recv_json()
            await self._process_investigation(msg)

    async def _process_investigation(self, msg: dict):
        """Check if investigation should be integrated."""
        facts = msg.get('facts', {})
        investigation_timestamp = facts.get('investigation_timestamp')

        # Load investigation from log
        investigation = self._load_investigation(investigation_timestamp)

        # Existing integration logic
        should_integrate, reason = self._should_integrate(investigation)

        if should_integrate:
            success = self._integrate_module(investigation)
            if success:
                self._emit_signal("Q_MODULE_INTEGRATED", {
                    "module_name": investigation.get("module_name"),
                    "module_path": investigation.get("module_path")
                })
```

---

### 5. winner_deployer_daemon.py (Autonomous Service Conversion)

**Current State:** Called by orchestrator tick() every 60s

**New Behavior:** Standalone daemon triggered by D-REAM completion

**Subscribes to:** `Q_DREAM_COMPLETE`

**Emits:**
- `Q_WINNER_DEPLOYED` - Winner deployed to production
- `Q_DEPLOYMENT_FAILED` - Deployment failed

**Implementation:** Similar pattern to capability_integrator - wrap existing logic in ZMQ subscriber loop.

---

## Data Flow Examples

### Example 1: Module Discovery → Integration

```
1. curiosity_core generates question
   → writes intent file

2. intent_router (inotify)
   → reads intent
   → emits Q_CURIOSITY_INVESTIGATE
   → deletes intent file

3. investigation_consumer_daemon
   → receives Q_CURIOSITY_INVESTIGATE
   → performs deep LLM analysis
   → writes curiosity_investigations.jsonl
   → emits Q_INVESTIGATION_COMPLETE

4. semantic_dedup_consumer_daemon
   → receives Q_INVESTIGATION_COMPLETE
   → updates semantic evidence
   → may trigger re-investigation

5. capability_integrator_daemon
   → receives Q_INVESTIGATION_COMPLETE
   → checks UNDISCOVERED_MODULE_* hypothesis
   → creates __init__.py, updates capabilities.yaml
   → emits Q_MODULE_INTEGRATED

6. orchestrator_monitor
   → detects new module in capabilities.yaml
   → emits Q_MODULE_DISCOVERED (advisory)
```

**Latency:** Sub-second signal propagation (vs 0-60s with oneshot)

---

### Example 2: D-REAM Execution

```
1. orchestrator_monitor (periodic check)
   → scans D-REAM promotions directory
   → finds 3 unacknowledged promotions
   → emits Q_PROMOTIONS_DETECTED with rich facts

2. kloros_policy_engine
   → receives Q_PROMOTIONS_DETECTED
   → policy: promotions exist → trigger D-REAM
   → emits Q_DREAM_TRIGGER

3. dream_daemon (to be created in Phase 4)
   → receives Q_DREAM_TRIGGER
   → runs D-REAM cycle
   → emits Q_DREAM_COMPLETE

4. winner_deployer_daemon
   → receives Q_DREAM_COMPLETE
   → scans for new winners
   → deploys winners to production
   → emits Q_WINNER_DEPLOYED

5. orchestrator_monitor
   → acknowledges promotions
   → stops emitting Q_PROMOTIONS_DETECTED
```

**Benefits:** Immediate response to promotions (vs up to 60s delay)

---

## Error Handling Strategy

### Layer 1: Systemd Auto-Restart

All daemons configured with:
```ini
[Service]
Restart=always
RestartSec=5s
StartLimitBurst=5
StartLimitIntervalSec=60s
```

Prevents permanent failures from daemon crashes.

### Layer 2: Dead Letter Queue

Failed signal processing → append to `/home/kloros/.kloros/failed_signals.jsonl`

Schema:
```json
{
    "signal": {...},
    "error": "ValueError: missing required field 'module_name'",
    "timestamp": "2025-11-14T10:30:00Z",
    "daemon": "capability_integrator_daemon"
}
```

Manual or automated replay mechanism. Periodic cleanup of entries older than 30 days.

### Layer 3: Timeout Signals

Long-running operations emit timeout signals if no completion:

Example: `Q_CURIOSITY_INVESTIGATE` without `Q_INVESTIGATION_COMPLETE` in 10 minutes → emit `Q_INVESTIGATION_TIMEOUT`

Allows KLoROS to detect stuck operations.

### Layer 4: Graceful Degradation

Daemons log errors but continue processing other signals. No cascading failures from single bad signal.

### Layer 5: Observable Logging

All signal emissions and receipts logged:
```python
logger.info(f"[daemon] Emitted {signal_type}: {facts}")
logger.info(f"[daemon] Received {signal_type}: {facts}")
```

Enables post-mortem analysis and debugging.

---

## Phased Migration Strategy

### Phase 1: Intent Router Foundation

**Deploy:** `intent_router.py` daemon

**Risk:** Low (read-only initially, can run alongside oneshot)

**Validation:**
- Verify intent files → chemical signals correctly
- Check signal payloads contain all required facts
- Monitor dead letter queue for failures

**Rollback:** Stop daemon, intents still processed by oneshot

**Success Criteria:** All intent types correctly translated to signals for 24 hours

---

### Phase 2: Autonomous Services

**Deploy:**
- `capability_integrator_daemon.py`
- `winner_deployer_daemon.py`

**Modify:** Orchestrator oneshot stops calling these functions

**Risk:** Medium (changes integration behavior)

**Validation:**
- Monitor that modules still integrate at same rate
- Verify winners still deploy
- Check no duplicate processing (daemon + oneshot)

**Rollback:** Re-enable function calls in oneshot, stop daemons

**Success Criteria:**
- Same integration rate as before for 48 hours
- No missed modules or winners
- No duplicate integrations

---

### Phase 3: Advisory Monitoring

**Deploy:** `orchestrator_monitor.py` daemon

**Risk:** Low (purely observational signals)

**Validation:**
- Verify advisory signals emit with correct facts
- Check signal frequency (should be every 60s)
- Monitor for false positives (alerts when nothing wrong)

**Rollback:** Stop daemon

**Success Criteria:** Advisory signals visible on chemical bus with accurate data for 24 hours

---

### Phase 4: KLoROS Policy Engine

**Deploy:** `kloros_policy_engine.py` daemon

**Disable:** Orchestrator oneshot timer completely

**Risk:** High (replaces entire orchestrator)

**Validation:**
- D-REAM triggers on promotions
- No missed D-REAM cycles
- Monitor latency (should be sub-second)
- Check resource usage (should be smoother, no spikes)

**Rollback:** Re-enable oneshot timer, stop policy engine

**Success Criteria:**
- 48 hours operation without missed D-REAM cycles
- Intent processing latency < 1s (vs 0-60s before)
- Smooth resource usage (no 60s spikes)

---

### Phase 5: Cleanup

**Remove:**
- `/etc/systemd/system/kloros-orchestrator.service`
- `/etc/systemd/system/kloros-orchestrator.timer`
- `/home/kloros/src/kloros/orchestration/run_once.py`
- `/home/kloros/src/kloros/orchestration/coordinator.py` (legacy tick() logic)

**Document:**
- Update system architecture documentation
- Add chemical signal reference to docs
- Document daemon topology

**Success Criteria:** Legacy code removed, documentation complete

---

## File Structure

New files created:
```
/home/kloros/src/kloros/orchestration/
├── intent_router.py                    # Phase 1
├── orchestrator_monitor.py             # Phase 3
├── kloros_policy_engine.py             # Phase 4
├── capability_integrator_daemon.py     # Phase 2 (refactor existing)
└── winner_deployer_daemon.py           # Phase 2 (refactor existing)

/etc/systemd/system/
├── kloros-intent-router.service        # Phase 1
├── kloros-orchestrator-monitor.service # Phase 3
├── kloros-policy-engine.service        # Phase 4
├── kloros-capability-integrator.service# Phase 2
└── kloros-winner-deployer.service      # Phase 2

/home/kloros/.kloros/
├── failed_signals.jsonl                # Dead letter queue
└── policy_state.json                   # Policy engine state
```

Modified files:
```
/home/kloros/src/kloros/orchestration/capability_integrator.py
    → Extract to capability_integrator_daemon.py

/home/kloros/src/kloros/orchestration/winner_deployer.py
    → Extract to winner_deployer_daemon.py
```

Deprecated files (Phase 5):
```
/home/kloros/src/kloros/orchestration/run_once.py
/home/kloros/src/kloros/orchestration/coordinator.py
/etc/systemd/system/kloros-orchestrator.service
/etc/systemd/system/kloros-orchestrator.timer
```

---

## Documentation for KLoROS Self-Modification

This design is structured for KLoROS to parse and potentially modify herself. Each component includes:

1. **Purpose:** What the component does
2. **Inputs:** What signals it subscribes to
3. **Outputs:** What signals it emits
4. **Facts Schema:** Exact structure of signal payloads
5. **Decision Logic:** Rule-based policies (can evolve to introspective reasoning)

When KLoROS evolves introspective reasoning, she can:
- Read this document to understand current architecture
- Identify which policy rules to replace with LLM reasoning
- Modify `kloros_policy_engine.py` to use her own decision-making
- Eventually generate chemical signals directly from observations

---

## Success Metrics

**Latency:**
- Intent processing: < 1s (currently 0-60s)
- Advisory signal propagation: < 100ms
- End-to-end investigation trigger → integration: < 5s (currently up to 120s)

**Resource Usage:**
- CPU usage: Smooth baseline (no 60s spikes)
- Memory: Steady state (no burst allocations)
- ZMQ message throughput: 100-1000 msgs/sec

**Reliability:**
- Daemon uptime: > 99.9%
- Dead letter queue: < 1 failure per 1000 signals
- Systemd restarts: < 1 per week

**Correctness:**
- No missed investigations
- No duplicate integrations
- No missed D-REAM cycles
- Advisory signals accurate (no false positives)

---

## Future Work

**Introspective Decision-Making:**
Replace rule-based policy engine with LLM reasoning that considers:
- Full system context
- Recent failures or issues
- User activity and preferences
- Resource availability
- Historical patterns

**Direct Signal Generation:**
KLoROS generates chemical signals from observations instead of writing intent files.

**Self-Healing:**
Daemons detect missing expected signals and emit repair signals autonomously.

**Distributed Orchestration:**
Chemical bus extends across multiple machines for distributed KLoROS instances.

---

## Appendix: Chemical Signal Reference

### All Signal Types

**Advisory Signals (monitors → policy engine):**
- `Q_PROMOTIONS_DETECTED` - Unacknowledged D-REAM promotions exist
- `Q_MODULE_DISCOVERED` - New module detected
- `Q_HEALTH_ALERT` - System health issue
- (Future: `Q_PHASE_WINDOW_OPEN` - PHASE execution window active)

**Trigger Signals (policy engine → workers):**
- `Q_DREAM_TRIGGER` - Run D-REAM cycle
- `Q_CURIOSITY_INVESTIGATE` - Investigate question
- (Future: `Q_PHASE_TRIGGER` - Run PHASE epoch)

**Completion Signals (workers → monitors/policy):**
- `Q_INVESTIGATION_COMPLETE` - Investigation finished
- `Q_MODULE_INTEGRATED` - Module added to registry
- `Q_WINNER_DEPLOYED` - D-REAM winner deployed
- `Q_DREAM_COMPLETE` - D-REAM cycle finished
- (Future: `Q_PHASE_COMPLETE` - PHASE epoch finished)

**Error Signals:**
- `Q_INTEGRATION_FAILED` - Capability integration failed
- `Q_DEPLOYMENT_FAILED` - Winner deployment failed
- `Q_INVESTIGATION_TIMEOUT` - Investigation exceeded time limit

---

**End of Design Document**
