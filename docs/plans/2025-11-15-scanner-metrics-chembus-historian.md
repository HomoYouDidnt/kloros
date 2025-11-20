# Scanner Metrics Collection via ChemBus Historian

**Date:** 2025-11-15
**Status:** Design Complete - Ready for Implementation
**Architecture Pattern:** Chemical Signal Bus + Memory Consolidation

## Problem

All 5 capability scanners expect metrics files that don't exist:
- `bottleneck_detector_scanner.py` → needs `queue_metrics.jsonl`, `operation_metrics.jsonl`
- `inference_performance_scanner.py` → needs `inference_metrics.jsonl`
- `context_utilization_scanner.py` → needs `context_utilization.jsonl`
- `resource_profiler_scanner.py` → needs `resource_metrics.jsonl`
- `comparative_analyzer_scanner.py` → needs `brainmod` and `variant` fields in fitness_ledger

Scanners can't detect optimization opportunities without operational data from running daemons.

## Solution

**Chemical Signal Paradigm**: Use ChemBus as the "interstitial fluid" carrying operational metrics. Daemons emit signals about their activity, historian preserves them, scanners "overhear" what they need, introspection consolidates into long-term memory.

**Key Insight**: Just like natural chemical signaling where adrenaline affects multiple systems simultaneously, a single `Q_INVESTIGATION_COMPLETE` signal serves semantic_dedup (intended recipient), bottleneck_detector (queue analysis), and inference_performance_scanner (timing analysis).

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────────┐
│                         ChemBus (ZMQ)                            │
│  Topics: Q_INVESTIGATION_COMPLETE, METRICS_SUMMARY, etc.        │
└────────┬──────────────────────────────────────────┬─────────────┘
         │                                           │
         ├───► ledger_writer (OBSERVATION)          │
         ├───► semantic_dedup (Q_INVESTIGATION_*)   │
         ├───► capability_integrator                │
         │                                           │
         └───► chembus_historian (NEW) ◄────────────┘
                      │                     subscribes to: ""
                      │                     (all topics)
                      ▼
         ┌──────────────────────────┐
         │ chembus_history.jsonl    │
         │  - Last 24-48h of msgs   │
         │  - Continuous append     │
         │  - 500MB size limit      │
         └──────┬───────────────────┘
                │
         ┌──────▼─────────────────────────────────────────┐
         │  introspection_daemon (ENHANCED)                │
         │   - Triggers scanners via RUN_SCANNER intents  │
         │   - Consolidates old history → episodic memory │
         │   - Prunes consolidated segments               │
         └──────┬─────────────────────────────────────────┘
                │
         ┌──────▼──────────────────────────────────┐
         │  Scanners (on-demand, event-driven)     │
         │   - Read chembus_history.jsonl          │
         │   - Analyze recent patterns             │
         │   - Emit CAPABILITY_GAP_FOUND           │
         │   - Write findings + deduplicate        │
         └─────────────────────────────────────────┘
```

### Data Flow

1. **Emission**: Daemons emit operational signals
   - **Routine**: `METRICS_SUMMARY` every 5 minutes (baseline counts)
   - **Anomaly**: `BOTTLENECK_DETECTED`, `PERFORMANCE_DEGRADED` (immediate)
   - **Critical events**: `Q_INVESTIGATION_COMPLETE` (already exists, augment with metrics)

2. **Collection**: ChemBus Historian persists all signals to `chembus_history.jsonl`

3. **Analysis**: Scanners read history on-demand when triggered by intents

4. **Consolidation**: Introspection daemon (runs several times daily):
   - Reads old segments from chembus_history.jsonl
   - Compresses into trends/statistics
   - Commits to episodic memory
   - Prunes raw data

5. **Memory Lifecycle**:
   - **Hot**: Last 24-48h in chembus_history.jsonl (high detail)
   - **Warm**: Consolidated statistics in episodic memory (patterns)
   - **Pruned**: Raw data older than consolidation is deleted

## Implementation Phases

### Phase 1: ChemBus Historian (Foundation)

**Goal**: Start collecting all ChemBus signals immediately.

**Files to Create**:
1. `/home/kloros/src/kloros/observability/chembus_historian_daemon.py`
2. `/etc/systemd/system/kloros-chembus-historian.service`

**Historian Daemon Spec**:
```python
"""
ChemBus Historian Daemon - Persists all chemical signals to history file.

Subscribes to all ChemBus topics and maintains a rolling window of recent messages.
Introspection daemon consolidates old segments and prunes the file.
"""

