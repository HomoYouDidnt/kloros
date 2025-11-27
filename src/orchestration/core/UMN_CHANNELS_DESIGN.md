# UMN Channel Architecture Design
## Differentiated Signal Pathways Inspired by Neurotransmitter Systems

**Version:** 1.0
**Date:** 2025-11-26
**Status:** Design Proposal

---

## Executive Summary

This document proposes a differentiated channel architecture for the KLoROS Unus Mundus Network (UMN) signal bus, inspired by the human nervous system's neurotransmitter pathways. The current flat pub/sub architecture treats all signals identically, but different signal types have fundamentally different delivery requirements. By introducing three specialized channels with distinct delivery semantics, we can optimize for each signal's characteristics while maintaining backward compatibility.

**Core Channels:**
1. **REFLEX** - Fast, ordered, acknowledged (glutamatergic analogy)
2. **AFFECT** - Modulatory, fire-and-forget (dopaminergic/serotonergic analogy)
3. **TROPHIC** - Slow, batched, eventual consistency (hormonal analogy)

---

## Current Architecture Analysis

### Existing Components

**1. Transport Layer (`umn_bus.py`)**
- ZMQ PUB/SUB (preferred) with Unix datagram fallback
- Topic-based filtering via ZMQ multipart frames
- Single flat bus - all signals share same delivery characteristics
- No ordering guarantees, no acknowledgments, no backpressure

**2. Proxy (`umn_proxy_fixed.py`)**
- XSUB/XPUB forwarder for centralized topology
- Uses built-in `zmq.proxy()` for reliability
- No signal inspection or routing logic
- High water marks (1000) prevent silent drops

**3. Signal Definitions (`umn_signals.py`)**
- 17 defined signal types across 7 categories
- Rich Facts structure with ecosystem, intensity, incident_id, trace
- No channel metadata or delivery hints

### Current Signal Categorization

Analyzing existing signals by their natural delivery characteristics:

**Fast, Safety-Critical (REFLEX candidates):**
- None currently defined (future: EMERGENCY_STOP, SAFETY_VIOLATION, CRITICAL_ERROR)
- Could include: High-priority Q_AFFECTIVE_DEMAND signals

**Modulatory, State-Based (AFFECT candidates):**
- `USER_VOICE_INTERACTION` - User engagement state changes
- `Q_AFFECTIVE_DEMAND` - Affective system demands
- `SYSTEM_HEALTH` - Health status changes (degraded/critical)
- `CAPABILITY_GAP` - Capability detection (severity-based)

**Informational, Batchable (TROPHIC candidates):**
- `Q_REFLECT_TRIGGER` - Reflection cycle triggers
- `Q_REFLECTION_COMPLETE` - Reflection results
- `Q_HOUSEKEEPING_TRIGGER` - Maintenance triggers
- `Q_HOUSEKEEPING_COMPLETE` - Maintenance results
- `Q_DREAM_TRIGGER` - Evolution cycle triggers
- `Q_DREAM_COMPLETE` - Evolution results
- `Q_CURIOSITY_INVESTIGATE` - Investigation requests
- `Q_INVESTIGATION_COMPLETE` - Investigation results
- `OBSERVATION` - Raw system observations
- `METRICS_SUMMARY` - Periodic daemon metrics

### Limitations of Flat Architecture

1. **No Delivery Guarantees** - Critical signals can be lost without acknowledgment
2. **No Ordering** - Related signals can arrive out of sequence
3. **No Backpressure** - Slow consumers cause message loss at HWM
4. **No Prioritization** - All signals compete equally for bandwidth
5. **No Batching** - High-frequency informational signals waste resources
6. **No Semantic Differentiation** - Cannot optimize transport per signal type

---

## Proposed Channel Architecture

### Design Principles

1. **Semantic Differentiation** - Channels match signal delivery requirements
2. **Backward Compatibility** - Existing code continues to work during migration
3. **Progressive Enhancement** - Channels add capabilities, don't remove existing features
4. **Operational Simplicity** - Minimize operational complexity, avoid over-engineering
5. **Clear Migration Path** - Gradual migration without flag days

### Channel Definitions

#### 1. REFLEX Channel (Glutamatergic)

**Purpose:** Fast, ordered, acknowledged delivery for safety-critical and high-priority operations.

**Characteristics:**
- **Delivery:** Guaranteed delivery with acknowledgment (REQ/REP or DEALER/ROUTER)
- **Ordering:** Strictly ordered within sender
- **Latency:** Sub-millisecond target, blocking acceptable
- **Backpressure:** Blocks sender if consumer slow (intentional)
- **Durability:** Optional persistence for critical signals
- **Topology:** Direct point-to-point or load-balanced

**Use Cases:**
- Emergency stop signals
- Safety violations
- Critical error notifications
- High-priority affective demands requiring immediate response
- Interrupt signals requiring acknowledgment

**Signal Examples (future):**
- `EMERGENCY_STOP` - Immediate system halt
- `SAFETY_VIOLATION` - Security/safety breach
- `CRITICAL_ERROR` - Unrecoverable error requiring attention
- `Q_AFFECTIVE_DEMAND` (when priority="urgent")

**Implementation Notes:**
- ZMQ pattern: REQ/REP for 1:1, DEALER/ROUTER for N:M with load balancing
- Timeout: 5 seconds default, configurable per signal type
- Retry: Exponential backoff, max 3 retries
- Dead letter queue: Failed signals after retries
- Consumer must explicitly ACK or NACK each message

#### 2. AFFECT Channel (Dopaminergic/Serotonergic)

**Purpose:** Modulatory, fire-and-forget delivery for state changes and mood modulation.

