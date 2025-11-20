# KLoROS Observer

**Streaming event collection and intent generation for KLoROS**

The Observer is the reactive, continuous component that watches the system in real-time and proposes actions to the Orchestrator.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        OBSERVER                              │
│  (Streaming, Reactive, Proposes)                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  journald    │  │   inotify    │  │   metrics    │     │
│  │   Source     │  │    Source    │  │   Source     │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         │                  │                  │              │
│         └──────────────────┴──────────────────┘              │
│                            │                                 │
│                    ┌───────▼────────┐                       │
│                    │  RuleEngine    │                       │
│                    │  (Process &    │                       │
│                    │   Classify)    │                       │
│                    └───────┬────────┘                       │
│                            │                                 │
│                    ┌───────▼────────┐                       │
│                    │ IntentEmitter  │                       │
│                    │ (Atomic Write) │                       │
│                    └───────┬────────┘                       │
│                            │                                 │
└────────────────────────────┼─────────────────────────────────┘
                             │
                             ▼
                   ~/.kloros/intents/
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                     ORCHESTRATOR                             │
│  (Discrete, Authoritative, Executes)                        │
│  • Consumes intents                                         │
│  • Schedules PHASE/D-REAM                                   │
│  • Enforces safety (locks, windows, atomicity)              │
└─────────────────────────────────────────────────────────────┘
```

## Design Principles

**Two halves, one loop:**

1. **Observer (new)** — Streaming, continuous
   - Tails logs via `journalctl -f`
   - Watches files via `inotify`
   - Scrapes metrics periodically
   - Turns raw signals into intents and suggestions

2. **Orchestrator (existing)** — Discrete, authoritative
   - Consumes intents from `~/.kloros/intents/`
   - Schedules PHASE/D-REAM safely
   - Enforces locks, windows, atomic writes
   - **Only component that executes actions**

**Safety model:** Observer proposes, Orchestrator disposes.

## Components

### Event Sources (`sources.py`)

Streaming event collection from multiple sources:

#### JournaldSource
- Streams systemd journal logs in real-time
- Watches specified units (dream.service, kloros.service)
- Classifies messages into event types
- Events: `dream_promotion`, `phase_complete`, `gpu_oom`, etc.

#### InotifySource
- Watches filesystem paths for changes
- Uses `watchdog` library for inotify support
- Detects file creation/modification
- Events: `promotion_new`, `phase_signal`, `dream_heartbeat`

#### MetricsSource
- Scrapes Prometheus metrics periodically
- Checks thresholds on key metrics
- Events: `lock_contention_high`, `phase_duration_high`

All sources yield normalized `Event` objects:
```python
@dataclass
class Event:
    source: str      # "journald", "inotify", "metrics"
    type: str        # "promotion_new", "phase_complete", etc.
    ts: float        # timestamp
    data: Dict[str, Any]  # source-specific payload
```

### Rule Engine (`rules.py`)

Processes events and generates intents based on configurable rules:

#### Implemented Rules

1. **Promotion Cluster** (≥3 promotions in 10 minutes)
   - Triggers: `trigger_phase_promotion_cluster`
   - Priority: 7
   - Rationale: Multiple promotions indicate convergence on good candidates

2. **PHASE Failure** (test failure or timeout)
   - Triggers: `suggest_phase_diagnostic`
   - Priority: 6
   - Provides diagnostic suggestions

3. **Heartbeat Stall** (no D-REAM heartbeat in 5 minutes)
   - Triggers: `alert_heartbeat_stall`
   - Priority: 8
   - Indicates D-REAM service may be hung

4. **Lock Contention** (>10 contentions)
   - Triggers: `suggest_lock_optimization`
   - Priority: 5
   - May need to adjust orchestrator tick rate

5. **GPU OOM** (out of memory)
   - Triggers: `alert_gpu_oom`
   - Priority: 9
   - Suggests resource adjustments

6. **PHASE Duration** (>2 hours)
   - Triggers: `suggest_phase_optimization`
   - Priority: 6
   - Test selection or hanging tests

7. **D-REAM Error** (experiment failure)
   - Triggers: `suggest_dream_diagnostic`
   - Priority: 5
   - Check logs and experiment configs

#### Intent Types

- `trigger_phase_*` - Request PHASE run
- `suggest_*` - Suggest diagnostic or optimization
- `alert_*` - High-priority alert requiring attention

#### Rate Limiting

- Events deduplicated using `hash_key()` (60s window)
- Intents have cooldowns per type (e.g., 1 hour for promotion clusters)
- Prevents intent flooding

### Intent Emitter (`emit.py`)

Atomic intent writing with integrity checks:

```python
intent = Intent(
    intent_type="trigger_phase_promotion_cluster",
    priority=7,
    reason="Promotion cluster detected: 3 promotions in 10 minutes",
    data={"promotion_count": 3}
)

