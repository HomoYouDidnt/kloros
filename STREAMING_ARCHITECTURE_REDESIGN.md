# KLoROS Streaming Architecture Redesign

**Problem**: CuriosityCore has devolved into a batch polling system, violating ChemBus streaming principles and causing memory leaks (200MB/min growth).

**Solution**: Convert all monitors to standalone streaming daemons that emit ChemBus signals incrementally.

---

## Current (Broken) Architecture

```
┌─────────────────────────────────────────────────────────┐
│  curiosity_core_consumer_daemon                         │
│  (runs every 60s)                                       │
│                                                         │
│  CuriosityCore.generate_questions():                   │
│    ├─ NEW ExceptionMonitor() → scan logs              │
│    ├─ NEW TestResultMonitor() → scan pytest files     │
│    ├─ NEW ModuleDiscoveryMonitor() → scan /src        │
│    ├─ NEW ChaosLabMonitor() → scan chaos artifacts    │
│    ├─ NEW IntegrationFlowMonitor() → SCAN 500+ FILES! │
│    ├─ NEW CapabilityDiscoveryMonitor() → scan tools   │
│    └─ NEW ExplorationScanner() → scan hardware        │
│                                                         │
│  Each monitor:                                          │
│    - Created fresh every cycle                          │
│    - Scans filesystem/logs synchronously                │
│    - Accumulates data in memory                         │
│    - Returns questions                                  │
│    - Destroyed (but memory lingers)                     │
└─────────────────────────────────────────────────────────┘

PROBLEMS:
❌ Batch processing every 60s
❌ Recreates heavy objects constantly
❌ Synchronous blocking scans
❌ Unbounded memory accumulation
❌ Redundant work (rescans same files)
❌ High CPU spikes every 60s
```

---

## Proper Streaming Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      ChemBus (Event Stream)                  │
│  Topics: EXCEPTION_DETECTED, TEST_FAILED, MODULE_DISCOVERED, │
│          CHAOS_HEALING_FAILED, INTEGRATION_GAP_FOUND, etc.   │
└──────────────────────────────────────────────────────────────┘
         ▲                    ▲                    ▲
         │                    │                    │
         │ emit               │ emit               │ emit
         │                    │                    │