class ChemBusHistorian:
    def __init__(self):
        self.history_file = Path.home() / ".kloros/chembus_history.jsonl"
        self.max_size_bytes = 500 * 1024 * 1024  # 500MB emergency limit

        # Subscribe to ALL topics (empty string matches everything)
        self.sub = ChemSub(
            topic="",  # All topics
            on_json=self._on_message,
            zooid_name="chembus_historian",
            niche="observability"
        )

    def _on_message(self, msg: dict):
        """Append message to history file."""
        # Add reception timestamp
        msg["_historian_ts"] = time.time()

        # Atomic append
        with open(self.history_file, "a") as f:
            f.write(json.dumps(msg, separators=(",", ":")) + "\n")

        # Check size, rotate if needed
        if self.history_file.stat().st_size > self.max_size_bytes:
            self._emergency_rotate()

    def _emergency_rotate(self):
        """Emergency rotation if introspection hasn't pruned in time."""
        old_path = self.history_file.with_suffix(".jsonl.old")
        self.history_file.rename(old_path)
        logger.warning(f"Emergency rotation: {self.history_file} exceeded 500MB")
```

**Systemd Service**:
```ini
[Unit]
Description=KLoROS ChemBus Historian - Chemical signal persistence
After=spica-chem-proxy.service
Wants=spica-chem-proxy.service

[Service]
Type=simple
User=kloros
Group=kloros
WorkingDirectory=/home/kloros
ExecStart=/home/kloros/.venv/bin/python3 -m src.kloros.observability.chembus_historian_daemon
Environment=PYTHONPATH=/home/kloros:/home/kloros/src
Restart=always
RestartSec=10
MemoryMax=128M

[Install]
WantedBy=multi-user.target
```

**Testing**:
```bash
# Start historian
sudo systemctl start kloros-chembus-historian

# Verify it's collecting
tail -f /home/kloros/.kloros/chembus_history.jsonl

# Trigger some activity (should see signals appear)
# Check file size growth
ls -lh /home/kloros/.kloros/chembus_history.jsonl
```

**Success Criteria**:
- [ ] Historian daemon starts without errors
- [ ] chembus_history.jsonl is created and grows with ChemBus activity
- [ ] All ChemBus signals (OBSERVATION, Q_INVESTIGATION_COMPLETE, HEARTBEAT) are captured
- [ ] Emergency rotation works when file exceeds 500MB

---

### Phase 2: Bottleneck Detector (First Vertical Slice)

**Goal**: End-to-end working bottleneck detection using ChemBus data.

**Files to Modify**:
1. `/home/kloros/src/kloros/orchestration/investigation_consumer_daemon.py` - emit metrics
2. `/home/kloros/src/registry/bottleneck_detector_scanner.py` - read from historian
3. `/home/kloros/src/registry/scanner_deduplication.py` (NEW) - hash-based dedup

**Step 2A: investigation_consumer Instrumentation**

Add metrics emission:
```python
class InvestigationConsumerDaemon:
    def __init__(self):
        # ... existing init ...
        self.metrics_window_start = time.time()
        self.metrics_investigations_completed = 0
        self.metrics_investigations_failed = 0

        # Start metrics summary thread
        self._metrics_thread = threading.Thread(
            target=self._emit_metrics_summary,
            daemon=True
        )
        self._metrics_thread.start()

    def _emit_metrics_summary(self):
        """Emit METRICS_SUMMARY every 5 minutes."""
        while True:
            time.sleep(300)  # 5 minutes

            try:
                queue_depth = self._get_queue_depth()

                self.chem_pub.emit(
                    signal="METRICS_SUMMARY",
                    ecosystem="introspection",
                    facts={
                        "daemon": "investigation_consumer",
                        "window_duration_s": 300,
                        "investigations_completed": self.metrics_investigations_completed,
                        "investigations_failed": self.metrics_investigations_failed,
                        "queue_depth_current": queue_depth
                    }
                )

                # Check for anomalies
                if queue_depth > 50:
                    self.chem_pub.emit(
                        signal="BOTTLENECK_DETECTED",
                        ecosystem="introspection",
                        intensity=2.0,
                        facts={
                            "daemon": "investigation_consumer",
                            "issue": "queue_buildup",
                            "queue_depth": queue_depth,
                            "threshold": 50
                        }
                    )

                # Reset counters
                self.metrics_investigations_completed = 0
                self.metrics_investigations_failed = 0

            except Exception as e:
                logger.error(f"Metrics summary emission failed: {e}")

    def _get_queue_depth(self):
        """Get current queue depth."""
        try:
            return len(list(Path("/home/kloros/.kloros/curiosity_questions").glob("*.json")))
        except:
            return 0