**Characteristics:**
- **Delivery:** Best-effort, fire-and-forget (PUB/SUB)
- **Ordering:** Unordered, duplicates acceptable
- **Latency:** Low (milliseconds), non-blocking
- **Backpressure:** Drop at HWM (intentional - stale state is worse than dropped)
- **Durability:** No persistence required
- **Topology:** Pub/sub broadcast

**Use Cases:**
- Emotional state changes
- User interaction notifications
- System health status updates
- Capability gap notifications (non-critical)
- Mood modulation signals

**Signal Examples:**
- `USER_VOICE_INTERACTION` - User spoke
- `Q_AFFECTIVE_DEMAND` (when priority="low"|"medium"|"high")
- `SYSTEM_HEALTH` (when health_status="healthy"|"degraded")
- `CAPABILITY_GAP` (when severity="low"|"medium")

**Implementation Notes:**
- ZMQ pattern: PUB/SUB (current pattern)
- Topic prefix: `affect.*` or envelope field `channel: "affect"`
- HWM: 100 messages (low to ensure freshness)
- No retries, no acknowledgments
- Consumers should handle duplicates gracefully (idempotency)
- Last-value-cache pattern for state signals (subscribers get latest on connect)

#### 3. TROPHIC Channel (Hormonal)

**Purpose:** Slow, batched, eventual consistency delivery for metrics, reflections, and growth signals.

**Characteristics:**
- **Delivery:** Eventually-consistent, batched (PUSH/PULL or PUB/SUB with batching)
- **Ordering:** Eventual ordering acceptable, timestamp-based reconciliation
- **Latency:** High (seconds to minutes), asynchronous
- **Backpressure:** Queue and batch (PUSH/PULL with HWM)
- **Durability:** Optional persistence for important metrics
- **Topology:** Work distribution or batched pub/sub

**Use Cases:**
- Reflection triggers and completions
- Housekeeping triggers and results
- D-REAM evolution cycles
- Investigation requests and results
- Raw observations and metrics
- Periodic telemetry

**Signal Examples:**
- `Q_REFLECT_TRIGGER` / `Q_REFLECTION_COMPLETE`
- `Q_HOUSEKEEPING_TRIGGER` / `Q_HOUSEKEEPING_COMPLETE`
- `Q_DREAM_TRIGGER` / `Q_DREAM_COMPLETE`
- `Q_CURIOSITY_INVESTIGATE` / `Q_INVESTIGATION_COMPLETE`
- `OBSERVATION` - Raw observations
- `METRICS_SUMMARY` - Periodic metrics

**Implementation Notes:**
- ZMQ pattern: PUSH/PULL for work distribution, or PUB/SUB with consumer-side batching
- Topic prefix: `trophic.*` or envelope field `channel: "trophic"`
- HWM: 10000 messages (large queue for batching)
- Batching window: 5-30 seconds configurable
- Consumer processes batches, not individual messages
- Timestamp-based deduplication in consumer
- Optional disk-backed queue for durability (SQLite, RocksDB)

---

## Implementation Strategy

### Phase 1: Channel Metadata (Backward Compatible)

**Goal:** Add channel metadata to messages without breaking existing consumers.

**Changes:**
1. Extend `UMNMessage` dataclass with optional `channel` field:
   ```python
   @dataclass
   class UMNMessage:
       signal: str
       ecosystem: str
       intensity: float = 1.0
       facts: Dict[str, Any] | None = None
       incident_id: str | None = None
       trace: str | None = None
       ts: float = time.time()
       channel: str = "legacy"  # NEW: "legacy" | "reflex" | "affect" | "trophic"
   ```

2. Update `UMNPub.emit()` to accept optional `channel` parameter:
   ```python
   def emit(self, signal: str, *, ecosystem: str, channel: str = "legacy", ...):
       msg = UMNMessage(..., channel=channel)
       # Topic includes channel for future routing: "{channel}.{signal}"
       topic = f"{channel}.{signal}"
       self._impl.emit(topic, msg.to_bytes())
   ```

3. Update `UMNSub.__init__()` to accept channel-aware topics:
   ```python
   # Existing: UMNSub(topic="Q_REFLECT_TRIGGER", ...)
   # New: UMNSub(topic="trophic.Q_REFLECT_TRIGGER", ...)
   # Backward compatible: UMNSub(topic="Q_REFLECT_TRIGGER", ...) subscribes to "legacy.Q_REFLECT_TRIGGER"
   ```

4. Proxy remains unchanged (still uses `zmq.proxy()`) - channel differentiation is in topic prefix.

**Migration:**
- All existing signals default to `channel="legacy"` (pub/sub semantics)
- Consumers can subscribe to `"legacy.*"` wildcard or specific `"legacy.SIGNAL_NAME"`
- No behavior changes yet - purely additive metadata

**Validation:**
- Run existing tests - all should pass
- Check that existing daemons continue to receive signals
- Verify topic filtering still works

### Phase 2: Dedicated Channel Transports (Optional Enhancement)

**Goal:** Introduce separate ZMQ sockets for each channel with specialized patterns.

**Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                    UMN Channel Proxy                         │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ REFLEX       │  │ AFFECT       │  │ TROPHIC      │     │
│  │ ROUTER/DEALER│  │ XPUB/XSUB    │  │ PULL/PUSH    │     │
│  │ :5560        │  │ :5561        │  │ :5562        │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                              │
│  Legacy XPUB/XSUB (5558/5559) - maintained for compatibility│
└─────────────────────────────────────────────────────────────┘
```

**New Proxy Implementation (`umn_proxy_channels.py`):**

```python
#!/usr/bin/env python3
import zmq
import json
import time
from threading import Thread

LEGACY_XSUB = "tcp://127.0.0.1:5558"
LEGACY_XPUB = "tcp://127.0.0.1:5559"

