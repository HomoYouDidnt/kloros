# Telemetry Infrastructure Decision Document
**Generated**: 2025-11-18 23:05 EST
**Investigation**: Orphaned telemetry signals - implement aggregator or cleanup?

---

## Executive Summary

**Orphaned Telemetry Signals**: 6 channels
- **HEARTBEAT** (ACTIVE - every ChemSub instance emits)
- **metric, timer_start, timer_stop** (DORMANT - D-REAM only)
- **logger_init, logger_close** (DORMANT - D-REAM only)

**Recommendation**: **SPLIT DECISION**
1. **HEARTBEAT**: Implement lightweight health-monitor daemon (valuable for production monitoring)
2. **D-REAM telemetry**: Leave as-is until D-REAM refactoring complete (dormant, no action needed)

---

## Signal Analysis

### 1. HEARTBEAT - ACTIVE & VALUABLE

**Producer**: `src/kloros/orchestration/chem_bus_v2.py:262-279`
- Emitted by: ChemSub class (every subscriber automatically emits)
- Frequency: Every 10 seconds
- Payload:
  ```python
  {
      "zooid": self.zooid_name,
      "niche": self.niche,
      "uptime_s": time.time(),
      "processed_count": len(self._processed_incidents)
  }
  ```

**Current Status**: **ACTIVELY EMITTING**
- Every running ChemSub subscriber emits heartbeats
- Confirmed active on ChemBus (hundreds of messages in consolidated logs)
- Includes valuable liveness data

**Value Proposition**:
- **Component health tracking**: Know when daemons are alive
- **Uptime monitoring**: Track component stability
- **Message throughput**: Track processed_count per zooid
- **Failure detection**: Detect when services stop emitting heartbeats

**Use Cases**:
1. **Health Dashboard**: Display which components are alive
2. **Alert on Silence**: Trigger alerts when heartbeats stop
3. **Uptime Metrics**: Track component reliability over time
4. **Performance Metrics**: Monitor message processing rates

**Implementation Cost**: LOW
- Simple consumer daemon (50-100 LOC)
- Store last heartbeat timestamp per zooid
- Emit CAPABILITY_GAP when heartbeat missing > threshold

---

### 2. D-REAM Telemetry (5 signals) - DORMANT

**Producer**: `src/dream/telemetry/logger.py`
- **EventLogger** class (lines 19-108):
  - `logger_init` - emitted on EventLogger.__init__() (line 39)
  - `logger_close` - emitted on EventLogger.close() (line 98)

- **TelemetryCollector** class (lines 111-160):
  - `metric` - emitted by record_metric() (line 121)
  - `timer_start` - emitted by start_timer() (line 135)
  - `timer_stop` - emitted by stop_timer() (line 146)

**Current Status**: **DORMANT**
- D-REAM is disabled (KLR_ENABLE_DREAM_EVOLUTION=0)
- D-REAM is being refactored
- These signals are not being actively emitted

**Value Proposition**: LOW (currently)
- Designed for D-REAM evolution run tracking
- Would be valuable when D-REAM is re-enabled
- Not needed while D-REAM is disabled

**Recommendation**: **NO ACTION**
- Leave emitters in place for when D-REAM is re-enabled
- If D-REAM refactoring changes telemetry approach, update then
- These are not causing noise (not being emitted)

---

## Decision Matrix

| Signal | Status | Active? | Value | Cost | Recommendation |
|--------|--------|---------|-------|------|----------------|
| HEARTBEAT | Orphaned | ✓ Yes (every ChemSub) | HIGH | LOW | Implement consumer |
| logger_init | Orphaned | ✗ No (D-REAM disabled) | LOW | N/A | Leave for D-REAM |
| logger_close | Orphaned | ✗ No (D-REAM disabled) | LOW | N/A | Leave for D-REAM |
| metric | Orphaned | ✗ No (D-REAM disabled) | MEDIUM | N/A | Leave for D-REAM |
| timer_start | Orphaned | ✗ No (D-REAM disabled) | MEDIUM | N/A | Leave for D-REAM |
| timer_stop | Orphaned | ✗ No (D-REAM disabled) | MEDIUM | N/A | Leave for D-REAM |

---

## Recommended Implementation: Heartbeat Monitor

### Option A: Lightweight Health Monitor Daemon (RECOMMENDED)

**Features**:
- Subscribe to HEARTBEAT signal
- Track last heartbeat timestamp per zooid
- Emit CAPABILITY_GAP when heartbeat missing > 30 seconds
- Log component start/stop events