```

Augment existing Q_INVESTIGATION_COMPLETE signal:
```python
# In _process_question method, after investigation completes:
self.chem_pub.emit(
    signal="Q_INVESTIGATION_COMPLETE",
    ecosystem="introspection",
    intensity=1.0,
    facts={
        # Existing fields
        "investigation_timestamp": investigation.get("timestamp"),
        "module_name": investigation.get("module_name"),
        "question_id": question_id,
        "status": investigation.get("status"),

        # NEW: Add performance metrics
        "duration_ms": investigation.get("duration_ms"),
        "model_used": investigation.get("model_used"),
        "tokens_used": investigation.get("tokens_used", 0),
        "queue_wait_time_ms": investigation.get("queue_wait_time_ms", 0)
    }
)
```

**Step 2B: Bottleneck Detector Adaptation**

Replace missing metrics files with chembus_history reader:
```python
class BottleneckDetectorScanner:
    def scan(self) -> List[Dict[str, Any]]:
        """Scan for bottlenecks using ChemBus history."""
        history_file = Path.home() / ".kloros/chembus_history.jsonl"

        if not history_file.exists():
            logger.warning("chembus_history.jsonl not found")
            return []

        # Read recent metrics (last 1 hour)
        cutoff_ts = time.time() - 3600
        metrics_summaries = []
        queue_events = []

        with open(history_file, "r") as f:
            for line in f:
                try:
                    msg = json.loads(line)

                    # Filter by timestamp
                    if msg.get("ts", 0) < cutoff_ts:
                        continue

                    # Collect METRICS_SUMMARY from investigation_consumer
                    if msg.get("signal") == "METRICS_SUMMARY" and \
                       msg.get("facts", {}).get("daemon") == "investigation_consumer":
                        metrics_summaries.append(msg)

                    # Collect queue-related events
                    if msg.get("signal") in ["BOTTLENECK_DETECTED", "Q_INVESTIGATION_COMPLETE"]:
                        queue_events.append(msg)

                except json.JSONDecodeError:
                    continue

        # Analyze patterns
        bottlenecks = []

        # Check queue depth trends
        queue_depths = [m["facts"]["queue_depth_current"]
                       for m in metrics_summaries
                       if "queue_depth_current" in m.get("facts", {})]

        if queue_depths and np.mean(queue_depths) > 30:
            bottlenecks.append({
                "type": "queue_buildup",
                "severity": "high" if np.mean(queue_depths) > 50 else "medium",
                "avg_queue_depth": np.mean(queue_depths),
                "max_queue_depth": max(queue_depths),
                "recommendation": "Investigation consumer may need more workers or faster model"
            })

        # Check investigation completion rate
        completed = sum(m["facts"].get("investigations_completed", 0)
                       for m in metrics_summaries)
        failed = sum(m["facts"].get("investigations_failed", 0)
                    for m in metrics_summaries)

        if completed > 0 and (failed / completed) > 0.2:
            bottlenecks.append({
                "type": "high_failure_rate",
                "severity": "critical",
                "failure_rate": failed / completed,
                "completed": completed,
                "failed": failed,
                "recommendation": "Investigate investigation failures - may indicate LLM issues or bad questions"
            })

        return bottlenecks
```

**Step 2C: Scanner Deduplication Module**

```python
# /home/kloros/src/registry/scanner_deduplication.py
"""
Scanner result deduplication using content hashing.

Prevents scanners from repeatedly reporting the same issue.
"""
import hashlib
import json
from pathlib import Path
from typing import Dict, Any, Optional