emitter.emit(intent)
```

**File format:**
- Filename: `{timestamp_ms}_{intent_type}_{hash}.json`
- Location: `~/.kloros/intents/`
- Atomic write: tmp file + fsync + rename
- SHA256 checksum for integrity

**Features:**
- Deduplication (1 hour window)
- Automatic pruning (>24 hours old)
- Checksum verification
- Atomic operations

### Observer Main Loop (`run.py`)

Coordinates all components:

```python
observer = Observer(
    journald_units=["dream.service", "kloros.service"],
    watch_paths=[Path("~/out/promotions"), Path("~/.kloros/signals")],
    metrics_endpoint="http://localhost:9090/metrics",
    metrics_interval_s=30
)

observer.run()  # Runs until SIGINT/SIGTERM
```

**Threading model:**
- Thread 1: JournaldSource streaming
- Thread 2: InotifySource watching
- Thread 3: MetricsSource scraping
- Thread 4: Housekeeping (prune old files, log stats)

**Graceful shutdown:**
- Handles SIGINT/SIGTERM
- Prints statistics on exit

## Installation & Deployment

### Dependencies

```bash
pip install watchdog requests
```

### Systemd Service

Service installed at: `/etc/systemd/system/kloros-observer.service`

```bash
# Start observer
sudo systemctl start kloros-observer.service

# Check status
sudo systemctl status kloros-observer.service

# View logs
sudo journalctl -u kloros-observer.service -f

# Stop observer
sudo systemctl stop kloros-observer.service
```

**Service details:**
- Runs as `kloros` user
- Restarts automatically on failure (RestartSec=10s)
- Resource limits: 512M memory, 50% CPU, 64 tasks
- Writes to systemd journal

### CLI Usage

```bash
# Run directly (foreground)
python3 -m src.kloros.observer.run --log-level INFO

# Enable event spooling (debug mode)
python3 -m src.kloros.observer.run --spool-events

# Custom metrics endpoint
python3 -m src.kloros.observer.run --metrics-endpoint http://localhost:8080/metrics
```

### Environment Variables

- `KLR_OBSERVER_SPOOL_EVENTS=1` - Enable raw event spooling to `~/.kloros/events/`

## Testing

Run component tests:

```bash
python3 /home/kloros/tmp/test_observer.py
```

Tests verify:
- Event creation and hashing
- Rule engine processing (promotion cluster)
- Intent emission and verification
- Observer instantiation

## Monitoring

### Statistics

Observer logs statistics every 10 minutes:
```
Observer stats: uptime=2.5h, events=1247, intents=3
```

### Intent Queue

Check pending intents:
```bash
ls -lh ~/.kloros/intents/
```

Verify intent integrity:
```python
from src.kloros.observer.emit import IntentEmitter
emitter = IntentEmitter()
emitter.verify_intent(Path("~/.kloros/intents/1234567890_test.json"))
```

### Event Spooling

Enable for debugging:
```bash
export KLR_OBSERVER_SPOOL_EVENTS=1
```

Raw events written to `~/.kloros/events/`:
- Format: `{timestamp_ms}_{source}_{type}.json`
- Auto-pruned after 7 days

## Integration with Orchestrator

The Orchestrator should:

1. **Poll intent directory** periodically (e.g., every 60s tick)
2. **Read and validate** intent files (check SHA256)
3. **Process intents** based on type and priority
4. **Execute actions** safely (locks, windows, atomicity)
5. **Archive/delete** processed intents

Example orchestrator integration:

```python
from pathlib import Path
from src.kloros.observer.emit import IntentEmitter

emitter = IntentEmitter()