**Implementation**:
```python
# /home/kloros/src/kloros/monitors/heartbeat_monitor_daemon.py

class HeartbeatMonitor:
    def __init__(self):
        self.last_seen = {}  # zooid -> timestamp
        self.threshold = 30  # seconds
        self.pub = ChemPub()

        self.sub = ChemSub(
            topic="HEARTBEAT",
            on_json=self._on_heartbeat,
            zooid_name="heartbeat_monitor",
            niche="monitoring"
        )

    def _on_heartbeat(self, msg):
        zooid = msg.get("facts", {}).get("zooid")
        if zooid:
            self.last_seen[zooid] = time.time()

    def _check_heartbeats(self):
        """Check for missing heartbeats every 15s."""
        now = time.time()
        for zooid, last_ts in self.last_seen.items():
            if now - last_ts > self.threshold:
                self.pub.emit(
                    signal="CAPABILITY_GAP",
                    ecosystem="monitoring",
                    facts={
                        "gap_type": "heartbeat_missing",
                        "gap_name": f"heartbeat_{zooid}",
                        "zooid": zooid,
                        "last_seen": last_ts,
                        "missing_seconds": now - last_ts
                    }
                )
```

**Systemd Service**:
```ini
[Unit]
Description=KLoROS Heartbeat Monitor
After=kloros-chembus-proxy.service

[Service]
Type=simple
User=kloros
WorkingDirectory=/home/kloros
ExecStart=/home/kloros/.venv/bin/python3 -m kloros.monitors.heartbeat_monitor_daemon
Restart=always
MemoryMax=50M
CPUQuota=5%
```

**Resource Usage**:
- Memory: ~30MB (store ~50 zooids with timestamps)
- CPU: <5% (simple timestamp checking every 15s)

**Benefits**:
- Detect component failures automatically
- Track component uptime and stability
- Low overhead (passive monitoring)
- Integrates with existing CAPABILITY_GAP workflow

---

### Option B: Add to Orchestrator Monitor (ALTERNATIVE)

**Approach**: Add heartbeat tracking to existing orchestrator-monitor daemon

**Benefits**:
- No new daemon needed
- Centralized monitoring

**Drawbacks**:
- Orchestrator-monitor is for service status, not real-time liveness
- Mixing concerns (systemd status vs ChemBus heartbeats)
- Harder to disable independently

---

## Recommendations

### Immediate (Phase 2)

**Implement Heartbeat Monitor** (Option A):
1. Create `/home/kloros/src/kloros/monitors/heartbeat_monitor_daemon.py`
2. Create `/etc/systemd/system/kloros-heartbeat-monitor.service`
3. Enable and start service
4. Verify CAPABILITY_GAP emissions for missing heartbeats

**Expected Outcome**:
- HEARTBEAT no longer orphaned
- Component liveness monitoring functional
- Automatic detection of component failures

---

### D-REAM Telemetry (Phase 4 - Future)

**NO ACTION NEEDED NOW**:
- Leave logger_init, logger_close, metric, timer_start, timer_stop as-is
- D-REAM refactoring will determine final telemetry approach
- If D-REAM keeps current approach, implement telemetry aggregator then
- If D-REAM changes to different approach, remove old emitters then

**When D-REAM is Re-enabled**:
- Evaluate if current telemetry approach is still desired
- If YES → Implement telemetry aggregator daemon
- If NO → Remove emitters and update to new approach

---

## Impact Assessment

### Before Implementation
- 6 orphaned telemetry signals
- No component liveness monitoring
- Cannot detect component failures via heartbeat

### After Heartbeat Monitor Implementation
- 1 orphaned telemetry signal (Q_CURIOSITY_ARCHIVED)
- 5 dormant signals (D-REAM telemetry - expected)
- Component liveness monitoring functional
- Automatic failure detection via heartbeat gaps

### Final Orphaned Count
- **Before**: 9 active orphaned channels
- **After heartbeat monitor**: 1 active orphaned channel (Q_CURIOSITY_ARCHIVED)
- **Dormant (acceptable)**: 5 D-REAM telemetry signals

---

## Decision

**PROCEED** with lightweight heartbeat monitor daemon (Option A)?
**DEFER** D-REAM telemetry until refactoring complete?

This decision will:
- ✅ Add valuable component health monitoring
- ✅ Reduce active orphaned channels from 9 → 1
- ✅ Minimal resource overhead (~30MB memory, <5% CPU)
- ✅ Integrate with existing CAPABILITY_GAP workflow
- ✅ Keep D-REAM telemetry for future use

**Recommended**: YES - Implement heartbeat monitor, defer D-REAM telemetry