class ScannerDeduplicator:
    def __init__(self, scanner_name: str):
        self.scanner_name = scanner_name
        self.state_file = Path.home() / ".kloros/scanner_state" / f"{scanner_name}_reported.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_state()

    def _load_state(self):
        """Load previously reported issue hashes."""
        if self.state_file.exists():
            self.reported = json.loads(self.state_file.read_text())
        else:
            self.reported = {}

    def _save_state(self):
        """Save reported issue hashes."""
        self.state_file.write_text(json.dumps(self.reported, indent=2))

    def fingerprint(self, finding: Dict[str, Any]) -> str:
        """Generate fingerprint hash for a finding."""
        # Use type + key identifying fields
        key_fields = {
            "type": finding.get("type"),
            "daemon": finding.get("daemon"),
            "issue": finding.get("issue")
        }

        fingerprint_str = json.dumps(key_fields, sort_keys=True)
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:16]

    def should_report(self, finding: Dict[str, Any]) -> bool:
        """Check if finding should be reported (not a duplicate)."""
        fp = self.fingerprint(finding)

        if fp not in self.reported:
            # New finding - report it
            self.reported[fp] = {
                "first_seen": time.time(),
                "last_seen": time.time(),
                "count": 1
            }
            self._save_state()
            return True

        # Already reported - update last_seen but don't report
        self.reported[fp]["last_seen"] = time.time()
        self.reported[fp]["count"] += 1
        self._save_state()
        return False

    def mark_resolved(self, finding: Dict[str, Any]):
        """Mark a finding as resolved (removes from reported set)."""
        fp = self.fingerprint(finding)
        if fp in self.reported:
            del self.reported[fp]
            self._save_state()
```

**Step 2D: Scanner Result Emission**

Update bottleneck_detector to emit results:
```python
# After detecting bottlenecks:
from registry.scanner_deduplication import ScannerDeduplicator

dedup = ScannerDeduplicator("bottleneck_detector")

for bottleneck in bottlenecks:
    if dedup.should_report(bottleneck):
        # Emit ChemBus signal
        chem_pub.emit(
            signal="CAPABILITY_GAP_FOUND",
            ecosystem="introspection",
            intensity=2.0 if bottleneck["severity"] == "critical" else 1.5,
            facts={
                "scanner": "bottleneck_detector",
                "finding": bottleneck
            }
        )

        # Write to file for audit trail
        findings_dir = Path.home() / ".kloros/scanner_findings"
        findings_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        findings_file = findings_dir / f"bottleneck_{timestamp}.json"
        findings_file.write_text(json.dumps(bottleneck, indent=2))
```

**Testing Phase 2**:
```bash
# Generate load to create bottleneck
for i in {1..60}; do
  echo '{"type": "curiosity_investigate", "question": "test '$i'"}' > \
    ~/.kloros/intents/test_$i.json
done

# Wait for metrics to accumulate
sleep 360  # 6 minutes (2 METRICS_SUMMARY cycles)

# Manually trigger scanner
python3 -m src.registry.bottleneck_detector_scanner

# Check results
ls -l ~/.kloros/scanner_findings/
cat ~/.kloros/scanner_findings/bottleneck_*.json
```

**Success Criteria Phase 2**:
- [ ] investigation_consumer emits METRICS_SUMMARY every 5 minutes
- [ ] Bottleneck detector reads chembus_history.jsonl successfully
- [ ] Bottleneck detector identifies queue buildup
- [ ] Findings are emitted to ChemBus and written to files
- [ ] Deduplication prevents repeated reports of same bottleneck

---

### Phase 3: Inference Performance Scanner (Second Vertical Slice)

**Goal**: Detect slow inference and model performance issues.

**Files to Modify**:
1. `/home/kloros/src/kloros/orchestration/investigation_consumer_daemon.py` - augment signals
2. `/home/kloros/src/registry/inference_performance_scanner.py` - adapt to chembus

**Step 3A: Enhanced Investigation Metrics**

Track per-model timing and add to Q_INVESTIGATION_COMPLETE:
```python
class InvestigationConsumerDaemon:
    def __init__(self):
        # ... existing init ...
        self.model_baselines = {}  # {model_name: {avg_ms: float, count: int}}

    def _process_question(self, question_id: str, question_data: dict):
        start_time = time.time()
        model_used = None

        # ... existing investigation logic ...

        # Track timing
        duration_ms = (time.time() - start_time) * 1000

        # Update baseline for this model
        if model_used:
            if model_used not in self.model_baselines:
                self.model_baselines[model_used] = {"avg_ms": duration_ms, "count": 1}
            else:
                baseline = self.model_baselines[model_used]
                baseline["avg_ms"] = (baseline["avg_ms"] * baseline["count"] + duration_ms) / (baseline["count"] + 1)
                baseline["count"] += 1

            # Check for anomaly: >2x baseline
            baseline_ms = self.model_baselines[model_used]["avg_ms"]
            if duration_ms > (baseline_ms * 2) and baseline["count"] > 5:
                self.chem_pub.emit(
                    signal="PERFORMANCE_DEGRADED",
                    ecosystem="introspection",
                    intensity=1.5,
                    facts={
                        "daemon": "investigation_consumer",
                        "model": model_used,
                        "duration_ms": duration_ms,
                        "baseline_ms": baseline_ms,
                        "deviation_factor": duration_ms / baseline_ms
                    }
                )