# In orchestrator tick
for intent_file in emitter.list_pending():
    if not emitter.verify_intent(intent_file):
        logger.error(f"Invalid intent: {intent_file}")
        continue

    # Load intent
    with open(intent_file) as f:
        intent_data = json.load(f)

    # Process based on type
    if intent_data["intent_type"] == "trigger_phase_promotion_cluster":
        orchestrator.schedule_phase(priority=intent_data["priority"])
    elif intent_data["intent_type"].startswith("suggest_"):
        orchestrator.log_suggestion(intent_data)
    elif intent_data["intent_type"].startswith("alert_"):
        orchestrator.send_alert(intent_data)

    # Archive processed intent
    intent_file.unlink()
```

## Future Enhancements (Phase S2)

### systemd.path Wake-ups

Instead of orchestrator polling every 60s, use systemd path units for instant wake-ups:

```ini
# /etc/systemd/system/kloros-intent.path
[Path]
PathChanged=/home/kloros/.kloros/intents
Unit=kloros-orchestrator.service

[Install]
WantedBy=multi-user.target
```

This enables:
- Zero-latency intent processing
- Reduced CPU usage (no polling)
- Event-driven architecture

### Additional Rules

Ideas for future rules:
- **Disk space** - Alert when /home/kloros usage >80%
- **Test flakes** - Detect flaky tests from PHASE results
- **Memory pressure** - Monitor swap usage
- **Service restarts** - Track service restart frequency
- **Promotion velocity** - Rate of promotions over time

### Advanced Features

- **Dynamic rule loading** - Hot-reload rules without restart
- **Prometheus integration** - Export observer metrics
- **Web dashboard** - Real-time event visualization
- **Intent replay** - Archive and replay historical intents
- **Rule tuning** - Machine learning for threshold optimization

## Troubleshooting

### Observer not starting

```bash
# Check service status
sudo systemctl status kloros-observer.service

# View logs
sudo journalctl -u kloros-observer.service --no-pager -n 50
```

### No intents generated

- Verify event sources are working (check logs)
- Ensure watched paths exist (`~/out/promotions`, `~/.kloros/signals`)
- Check rule thresholds (may need more events)

### High CPU usage

- Reduce metrics scraping frequency (`--metrics-interval 60`)
- Check for journald spam (may need filtering)
- Verify no infinite loops in rule processing

### Metrics scrape errors

If Prometheus not available:
```
WARNING: Metrics scrape error: Connection refused
```

This is non-fatal. MetricsSource will continue trying every interval.

## Implementation Status

✅ **Phase S0 - Scaffolding**
- Event sources (journald, inotify, metrics)
- Rule engine with rate limiting
- Intent emitter with atomic writes
- Main observer loop with threading

✅ **Phase S1 - First Rules**
- Promotion cluster detection
- PHASE failure diagnostics
- Heartbeat stall monitoring
- Lock contention alerts
- GPU OOM alerts
- PHASE duration warnings
- D-REAM error diagnostics

✅ **Phase S2 - Deployment**
- Systemd service integration
- Component testing
- Documentation

⏳ **Phase S3 - Orchestrator Integration** (pending)
- Intent consumption in orchestrator
- Action execution based on intents
- Intent archival and cleanup

⏳ **Phase S4 - Advanced Features** (future)
- systemd.path wake-ups
- Dynamic rule loading
- Prometheus metrics export
- Web dashboard

## References

- Architecture discussion: `/home/kloros/docs/SYSTEM_ARCHITECTURE_OVERVIEW.md`
- Orchestrator implementation: `/home/kloros/src/kloros/orchestration/`
- Test logs: `/home/kloros/logs/spica-phase-test.log`
- PHASE heuristics: `/home/kloros/out/heuristics/summary.json`

## Contributing

When adding new rules:

1. Define rule logic in `rules.py` (`_rule_*` method)
2. Add to rules list in `RuleEngine.process()`
3. Define intent type and priority
4. Document rationale and threshold
5. Add test case in `/home/kloros/tmp/test_observer.py`
6. Update this README

Rule guidelines:
- **Priority 0-4**: Informational suggestions
- **Priority 5-7**: Actionable recommendations
- **Priority 8-10**: Critical alerts requiring immediate attention

---

**Implementation Date:** 2025-10-29
**Author:** Claude (via KLoROS introspection)
**Version:** 0.1.0