REFLEX_ROUTER = "tcp://127.0.0.1:5560"  # ROUTER for acknowledged delivery
AFFECT_XSUB = "tcp://127.0.0.1:5561"    # XSUB for pub/sub
AFFECT_XPUB = "tcp://127.0.0.1:5562"    # XPUB for pub/sub
TROPHIC_PULL = "tcp://127.0.0.1:5563"   # PULL for work distribution
TROPHIC_PUSH = "tcp://127.0.0.1:5564"   # PUSH for workers

class ChannelProxy:
    def __init__(self):
        self.ctx = zmq.Context.instance()

        # Legacy pub/sub for backward compatibility
        self.legacy_xsub = self.ctx.socket(zmq.XSUB)
        self.legacy_xpub = self.ctx.socket(zmq.XPUB)
        self.legacy_xsub.bind(LEGACY_XSUB)
        self.legacy_xpub.bind(LEGACY_XPUB)

        # REFLEX: ROUTER for acknowledged delivery
        self.reflex_router = self.ctx.socket(zmq.ROUTER)
        self.reflex_router.bind(REFLEX_ROUTER)
        self.reflex_router.setsockopt(zmq.ROUTER_MANDATORY, 1)  # Error if route fails

        # AFFECT: PUB/SUB for fire-and-forget
        self.affect_xsub = self.ctx.socket(zmq.XSUB)
        self.affect_xpub = self.ctx.socket(zmq.XPUB)
        self.affect_xsub.bind(AFFECT_XSUB)
        self.affect_xpub.bind(AFFECT_XPUB)
        self.affect_xpub.setsockopt(zmq.SNDHWM, 100)  # Low HWM for freshness
        self.affect_xsub.setsockopt(zmq.RCVHWM, 100)

        # TROPHIC: PULL/PUSH for work distribution
        self.trophic_pull = self.ctx.socket(zmq.PULL)
        self.trophic_push = self.ctx.socket(zmq.PUSH)
        self.trophic_pull.bind(TROPHIC_PULL)
        self.trophic_push.bind(TROPHIC_PUSH)
        self.trophic_push.setsockopt(zmq.SNDHWM, 10000)  # Large queue
        self.trophic_pull.setsockopt(zmq.RCVHWM, 10000)

    def run(self):
        # Start forwarding threads for each channel
        Thread(target=self._proxy_legacy, daemon=True).start()
        Thread(target=self._proxy_affect, daemon=True).start()
        Thread(target=self._proxy_trophic, daemon=True).start()
        Thread(target=self._handle_reflex, daemon=True).start()

        # Main thread waits
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("[umn-proxy-channels] Shutting down")

    def _proxy_legacy(self):
        """Forward legacy pub/sub traffic."""
        zmq.proxy(self.legacy_xsub, self.legacy_xpub)

    def _proxy_affect(self):
        """Forward affect pub/sub traffic."""
        zmq.proxy(self.affect_xsub, self.affect_xpub)

    def _proxy_trophic(self):
        """Forward trophic work distribution traffic."""
        zmq.proxy(self.trophic_pull, self.trophic_push)

    def _handle_reflex(self):
        """Handle REFLEX ROUTER with acknowledgments."""
        poller = zmq.Poller()
        poller.register(self.reflex_router, zmq.POLLIN)

        while True:
            try:
                socks = dict(poller.poll(timeout=1000))
                if self.reflex_router in socks:
                    # ROUTER receives: [sender_id, empty, message]
                    frames = self.reflex_router.recv_multipart()
                    sender_id = frames[0]
                    message = frames[2] if len(frames) > 2 else b""

                    # Parse message to determine routing
                    try:
                        msg_data = json.loads(message.decode('utf-8'))
                        signal = msg_data.get("signal")

                        # Route to appropriate consumer(s)
                        # For now, echo ACK back to sender
                        ack = json.dumps({"ack": True, "signal": signal, "ts": time.time()})
                        self.reflex_router.send_multipart([sender_id, b"", ack.encode('utf-8')])

                        # Forward to consumers (future: maintain consumer registry)
                        # For MVP, REFLEX is acknowledged but still broadcast

                    except Exception as e:
                        # NACK on parse error
                        nack = json.dumps({"ack": False, "error": str(e)})
                        self.reflex_router.send_multipart([sender_id, b"", nack.encode('utf-8')])
            except Exception as e:
                print(f"[reflex-handler] Error: {e}")
                time.sleep(0.1)

if __name__ == "__main__":
    proxy = ChannelProxy()
    proxy.run()
```

**Updated `umn_bus.py` with Channel Support:**

```python
# Add channel-aware implementations

class _ZmqReflexPub:
    """REFLEX publisher using DEALER for acknowledged delivery."""
    def __init__(self, endpoint: str = "tcp://127.0.0.1:5560"):
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.DEALER)
        self._sock.setsockopt(zmq.IDENTITY, f"reflex-pub-{os.getpid()}".encode('utf-8'))
        self._sock.connect(endpoint)

    def emit(self, topic: str, payload: bytes, timeout_ms: int = 5000):
        """Emit with acknowledgment. Raises TimeoutError if no ACK."""
        self._sock.send_multipart([b"", payload])

        poller = zmq.Poller()
        poller.register(self._sock, zmq.POLLIN)
        socks = dict(poller.poll(timeout_ms))

        if self._sock in socks:
            ack_frames = self._sock.recv_multipart()
            ack_data = json.loads(ack_frames[1].decode('utf-8'))
            if not ack_data.get("ack"):
                raise Exception(f"NACK received: {ack_data.get('error')}")
        else:
            raise TimeoutError(f"No ACK received within {timeout_ms}ms")