```

**Step 3B: Inference Performance Scanner**

```python
def scan(self) -> List[Dict[str, Any]]:
    """Detect slow inference and model performance issues."""
    history_file = Path.home() / ".kloros/chembus_history.jsonl"

    # Read Q_INVESTIGATION_COMPLETE events from last 6 hours
    cutoff_ts = time.time() - (6 * 3600)
    investigations = []

    with open(history_file, "r") as f:
        for line in f:
            try:
                msg = json.loads(line)

                if msg.get("ts", 0) < cutoff_ts:
                    continue

                if msg.get("signal") == "Q_INVESTIGATION_COMPLETE":
                    investigations.append(msg["facts"])

            except json.JSONDecodeError:
                continue

    # Analyze per-model performance
    findings = []
    model_timings = defaultdict(list)

    for inv in investigations:
        model = inv.get("model_used")
        duration = inv.get("duration_ms")

        if model and duration:
            model_timings[model].append(duration)

    # Check for slow models
    for model, timings in model_timings.items():
        avg_ms = np.mean(timings)
        p95_ms = np.percentile(timings, 95)

        # Flag if average >60s or p95 >120s
        if avg_ms > 60000 or p95_ms > 120000:
            findings.append({
                "type": "slow_inference",
                "model": model,
                "avg_duration_ms": avg_ms,
                "p95_duration_ms": p95_ms,
                "sample_size": len(timings),
                "severity": "high" if avg_ms > 120000 else "medium",
                "recommendation": f"Model {model} is slow. Consider switching to faster model or increasing timeout."
            })

    return findings
```

**Testing Phase 3**:
```bash
# Trigger investigations with 32B model (slow)
# Wait for data collection
# Run scanner
python3 -m src.registry.inference_performance_scanner

# Verify findings
cat ~/.kloros/scanner_findings/inference_*.json
```

**Success Criteria Phase 3**:
- [ ] investigation_consumer tracks per-model baselines
- [ ] PERFORMANCE_DEGRADED signals emitted for anomalies
- [ ] Inference scanner identifies slow models
- [ ] Findings correctly flag models exceeding thresholds

---

### Phase 4: Context & Resource Scanners (Third Vertical Slice)

**Goal**: Complete remaining scanner adaptations using same pattern.

**Files to Modify**:
1. `/home/kloros/src/registry/context_utilization_scanner.py`
2. `/home/kloros/src/registry/resource_profiler_scanner.py`

**Context Utilization Scanner**:
- Read Q_INVESTIGATION_COMPLETE events
- Track `context_tokens` field (need to add to investigation_consumer emission)
- Detect wasted context (high tokens, low information density)

**Resource Profiler Scanner**:
- Read METRICS_SUMMARY from all daemons
- Track memory usage, CPU time from daemon self-reporting
- Detect resource leaks (memory growing over time)

**Implementation Note**: Follow exact same pattern as Phase 2 and 3:
1. Add metrics to daemon signals
2. Adapt scanner to read chembus_history.jsonl
3. Use ScannerDeduplicator
4. Emit CAPABILITY_GAP_FOUND + write findings

---

### Phase 5: Comparative Analyzer + Ledger Enrichment

**Goal**: Enable brainmod/variant comparison.

**Files to Modify**:
1. `/home/kloros/src/kloros/observability/ledger_writer_daemon.py` - enrich observations
2. `/home/kloros/src/registry/comparative_analyzer_scanner.py` - use enriched ledger

**Step 5A: Ledger Enrichment**

```python
class LedgerWriterDaemon:
    def __init__(self):
        # ... existing init ...
        self.reg_mgr = LifecycleRegistry()

    def _process_observation(self, msg: dict):
        """Process OBSERVATION and write to ledger with enrichment."""
        # Extract zooid info from message
        zooid_name = msg.get("facts", {}).get("zooid")

        # Look up brainmod and variant from registry
        brainmod = None
        variant = None

        if zooid_name:
            try:
                zooid_meta = self.reg_mgr.get_zooid_metadata(zooid_name)
                brainmod = zooid_meta.get("brainmod")
                variant = zooid_meta.get("variant")
            except Exception as e:
                logger.debug(f"Could not enrich zooid {zooid_name}: {e}")

        # Enrich observation with brainmod/variant
        observation = {
            **msg.get("facts", {}),
            "timestamp": msg.get("ts"),
            "brainmod": brainmod,
            "variant": variant
        }

        # Append to ledger (existing logic)
        append_observation_atomic(
            ledger_path=LEDGER_PATH,
            observation=observation,
            hmac_key_path=HMAC_KEY_PATH
        )