┌────────┴─────────┐  ┌──────┴──────────┐  ┌──────┴──────────┐
│ exception-       │  │ integration-    │  │ chaos-          │
│ monitor-daemon   │  │ monitor-daemon  │  │ monitor-daemon  │
│                  │  │                 │  │                 │
│ - Tail journalctl│  │ - inotify on    │  │ - inotify on    │
│ - Parse errors   │  │   /src/*.py     │  │   chaos/ dir    │
│ - Emit signals   │  │ - Incremental   │  │ - Parse results │
│                  │  │   AST updates   │  │ - Emit signals  │
└──────────────────┘  └─────────────────┘  └─────────────────┘

         ... + 6 more streaming daemons ...

                              │ subscribe
                              ▼
                  ┌───────────────────────────┐
                  │ curiosity-core-consumer   │
                  │                           │
                  │ ChemSub(CAPABILITY_GAP):  │
                  │   → Convert to Question   │
                  │   → Emit to priority queue│
                  │                           │
                  │ NO POLLING                │
                  │ NO SCANNING               │
                  │ PURE SIGNAL CONSUMER      │
                  └───────────────────────────┘

BENEFITS:
✓ Streaming, incremental processing
✓ Event-driven (no polling)
✓ Singleton daemons (low memory)
✓ Bounded memory per daemon
✓ Low, constant CPU usage
✓ Real-time responsiveness
✓ Proper separation of concerns
```

---

## Monitor Daemon Specifications

### 1. exception-monitor-daemon

**Purpose**: Detect exceptions in system logs in real-time

**Implementation**:
```python
#!/usr/bin/env python3
"""Exception Monitor Daemon - Streams journalctl for exceptions."""

class ExceptionMonitorDaemon:
    def __init__(self):
        self.pub = ChemPub()
        self.seen_exceptions = LRUCache(maxsize=1000)  # Dedup recent

    def run(self):
        # Stream journalctl with --follow (like tail -f)
        process = subprocess.Popen(
            ['journalctl', '-f', '--output=json', '--unit=kloros-*'],
            stdout=subprocess.PIPE
        )

        for line in iter(process.stdout.readline, b''):
            entry = json.loads(line)

            # Parse for exceptions
            if self._is_exception(entry):
                exception_id = self._hash_exception(entry)

                # Deduplicate
                if exception_id not in self.seen_exceptions:
                    self.seen_exceptions[exception_id] = True

                    # Emit to ChemBus
                    self.pub.emit(
                        signal="CAPABILITY_GAP",
                        ecosystem="diagnostics",
                        facts={
                            "gap_type": "exception",
                            "gap_name": entry['MESSAGE'],
                            "gap_category": "error_handling",
                            "unit": entry['_SYSTEMD_UNIT'],
                            "traceback": entry.get('TRACEBACK'),
                            "timestamp": entry['__REALTIME_TIMESTAMP']
                        }
                    )
```

**Systemd Service**:
```ini
[Unit]
Description=KLoROS Exception Monitor Daemon
After=network.target

[Service]
Type=simple
User=kloros
WorkingDirectory=/home/kloros/src
ExecStart=/home/kloros/.venv/bin/python3 -m kloros.monitors.exception_monitor_daemon
Restart=always
RestartSec=10s
MemoryMax=100M
CPUQuota=10%

[Install]
WantedBy=multi-user.target
```

**Memory Profile**: ~50MB (LRU cache + journal stream buffer)
**CPU Profile**: 5-10% (parsing JSON stream)

---

### 2. integration-monitor-daemon

**Purpose**: Detect broken integrations by watching code changes

**Implementation**:
```python
#!/usr/bin/env python3
"""Integration Monitor Daemon - Incremental static analysis."""

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class IntegrationMonitorDaemon:
    def __init__(self):
        self.pub = ChemPub()
        self.file_index = {}  # file_path → {flows, responsibilities}
        self.orphaned_queues = set()

    def run(self):
        # Initial scan on startup
        self._initial_scan()

        # Watch for changes
        event_handler = CodeChangeHandler(self)
        observer = Observer()
        observer.schedule(event_handler, "/home/kloros/src", recursive=True)
        observer.start()

        # Periodic orphan check (every 5 minutes, not 60 seconds!)
        while True:
            time.sleep(300)  # 5 minutes
            self._check_for_orphans()

    def _initial_scan(self):
        """Scan all files once on startup."""
        for py_file in Path("/home/kloros/src").rglob("*.py"):
            self._analyze_file(py_file)

    def on_file_changed(self, file_path):
        """Called by watchdog when file changes."""
        # Remove old data for this file
        if file_path in self.file_index:
            old_data = self.file_index[file_path]
            self._remove_flows(old_data['flows'])

        # Analyze updated file
        self._analyze_file(file_path)

        # Check if this change created/fixed an orphan
        self._check_for_orphans()

    def _analyze_file(self, file_path):
        """Parse one file, update index incrementally."""
        with open(file_path) as f:
            tree = ast.parse(f.read())

        analyzer = FlowAnalyzer(file_path)
        analyzer.visit(tree)

        # Update index for this file only
        self.file_index[file_path] = {
            'flows': analyzer.flows,
            'responsibilities': analyzer.responsibilities
        }

    def _check_for_orphans(self):
        """Check all flows for orphaned queues."""
        channels = defaultdict(lambda: {"producers": set(), "consumers": set()})

        for file_data in self.file_index.values():
            for flow in file_data['flows']:
                channels[flow.channel]["producers"].add(flow.producer)
                if flow.consumer:
                    channels[flow.channel]["consumers"].add(flow.consumer)

        # Emit signals for orphans
        for channel, info in channels.items():
            if info["producers"] and not info["consumers"]:
                orphan_id = f"orphaned_queue_{channel}"

                if orphan_id not in self.orphaned_queues:
                    self.orphaned_queues.add(orphan_id)

                    self.pub.emit(
                        signal="CAPABILITY_GAP",
                        ecosystem="architecture",
                        facts={
                            "gap_type": "orphaned_queue",
                            "gap_name": channel,
                            "gap_category": "integration",
                            "producers": list(info["producers"]),
                            "reason": "data structure populated but never consumed"
                        }
                    )

class CodeChangeHandler(FileSystemEventHandler):
    def __init__(self, daemon):
        self.daemon = daemon

    def on_modified(self, event):
        if event.src_path.endswith('.py'):
            self.daemon.on_file_changed(event.src_path)
```

**Systemd Service**:
```ini
[Unit]
Description=KLoROS Integration Monitor Daemon
After=network.target

[Service]
Type=simple
User=kloros
WorkingDirectory=/home/kloros/src
ExecStart=/home/kloros/.venv/bin/python3 -m kloros.monitors.integration_monitor_daemon
Restart=always
RestartSec=10s
MemoryMax=200M  # Index for all files
CPUQuota=15%

[Install]
WantedBy=multi-user.target
```

**Memory Profile**: ~150MB (AST index for ~500 files)
**CPU Profile**:
- Initial scan: 30% for 10 seconds
- Steady state: 2-5% (only reparse changed files)

---

### 3. chaos-monitor-daemon

**Purpose**: Watch chaos lab artifacts for healing failures

**Implementation**:
```python
#!/usr/bin/env python3
"""Chaos Monitor Daemon - Watches chaos lab results."""

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ChaosMonitorDaemon:
    def __init__(self):
        self.pub = ChemPub()
        self.history_file = Path("/home/kloros/.kloros/chaos_history.jsonl")
        self.last_position = 0

    def run(self):
        # Watch chaos_history.jsonl for new lines
        event_handler = ChaosHistoryHandler(self)
        observer = Observer()
        observer.schedule(
            event_handler,
            str(self.history_file.parent),
            recursive=False
        )
        observer.start()

        # Also poll every 60s in case inotify misses
        while True:
            self._check_new_entries()
            time.sleep(60)

    def _check_new_entries(self):
        """Read only NEW lines from chaos_history.jsonl."""
        if not self.history_file.exists():
            return

        with open(self.history_file) as f:
            # Seek to last position
            f.seek(self.last_position)

            # Read new lines only
            for line in f:
                try:
                    entry = json.loads(line)
                    self._process_chaos_entry(entry)
                except json.JSONDecodeError:
                    continue

            # Update position
            self.last_position = f.tell()

    def _process_chaos_entry(self, entry):
        """Process one chaos entry."""
        # Check if this is a healing failure
        if entry.get('healed') is False:
            scenario = entry['scenario']

            self.pub.emit(
                signal="CAPABILITY_GAP",
                ecosystem="self_healing",
                facts={
                    "gap_type": "healing_failure",
                    "gap_name": scenario,
                    "gap_category": "resilience",
                    "failure_count": entry.get('failure_count', 1),
                    "last_error": entry.get('error'),
                    "timestamp": entry.get('timestamp')
                }
            )
```

**Memory Profile**: ~20MB
**CPU Profile**: <5%

---

### 4. test-monitor-daemon

**Purpose**: Watch pytest result files for test failures

**Implementation**:
```python
#!/usr/bin/env python3
"""Test Monitor Daemon - Watches pytest results."""

class TestMonitorDaemon:
    def __init__(self):
        self.pub = ChemPub()
        self.results_dir = Path("/home/kloros/test-results")

    def run(self):
        # Watch test-results directory
        event_handler = TestResultHandler(self)
        observer = Observer()
        observer.schedule(event_handler, str(self.results_dir), recursive=True)
        observer.start()

        observer.join()

    def on_new_result(self, result_file):
        """Called when new pytest result appears."""
        with open(result_file) as f:
            result = json.load(f)

        # Emit signal for each failure
        for test in result.get('tests', []):
            if test['outcome'] == 'failed':
                self.pub.emit(
                    signal="CAPABILITY_GAP",
                    ecosystem="testing",
                    facts={
                        "gap_type": "test_failure",
                        "gap_name": test['nodeid'],
                        "gap_category": "quality",
                        "error": test.get('call', {}).get('longrepr'),
                        "duration": test.get('call', {}).get('duration')
                    }
                )
```

**Memory Profile**: ~15MB
**CPU Profile**: <5%

---

### 5. module-discovery-daemon

**Purpose**: Detect new modules in /src

**Implementation**:
```python
#!/usr/bin/env python3
"""Module Discovery Daemon - Watches for new Python modules."""

class ModuleDiscoveryDaemon:
    def __init__(self):
        self.pub = ChemPub()
        self.known_modules = set()

    def run(self):
        # Initial scan
        for py_file in Path("/home/kloros/src").rglob("*.py"):
            self.known_modules.add(str(py_file))

        # Watch for new files
        event_handler = NewModuleHandler(self)
        observer = Observer()
        observer.schedule(observer, "/home/kloros/src", recursive=True)
        observer.start()
        observer.join()

    def on_new_module(self, module_path):
        """Called when new .py file created."""
        if str(module_path) not in self.known_modules:
            self.known_modules.add(str(module_path))

            # Quick analysis: what does it do?
            capabilities = self._quick_scan(module_path)

            self.pub.emit(
                signal="CAPABILITY_GAP",
                ecosystem="discovery",
                facts={
                    "gap_type": "new_module",
                    "gap_name": module_path.stem,
                    "gap_category": "capability_expansion",
                    "file_path": str(module_path),
                    "capabilities": capabilities
                }
            )
```

**Memory Profile**: ~30MB
**CPU Profile**: <5%

---

### Remaining Daemons (Brief)

**6. capability-discovery-daemon**: Scans for missing tools/libraries
**7. exploration-daemon**: Monitors GPU/hardware availability
**8. metric-quality-daemon**: Meta-cognitive checks on investigation quality
**9. knowledge-discovery-daemon**: Watches for unindexed docs

Each follows same pattern:
- Singleton daemon
- inotify or streaming source
- Bounded memory
- Emits ChemBus signals
- Never polled

---

## Refactored CuriosityCore

**Before** (2000+ lines, does everything):
```python
def generate_questions_from_matrix(self, matrix):
    # Poll 9 different monitors synchronously
    # Create/destroy heavy objects
    # Scan filesystems
    # etc.
```

**After** (100 lines, pure signal consumer):
```python
class CuriosityCore:
    """
    Pure signal consumer - converts CAPABILITY_GAP signals to questions.

    NO POLLING. NO SCANNING. Just signal transformation.
    """

    def __init__(self, feed_path):
        self.feed_path = feed_path
        self.semantic_store = SemanticEvidenceStore()

    def create_question_from_gap(self, gap_signal):
        """
        Convert one CAPABILITY_GAP signal into a CuriosityQuestion.

        Args:
            gap_signal: ChemBus message with facts about capability gap

        Returns:
            CuriosityQuestion object
        """
        facts = gap_signal['facts']

        # Map gap type to question template
        if facts['gap_type'] == 'orphaned_queue':
            return self._question_for_orphaned_queue(facts)
        elif facts['gap_type'] == 'exception':
            return self._question_for_exception(facts)
        elif facts['gap_type'] == 'test_failure':
            return self._question_for_test_failure(facts)
        # ... etc for each gap type

    def _question_for_orphaned_queue(self, facts):
        """Create question for orphaned queue gap."""
        return CuriosityQuestion(
            id=f"orphaned_queue_{facts['gap_name']}",
            hypothesis=f"ORPHANED_QUEUE_{facts['gap_name'].upper()}",
            question=f"Data structure '{facts['gap_name']}' is populated by "
                    f"{', '.join(facts['producers'])} but never consumed. "
                    f"Is this a broken integration?",
            evidence=[
                f"Producers: {', '.join(facts['producers'])}",
                facts.get('reason', 'No consumers found')
            ],
            action_class=ActionClass.PROPOSE_FIX,
            autonomy=3,
            value_estimate=0.95,
            cost=0.2,
            capability_key=f"integration.{facts['gap_name']}"
        )

    # Similar methods for other gap types
```

**curiosity_core_consumer_daemon** stays almost the same, but now just:
1. Subscribes to CAPABILITY_GAP
2. Calls `curiosity_core.create_question_from_gap(msg)`
3. Emits to priority queue

---

## Migration Plan

### Phase 1: Stop the Bleeding (IMMEDIATE - 30 min)

1. **Disable heavy monitors temporarily**:
```python
# In curiosity_core.py, comment out:
# - IntegrationFlowMonitor
# - ModuleDiscoveryMonitor
# - CapabilityDiscoveryMonitor
# (Keep lightweight ones: ExceptionMonitor, ChaosLabMonitor)
```

2. **Fix chembus_history consolidation**:
```python
# In introspection_daemon.py, change to incremental:
def consolidate_chembus_history(self):
    # Only consolidate if file > 100MB
    if history_file.stat().st_size < 100_000_000:
        return

    # Process in 10MB chunks, not all at once
    # ... implement chunked processing
```

3. **Restart services**, verify memory stable

### Phase 2: Build Streaming Daemons (Week 1)

**Day 1-2**: Implement core monitor daemons
- exception-monitor-daemon
- chaos-monitor-daemon
- test-monitor-daemon

**Day 3-4**: Implement filesystem watchers
- integration-monitor-daemon
- module-discovery-daemon

**Day 5**: Refactor CuriosityCore to signal consumer

### Phase 3: Deploy & Validate (Week 2)

**Day 1**: Deploy to test environment
- Run old + new in parallel
- Compare signal outputs
- Validate question generation

**Day 2-3**: Fix issues, tune performance

**Day 4**: Deploy to production
- Switch curiosity-core to use new signals
- Disable old polling code
- Monitor memory/CPU

**Day 5**: Cleanup
- Remove old monitor code from curiosity_core.py
- Remove temporary compatibility layers
- Restore memory limits to 1G

---

## Success Metrics

### Before (Current):
- Memory: 200MB/min growth → OOM in 12 min
- CPU: 50% spikes every 60s
- Restarts: 11+ per day
- Latency: 60s worst-case for gap detection

### After (Target):
- Memory: Stable ~300MB total (all daemons)
- CPU: 15-20% steady state
- Restarts: 0 (except deployments)
- Latency: <5s real-time gap detection

---

## Code Organization

```
/home/kloros/src/kloros/monitors/
├── __init__.py
├── exception_monitor_daemon.py
├── chaos_monitor_daemon.py
├── test_monitor_daemon.py
├── integration_monitor_daemon.py
├── module_discovery_daemon.py
├── capability_discovery_daemon.py
├── exploration_daemon.py
├── metric_quality_daemon.py
└── knowledge_discovery_daemon.py

/etc/systemd/system/
├── kloros-exception-monitor.service
├── kloros-chaos-monitor.service
├── kloros-test-monitor.service
├── kloros-integration-monitor.service
├── kloros-module-discovery.service
├── kloros-capability-discovery.service
├── kloros-exploration.service
├── kloros-metric-quality.service
└── kloros-knowledge-discovery.service
```

---

## Appendix: ChemBus Signal Contract

### CAPABILITY_GAP Signal Schema

```json
{
  "signal": "CAPABILITY_GAP",
  "ecosystem": "string",  // "architecture", "diagnostics", "testing", etc.
  "ts": 1234567890.123,
  "facts": {
    "gap_type": "string",      // "orphaned_queue", "exception", "test_failure", etc.
    "gap_name": "string",      // Identifier for this gap
    "gap_category": "string",  // "integration", "error_handling", "quality", etc.
    "gap_reason": "string",    // Human-readable explanation

    // Type-specific fields:
    // For orphaned_queue:
    "producers": ["string"],

    // For exception:
    "unit": "string",
    "traceback": "string",

    // For test_failure:
    "error": "string",
    "duration": 1.23,

    // etc.
  }
}
```

All monitor daemons MUST emit this schema.
CuriosityCore MUST handle all gap_type values.

---

## Implementation Notes

1. **Deduplication**: Each daemon maintains LRU cache of recent signals to avoid spam
2. **Backpressure**: If ChemBus queue fills, daemons should drop oldest signals
3. **Health Checks**: Each daemon exposes `/health` endpoint for monitoring
4. **Graceful Shutdown**: All daemons handle SIGTERM properly
5. **Logging**: Structured JSON logs to journald for debugging

---

**This is how KLoROS was meant to work from the beginning.**

The architecture is clean, streaming, and resource-efficient. Let's build it.