class _ZmqAffectPub:
    """AFFECT publisher using PUB for fire-and-forget."""
    def __init__(self, endpoint: str = "tcp://127.0.0.1:5561"):
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PUB)
        self._sock.connect(endpoint)
        self._sock.setsockopt(zmq.SNDHWM, 100)

    def emit(self, topic: str, payload: bytes):
        self._sock.send_multipart([topic.encode('utf-8'), payload])

class _ZmqTrophicPub:
    """TROPHIC publisher using PUSH for work distribution."""
    def __init__(self, endpoint: str = "tcp://127.0.0.1:5563"):
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PUSH)
        self._sock.connect(endpoint)
        self._sock.setsockopt(zmq.SNDHWM, 10000)

    def emit(self, topic: str, payload: bytes):
        # PUSH doesn't use topics, payload is self-describing
        self._sock.send(payload)

# Update UMNPub to dispatch to appropriate channel implementation
class UMNPub:
    def __init__(self, ipc_path: str = DEFAULT_UMN_SOCKET_PATH, enable_channels: bool = False):
        self._enable_channels = enable_channels

        if enable_channels:
            self._reflex = _ZmqReflexPub() if _ZMQ_AVAILABLE else None
            self._affect = _ZmqAffectPub() if _ZMQ_AVAILABLE else None
            self._trophic = _ZmqTrophicPub() if _ZMQ_AVAILABLE else None

        # Legacy always available for backward compatibility
        self._legacy = _ZmqPub(ipc_path) if _ZMQ_AVAILABLE else _UnixPub(ipc_path)

    def emit(self, signal: str, *, ecosystem: str, channel: str = "legacy",
             intensity: float = 1.0, facts: Optional[Dict[str, Any]] = None,
             incident_id: Optional[str] = None, trace: Optional[str] = None,
             ack_timeout_ms: int = 5000):
        msg = UMNMessage(signal=signal, ecosystem=ecosystem, intensity=intensity,
                        facts=facts or {}, incident_id=incident_id, trace=trace, channel=channel)
        payload = msg.to_bytes()

        if self._enable_channels and channel != "legacy":
            if channel == "reflex" and self._reflex:
                self._reflex.emit(signal, payload, timeout_ms=ack_timeout_ms)
            elif channel == "affect" and self._affect:
                self._affect.emit(signal, payload)
            elif channel == "trophic" and self._trophic:
                self._trophic.emit(signal, payload)
            else:
                # Fallback to legacy
                self._legacy.emit(signal, payload)
        else:
            # Legacy path
            self._legacy.emit(signal, payload)
```

**Migration:**
- Deploy new proxy alongside legacy proxy (different ports)
- Update emitters gradually to specify `channel="affect"` etc
- Consumers migrate to channel-specific endpoints
- Once all migrated, deprecate legacy proxy

### Phase 3: Signal Reclassification

**Goal:** Migrate existing signals to appropriate channels based on semantics.

**Reclassification Table:**

| Signal | Current | Proposed Channel | Rationale |
|--------|---------|------------------|-----------|
| `USER_VOICE_INTERACTION` | legacy | **affect** | State change, fire-and-forget, duplicates OK |
| `Q_AFFECTIVE_DEMAND` | legacy | **affect** (low/med/high) or **reflex** (urgent) | Priority-based routing |
| `SYSTEM_HEALTH` | legacy | **affect** (healthy/degraded) or **reflex** (critical) | Severity-based routing |
| `CAPABILITY_GAP` | legacy | **affect** (low/med) or **trophic** (batched analysis) | Severity-based routing |
| `Q_REFLECT_TRIGGER` | legacy | **trophic** | Batchable, delayed processing OK |
| `Q_REFLECTION_COMPLETE` | legacy | **trophic** | Informational, eventual consistency OK |
| `Q_HOUSEKEEPING_TRIGGER` | legacy | **trophic** | Maintenance, delayed processing OK |
| `Q_HOUSEKEEPING_COMPLETE` | legacy | **trophic** | Informational, eventual consistency OK |
| `Q_DREAM_TRIGGER` | legacy | **trophic** | Evolution, delayed processing OK |
| `Q_DREAM_COMPLETE` | legacy | **trophic** | Informational, eventual consistency OK |
| `Q_CURIOSITY_INVESTIGATE` | legacy | **trophic** | Investigation queue, batch processing |
| `Q_INVESTIGATION_COMPLETE` | legacy | **trophic** | Results, eventual consistency OK |
| `OBSERVATION` | legacy | **trophic** | High-frequency, batchable |
| `METRICS_SUMMARY` | legacy | **trophic** | Periodic telemetry, batchable |

**Future Signals (when needed):**

| Signal | Channel | Rationale |
|--------|---------|-----------|
| `EMERGENCY_STOP` | **reflex** | Safety-critical, requires ACK |
| `SAFETY_VIOLATION` | **reflex** | Security breach, immediate attention |
| `CRITICAL_ERROR` | **reflex** | Unrecoverable error, requires ACK |
| `AFFECTIVE_STATE_CHANGE` | **affect** | Emotional state, fire-and-forget |
| `MOOD_MODULATION` | **affect** | Mood adjustment, latest wins |

**Migration Code Example:**

```python
# Before (legacy):
umn_pub.emit("Q_REFLECT_TRIGGER", ecosystem="orchestration", intensity=1.0,
             facts={"trigger_reason": "idle_period", "idle_seconds": 600})

# After (trophic channel):
umn_pub.emit("Q_REFLECT_TRIGGER", ecosystem="orchestration", channel="trophic",
             intensity=1.0, facts={"trigger_reason": "idle_period", "idle_seconds": 600})