```

**Step 5B: Registry Metadata Support**

Add brainmod/variant tracking to LifecycleRegistry (if not already present):
```python
# Infer from zooid filename or source path
def get_zooid_metadata(self, zooid_name: str) -> Dict[str, Any]:
    """Get metadata for a zooid including brainmod and variant."""
    zooid_path = self._find_zooid_file(zooid_name)

    if not zooid_path:
        return {}

    # Parse from filename: {capability}_{timestamp}_{variant}.py
    parts = zooid_path.stem.split("_")

    return {
        "brainmod": parts[0] if len(parts) > 0 else None,
        "variant": parts[-1] if len(parts) > 2 else "0",
        "path": str(zooid_path)
    }
```

**Step 5C: Comparative Analyzer**

```python
def scan(self) -> List[Dict[str, Any]]:
    """Compare performance across brainmods and variants."""
    ledger_file = Path.home() / ".kloros/lineage/fitness_ledger.jsonl"

    # Read observations from last 7 days
    cutoff_ts = time.time() - (7 * 86400)
    observations = []

    with open(ledger_file, "r") as f:
        for line in f:
            try:
                obs = json.loads(line)

                if obs.get("timestamp", 0) < cutoff_ts:
                    continue

                # Only include observations with brainmod/variant
                if obs.get("brainmod") and obs.get("variant"):
                    observations.append(obs)

            except json.JSONDecodeError:
                continue

    # Group by brainmod
    brainmod_performance = defaultdict(lambda: {"ok": 0, "fail": 0, "variants": defaultdict(lambda: {"ok": 0, "fail": 0})})

    for obs in observations:
        brainmod = obs["brainmod"]
        variant = obs["variant"]
        outcome = obs.get("outcome", "fail")

        if outcome == "ok":
            brainmod_performance[brainmod]["ok"] += 1
            brainmod_performance[brainmod]["variants"][variant]["ok"] += 1
        else:
            brainmod_performance[brainmod]["fail"] += 1
            brainmod_performance[brainmod]["variants"][variant]["fail"] += 1

    # Find best/worst performers
    findings = []

    for brainmod, stats in brainmod_performance.items():
        total = stats["ok"] + stats["fail"]
        if total < 10:  # Skip low sample sizes
            continue

        ok_rate = stats["ok"] / total

        # Find best variant
        best_variant = None
        best_rate = 0

        for variant, vstats in stats["variants"].items():
            vtotal = vstats["ok"] + vstats["fail"]
            if vtotal < 5:
                continue

            vrate = vstats["ok"] / vtotal
            if vrate > best_rate:
                best_rate = vrate
                best_variant = variant

        findings.append({
            "type": "brainmod_performance",
            "brainmod": brainmod,
            "overall_ok_rate": ok_rate,
            "best_variant": best_variant,
            "best_variant_ok_rate": best_rate,
            "sample_size": total,
            "recommendation": f"Brainmod {brainmod}: variant {best_variant} performing best at {best_rate:.1%}"
        })

    return findings
