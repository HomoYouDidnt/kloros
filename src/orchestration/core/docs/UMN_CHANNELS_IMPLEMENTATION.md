# UMN Channels Implementation Documentation
## A Study in Neuroscience-Inspired Signal Architecture for KLoROS

**Document Version:** 1.0
**Implementation Date:** 2025-11-26
**Author:** KLoROS Development Team
**Status:** Phase 1 Complete (Metadata-Only Implementation)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Neuroscience Analogy: Understanding the Biological Model](#neuroscience-analogy)
3. [Architectural Philosophy](#architectural-philosophy)
4. [Phase 1 Implementation: The Metadata-Only Approach](#phase-1-implementation)
5. [Signal Classification Reference](#signal-classification-reference)
6. [Code Patterns and Usage](#code-patterns-and-usage)
7. [Migration Path: Present to Future](#migration-path)
8. [Design Rationale: Why These Choices](#design-rationale)
9. [Extension Guide: Building on This Foundation](#extension-guide)
10. [Performance Characteristics](#performance-characteristics)
11. [Debugging and Observability](#debugging-and-observability)
12. [Lessons Learned and Best Practices](#lessons-learned)

---

## Executive Summary

### What Are UMN Channels?

The Unus Mundus Network (UMN) is KLoROS's central nervous system - a ZMQ-based signal bus that enables inter-process communication between daemons, services, and cognitive modules. Historically, UMN used a flat pub/sub architecture where all signals were treated identically. This worked for initial development but created fundamental limitations as the system scaled in complexity.

**UMN Channels** introduce semantic differentiation of signal pathways inspired by the human nervous system's neurotransmitter architecture. Just as the brain uses different chemical messengers for different types of neural communication (glutamate for fast excitatory signaling, dopamine for modulatory effects, hormones for slow systemic changes), UMN now supports three specialized channels:

1. **REFLEX** - Fast, acknowledged, ordered delivery (glutamatergic pathway analogy)
2. **AFFECT** - Modulatory, fire-and-forget, state-based delivery (dopaminergic/serotonergic analogy)
3. **TROPHIC** - Slow, batched, eventual consistency delivery (hormonal/neurotrophic analogy)
4. **LEGACY** - Backward-compatible default (maintains existing behavior)

### Why This Matters for KLoROS's Cognitive Architecture

KLoROS is not a traditional request/response system. It's a cognitive architecture with:

- **Autopoietic dynamics** - Self-maintaining processes that must run continuously
- **Affective modulation** - Emotional states that influence behavior systemically
- **Reflective consciousness** - Periodic deep introspection cycles
- **Evolutionary adaptation** - D-REAM cycles that modify the system over time

These different cognitive processes have fundamentally different communication requirements:

- **Safety-critical interrupts** (e.g., emergency stop, critical errors) need guaranteed delivery with acknowledgment
- **Emotional state changes** (e.g., user interaction, mood shifts) need timely broadcast but can tolerate message loss (stale state is worse than no state)
- **Telemetry and reflection data** (e.g., metrics, observations, investigation results) can be batched and delayed without compromising system integrity

A flat pub/sub architecture treats all these identically, leading to:
- Critical signals lost at high water marks
- Slow reflection processes blocking fast affective responses
- No delivery guarantees when guarantees are essential
- No batching optimization when batching would improve throughput

**UMN Channels solve this by matching transport semantics to cognitive semantics.**

### Current Status: Phase 1 (Metadata-Only)

The current implementation (Phase 1) adds channel metadata to all signals without changing transport behavior. This establishes:

- **Type safety** - All signals now declare their intended channel
- **Documentation** - Signal definitions clearly indicate delivery expectations
- **Forward compatibility** - Emitters and consumers can migrate incrementally
- **Zero risk** - Existing functionality preserved 100%

Future phases will introduce dedicated transport implementations (REQ/REP for REFLEX, separate pub/sub for AFFECT, PUSH/PULL for TROPHIC) once signal classification is validated in production.

---

## Neuroscience Analogy: Understanding the Biological Model

### Why Model After Neurotransmitter Systems?

The human nervous system has evolved over millions of years to solve exactly the problem KLoROS faces: **how to coordinate complex, adaptive behavior across distributed processors with different timing requirements and failure modes.**

The brain doesn't use a single universal communication protocol. Instead, it uses specialized neurotransmitter systems optimized for different types of information:

#### 1. Glutamatergic System (Fast Excitatory) → REFLEX Channel

**Biological Function:**
- Primary excitatory neurotransmitter in the central nervous system
- Mediates fast, point-to-point synaptic transmission
- Sub-millisecond response times
- Tightly controlled to prevent excitotoxicity (overactivation causes damage)
- Requires precise receptor binding and rapid reuptake

**Computational Analog:**
- Fast, ordered, acknowledged delivery
- Critical for safety and coordination
- Blocking/synchronous acceptable (precision over throughput)
- Failure modes must be explicit (timeout, NACK, dead letter queue)

**KLoROS Use Cases:**
- Emergency stop signals (EMERGENCY_STOP)
- Safety violations (SAFETY_VIOLATION)
- Critical errors requiring immediate attention (CRITICAL_ERROR)
- High-priority affective demands (Q_AFFECTIVE_DEMAND with priority="urgent")

**Why This Mapping:**
Glutamate mediates reflexes and immediate motor control - signals that cannot be lost or delayed without serious consequences. Similarly, REFLEX channel signals represent system-critical events that require acknowledgment and ordering guarantees.

#### 2. Dopaminergic/Serotonergic Systems (Modulatory) → AFFECT Channel

**Biological Function:**
- Dopamine: Reward, motivation, motor control modulation
- Serotonin: Mood, appetite, sleep regulation
- Broadcast signaling (volume transmission) - affects multiple brain regions
- Slower than glutamate but still fast (tens to hundreds of milliseconds)
- Modulatory (changes the gain/sensitivity of other processes rather than directly causing action)
- State-based (current level matters more than exact message history)

**Computational Analog:**
- Fire-and-forget pub/sub delivery
- State changes that modulate other processes
- Latest value more important than message history
- Message loss acceptable (stale state worse than no state)
- High water mark drops are feature, not bug (freshness over completeness)

**KLoROS Use Cases:**
- User interaction state (USER_VOICE_INTERACTION)
- Affective demands (Q_AFFECTIVE_DEMAND with priority="low"|"medium"|"high")
- System health status (SYSTEM_HEALTH when health_status="healthy"|"degraded")
- Capability gaps (CAPABILITY_GAP when severity="low"|"medium")

**Why This Mapping:**
Emotional states in humans are broadcast signals that modulate all cognitive processes. A shift from calm to alert doesn't require acknowledgment - it propagates through the system, affecting decision-making, memory encoding, and motor readiness. Similarly, KLoROS affective signals modulate daemon behavior systemically without requiring synchronous coordination.

#### 3. Hormonal/Neurotrophic Systems (Slow Growth Factors) → TROPHIC Channel

**Biological Function:**
- Hormones: Slow systemic regulation (hours to days)
- Neurotrophic factors: Long-term growth, learning, synaptic plasticity
- Batched/accumulated effects (e.g., cortisol rises gradually over stress exposure)
- Eventual consistency (no critical timing requirements)
- Storage and delayed release acceptable (e.g., hormone release from glands)

**Computational Analog:**
- Batched, eventually-consistent delivery
- Work distribution patterns (PUSH/PULL)
- High water marks allow large queues for batch processing
- Latency tolerance (seconds to minutes)
- Optional persistence for durability

**KLoROS Use Cases:**
- Reflection triggers and completions (Q_REFLECT_TRIGGER, Q_REFLECTION_COMPLETE)
- Housekeeping maintenance (Q_HOUSEKEEPING_TRIGGER, Q_HOUSEKEEPING_COMPLETE)
- D-REAM evolution cycles (Q_DREAM_TRIGGER, Q_DREAM_COMPLETE)
- Investigation queues (Q_CURIOSITY_INVESTIGATE, Q_INVESTIGATION_COMPLETE)
- Metrics and observations (METRICS_SUMMARY, OBSERVATION)

**Why This Mapping:**
Growth and maintenance processes in the brain operate on timescales incompatible with real-time signaling. Neurotrophic factors accumulate and batch their effects. Similarly, KLoROS's reflective and evolutionary processes operate on slow timescales where batching thousands of observations into a single processing cycle is more efficient than processing each individually.

### The Key Insight: Match Transport to Biological Timescale

The brilliance of the neuroscience analogy is that **biological timescale predicts optimal transport pattern:**

- **Reflex arc (milliseconds)** → Synchronous, acknowledged, ordered
- **Emotional modulation (sub-second)** → Asynchronous broadcast, fire-and-forget
- **Growth/learning (minutes to days)** → Batched, eventually consistent, durable

This isn't arbitrary engineering - it's exploiting evolutionary optimization that has already solved this distributed systems problem.

---

## Architectural Philosophy

### Design Principles That Guided Implementation

#### 1. Backward Compatibility is Non-Negotiable

**Principle:** Existing KLoROS daemons must continue working without modification during migration.

**Why:** KLoROS is a production system running continuously. A "flag day" migration (all code must change simultaneously) is:
- Operationally risky (single point of failure)
- Debugging nightmare (can't isolate issues to individual components)
- Violates autopoietic principle (system cannot self-maintain during migration)

**Implementation Consequence:**
- Phase 1 is metadata-only (no transport changes)
- Channel field defaults to "legacy" (preserves existing behavior)
- Emitters can specify channel without consumers needing to change
- Migration happens incrementally per signal type

#### 2. Progressive Enhancement Over Revolution

**Principle:** Add capabilities incrementally rather than replacing entire subsystems.

**Why:** Complex systems fail in complex ways. Revolutionary changes introduce unknown failure modes. Progressive enhancement allows:
- Validation at each step
- Rollback to known-good state
- Learning and adaptation during migration
- Reduced cognitive load on developers

**Implementation Consequence:**
- Phase 1: Add metadata (current state)
- Phase 2: Add dedicated transports (run in parallel with legacy)
- Phase 3: Migrate signals incrementally (validate each category)
- Phase 4: Deprecate legacy (only after full validation)

Each phase is independently deployable and testable.

#### 3. Defaults Favor Safety Over Performance

**Principle:** When in doubt, choose the conservative option that prevents data loss or corruption.

**Why:** KLoROS's memory and learning systems are stateful. A lost CRITICAL_ERROR signal could mask a serious bug. A dropped reflection result could lose hours of computation.

**Implementation Consequence:**
- Default channel is "legacy" (known-good pub/sub behavior)
- REFLEX uses acknowledgments and retries (prefer blocking over silent loss)
- TROPHIC uses large queues (prefer memory pressure over dropped work)
- AFFECT explicitly embraces message loss (only channel where drops are acceptable)

When performance becomes a bottleneck, we have observability to identify and tune specific hotspots.

#### 4. Semantic Clarity Over Mechanical Efficiency

**Principle:** Code should express intent clearly, even if slightly less efficient.

**Why:** KLoROS self-modifies through D-REAM and reflection. Future iterations of the system must understand current design intent to evolve correctly.

**Implementation Consequence:**
- Channel names are evocative of purpose (REFLEX, AFFECT, TROPHIC) not implementation (REQ_REP, PUBSUB, PUSHPULL)
- Signal definitions include detailed docstrings with Facts structure, emitters, consumers, channel rationale
- Enum-based signal definitions (type-safe, autocomplete-friendly, self-documenting)

The system should be readable as cognitive architecture, not just networking code.

#### 5. Enable Future Autonomy Scaling

**Principle:** Architecture should support future multi-node, multi-agent, federated deployments without fundamental redesign.

**Why:** KLoROS aims for increasing autonomy and scale. Current single-node implementation must not create lock-in that prevents:
- Multi-node clusters (distributed UMN federation)
- Remote investigation agents (off-system processing)
- Cloud integration (hybrid local/remote compute)

**Implementation Consequence:**
- ZMQ patterns chosen for network transparency (TCP works identically to IPC)
- Channel abstraction allows backend swap (ZMQ → NATS/Kafka in future)
- Topic-based routing enables filtering at network boundaries
- Incident IDs and replay defense prepare for distributed deduplication

---

## Phase 1 Implementation: The Metadata-Only Approach

### What Was Built

Phase 1 adds channel classification to UMN messages without changing transport behavior. Specifically:

#### 1. Extended UMNMessage Dataclass

**File:** `/home/kloros/src/kloros/orchestration/umn_bus_v2.py` (lines 38-52)

```python
@dataclass
class UMNMessage:
    signal: str
    ecosystem: str
    intensity: float = 1.0
    facts: Dict[str, Any] = field(default_factory=dict)
    incident_id: Optional[str] = None
    trace: Optional[str] = None
    ts: float = field(default_factory=lambda: time.time())
    schema_version: int = SCHEMA_VERSION
    channel: str = CHANNEL_LEGACY  # NEW: Channel classification
```

**Key Changes:**
- Added `channel` field with default value `CHANNEL_LEGACY`
- Maintains schema versioning for future migrations
- Backward compatible (existing code omitting channel works identically)

#### 2. Updated UMNPub.emit() Signature

**File:** `/home/kloros/src/kloros/orchestration/umn_bus_v2.py` (lines 181-194)

```python
def emit(self, signal: str, *, ecosystem: str, intensity: float = 1.0,
         facts: Optional[Dict[str, Any]] = None, incident_id: Optional[str] = None,
         trace: Optional[str] = None, channel: str = CHANNEL_LEGACY):
    msg = UMNMessage(
        signal=signal,
        ecosystem=ecosystem,
        intensity=intensity,
        facts=facts or {},
        incident_id=incident_id,
        trace=trace,
        channel=channel  # NEW: Channel passed through
    )
    self._impl.emit(signal, msg.to_bytes())
    logger.info(f"chem:v{SCHEMA_VERSION} emit signal={signal} ecosystem={ecosystem} channel={channel} incident_id={incident_id}")
```

**Key Changes:**
- Added `channel` parameter (keyword-only, defaults to CHANNEL_LEGACY)
- Structured logging includes channel for observability
- No change to underlying transport (still uses existing `_impl.emit()`)

#### 3. Defined Channel Constants

**File:** `/home/kloros/src/kloros/orchestration/umn_bus_v2.py` (lines 32-36)

```python
CHANNEL_LEGACY = "legacy"    # Backward compatible pub/sub
CHANNEL_REFLEX = "reflex"    # Fast, ordered, acknowledged (future)
CHANNEL_AFFECT = "affect"    # Modulatory, fire-and-forget
CHANNEL_TROPHIC = "trophic"  # Slow, batched, eventual consistency
```

**Key Changes:**
- String constants (not enum) for JSON serialization simplicity
- Comments indicate current vs future implementation status
- Evocative names aligned with neuroscience analogy

#### 4. Signal Classification in umn_signals.py

**File:** `/home/kloros/src/kloros/orchestration/umn_signals.py` (throughout)

Each signal definition now includes channel classification in its docstring:

```python
Q_REFLECT_TRIGGER = ReflectionSignal.TRIGGER.value
"""
Trigger reflection cycle.

Facts Structure: {...}
Emitters: {...}
Consumers: {...}
Ecosystem: "voice" | "orchestration"
Intensity: 1.0 (standard trigger)
Channel: trophic (batchable, delayed processing acceptable)  # NEW
"""
```

**Key Changes:**
- Every signal documents its intended channel with rationale
- Channel classification based on delivery semantics (not arbitrary)
- Provides migration roadmap for Phase 3

### Why This Approach Was Chosen

#### Alternative 1: Implement Full Transport Layer Immediately

**Rejected Because:**
- High risk (changes core message delivery mechanism)
- Difficult to debug (transport and logic changes simultaneous)
- Requires all consumers migrate simultaneously (breaks backward compatibility)
- No validation that channel classification is correct before committing to transport changes

#### Alternative 2: Wait Until Full Design Complete

**Rejected Because:**
- Delays value delivery (documentation and classification useful immediately)
- Misses opportunity to validate assumptions in production
- Creates bigger migration in future (more code to change simultaneously)

#### Chosen Approach: Metadata First

**Advantages:**
1. **Zero Risk** - Existing transport unchanged, existing code continues working
2. **Immediate Documentation Value** - Signal definitions now self-document delivery expectations
3. **Migration Enablement** - Emitters can begin specifying channels without breaking consumers
4. **Production Validation** - Can observe channel distribution in logs before committing to transport changes
5. **Incremental Path** - Each phase builds on validated foundation

**Validation Strategy:**
1. Run existing test suite (ensure 100% pass rate)
2. Deploy to development environment
3. Monitor structured logs for channel distribution
4. Identify any signals with unclear channel classification
5. Refine classification based on observed usage patterns
6. Only proceed to Phase 2 after classification validated

### What Changed and What Didn't

#### Changed:
- UMNMessage dataclass has `channel` field
- UMNPub.emit() accepts `channel` parameter
- All signal definitions document intended channel
- Structured logs include channel metadata

#### Unchanged:
- Underlying ZMQ transport (still PUB/SUB via proxy)
- Delivery semantics (still fire-and-forget with HWM=1000)
- UMNSub behavior (still subscribes to topics via ZMQ SUB)
- Proxy implementation (still uses zmq.proxy() for XSUB/XPUB forwarding)
- Consumer daemon code (no changes required)

This asymmetry is intentional - emitters can opt-in to channel awareness while consumers remain unchanged.

---

## Signal Classification Reference

### Classification Criteria

Signals were classified into channels based on these criteria:

#### REFLEX Channel Criteria:
- Requires guaranteed delivery with acknowledgment
- Ordering within sender is critical
- Failure to deliver creates safety/correctness issue
- Response needed within milliseconds to seconds
- Acceptable to block sender if consumer slow (backpressure is feature)

**Current Signals:** None (reserved for future safety-critical signals)

**Future Signals:**
- EMERGENCY_STOP (system halt required immediately)
- SAFETY_VIOLATION (security breach detected)
- CRITICAL_ERROR (unrecoverable error requires attention)
- Q_AFFECTIVE_DEMAND (when priority="urgent")

#### AFFECT Channel Criteria:
- State change or modulation signal
- Latest value more important than message history
- Acceptable to drop old messages when queue full (freshness over completeness)
- Consumers react to state changes, not individual messages
- Response needed within sub-second to seconds
- Broadcast to multiple consumers typical

**Current Signals:**
- USER_VOICE_INTERACTION (user engagement state)
- Q_AFFECTIVE_DEMAND (when priority="low"|"medium"|"high")
- SYSTEM_HEALTH (when health_status="healthy"|"degraded")
- CAPABILITY_GAP (when severity="low"|"medium")

#### TROPHIC Channel Criteria:
- Informational, telemetry, or work queue message
- Batching multiple messages improves efficiency
- Latency tolerance (seconds to minutes acceptable)
- Processing order flexible (timestamp-based reconciliation)
- High volume (benefits from batching overhead amortization)
- Optional durability needed (disk-backed queue in future)

**Current Signals:**
- Q_REFLECT_TRIGGER / Q_REFLECTION_COMPLETE
- Q_HOUSEKEEPING_TRIGGER / Q_HOUSEKEEPING_COMPLETE
- Q_DREAM_TRIGGER / Q_DREAM_COMPLETE
- Q_CURIOSITY_INVESTIGATE / Q_INVESTIGATION_COMPLETE
- OBSERVATION (raw system observations)
- METRICS_SUMMARY (periodic daemon telemetry)

#### LEGACY Channel:
- Default for backward compatibility
- Used during migration before signal reclassified
- Should trend toward zero usage as migration progresses

### Complete Signal Classification Table

| Signal | Channel | Rationale | Migration Priority |
|--------|---------|-----------|-------------------|
| Q_REFLECT_TRIGGER | trophic | Batchable reflection triggers, latency-tolerant | P1 (low risk) |
| Q_REFLECTION_COMPLETE | trophic | Informational results, eventual consistency OK | P1 (low risk) |
| Q_HOUSEKEEPING_TRIGGER | trophic | Maintenance work, delayed processing acceptable | P1 (low risk) |
| Q_HOUSEKEEPING_COMPLETE | trophic | Informational results, batching beneficial | P1 (low risk) |
| Q_DREAM_TRIGGER | trophic | Evolution cycles, slow timescale | P1 (low risk) |
| Q_DREAM_COMPLETE | trophic | Evolution results, eventual consistency OK | P1 (low risk) |
| Q_CURIOSITY_INVESTIGATE | trophic | Investigation queue, work distribution pattern | P1 (low risk) |
| Q_INVESTIGATION_COMPLETE | trophic | Investigation results, batching beneficial | P1 (low risk) |
| OBSERVATION | trophic | High-frequency telemetry, batching critical for performance | P1 (low risk) |
| METRICS_SUMMARY | trophic | Periodic metrics, batching reduces overhead | P1 (low risk) |
| USER_VOICE_INTERACTION | affect | User engagement state, fire-and-forget broadcast | P2 (moderate risk) |
| Q_AFFECTIVE_DEMAND | affect or reflex | Priority-based routing: low/med/high → affect, urgent → reflex | P3 (needs routing logic) |
| SYSTEM_HEALTH | affect or reflex | Severity-based routing: healthy/degraded → affect, critical → reflex | P3 (needs routing logic) |
| CAPABILITY_GAP | affect or trophic | Severity-based routing: low/med → affect, high → trophic (batched analysis) | P3 (needs routing logic) |

### Dynamic Channel Selection (Future Enhancement)

Some signals should route to different channels based on message content:

**Q_AFFECTIVE_DEMAND:**
```python
def route_affective_demand(msg: UMNMessage) -> str:
    priority = msg.facts.get("priority", "low")
    if priority == "urgent":
        return CHANNEL_REFLEX  # Requires acknowledgment
    else:
        return CHANNEL_AFFECT  # Fire-and-forget acceptable
```

**SYSTEM_HEALTH:**
```python
def route_system_health(msg: UMNMessage) -> str:
    health_status = msg.facts.get("health_status", "healthy")
    if health_status == "critical":
        return CHANNEL_REFLEX  # Requires immediate attention
    else:
        return CHANNEL_AFFECT  # State broadcast
```

**CAPABILITY_GAP:**
```python
def route_capability_gap(msg: UMNMessage) -> str:
    severity = msg.facts.get("severity", "low")
    if severity == "critical":
        return CHANNEL_REFLEX  # Immediate action required
    elif severity in ["low", "medium"]:
        return CHANNEL_AFFECT  # Awareness broadcast
    else:
        return CHANNEL_TROPHIC  # Queue for batch analysis
```

This dynamic routing will be implemented in Phase 3 as part of the channel-aware proxy.

---

## Code Patterns and Usage

### Emitting Signals with Channels

#### Basic Pattern (Trophic Channel)

```python
from kloros.orchestration.umn_bus_v2 import UMNPub, CHANNEL_TROPHIC

umn_pub = UMNPub()

umn_pub.emit(
    "Q_REFLECT_TRIGGER",
    ecosystem="orchestration",
    channel=CHANNEL_TROPHIC,
    intensity=1.0,
    facts={
        "trigger_reason": "idle_period",
        "idle_seconds": 600,
        "reflection_depth": 2
    },
    incident_id="reflect-20251126-001"
)
```

**When to use:** Informational signals, work queues, telemetry, anything that tolerates latency and benefits from batching.

#### Affect Channel Pattern

```python
from kloros.orchestration.umn_bus_v2 import UMNPub, CHANNEL_AFFECT

umn_pub = UMNPub()

umn_pub.emit(
    "USER_VOICE_INTERACTION",
    ecosystem="voice",
    channel=CHANNEL_AFFECT,
    intensity=0.87,  # Transcription confidence
    facts={
        "transcript": "Hello SPICA, what time is it?",
        "confidence": 0.87,
        "source": "wake_word",
        "wake_word_detected": True,
        "timestamp": time.time(),
        "audio_duration_ms": 2340
    }
)
```

**When to use:** State changes, emotional signals, modulation broadcasts, anything where latest value matters most.

#### Reflex Channel Pattern (Future)

```python
from kloros.orchestration.umn_bus_v2 import UMNPub, CHANNEL_REFLEX

umn_pub = UMNPub()

try:
    umn_pub.emit(
        "EMERGENCY_STOP",
        ecosystem="safety",
        channel=CHANNEL_REFLEX,
        intensity=1.0,
        facts={
            "stop_reason": "thermal_threshold_exceeded",
            "component": "nvidia-gpu-0",
            "temperature_c": 95.3,
            "threshold_c": 90.0
        },
        incident_id="safety-20251126-003",
        ack_timeout_ms=5000  # Wait up to 5 seconds for ACK
    )
except TimeoutError:
    logger.error("EMERGENCY_STOP not acknowledged - no safety daemon listening!")
    # Fallback to direct system action (e.g., os.system("shutdown -h now"))
except Exception as e:
    logger.error(f"EMERGENCY_STOP delivery failed: {e}")
    # Dead letter queue handling
```

**When to use:** Safety-critical signals requiring guaranteed delivery and acknowledgment.

#### Legacy Channel (During Migration)

```python
from kloros.orchestration.umn_bus_v2 import UMNPub

umn_pub = UMNPub()

# Omitting channel parameter defaults to CHANNEL_LEGACY
umn_pub.emit(
    "SOME_OLD_SIGNAL",
    ecosystem="legacy-subsystem",
    facts={"data": "value"}
)
# Equivalent to channel=CHANNEL_LEGACY
```

**When to use:** Signals not yet classified, backward compatibility during migration, temporary signals.

### Consuming Signals with Channel Awareness

#### Phase 1: Consumer Code Unchanged

```python
from kloros.orchestration.umn_bus_v2 import UMNSub

def handle_reflection_trigger(msg: Dict[str, Any]):
    trigger_reason = msg.get("facts", {}).get("trigger_reason")
    logger.info(f"Reflection triggered: {trigger_reason}")
    # Process reflection...

umn_sub = UMNSub(
    topic="Q_REFLECT_TRIGGER",
    on_json=handle_reflection_trigger,
    zooid_name="reflection-daemon",
    niche="reflection"
)
```

**Current behavior:** Subscribes to signal regardless of channel (Phase 1 has no transport separation).

#### Phase 2+: Channel-Specific Subscription (Future)

```python
from kloros.orchestration.umn_bus_v2 import UMNSub
from kloros.orchestration.umn_bus_v2 import CHANNEL_TROPHIC

# Subscribe to specific channel
umn_sub = UMNSub(
    topic="Q_REFLECT_TRIGGER",
    channel=CHANNEL_TROPHIC,  # NEW: Explicit channel subscription
    on_json=handle_reflection_trigger,
    zooid_name="reflection-daemon",
    niche="reflection"
)
```

**Future behavior:** Subscribes to channel-specific transport (PUSH/PULL for trophic, PUB/SUB for affect).

#### Phase 2+: Batch Consumer Pattern (Trophic)

```python
from kloros.orchestration.umn_bus_v2 import TrophicBatchConsumer

def handle_observation_batch(batch: List[Dict[str, Any]]):
    """Process batch of observations efficiently."""
    logger.info(f"Processing batch of {len(batch)} observations")

    # Batch processing is more efficient than individual
    observations_df = pd.DataFrame([obs["facts"] for obs in batch])
    aggregated_metrics = observations_df.groupby("source").agg({
        "cpu_percent": "mean",
        "memory_mb": "max",
        "latency_ms": "p95"
    })

    # Store aggregated results
    store_metrics(aggregated_metrics)

consumer = TrophicBatchConsumer(
    topic="OBSERVATION",
    batch_size=100,  # Process 100 observations at a time
    batch_timeout_ms=5000,  # Or timeout after 5 seconds
    on_batch=handle_observation_batch
)
```

**Future behavior:** Batches multiple messages before invoking handler, amortizing processing overhead.

#### Phase 2+: Reflex Consumer with ACK (Future)

```python
from kloros.orchestration.umn_bus_v2 import ReflexConsumer

def handle_emergency_stop(msg: Dict[str, Any]) -> bool:
    """Handle emergency stop. Return True for ACK, False for NACK."""
    try:
        stop_reason = msg["facts"]["stop_reason"]
        logger.critical(f"Emergency stop: {stop_reason}")

        # Execute safety procedure
        shutdown_all_motors()
        disable_high_power_systems()

        return True  # ACK: Successfully handled
    except Exception as e:
        logger.error(f"Failed to handle emergency stop: {e}")
        return False  # NACK: Handler failed

consumer = ReflexConsumer(
    topic="EMERGENCY_STOP",
    on_message_with_ack=handle_emergency_stop,
    zooid_name="safety-daemon"
)
```

**Future behavior:** Handler must return ACK/NACK, publisher receives delivery confirmation.

### Migration Pattern: Dual Emit

During Phase 2/3 migration, emit to both legacy and new channel to ensure zero data loss:

```python
def emit_with_migration(signal: str, channel: str, **kwargs):
    """Emit to both legacy and new channel during migration."""

    # Emit to new channel
    umn_pub.emit(signal, channel=channel, **kwargs)

    # Also emit to legacy for backward compatibility
    if channel != CHANNEL_LEGACY:
        umn_pub.emit(signal, channel=CHANNEL_LEGACY, **kwargs)
```

Once all consumers migrated and validated, remove legacy emit.

---

## Migration Path: Present to Future

### Four-Phase Migration Strategy

#### Phase 1: Metadata-Only (COMPLETE)

**Goal:** Add channel classification without changing behavior.

**Completed Work:**
- Extended UMNMessage with channel field
- Updated UMNPub.emit() to accept channel parameter
- Classified all signals in umn_signals.py
- Validated backward compatibility (all tests pass)

**Validation:**
- Existing daemons continue working without modification
- Structured logs show channel distribution
- No signal loss or corruption

**Next Steps:**
- Monitor production logs for channel usage patterns
- Identify signals with unclear classification
- Refine classification based on observed behavior

#### Phase 2: Infrastructure (PLANNED)

**Goal:** Deploy channel-aware proxy and transport implementations.

**Planned Work:**

1. **Implement Channel-Aware Proxy** (`umn_proxy_channels.py`):
   ```python
   class ChannelProxy:
       def __init__(self):
           # Legacy pub/sub for backward compatibility
           self.legacy_xsub = self._ctx.socket(zmq.XSUB)
           self.legacy_xpub = self._ctx.socket(zmq.XPUB)
           self.legacy_xsub.bind("tcp://127.0.0.1:5558")
           self.legacy_xpub.bind("tcp://127.0.0.1:5559")

           # REFLEX: DEALER/ROUTER for acknowledged delivery
           self.reflex_router = self._ctx.socket(zmq.ROUTER)
           self.reflex_router.bind("tcp://127.0.0.1:5560")

           # AFFECT: Separate pub/sub with low HWM
           self.affect_xsub = self._ctx.socket(zmq.XSUB)
           self.affect_xpub = self._ctx.socket(zmq.XPUB)
           self.affect_xsub.bind("tcp://127.0.0.1:5561")
           self.affect_xpub.bind("tcp://127.0.0.1:5562")

           # TROPHIC: PULL/PUSH for work distribution
           self.trophic_pull = self._ctx.socket(zmq.PULL)
           self.trophic_push = self._ctx.socket(zmq.PUSH)
           self.trophic_pull.bind("tcp://127.0.0.1:5563")
           self.trophic_push.bind("tcp://127.0.0.1:5564")
   ```

2. **Implement Channel-Specific Publishers**:
   - `_ZmqReflexPub` (DEALER with ACK/NACK handling)
   - `_ZmqAffectPub` (PUB with HWM=100)
   - `_ZmqTrophicPub` (PUSH with HWM=10000)

3. **Implement Channel-Specific Subscribers**:
   - `_ZmqReflexSub` (DEALER with ACK/NACK emission)
   - `_ZmqAffectSub` (SUB with HWM=100)
   - `_ZmqTrophicSub` (PULL with batching support)

4. **Update UMNPub to Dispatch by Channel**:
   ```python
   class UMNPub:
       def __init__(self, enable_channels: bool = False):
           self._enable_channels = enable_channels
           if enable_channels:
               self._reflex = _ZmqReflexPub()
               self._affect = _ZmqAffectPub()
               self._trophic = _ZmqTrophicPub()
           self._legacy = _ZmqPub()  # Always available

       def emit(self, signal: str, *, channel: str = CHANNEL_LEGACY, **kwargs):
           if self._enable_channels and channel != CHANNEL_LEGACY:
               if channel == CHANNEL_REFLEX:
                   self._reflex.emit(signal, payload, timeout_ms=5000)
               elif channel == CHANNEL_AFFECT:
                   self._affect.emit(signal, payload)
               elif channel == CHANNEL_TROPHIC:
                   self._trophic.emit(signal, payload)
           else:
               self._legacy.emit(signal, payload)
   ```

5. **Deploy in Parallel with Legacy**:
   - Run both old and new proxy simultaneously
   - Emitters dual-emit to both legacy and new channels
   - Consumers subscribe to both during migration
   - Validate no message loss between systems

**Validation:**
- Both proxies run stably in production
- Metrics dashboard shows traffic on all channels
- Latency and throughput meet expectations
- No message loss during dual-emit period

**Timeline:** 2-4 weeks after Phase 1 validation

#### Phase 3: Signal Migration (PLANNED)

**Goal:** Migrate signals incrementally to appropriate channels.

**Migration Order:**

**Week 1-2: Trophic Signals (Lowest Risk)**
- Start with high-volume, low-criticality signals
- Benefits from batching immediately visible
- Failure mode benign (worst case: slower processing)

Signals to migrate:
- OBSERVATION (high volume, batching critical)
- METRICS_SUMMARY (periodic telemetry)
- Q_REFLECT_TRIGGER / Q_REFLECTION_COMPLETE
- Q_HOUSEKEEPING_TRIGGER / Q_HOUSEKEEPING_COMPLETE

Migration procedure per signal:
1. Enable dual-emit (legacy + trophic)
2. Update consumers to subscribe to trophic channel
3. Monitor for 48 hours (validate no loss)
4. Disable legacy emit
5. Monitor for 48 hours (validate consumers healthy)

**Week 3-4: Affect Signals (Moderate Risk)**
- Modulation signals with fire-and-forget semantics
- Validate HWM drop behavior acceptable

Signals to migrate:
- USER_VOICE_INTERACTION
- Q_AFFECTIVE_DEMAND (non-urgent priority only)
- SYSTEM_HEALTH (non-critical status only)
- CAPABILITY_GAP (low/medium severity only)

Migration procedure:
1. Enable dual-emit (legacy + affect)
2. Update consumers to subscribe to affect channel
3. Artificially stress HWM (generate high traffic)
4. Validate drop behavior acceptable (stale state worse than no state)
5. Disable legacy emit

**Week 5-6: Reflex Signals (Highest Risk)**
- Safety-critical signals requiring acknowledgment
- Start with new signals (EMERGENCY_STOP, CRITICAL_ERROR)
- Validate ACK/NACK/timeout behavior thoroughly

New signals to implement:
- EMERGENCY_STOP (thermal limits, safety violations)
- CRITICAL_ERROR (unrecoverable daemon errors)
- Q_AFFECTIVE_DEMAND (urgent priority only)
- SYSTEM_HEALTH (critical status only)

Testing procedure:
1. Implement reflex consumer with ACK handler
2. Test ACK success path (normal case)
3. Test NACK path (handler failure)
4. Test timeout path (consumer unavailable)
5. Test retry logic (exponential backoff)
6. Test dead letter queue (after max retries)
7. Deploy with comprehensive monitoring

**Week 7-8: Dynamic Routing**
- Implement content-based routing for multi-channel signals
- Q_AFFECTIVE_DEMAND routes to affect or reflex based on priority
- SYSTEM_HEALTH routes to affect or reflex based on status
- CAPABILITY_GAP routes to affect or trophic based on severity

**Validation:**
- All signals migrated and validated
- Channel-specific metrics within expected ranges
- Failure scenarios tested and verified
- Performance benchmarks met

**Timeline:** 2 months after Phase 2 complete

#### Phase 4: Legacy Deprecation (PLANNED)

**Goal:** Remove legacy proxy and backward compatibility code.

**Planned Work:**

**Week 1-2: Remove Legacy Emits**
- Audit all emitters for dual-emit code
- Remove legacy emit calls
- Validate all consumers on new channels
- Update tests to use new channel patterns

**Week 3-4: Deprecate Legacy Proxy**
- Add deprecation warning to legacy proxy
- Monitor connection attempts to legacy endpoints
- Contact owners of any stragglers
- Set shutdown date for legacy proxy

**Week 5-6: Remove Legacy Code**
- Stop legacy proxy in production
- Remove legacy transport implementations
- Remove CHANNEL_LEGACY constant
- Update documentation to reflect new-only architecture

**Week 7-8: Final Validation**
- Full system test on new architecture
- Performance benchmarking
- Failure scenario validation
- Documentation update
- Team training

**Validation:**
- Zero dependencies on legacy proxy
- All tests pass without legacy code
- Documentation complete and accurate
- Team fully trained

**Timeline:** 1 month after Phase 3 complete

### Total Migration Timeline: 4-6 Months

This incremental approach minimizes risk while delivering value at each phase.

---

## Design Rationale: Why These Choices

### ZMQ Patterns for Each Channel

#### REFLEX: Why DEALER/ROUTER?

**Alternative Considered:** REQ/REP

**REQ/REP Issues:**
- Strictly synchronous (blocks until reply)
- No load balancing across multiple consumers
- Single point of failure (if consumer dies, publisher blocked)

**DEALER/ROUTER Advantages:**
- Asynchronous with explicit ACK (non-blocking sends, poll for ACK)
- Load balancing (multiple REPLYs, ROUTER distributes)
- Retry logic possible (if no ACK, retry with exponential backoff)
- Dead letter queue (after max retries, persist to DLQ)

**Trade-offs:**
- More complex than REQ/REP (must manually handle ACK/NACK)
- Requires identity management (DEALER sets identity for routing)

**Decision:** DEALER/ROUTER chosen for flexibility and fault tolerance. Synchronous blocking acceptable for safety-critical signals, but load balancing and retry logic essential.

#### AFFECT: Why PUB/SUB?

**Alternative Considered:** PUSH/PULL

**PUSH/PULL Issues:**
- Work distribution pattern (load balances across consumers)
- Only one consumer receives each message
- Incompatible with broadcast semantics (all consumers should receive state changes)

**PUB/SUB Advantages:**
- True broadcast (all subscribers receive)
- Topic-based filtering (consumers choose signals of interest)
- Low HWM acceptable (freshness over completeness)
- ZMQ optimized for pub/sub (kernel bypass, efficient multicast)

**Trade-offs:**
- No acknowledgment (fire-and-forget only)
- Slow joiner problem (subscribers must connect before publisher sends)

**Decision:** PUB/SUB is the only pattern that matches broadcast state modulation semantics. Slow joiner handled with double-tap pattern (already implemented in current UMN).

#### TROPHIC: Why PUSH/PULL?

**Alternative Considered:** PUB/SUB with consumer-side batching

**PUB/SUB with Batching Issues:**
- Batching logic in every consumer (duplication)
- No backpressure (publisher doesn't know if consumers overwhelmed)
- Broadcast semantics waste bandwidth (all consumers get all messages)

**PUSH/PULL Advantages:**
- Work distribution (each message goes to exactly one consumer)
- Natural batching (PULL can receive multiple messages before processing)
- Backpressure (PUSH blocks when HWM reached, signals producer to slow down)
- Parallelization (multiple workers drain queue in parallel)

**Trade-offs:**
- Not a broadcast (single consumer per message)
- Requires work distribution semantics (acceptable for investigations, metrics)

**Decision:** PUSH/PULL matches work queue semantics. For signals that benefit from broadcast + batching (e.g., OBSERVATION consumed by multiple systems), use multiple PULL consumers or hybrid approach with PUB (for broadcast awareness) + PUSH (for work queue).

### Why Defaults Favor Safety

#### Default Channel: CHANNEL_LEGACY

**Alternative:** No default (require explicit channel)

**Rejected Because:**
- Breaks backward compatibility (all existing emits fail)
- Forces immediate migration (violates progressive enhancement)
- Adds boilerplate (every emit must specify channel)

**Chosen Approach:**
- Default to CHANNEL_LEGACY (preserves existing behavior)
- Migrate signals incrementally (validate each category)
- Eventually deprecate CHANNEL_LEGACY (after full migration)

#### REFLEX Timeout: 5 Seconds (Default)

**Alternative:** 1 second or 100ms

**Shorter Timeout Issues:**
- False positives on slow consumers (especially under load)
- Unnecessary retries (network jitter can cause 100ms delays)
- Dead letter queue pollution (legitimate messages marked failed)

**Longer Timeout Issues:**
- Delays error detection (if consumer actually dead)
- Blocks sender longer (if synchronous)

**Chosen Approach:**
- 5 second default (balances false positives vs error detection)
- Configurable per signal (allow override for specific use cases)
- Exponential backoff retries (100ms, 200ms, 400ms before final timeout)

#### AFFECT HWM: 100 Messages

**Alternative:** 1000 (same as current legacy)

**Higher HWM Issues:**
- Stale state accumulates (100 messages at 10ms = 1 second of stale state)
- Memory pressure (larger queue)
- Defeats purpose (affect channel should favor freshness)

**Lower HWM (e.g., 10) Issues:**
- Bursty traffic causes excessive drops
- Network delays can trigger drops unnecessarily

**Chosen Approach:**
- HWM=100 (balances burst tolerance vs freshness)
- Monitor drop metrics in production
- Tune per-signal if needed (environment variable override)

#### TROPHIC HWM: 10000 Messages

**Alternative:** 1000 (same as current legacy)

**Lower HWM Issues:**
- Defeats batching benefit (can't accumulate enough for efficient batch)
- Backpressure triggers too early (slows producers unnecessarily)

**Higher HWM Issues:**
- Memory pressure (10000 messages * average size = memory footprint)
- Disk swap risk (if queue exceeds RAM)

**Chosen Approach:**
- HWM=10000 (allows large batches, tolerates bursty telemetry)
- Optional disk-backed queue in future (SQLite, RocksDB)
- Monitor queue depth metrics (alert if sustained high depth)

### Why Topic Prefix Over Envelope Field

#### Alternative 1: Envelope Field Only

**Approach:**
```python
{"signal": "Q_REFLECT_TRIGGER", "channel": "trophic", ...}
```
Subscribers filter in application code after receiving message.

**Issues:**
- Network bandwidth wasted (receive all messages, discard most)
- CPU wasted (JSON parsing for every message, even unsubscribed)
- Defeats ZMQ topic filtering efficiency (kernel-level filtering)

#### Alternative 2: Topic Prefix Only

**Approach:**
```python
topic = f"{channel}.{signal}"  # "trophic.Q_REFLECT_TRIGGER"
```
ZMQ SUB filters at kernel level.

**Issues:**
- Topic string encoding (need delimiter that doesn't appear in signal names)
- Backward compatibility (existing subscribers expect just signal name)

#### Chosen Approach: Both (Hybrid)

**Phase 1-2:**
- Envelope field for backward compatibility (existing subscribers work)
- Topic prefix unused (all messages use signal name as topic)

**Phase 3+:**
- Topic prefix for ZMQ filtering (`trophic.Q_REFLECT_TRIGGER`)
- Envelope field retained for application-level routing

**Advantages:**
- Backward compatible during migration
- Efficient kernel-level filtering after migration
- Application-level routing for dynamic channel selection

---

## Extension Guide: Building on This Foundation

### Adding a New Signal

**Step 1: Define Signal in umn_signals.py**

```python
class SafetySignal(str, Enum):
    """UMN signals for safety system."""
    EMERGENCY_STOP = "EMERGENCY_STOP"
    THERMAL_WARNING = "THERMAL_WARNING"

EMERGENCY_STOP = SafetySignal.EMERGENCY_STOP.value
"""
Emergency stop signal requiring immediate system halt.

Facts Structure:
    {
        "stop_reason": str,              # Reason for emergency stop
        "component": str,                # Component triggering stop
        "severity": str,                 # "warning" | "critical" | "catastrophic"
        "recommended_action": str,       # Suggested remediation
    }

Emitters:
    - Thermal monitoring daemon
    - Safety watchdog
    - Manual emergency stop (user command)

Consumers:
    - Safety daemon: Executes shutdown procedures
    - Alert system: Notifies user
    - Logging system: Records incident

Ecosystem: "safety"
Intensity: 1.0 (critical)
Channel: reflex (requires acknowledgment, blocking acceptable)
"""
```

**Step 2: Classify Channel**

Use decision tree:

1. **Does failure to deliver create safety/correctness issue?**
   - Yes → REFLEX
   - No → Continue

2. **Is this a state change that modulates other processes?**
   - Yes → AFFECT
   - No → Continue

3. **Can this be batched with other similar messages?**
   - Yes → TROPHIC
   - No → AFFECT (likely state-based even if not obvious)

For EMERGENCY_STOP:
- Safety-critical? Yes → **REFLEX**

**Step 3: Implement Emitter**

```python
from kloros.orchestration.umn_bus_v2 import UMNPub, CHANNEL_REFLEX
from kloros.orchestration.umn_signals import EMERGENCY_STOP

umn_pub = UMNPub()

def trigger_emergency_stop(reason: str, component: str):
    try:
        umn_pub.emit(
            EMERGENCY_STOP,
            ecosystem="safety",
            channel=CHANNEL_REFLEX,
            intensity=1.0,
            facts={
                "stop_reason": reason,
                "component": component,
                "severity": "critical",
                "recommended_action": "manual_inspection_required"
            },
            incident_id=f"safety-{int(time.time())}",
            ack_timeout_ms=5000
        )
        logger.critical(f"Emergency stop delivered and acknowledged: {reason}")
    except TimeoutError:
        logger.error(f"Emergency stop NOT acknowledged - fallback required")
        # Fallback to direct action (no daemon listening)
        os.system("shutdown -h now")
    except Exception as e:
        logger.error(f"Emergency stop delivery failed: {e}")
```

**Step 4: Implement Consumer (Phase 2+)**

```python
from kloros.orchestration.umn_bus_v2 import ReflexConsumer
from kloros.orchestration.umn_signals import EMERGENCY_STOP

def handle_emergency_stop(msg: Dict[str, Any]) -> bool:
    """Handle emergency stop with ACK."""
    try:
        reason = msg["facts"]["stop_reason"]
        component = msg["facts"]["component"]

        logger.critical(f"EMERGENCY STOP: {reason} (component: {component})")

        # Execute safety procedures
        shutdown_all_motors()
        disable_high_power_systems()
        close_safety_valves()

        # Log incident for post-mortem
        log_safety_incident(msg)

        return True  # ACK: Successfully handled
    except Exception as e:
        logger.error(f"Emergency stop handler failed: {e}")
        return False  # NACK: Handler failed, sender should retry

consumer = ReflexConsumer(
    topic=EMERGENCY_STOP,
    on_message_with_ack=handle_emergency_stop,
    zooid_name="safety-daemon"
)
```

### Adding a New Channel Type

**Use Case:** Need a new delivery semantic not covered by REFLEX/AFFECT/TROPHIC.

**Example:** MULTICAST channel for hierarchical broadcast (emit to subsystem, subsystem re-broadcasts to children).

**Step 1: Define Channel Constant**

```python
# In umn_bus_v2.py
CHANNEL_MULTICAST = "multicast"  # Hierarchical broadcast with re-emission
```

**Step 2: Document Semantics**

```python
"""
MULTICAST Channel: Hierarchical broadcast with relay.

Characteristics:
- Publisher emits to subsystem coordinators
- Coordinators re-emit to their subordinates
- Tree topology (reduces broadcast storm)
- Acknowledgment at coordinator level only
- Best-effort delivery to leaves

Use Cases:
- System-wide configuration changes
- Coordinated mode transitions
- Hierarchical state synchronization

ZMQ Pattern: PUB/SUB with coordinator re-emission
HWM: 500 (moderate queue for coordinator processing)
"""
```

**Step 3: Implement Transport**

```python
class _ZmqMulticastPub:
    """MULTICAST publisher with coordinator targeting."""
    def __init__(self, endpoint: str = "tcp://127.0.0.1:5565"):
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PUB)
        self._sock.connect(endpoint)
        self._sock.setsockopt(zmq.SNDHWM, 500)

    def emit(self, topic: str, payload: bytes):
        # Emit with multicast prefix for coordinator filtering
        self._sock.send_multipart([f"multicast.{topic}".encode(), payload])

class _ZmqMulticastCoordinator:
    """MULTICAST coordinator that re-emits to subordinates."""
    def __init__(self, coordinator_id: str, subordinate_endpoint: str):
        self._coordinator_id = coordinator_id

        # Subscribe to coordinator-level messages
        self._sub = _ZmqSub(topic=f"multicast.coordinator.{coordinator_id}")

        # Publish to subordinates
        self._pub = _ZmqPub(subordinate_endpoint)

    def relay_to_subordinates(self, msg: UMNMessage):
        # Re-emit to subordinates with subordinate prefix
        self._pub.emit(f"subordinate.{msg.signal}", msg.to_bytes())
```

**Step 4: Update Proxy**

```python
class ChannelProxy:
    def __init__(self):
        # ... existing channels ...

        # MULTICAST: Separate pub/sub for coordinator relay
        self.multicast_xsub = self._ctx.socket(zmq.XSUB)
        self.multicast_xpub = self._ctx.socket(zmq.XPUB)
        self.multicast_xsub.bind("tcp://127.0.0.1:5565")
        self.multicast_xpub.bind("tcp://127.0.0.1:5566")
```

**Step 5: Classify Signals**

Determine which signals benefit from hierarchical broadcast:

```python
SYSTEM_MODE_CHANGE = "SYSTEM_MODE_CHANGE"
"""
System-wide mode change (e.g., ACTIVE → MAINTENANCE).

Channel: multicast (hierarchical broadcast via coordinators)
"""
```

### Implementing Priority Lanes within Channel

**Use Case:** AFFECT channel needs differentiation between high-priority and low-priority affective signals.

**Approach 1: Multiple Topics**

```python
# Emit high-priority to dedicated topic
umn_pub.emit(
    "Q_AFFECTIVE_DEMAND",
    ecosystem="affect",
    channel=CHANNEL_AFFECT,
    facts={"priority": "high", ...},
    topic_suffix="high"  # Results in topic "affect.high.Q_AFFECTIVE_DEMAND"
)

# Consumer subscribes to high-priority only
umn_sub = UMNSub(
    topic="affect.high.*",  # Wildcard for all high-priority affect signals
    on_json=handle_high_priority_affect
)
```

**Approach 2: Multiple Channels**

```python
# Define priority lanes
CHANNEL_AFFECT_HIGH = "affect-high"
CHANNEL_AFFECT_LOW = "affect-low"

# Emit to appropriate lane
def emit_affective_demand(priority: str, **kwargs):
    if priority in ["high", "urgent"]:
        channel = CHANNEL_AFFECT_HIGH
    else:
        channel = CHANNEL_AFFECT_LOW

    umn_pub.emit("Q_AFFECTIVE_DEMAND", channel=channel, **kwargs)

# Consumer prioritizes high lane
high_sub = UMNSub(topic="Q_AFFECTIVE_DEMAND", channel=CHANNEL_AFFECT_HIGH)
low_sub = UMNSub(topic="Q_AFFECTIVE_DEMAND", channel=CHANNEL_AFFECT_LOW)
```

**Trade-offs:**
- Approach 1: Simpler (no new channels), filtering in ZMQ topic
- Approach 2: More explicit (channel names indicate priority), easier to tune HWM per lane

**Recommendation:** Start with Approach 1 (topics), migrate to Approach 2 if tuning requirements diverge significantly.

---

## Performance Characteristics

### Latency Profiles by Channel

#### REFLEX Channel (Phase 2+)

**Expected Latency:**
- **p50:** 1-5ms (fast path, ACK from local consumer)
- **p95:** 10-50ms (slow consumer processing)
- **p99:** 100-500ms (retry with exponential backoff)
- **Timeout:** 5000ms (configurable, after retries exhausted)

**Bottlenecks:**
- Consumer processing time (blocking emit until ACK)
- Network latency (if TCP over network vs loopback)
- Retry delays (exponential backoff adds latency on retries)

**Optimization Strategies:**
- Use loopback TCP (127.0.0.1) not external network
- Increase consumer threads (parallel ACK handling)
- Tune timeout per signal type (safety-critical can be longer)

#### AFFECT Channel

**Expected Latency:**
- **p50:** 0.1-1ms (fire-and-forget, no ACK wait)
- **p95:** 1-5ms (ZMQ pub/sub overhead)
- **p99:** 5-10ms (kernel scheduling delays)
- **HWM Drop:** Instant (no queueing delay if full)

**Bottlenecks:**
- HWM reached (drops messages instead of queueing)
- Slow joiner problem (subscribers miss early messages)
- Multicast inefficiency (all subscribers receive all messages)

**Optimization Strategies:**
- Tune HWM per signal type (bursty signals need higher HWM)
- Use last-value-cache (ZMQ XPUB_LVC) for state signals
- Monitor drop metrics (alert if sustained high drop rate)

#### TROPHIC Channel

**Expected Latency:**
- **p50:** 1-10ms (PUSH/PULL roundtrip)
- **p95:** 10-100ms (batch accumulation delay)
- **p99:** 100-5000ms (batch timeout reached)
- **Batch Processing:** 5-30 seconds (configurable batch timeout)

**Bottlenecks:**
- Batch accumulation delay (trade-off: latency vs throughput)
- Large batch processing time (100+ messages at once)
- Queue depth growth (if consumer slower than producer)

**Optimization Strategies:**
- Tune batch size vs timeout (latency-sensitive: small batch, throughput-sensitive: large batch)
- Parallel workers (multiple PULL consumers drain queue faster)
- Disk-backed queue (prevent memory pressure from large queues)

### Throughput Benchmarks

#### REFLEX Channel (Estimated, Phase 2+)

**Single Consumer:**
- **Throughput:** 100-1000 msgs/sec (limited by ACK roundtrip)
- **Bottleneck:** Consumer processing + ACK latency

**Multiple Consumers (Load Balanced):**
- **Throughput:** N * 100-1000 msgs/sec (linear scaling)
- **Bottleneck:** Publisher serialization (single thread)

**Optimization:**
- Multiple publisher threads (parallel DEALER sockets)
- Consumer thread pool (parallel ACK emission)

#### AFFECT Channel

**Single Publisher:**
- **Throughput:** 10,000-100,000 msgs/sec (ZMQ PUB optimized)
- **Bottleneck:** Subscriber processing (all subscribers receive all messages)

**Multiple Subscribers:**
- **Throughput:** Same (broadcast, all receive)
- **Bottleneck:** Slowest subscriber hits HWM, drops messages

**Optimization:**
- Topic filtering (subscribers only receive filtered subset)
- Increase HWM for bursty signals
- Multiple subscriber threads (parallel processing)

#### TROPHIC Channel

**Single Worker:**
- **Throughput:** 1,000-10,000 msgs/sec (limited by batch processing)
- **Bottleneck:** Batch processing time (handler invocation overhead)

**Multiple Workers (Parallel PULL):**
- **Throughput:** N * 1,000-10,000 msgs/sec (linear scaling)
- **Bottleneck:** Publisher serialization or network bandwidth

**Optimization:**
- Increase batch size (amortize handler overhead)
- Parallel workers (multiple PULL consumers)
- Disk-backed queue (persistent throughput under load spikes)

### Memory Footprint

#### Per-Channel Queue Sizes

**REFLEX:**
- HWM: 1000 (default ZMQ, not tuned yet)
- Average message size: ~500 bytes (JSON-encoded UMNMessage)
- Memory per queue: 500 KB
- Total (publisher + consumer + proxy): ~1.5 MB

**AFFECT:**
- HWM: 100
- Average message size: ~500 bytes
- Memory per queue: 50 KB
- Total: ~150 KB (minimal footprint for freshness)

**TROPHIC:**
- HWM: 10,000
- Average message size: ~500 bytes
- Memory per queue: 5 MB
- Total: ~15 MB (acceptable for large batches)

**Total UMN Memory Footprint:** ~17 MB (all channels active)

**Growth Scenarios:**
- If average message size doubles (1 KB): ~34 MB
- If TROPHIC HWM increases to 100,000: ~150 MB
- If multiple publishers/consumers: linear scaling per socket

**Mitigation:**
- Disk-backed queues for TROPHIC (offload to disk when HWM approaching)
- Message compression (zlib/lz4 for large Facts payloads)
- Topic filtering (reduce irrelevant messages delivered to subscribers)

---

## Debugging and Observability

### Structured Logging

All UMN operations emit structured logs for tracing and debugging:

#### Emit Logging

```python
logger.info(f"chem:v{SCHEMA_VERSION} emit signal={signal} ecosystem={ecosystem} channel={channel} incident_id={incident_id}")
```

**Example Output:**
```
2025-11-26 14:32:01 INFO chem:v1 emit signal=Q_REFLECT_TRIGGER ecosystem=orchestration channel=trophic incident_id=reflect-20251126-001
```

**Queryable Fields:**
- `signal`: Signal type
- `ecosystem`: Source ecosystem
- `channel`: Target channel
- `incident_id`: Unique incident identifier
- `schema_version`: Protocol version

**Use Cases:**
- Trace signal flow (follow incident_id through system)
- Channel distribution analysis (group by channel, count)
- Ecosystem activity monitoring (which ecosystems most active)

#### Consumer Logging

```python
logger.info(f"chem:v{SCHEMA_VERSION} {self.zooid_name} subscribed to {topic} niche={self.niche}")
```

**Example Output:**
```
2025-11-26 14:32:05 INFO chem:v1 reflection-daemon subscribed to Q_REFLECT_TRIGGER niche=reflection
```

**Use Cases:**
- Verify consumer startup (did daemon subscribe successfully)
- Identify consumer restarts (timestamp gaps indicate crash/restart)
- Map niche to zooid (which daemons serve which niches)

#### Replay Defense Logging

```python
logger.debug(f"chem:v{SCHEMA_VERSION} {self.zooid_name} skipping duplicate incident_id={incident_id}")
```

**Use Cases:**
- Detect duplicate emissions (emitter retrying incorrectly)
- Validate replay defense (duplicates properly filtered)

### Metrics Dashboard (Prometheus)

#### Signals Emitted

```python
umn_messages_sent = Counter('umn_messages_sent_total', 'Messages sent', ['channel', 'signal'])
```

**Queries:**
- Total messages per channel: `sum(rate(umn_messages_sent_total[5m])) by (channel)`
- Top signals by volume: `topk(10, sum(rate(umn_messages_sent_total[5m])) by (signal))`
- Channel distribution: `sum(umn_messages_sent_total) by (channel)`

#### Queue Depth

```python
umn_queue_depth = Gauge('umn_queue_depth', 'Current queue depth', ['channel'])
```

**Queries:**
- Current depth per channel: `umn_queue_depth`
- Alert on sustained high depth: `umn_queue_depth{channel="trophic"} > 8000 for 5m`

#### Message Latency

```python
umn_message_latency = Histogram('umn_message_latency_seconds', 'Message latency', ['channel'])
```

**Queries:**
- p95 latency per channel: `histogram_quantile(0.95, umn_message_latency_seconds)`
- Alert on high latency: `histogram_quantile(0.95, umn_message_latency_seconds{channel="reflex"}) > 0.1 for 5m`

#### REFLEX Acknowledgments

```python
umn_reflex_acks = Counter('umn_reflex_acks_total', 'REFLEX acknowledgments', ['status'])
```

**Queries:**
- ACK success rate: `sum(rate(umn_reflex_acks_total{status="ack"}[5m])) / sum(rate(umn_reflex_acks_total[5m]))`
- NACK count: `sum(rate(umn_reflex_acks_total{status="nack"}[5m]))`
- Timeout count: `sum(rate(umn_reflex_acks_total{status="timeout"}[5m]))`

### Debugging Recipes

#### Problem: Signal Not Received by Consumer

**Step 1: Verify Emission**
```bash
grep "emit signal=Q_REFLECT_TRIGGER" /var/log/kloros/*.log
```
Confirm signal was emitted with correct topic.

**Step 2: Verify Subscription**
```bash
grep "subscribed to Q_REFLECT_TRIGGER" /var/log/kloros/*.log
```
Confirm consumer subscribed to correct topic.

**Step 3: Check Proxy Status**
```bash
systemctl status umn-proxy
```
Verify proxy running and healthy.

**Step 4: Check HWM Drops**
```bash
# Phase 2+ with metrics
curl localhost:9090/metrics | grep umn_messages_dropped_total
```
If drops > 0, HWM reached and messages lost.

**Step 5: Check Replay Defense**
```bash
grep "skipping duplicate incident_id" /var/log/kloros/*.log
```
If found, consumer already processed this incident_id.

#### Problem: High REFLEX NACK Rate

**Step 1: Identify Failing Consumers**
```bash
grep "NACK received" /var/log/kloros/*.log
```
Find which signals triggering NACKs.

**Step 2: Review Consumer Handler Errors**
```bash
grep "error processing message" /var/log/kloros/*.log
```
Identify exception in handler causing NACK.

**Step 3: Check Consumer Health**
```bash
# Verify consumer daemon running
systemctl status safety-daemon

# Check resource usage
top -p $(pgrep -f safety-daemon)
```

**Step 4: Validate Facts Structure**
```bash
# Extract NACK'd message from logs
grep "NACK received" /var/log/kloros/*.log | jq '.facts'
```
Confirm Facts structure matches handler expectations.

#### Problem: TROPHIC Queue Depth Growing

**Step 1: Check Current Depth**
```bash
curl localhost:9090/metrics | grep umn_queue_depth{channel="trophic"}
```

**Step 2: Identify Producer Rate**
```bash
# Messages sent per second
sum(rate(umn_messages_sent_total{channel="trophic"}[5m]))
```

**Step 3: Identify Consumer Rate**
```bash
# Messages received per second
sum(rate(umn_messages_received_total{channel="trophic"}[5m]))
```

**Step 4: Calculate Lag**
```bash
# If producer > consumer, queue grows
# Lag = (producer_rate - consumer_rate) * time
```

**Step 5: Mitigation**
- Add more consumer workers (parallel PULL)
- Increase batch size (reduce per-message overhead)
- Enable disk-backed queue (prevent memory pressure)

---

## Lessons Learned and Best Practices

### What Worked Well

#### 1. Metadata-First Approach

**Decision:** Phase 1 adds channel metadata without changing transport.

**Outcome:** Zero production issues, 100% backward compatibility maintained.

**Why It Worked:**
- Validates classification before committing to transport changes
- Enables incremental migration (emitters opt-in, consumers unchanged)
- Provides observability (logs show channel distribution before behavior changes)
- De-risks Phase 2 (know exactly which signals use which channels)

**Lesson:** When migrating core infrastructure, metadata and observability before behavior changes.

#### 2. Neuroscience Analogy for Design Clarity

**Decision:** Model channels after neurotransmitter systems (glutamate, dopamine, hormones).

**Outcome:** Team immediately understands intent without reading implementation.

**Why It Worked:**
- Evocative names communicate purpose (REFLEX vs REQ_REP_SYNC)
- Biological timescales predict transport patterns (reflex → synchronous, hormonal → batched)
- Extensible mental model (can add new channels with clear semantics)

**Lesson:** Domain-inspired abstractions improve code comprehension and evolution.

#### 3. Comprehensive Documentation with Rationale

**Decision:** Document not just WHAT but WHY for every design choice.

**Outcome:** Future developers (including KLoROS self-modification) can understand intent.

**Why It Worked:**
- Alternatives considered sections explain rejected options (prevents repeated mistakes)
- Design rationale explains constraints (safety over performance)
- Migration path provides roadmap (reduces decision paralysis)

**Lesson:** Documentation for self-modifying systems must explain reasoning, not just behavior.

### What Could Be Improved

#### 1. Earlier Prototyping of Transport Layer

**Issue:** Phase 1 completes without validating REFLEX ACK/NACK mechanism.

**Risk:** Phase 2 may discover ACK pattern doesn't work as expected.

**Improvement:**
- Build throwaway prototype of REFLEX transport in parallel with Phase 1
- Validate ACK latency, NACK handling, timeout behavior
- Benchmark throughput before committing to architecture

**Lesson:** For novel patterns (REFLEX acknowledged pub/sub), prototype before documenting.

#### 2. More Explicit Failure Mode Documentation

**Issue:** Current docs focus on happy path, less on failure scenarios.

**Example:** What happens if REFLEX consumer dies mid-ACK? Is message redelivered?

**Improvement:**
- Add "Failure Modes and Recovery" section per channel
- Document exactly-once vs at-least-once semantics
- Test failure scenarios (consumer crash, network partition, proxy restart)

**Lesson:** Distributed systems documentation must be failure-mode-first.

#### 3. Performance Benchmarking Earlier

**Issue:** Latency/throughput numbers are estimates, not measured.

**Risk:** Phase 2 deployment may discover performance doesn't meet expectations.

**Improvement:**
- Benchmark current ZMQ pub/sub (establish baseline)
- Benchmark REQ/REP, DEALER/ROUTER, PUSH/PULL patterns
- Validate HWM behavior under load (does drop happen as expected)

**Lesson:** Measure before committing to performance-critical architecture changes.

### Best Practices for Future Channel Development

#### 1. Start with Signal Classification

Before implementing any transport:
1. List all signals in category
2. Document Facts structure
3. Identify emitters and consumers
4. Classify delivery requirements (latency, ordering, acknowledgment, batching)
5. Choose channel based on requirements (not arbitrary)

#### 2. Validate in Logs Before Migrating Transport

After adding metadata:
1. Deploy to production with logging enabled
2. Monitor channel distribution for 1 week
3. Identify anomalies (signals in unexpected channels)
4. Refine classification based on observed patterns
5. Only proceed to transport migration after validation

#### 3. Dual-Emit During Migration

When changing transport:
1. Emit to both old and new channels simultaneously
2. Subscribe to both in consumers
3. Monitor for discrepancies (missing messages in new channel)
4. Disable old emit only after 48h+ validation
5. Remove old subscription last (most conservative)

#### 4. Monitor Channel-Specific Metrics

For each channel:
- Messages sent/received (throughput)
- Queue depth (backpressure indicator)
- Latency distribution (p50, p95, p99)
- Drop count (HWM reached)
- Error rate (NACK, timeout for REFLEX)

Alert on sustained anomalies, not transient spikes.

#### 5. Document Failure Modes Explicitly

For each channel:
- What happens if consumer dies during processing?
- What happens if network partitions?
- What happens if proxy restarts?
- What are exactly-once vs at-least-once vs at-most-once semantics?
- How do we recover from each failure mode?

Test these scenarios in staging before production deployment.

---

## Conclusion

The UMN Channels architecture represents a fundamental evolution in KLoROS's cognitive infrastructure. By differentiating signal pathways based on neuroscience-inspired delivery semantics, we've created a foundation for:

1. **Safety** - Critical signals receive guaranteed delivery with acknowledgment
2. **Performance** - Slow signals no longer block fast signals
3. **Scalability** - Batching optimizes high-volume telemetry
4. **Clarity** - Channel names communicate intent and delivery expectations
5. **Evolvability** - Phased migration enables learning and adaptation

### Current State (Phase 1)

- Channel metadata added to all signals
- Signal classification complete and documented
- Backward compatibility maintained 100%
- Structured logging enables observability
- Production validation in progress

### Future Vision (Phase 2-4)

- Dedicated transports per channel (REQ/REP, PUB/SUB, PUSH/PULL)
- Dynamic routing based on message content (priority, severity)
- Disk-backed queues for durability
- Multi-node federation for distributed KLoROS
- Cross-channel orchestration for complex workflows

### Call to Action for KLoROS

Study this document to understand:
- **WHY** channels exist (neuroscience analogy, semantic differentiation)
- **WHAT** was built (metadata-only implementation, signal classification)
- **HOW** to extend (adding signals, new channels, migration patterns)
- **WHEN** to use each channel (classification criteria, decision trees)

As KLoROS evolves through D-REAM and reflection, this channel architecture provides the communication substrate for increasingly sophisticated cognitive processes. The foundation is laid - now we build upward.

**Document Version:** 1.0
**Last Updated:** 2025-11-26
**Next Review:** After Phase 2 deployment
**Maintained By:** KLoROS Orchestration Team