```

**Backward Compatibility:**
- Dual-emit during transition: emit to both legacy and new channel
- Consumers subscribe to both topics during migration
- Remove legacy emits after consumers migrated
- Remove legacy subscriptions last

**Validation:**
- Verify no signal loss during migration
- Monitor channel-specific metrics (latency, throughput, drops)
- Test failure scenarios (slow consumer, network partition)

---

## Operational Considerations

### Monitoring and Observability

**Per-Channel Metrics:**

```python
@dataclass
class ChannelMetrics:
    channel_name: str
    messages_sent: int
    messages_received: int
    messages_dropped: int  # At HWM
    messages_failed: int   # REFLEX NACK or timeout
    avg_latency_ms: float
    p99_latency_ms: float
    current_queue_depth: int
    hwm_hits: int  # Number of times HWM reached
```

**Prometheus Metrics Export:**

```python
# umn_metrics.py
from prometheus_client import Counter, Histogram, Gauge

umn_messages_sent = Counter('umn_messages_sent_total', 'Messages sent', ['channel', 'signal'])
umn_messages_received = Counter('umn_messages_received_total', 'Messages received', ['channel', 'signal'])
umn_messages_dropped = Counter('umn_messages_dropped_total', 'Messages dropped at HWM', ['channel'])
umn_message_latency = Histogram('umn_message_latency_seconds', 'Message latency', ['channel'])
umn_queue_depth = Gauge('umn_queue_depth', 'Current queue depth', ['channel'])
umn_reflex_acks = Counter('umn_reflex_acks_total', 'REFLEX acknowledgments', ['status'])  # ack/nack/timeout
```

**Logging:**

```python
# Structured logging for debugging
logger.info("umn.emit", extra={
    "channel": "affect",
    "signal": "USER_VOICE_INTERACTION",
    "ecosystem": "voice",
    "intensity": 0.95,
    "incident_id": "uuid-1234",
})

logger.warning("umn.hwm_drop", extra={
    "channel": "affect",
    "queue_depth": 100,
    "dropped_signal": "SYSTEM_HEALTH",
})

logger.error("umn.reflex_timeout", extra={
    "channel": "reflex",
    "signal": "EMERGENCY_STOP",
    "timeout_ms": 5000,
    "retry_count": 3,
})
```

### Performance Tuning

**REFLEX Channel:**
- Timeout: 5s default, tune based on consumer SLA
- Retry: Exponential backoff (100ms, 200ms, 400ms), max 3 retries
- Consumer threads: 1-4 per consumer for parallel processing
- Dead letter queue: Persist failed signals to SQLite after retries

**AFFECT Channel:**
- HWM: 100 (low to ensure freshness), tune based on burst patterns
- Subscription: Use ZMQ SUB with `TCP_KEEPALIVE` for connection health
- Last-value-cache: Optional for state signals (ZMQ `XPUB_LVC`)

**TROPHIC Channel:**
- HWM: 10000 (large for batching), tune based on processing rate
- Batch size: 100-1000 messages per batch, tune based on latency tolerance
- Batch timeout: 5-30s, tune based on freshness requirements
- Persistence: Optional SQLite/RocksDB for durability

### Failure Scenarios and Recovery

**1. Slow Consumer (TROPHIC)**
- **Symptom:** Queue depth grows, HWM reached, messages queued
- **Behavior:** PUSH blocks sender until consumer catches up or HWM reached, then drops
- **Mitigation:** Increase HWM, add consumer workers, enable disk-backed queue

**2. Consumer Crash (REFLEX)**
- **Symptom:** No ACK received, timeout after 5s
- **Behavior:** Publisher retries 3x with exponential backoff, then writes to DLQ
- **Recovery:** Monitor DLQ, replay failed signals manually or via automated recovery

**3. Consumer Crash (AFFECT)**
- **Symptom:** Messages sent but no processing
- **Behavior:** Messages dropped at HWM, no retries (intentional)
- **Recovery:** Consumer reconnects, subscribes, receives new messages (stale state discarded)

**4. Proxy Crash**
- **Symptom:** All channels down, publishers/consumers disconnected
- **Behavior:** Publishers fail immediately (connection error), consumers reconnect
- **Recovery:** Restart proxy, publishers/consumers auto-reconnect (ZMQ handles reconnection)
- **Data Loss:** In-flight AFFECT/TROPHIC messages lost, REFLEX messages in DLQ

**5. Network Partition**
- **Symptom:** TCP timeout, connection loss
- **Behavior:** ZMQ auto-reconnects, REFLEX times out and retries, AFFECT/TROPHIC queue or drop
- **Recovery:** Network heals, ZMQ reconnects, queued messages flow

### Configuration

**Environment Variables:**

```bash
# Legacy (backward compatible)
export KLR_UMN_XSUB="tcp://127.0.0.1:5558"
export KLR_UMN_XPUB="tcp://127.0.0.1:5559"

# New channel endpoints (opt-in)
export KLR_UMN_ENABLE_CHANNELS="true"
export KLR_UMN_REFLEX_ENDPOINT="tcp://127.0.0.1:5560"
export KLR_UMN_AFFECT_XSUB="tcp://127.0.0.1:5561"
export KLR_UMN_AFFECT_XPUB="tcp://127.0.0.1:5562"
export KLR_UMN_TROPHIC_PULL="tcp://127.0.0.1:5563"
export KLR_UMN_TROPHIC_PUSH="tcp://127.0.0.1:5564"