```

**Success Criteria Phase 5**:
- [ ] Ledger writer enriches observations with brainmod/variant
- [ ] fitness_ledger.jsonl contains brainmod/variant fields
- [ ] Comparative analyzer successfully compares performance
- [ ] Findings identify best-performing variants

---

### Phase 6: Introspection Integration

**Goal**: Trigger scanners on schedule and consolidate history to episodic memory.

**Files to Modify**:
1. `/home/kloros/src/kloros/introspection/introspection_daemon.py` - trigger scanners, consolidate history

**Step 6A: Scanner Triggering**

```python
# In introspection_daemon's main cycle:
def run_introspection_cycle(self):
    """Run full introspection cycle including scanners."""
    logger.info("[introspection] Starting introspection cycle")

    # Existing introspection logic...

    # Trigger all scanners via intents
    scanners = [
        "bottleneck_detector",
        "inference_performance",
        "context_utilization",
        "resource_profiler",
        "comparative_analyzer"
    ]

    for scanner_name in scanners:
        intent_file = Path.home() / ".kloros/intents" / f"run_scanner_{scanner_name}_{int(time.time())}.json"
        intent_file.write_text(json.dumps({
            "type": "run_scanner",
            "scanner": scanner_name,
            "triggered_by": "introspection_cycle",
            "timestamp": time.time()
        }))

        logger.info(f"[introspection] Triggered scanner: {scanner_name}")
```

**Step 6B: History Consolidation**

```python
def consolidate_chembus_history(self):
    """Consolidate old ChemBus history to episodic memory and prune."""
    history_file = Path.home() / ".kloros/chembus_history.jsonl"

    if not history_file.exists():
        return

    # Consolidation threshold: messages older than 24h
    cutoff_ts = time.time() - 86400

    # Read and split: old vs recent
    old_messages = []
    recent_messages = []

    with open(history_file, "r") as f:
        for line in f:
            try:
                msg = json.loads(line)

                if msg.get("ts", 0) < cutoff_ts:
                    old_messages.append(msg)
                else:
                    recent_messages.append(msg)

            except json.JSONDecodeError:
                continue

    if not old_messages:
        logger.info("[introspection] No old messages to consolidate")
        return

    # Aggregate statistics from old messages
    consolidated = {
        "consolidation_timestamp": time.time(),
        "window_start": min(m.get("ts", 0) for m in old_messages),
        "window_end": cutoff_ts,
        "total_messages": len(old_messages),
        "signals_by_type": defaultdict(int),
        "daemons_active": set(),
        "anomalies": []
    }

    for msg in old_messages:
        signal = msg.get("signal")
        consolidated["signals_by_type"][signal] += 1

        daemon = msg.get("facts", {}).get("daemon")
        if daemon:
            consolidated["daemons_active"].add(daemon)

        # Preserve anomaly signals
        if signal in ["BOTTLENECK_DETECTED", "PERFORMANCE_DEGRADED", "CAPABILITY_GAP_FOUND"]:
            consolidated["anomalies"].append({
                "signal": signal,
                "ts": msg.get("ts"),
                "facts": msg.get("facts")
            })

    # Convert sets to lists for JSON serialization
    consolidated["daemons_active"] = list(consolidated["daemons_active"])
    consolidated["signals_by_type"] = dict(consolidated["signals_by_type"])

    # Write to episodic memory
    episodic_memory_file = Path.home() / ".kloros/episodic_memory/chembus_consolidated.jsonl"
    episodic_memory_file.parent.mkdir(parents=True, exist_ok=True)

    with open(episodic_memory_file, "a") as f:
        f.write(json.dumps(consolidated) + "\n")

    logger.info(f"[introspection] Consolidated {len(old_messages)} old messages to episodic memory")

    # Rewrite history file with only recent messages
    with open(history_file, "w") as f:
        for msg in recent_messages:
            f.write(json.dumps(msg, separators=(",", ":")) + "\n")

    logger.info(f"[introspection] Pruned history file, kept {len(recent_messages)} recent messages")
```

**Step 6C: Intent Router Scanner Support**

Add scanner intent handler to intent_router:
```python
# In intent_router's intent type handlers:
if intent_type == "run_scanner":
    scanner_name = intent_data.get("scanner")

    logger.info(f"[intent_router] Running scanner: {scanner_name}")

    # Execute scanner
    result = subprocess.run(
        ["/home/kloros/.venv/bin/python3", "-m", f"src.registry.{scanner_name}_scanner"],
        capture_output=True,
        text=True,
        timeout=60
    )

    if result.returncode != 0:
        logger.error(f"Scanner {scanner_name} failed: {result.stderr}")
    else:
        logger.info(f"Scanner {scanner_name} completed successfully")