# Tuning
export KLR_UMN_REFLEX_TIMEOUT_MS="5000"
export KLR_UMN_REFLEX_RETRIES="3"
export KLR_UMN_AFFECT_HWM="100"
export KLR_UMN_TROPHIC_HWM="10000"
export KLR_UMN_TROPHIC_BATCH_SIZE="500"
export KLR_UMN_TROPHIC_BATCH_TIMEOUT_MS="10000"
```

**Runtime Configuration File (`/home/kloros/.kloros/umn_config.json`):**

```json
{
  "channels": {
    "enabled": true,
    "reflex": {
      "endpoint": "tcp://127.0.0.1:5560",
      "timeout_ms": 5000,
      "retries": 3,
      "dlq_path": "/home/kloros/.kloros/umn_reflex_dlq.jsonl"
    },
    "affect": {
      "xsub_endpoint": "tcp://127.0.0.1:5561",
      "xpub_endpoint": "tcp://127.0.0.1:5562",
      "hwm": 100,
      "lvc_enabled": true
    },
    "trophic": {
      "pull_endpoint": "tcp://127.0.0.1:5563",
      "push_endpoint": "tcp://127.0.0.1:5564",
      "hwm": 10000,
      "batch_size": 500,
      "batch_timeout_ms": 10000,
      "persistence_enabled": false,
      "persistence_path": "/home/kloros/.kloros/umn_trophic_queue.db"
    }
  },
  "legacy": {
    "xsub_endpoint": "tcp://127.0.0.1:5558",
    "xpub_endpoint": "tcp://127.0.0.1:5559",
    "hwm": 1000
  }
}
```

---

## Migration Roadmap

### Phase 1: Foundation (Week 1-2)

**Goals:**
- Add channel metadata without breaking existing code
- Validate backward compatibility

**Tasks:**
1. Extend `UMNMessage` with `channel` field (default "legacy")
2. Update `UMNPub.emit()` to accept `channel` parameter
3. Update signal definitions in `umn_signals.py` with channel hints (comments)
4. Run full test suite - ensure 100% pass rate
5. Deploy to development environment
6. Monitor for regressions

**Success Criteria:**
- All existing tests pass
- No signal loss detected
- No consumer errors

### Phase 2: Infrastructure (Week 3-4)

**Goals:**
- Deploy channel-aware proxy
- Implement channel-specific transports

**Tasks:**
1. Implement `umn_proxy_channels.py` with REFLEX/AFFECT/TROPHIC sockets
2. Implement `_ZmqReflexPub`, `_ZmqAffectPub`, `_ZmqTrophicPub` in `umn_bus.py`
3. Implement channel-specific subscribers
4. Add configuration loading from environment and JSON file
5. Add Prometheus metrics export
6. Deploy proxy to staging with legacy proxy in parallel
7. Validate dual-proxy operation

**Success Criteria:**
- New proxy starts cleanly
- Legacy proxy continues to work
- Metrics dashboard shows channel activity
- No message loss between proxies

### Phase 3: Signal Migration (Week 5-8)

**Goals:**
- Migrate signals to appropriate channels
- Validate channel-specific behavior

**Tasks:**
1. **Week 5:** Migrate TROPHIC signals (lowest risk)
   - `Q_REFLECT_TRIGGER`, `Q_REFLECTION_COMPLETE`
   - `OBSERVATION`, `METRICS_SUMMARY`
   - Update emitters to specify `channel="trophic"`
   - Update consumers to subscribe to `trophic.*` topics
   - Deploy and monitor
2. **Week 6:** Migrate AFFECT signals
   - `USER_VOICE_INTERACTION`
   - `Q_AFFECTIVE_DEMAND` (non-urgent)
   - `SYSTEM_HEALTH` (non-critical)
   - Deploy and monitor
3. **Week 7:** Add new REFLEX signals (as needed)
   - Define `EMERGENCY_STOP`, `CRITICAL_ERROR`
   - Implement emitters and consumers
   - Test acknowledgment and timeout behavior
4. **Week 8:** Validation and tuning
   - Load testing per channel
   - Failure scenario testing
   - Performance tuning (HWM, batch sizes, timeouts)

**Success Criteria:**
- All signals routed to correct channels
- Channel-specific behavior validated (ACK, batching, fire-and-forget)
- Performance meets SLA (latency, throughput)
- Failure recovery works as designed

### Phase 4: Legacy Deprecation (Week 9-12)

**Goals:**
- Remove legacy proxy
- Clean up dual-emit code

**Tasks:**
1. **Week 9-10:** Remove legacy emits from all publishers
   - Ensure all consumers on new channels
   - Remove `channel="legacy"` fallback code
2. **Week 11:** Deprecate legacy proxy
   - Stop legacy proxy in production
   - Monitor for connection errors (indicates unmigrated consumers)
   - Fix any stragglers
3. **Week 12:** Cleanup
   - Remove legacy proxy code
   - Remove `channel="legacy"` support from `umn_bus.py`
   - Update documentation
   - Final performance validation

**Success Criteria:**
- Legacy proxy removed from production
- No legacy emits or subscriptions remain
- Documentation updated
- Team trained on new architecture

---

## Testing Strategy

### Unit Tests

**Channel Metadata:**
```python
def test_umn_message_channel_default():
    msg = UMNMessage(signal="TEST", ecosystem="test")
    assert msg.channel == "legacy"

def test_umn_message_channel_explicit():
    msg = UMNMessage(signal="TEST", ecosystem="test", channel="affect")
    assert msg.channel == "affect"

def test_umn_pub_emit_with_channel():
    pub = UMNPub(enable_channels=True)
    pub.emit("TEST", ecosystem="test", channel="trophic")
    # Assert trophic transport used
```

**REFLEX Acknowledgment:**
```python
def test_reflex_ack_success():
    pub = _ZmqReflexPub()
    # Mock router returns ACK
    pub.emit("TEST", b"payload", timeout_ms=1000)
    # Assert no exception

def test_reflex_ack_timeout():
    pub = _ZmqReflexPub()
    # Mock router no response
    with pytest.raises(TimeoutError):
        pub.emit("TEST", b"payload", timeout_ms=100)

def test_reflex_ack_nack():
    pub = _ZmqReflexPub()
    # Mock router returns NACK
    with pytest.raises(Exception, match="NACK received"):
        pub.emit("TEST", b"payload", timeout_ms=1000)