```

**Success Criteria Phase 6**:
- [ ] Introspection triggers all scanners via intents
- [ ] Scanners execute and emit findings
- [ ] Old history is consolidated to episodic memory
- [ ] chembus_history.jsonl is pruned to recent messages only
- [ ] Consolidation preserves anomaly signals

---

## Error Handling

### ChemBus Historian
- **ChemBus unavailable**: Retry connection with exponential backoff
- **Disk full**: Emergency rotation, log critical error, emit alert signal
- **Corrupt line in history**: Skip line, log warning, continue

### Scanners
- **History file missing**: Log warning, return empty findings
- **Malformed JSON in history**: Skip line, continue parsing
- **Zero data points**: Return empty findings (not an error)
- **Scanner crash**: Log error, emit CAPABILITY_GAP_FOUND with error details

### Introspection
- **Scanner timeout**: Kill scanner process after 60s, log error, continue with next scanner
- **Consolidation failure**: Log error but don't prune (preserve raw data)
- **Intent emission failure**: Log error, continue introspection cycle

## Testing Strategy

### Unit Tests
- ChemBus historian message persistence
- Scanner deduplication fingerprinting
- History consolidation logic
- Scanner parsers (mock chembus_history.jsonl)

### Integration Tests
- End-to-end: emit signal → historian captures → scanner reads → findings emitted
- Load test: 10k messages/minute sustained for 1 hour
- Rotation: verify emergency rotation at 500MB
- Consolidation: verify old data pruned correctly

### System Tests
- Run full system for 48h, verify no memory leaks
- Trigger actual bottleneck, verify scanner detects it
- Compare scanner findings with manual analysis (ground truth)

## Rollback Plan

Each phase can be disabled independently:
1. **Historian**: Stop service, scanners fail gracefully (no data)
2. **Daemon metrics**: Remove METRICS_SUMMARY emission, historian still works
3. **Scanners**: Don't trigger them, system continues normally
4. **Introspection**: Skip scanner triggering, manual scanner invocation still works

## Success Metrics

- **Coverage**: All 5 scanners operational and finding real issues
- **Latency**: Scanners complete analysis in <60s
- **Accuracy**: Findings match manual analysis (>90% agreement)
- **Noise**: <5% false positive rate on CAPABILITY_GAP_FOUND signals
- **Stability**: No crashes or memory leaks over 7 days of operation

## Future Enhancements

1. **Adaptive sampling**: Historian samples high-frequency signals (HEARTBEAT) but keeps 100% of critical signals
2. **Distributed scanning**: Run scanners in parallel using multiprocessing
3. **ML-based anomaly detection**: Replace threshold-based detection with learned baselines
4. **Scanner self-tuning**: Scanners learn optimal thresholds from historical false positive rates
5. **Real-time alerts**: Emit high-priority intents for critical findings (bypass queue)
6. **Scanner benchmarking**: Track scanner execution time and accuracy over time

---

## Implementation Checklist

### Phase 1: ChemBus Historian
- [ ] Create `chembus_historian_daemon.py`
- [ ] Create systemd service file
- [ ] Test message collection
- [ ] Verify emergency rotation
- [ ] Enable and start service

### Phase 2: Bottleneck Detector
- [ ] Add METRICS_SUMMARY to investigation_consumer
- [ ] Add BOTTLENECK_DETECTED anomaly emission
- [ ] Create `scanner_deduplication.py`
- [ ] Adapt `bottleneck_detector_scanner.py`
- [ ] Add ChemBus result emission
- [ ] Test with artificial bottleneck
- [ ] Verify deduplication

### Phase 3: Inference Performance
- [ ] Add model timing tracking to investigation_consumer
- [ ] Add PERFORMANCE_DEGRADED emission
- [ ] Adapt `inference_performance_scanner.py`
- [ ] Test with slow model
- [ ] Verify findings accuracy

### Phase 4: Context & Resource
- [ ] Add context_tokens to investigation signals
- [ ] Adapt `context_utilization_scanner.py`
- [ ] Add daemon resource self-reporting
- [ ] Adapt `resource_profiler_scanner.py`
- [ ] Test both scanners

### Phase 5: Comparative Analyzer
- [ ] Add brainmod/variant lookup to ledger_writer
- [ ] Enrich fitness_ledger observations
- [ ] Adapt `comparative_analyzer_scanner.py`
- [ ] Test with multi-variant zooids
- [ ] Verify performance comparisons

### Phase 6: Introspection Integration
- [ ] Add scanner triggering to introspection_daemon
- [ ] Implement history consolidation
- [ ] Add episodic memory storage
- [ ] Add scanner intent handler to intent_router
- [ ] Test full introspection cycle
- [ ] Verify consolidation and pruning

---

**End of Design Document**