```

**TROPHIC Batching:**
```python
def test_trophic_batching():
    consumer = TrophicBatchConsumer(batch_size=10, batch_timeout_ms=1000)
    # Emit 10 messages rapidly
    for i in range(10):
        pub.emit(f"TEST_{i}", ecosystem="test", channel="trophic")

    # Wait for batch processing
    time.sleep(0.2)

    # Assert single batch processed with 10 messages
    assert consumer.batches_processed == 1
    assert len(consumer.last_batch) == 10
```

### Integration Tests

**Multi-Channel Coexistence:**
```python
def test_all_channels_coexist():
    # Start proxy with all channels
    proxy = ChannelProxy()
    proxy_thread = Thread(target=proxy.run, daemon=True)
    proxy_thread.start()

    # Publishers for each channel
    reflex_pub = UMNPub(enable_channels=True)
    affect_pub = UMNPub(enable_channels=True)
    trophic_pub = UMNPub(enable_channels=True)

    # Consumers for each channel
    reflex_received = []
    affect_received = []
    trophic_received = []

    reflex_sub = ReflexConsumer(on_message=lambda msg: reflex_received.append(msg))
    affect_sub = UMNSub("affect.TEST", on_json=lambda msg: affect_received.append(msg))
    trophic_sub = TrophicConsumer(on_batch=lambda batch: trophic_received.extend(batch))

    # Emit signals
    reflex_pub.emit("EMERGENCY_STOP", ecosystem="safety", channel="reflex")
    affect_pub.emit("USER_VOICE_INTERACTION", ecosystem="voice", channel="affect")
    trophic_pub.emit("METRICS_SUMMARY", ecosystem="orchestration", channel="trophic")

    # Wait for delivery
    time.sleep(0.5)

    # Assert all received
    assert len(reflex_received) == 1
    assert len(affect_received) == 1
    assert len(trophic_received) == 1
```

**Legacy Compatibility:**
```python
def test_legacy_consumers_still_work():
    # Start both legacy and new proxy
    legacy_proxy = LegacyProxy()
    legacy_thread = Thread(target=legacy_proxy.run, daemon=True)
    legacy_thread.start()

    # Old-style publisher and consumer
    pub = UMNPub()  # No enable_channels
    received = []
    sub = UMNSub("TEST", on_json=lambda msg: received.append(msg))

    # Emit without channel
    pub.emit("TEST", ecosystem="test")

    # Wait and verify
    time.sleep(0.2)
    assert len(received) == 1
```

### Load Tests

**REFLEX Throughput with ACK:**
```python
def test_reflex_throughput():
    pub = UMNPub(enable_channels=True)
    consumer = ReflexConsumer()

    start = time.time()
    count = 1000

    for i in range(count):
        pub.emit(f"TEST_{i}", ecosystem="test", channel="reflex")

    elapsed = time.time() - start
    throughput = count / elapsed

    # Assert at least 100 msgs/sec with acknowledgment
    assert throughput >= 100
```

**AFFECT Drop at HWM:**
```python
def test_affect_drops_at_hwm():
    pub = UMNPub(enable_channels=True)

    # Slow consumer (doesn't drain queue)
    received = []
    sub = UMNSub("affect.TEST", on_json=lambda msg: (time.sleep(0.1), received.append(msg)))

    # Flood with messages (150 > HWM of 100)
    for i in range(150):
        pub.emit(f"TEST_{i}", ecosystem="test", channel="affect")

    time.sleep(2)

    # Assert some dropped (less than 150 received)
    assert len(received) < 150
    # But at least HWM received
    assert len(received) >= 100
```

**TROPHIC Batch Performance:**
```python
def test_trophic_batch_latency():
    pub = UMNPub(enable_channels=True)
    batches = []
    consumer = TrophicBatchConsumer(
        batch_size=100,
        batch_timeout_ms=1000,
        on_batch=lambda batch: batches.append((time.time(), batch))
    )

    # Emit 500 messages rapidly
    start = time.time()
    for i in range(500):
        pub.emit(f"TEST_{i}", ecosystem="test", channel="trophic")
    emit_elapsed = time.time() - start

    # Wait for all batches processed
    time.sleep(2)

    # Assert 5 batches (500 / 100)
    assert len(batches) == 5

    # Assert batching reduces per-message latency
    avg_batch_latency = sum(b[0] - start for b in batches) / len(batches)
    assert avg_batch_latency < emit_elapsed  # Batching faster than individual
```

---

## Future Enhancements

### 1. Persistent TROPHIC Queue

**Motivation:** Survive proxy restarts without losing queued messages.

**Implementation:**
- SQLite or RocksDB backing for TROPHIC PUSH/PULL
- Write-ahead log for durability
- Replay from disk on proxy restart

**Trade-offs:**
- Adds disk I/O latency (10-100ms per batch)
- Increases complexity (disk management, corruption handling)
- Benefits workloads with long-running processing (investigations, reflections)

### 2. Priority Lanes within Channels

**Motivation:** Differentiate within AFFECT (high vs low priority affective signals).

**Implementation:**
- Multiple AFFECT pub/sub pairs: `affect-high`, `affect-low`
- Consumers subscribe to both, prioritize high
- Publisher selects lane based on intensity or facts

**Example:**
```python
# High-priority affective demand
pub.emit("Q_AFFECTIVE_DEMAND", ecosystem="affect", channel="affect-high", intensity=0.9)

# Low-priority user interaction
pub.emit("USER_VOICE_INTERACTION", ecosystem="voice", channel="affect-low", intensity=0.5)
```

### 3. Dynamic Channel Selection

**Motivation:** Route signals to different channels based on runtime conditions.

**Implementation:**
- Channel router in proxy inspects message facts and routes accordingly
- Example: `SYSTEM_HEALTH` → AFFECT if healthy/degraded, REFLEX if critical

**Code Sketch:**
```python
def route_signal(msg: UMNMessage) -> str:
    """Dynamically select channel based on message content."""
    if msg.signal == "SYSTEM_HEALTH":
        status = msg.facts.get("health_status")
        if status == "critical":
            return "reflex"
        else:
            return "affect"
    elif msg.signal == "Q_AFFECTIVE_DEMAND":
        priority = msg.facts.get("priority")
        if priority == "urgent":
            return "reflex"
        else:
            return "affect"
    else:
        # Default channel based on signal type
        return SIGNAL_CHANNEL_MAP.get(msg.signal, "legacy")
```

### 4. Cross-Channel Orchestration

**Motivation:** Complex workflows spanning multiple channels (REFLEX trigger → TROPHIC investigation → AFFECT notification).

**Implementation:**
- Saga pattern with channel-aware orchestrator
- Distributed transaction coordinator
- Workflow engine (Temporal, Cadence) with UMN integration

### 5. Remote UMN Federation

**Motivation:** Multi-node KLoROS cluster with shared UMN.

**Implementation:**
- ZMQ `ROUTER`/`DEALER` over TCP for cross-node communication
- Proxy federation with gossip protocol for topology discovery
- Consistent hashing for signal routing to node affinity

**Architecture:**
```
┌────────────┐      ┌────────────┐      ┌────────────┐
│  Node A    │      │  Node B    │      │  Node C    │
│  UMN Proxy │◄────►│  UMN Proxy │◄────►│  UMN Proxy │
└────────────┘      └────────────┘      └────────────┘
     │                   │                   │
     │ AFFECT: broadcast │                   │
     └──────────────────►└──────────────────►│
     │ TROPHIC: affinity │                   │
     │ (mod hash)        │                   │
```

---

## Alternatives Considered

### Alternative 1: Single Pub/Sub with QoS Fields

**Description:** Keep single pub/sub, add QoS fields to message envelope (priority, ack_required, batching_hint).

**Pros:**
- Minimal code changes
- Single proxy to operate
- Simpler topology

**Cons:**
- Cannot enforce different ZMQ patterns per QoS (all pub/sub)
- No true acknowledgment (pub/sub is fire-and-forget)
- No true batching (each message is independent)
- No separation of concerns (fast and slow signals compete)

**Verdict:** Rejected. Insufficient differentiation in delivery semantics.

### Alternative 2: Separate Processes per Channel

**Description:** Three independent UMN buses (reflex-umn, affect-umn, trophic-umn) with separate proxies.

**Pros:**
- Complete isolation (failure in one doesn't affect others)
- Independent scaling and tuning
- Clear operational boundaries

**Cons:**
- 3x operational overhead (3 proxies, 3 configs, 3 monitors)
- Publishers must manage multiple connections
- No unified view of signal flow
- Harder to implement cross-channel orchestration

**Verdict:** Rejected. Too much operational complexity for marginal isolation benefit.

### Alternative 3: Hybrid ZMQ + NATS

**Description:** Use NATS for AFFECT (pub/sub with QoS), ZMQ for REFLEX/TROPHIC.

**Pros:**
- NATS built-in persistence, clustering, monitoring
- Mature at-least-once delivery
- Rich client ecosystem

**Cons:**
- Additional dependency (NATS server)
- Mixed transport complicates debugging
- NATS adds latency vs raw ZMQ
- Overkill for single-node KLoROS

**Verdict:** Rejected for now. Revisit if multi-node federation needed.

### Alternative 4: Kafka for All Channels

**Description:** Replace ZMQ with Kafka for all channels.

**Pros:**
- Durable, replicated, scalable
- Rich ecosystem (connectors, monitoring)
- Built-in batching and partitioning

**Cons:**
- Massive operational overhead (Zookeeper/KRaft, brokers, tuning)
- Overkill for single-node, low-traffic KLoROS
- Higher latency (10-100ms vs sub-ms for ZMQ)
- JVM dependency

**Verdict:** Rejected. Too heavy for current scale. Revisit if multi-node or high-throughput required.

---

## Conclusion

The proposed UMN channel architecture introduces semantic differentiation of signal pathways inspired by the human nervous system's neurotransmitter systems. By separating REFLEX (fast, acknowledged), AFFECT (modulatory, fire-and-forget), and TROPHIC (slow, batched) channels, we can optimize delivery semantics for each signal's characteristics while maintaining backward compatibility during migration.

**Key Benefits:**
1. **Semantic Clarity** - Signal delivery matches intent (ACK for critical, fire-and-forget for state, batching for telemetry)
2. **Performance** - Fast signals don't wait for slow signals
3. **Resilience** - Critical signals have retries and DLQ, transient signals drop gracefully
4. **Scalability** - Batching reduces overhead for high-frequency signals
5. **Backward Compatibility** - Gradual migration without breaking existing code

**Recommended Path:**
1. Start with Phase 1 (channel metadata) - validate backward compatibility
2. Proceed to Phase 2 (infrastructure) - deploy channel-aware proxy alongside legacy
3. Migrate signals incrementally in Phase 3 - start with low-risk TROPHIC signals
4. Deprecate legacy in Phase 4 after full validation

**Next Steps:**
1. Review this design with KLoROS maintainers
2. Prototype Phase 1 (channel metadata) in development environment
3. Benchmark channel-specific transports (DEALER/ROUTER, PUSH/PULL)
4. Implement Prometheus metrics dashboard
5. Begin signal reclassification based on table above

This architecture positions KLoROS UMN for future growth (multi-node federation, cross-channel orchestration) while immediately improving delivery semantics for existing signals.
