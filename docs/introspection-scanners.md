# Introspection Scanners

## Overview

Five capability scanners that monitor KLoROS's internal inference and resource usage patterns, feeding insights into the observation/curiosity system for autonomous self-optimization.

## Scanners

### 1. InferencePerformanceScanner

**Purpose:** Monitors token generation performance

**Metrics:**
- Tokens/second by task type
- Probability distribution entropy
- Backtracking frequency

**Triggers When:**
- Token generation < 10 tokens/sec (slow threshold)
- Performance variance > 30% (unstable)

**Outputs:**
- `performance_optimization` capability gaps
- Feeds curiosity system with optimization questions

**Schedule:** Every ~1.7 hours (schedule_weight: 0.6)

---

### 2. ContextUtilizationScanner

**Purpose:** Monitors which portions of context windows get referenced

**Metrics:**
- Context reference patterns
- Unused context tail detection
- Recency bias detection

**Triggers When:**
- Last 30%+ of context never referenced
- >80% of references in last 20% of context (recency bias)

**Outputs:**
- `context_optimization` capability gaps
- Context windowing recommendations

**Schedule:** Every 2 hours (schedule_weight: 0.5)

---

### 3. ResourceProfilerScanner

**Purpose:** Monitors CPU/GPU/RAM usage per operation

**Metrics:**
- GPU utilization per operation
- CPU utilization and bottlenecks
- Memory consumption patterns

**Triggers When:**
- GPU utilization < 50% (underutilized)
- CPU utilization > 90% (bottlenecked)

**Outputs:**
- `resource_optimization` capability gaps
- Batching/allocation recommendations

**Schedule:** Every ~1.7 hours (schedule_weight: 0.6)

**Special:** Gracefully degrades to CPU-only monitoring if no GPU

---

### 4. BottleneckDetectorScanner

**Purpose:** Monitors queue depths and slow operations

**Metrics:**
- Queue depth trends
- Queue growth rates
- Operation duration patterns

**Triggers When:**
- Queue depth sustained > 100
- Queue growing 2x+ (exponential growth)
- Operations averaging > 200ms

**Outputs:**
- `bottleneck` capability gaps
- Worker scaling recommendations

**Schedule:** Every ~1.4 hours (schedule_weight: 0.7)

---

### 5. ComparativeAnalyzerScanner

**Purpose:** Compares strategy and variant performance

**Metrics:**
- Brainmod success rates
- Zooid variant TTR comparisons
- Strategy effectiveness

**Triggers When:**
- Strategy performance gap > 15%
- Success rate difference > 20%
- Min 10 samples per strategy required

**Outputs:**
- `strategy_optimization` capability gaps
- Default strategy recommendations

**Schedule:** Every 2 hours (schedule_weight: 0.5)

---

## Architecture Integration

### Data Flow

```
1. Scanner runs on schedule (CapabilityDiscoveryMonitor)
2. Scans metrics files in ~/.kloros/
3. Detects optimization opportunities
4. Emits CapabilityGaps
5. CuriosityCore generates questions from gaps
6. curiosity_processor routes to experiments
7. D-REAM/SPICA run optimization experiments
8. Results feed back to fitness ledger
```

### Failure Handling

All scanners inherit quarantine infrastructure:
- 3 failures → quarantine (exponential backoff)
- Failed scanner becomes curiosity question
- System investigates scanner itself
- Graceful degradation (continues without scanner)

### Metrics Files

Scanners read from:
- `/home/kloros/.kloros/inference_metrics.jsonl` - Token performance
- `/home/kloros/.kloros/context_utilization.jsonl` - Context usage
- `/home/kloros/.kloros/resource_metrics.jsonl` - CPU/GPU/RAM
- `/home/kloros/.kloros/queue_metrics.jsonl` - Queue depths
- `/home/kloros/.kloros/operation_metrics.jsonl` - Operation timings
- `/home/kloros/.kloros/lineage/fitness_ledger.jsonl` - Strategy fitness

**Note:** Metrics files are created by zooids/modules during normal operation. If files don't exist, scanners return empty (no crash).

---

## Configuration

### Thresholds

Edit scanner source files to tune:

**InferencePerformanceScanner:**
- `SLOW_TOKENS_PER_SEC = 10.0`
- `SIGNIFICANT_VARIANCE = 0.3`

**ContextUtilizationScanner:**
- `UNUSED_TAIL_THRESHOLD = 0.7`
- `RECENCY_BIAS_THRESHOLD = 0.2`

**ResourceProfilerScanner:**
- `LOW_GPU_UTIL_THRESHOLD = 50.0`
- `HIGH_CPU_UTIL_THRESHOLD = 90.0`

**BottleneckDetectorScanner:**
- `QUEUE_GROWTH_THRESHOLD = 2.0`
- `QUEUE_SUSTAINED_THRESHOLD = 100`
- `SLOW_OPERATION_MS = 200`

**ComparativeAnalyzerScanner:**
- `MIN_SAMPLES_PER_STRATEGY = 10`
- `SIGNIFICANT_PERFORMANCE_GAP = 0.15`
- `SIGNIFICANT_SUCCESS_GAP = 0.20`

### Scan Frequency

Edit `schedule_weight` in `get_metadata()`:
- `1.0` = every hour
- `0.5` = every 2 hours
- `0.25` = every 4 hours

---

## Testing

### Unit Tests

```bash
# Test individual scanners
pytest tests/registry/capability_scanners/test_inference_performance_scanner.py -v
pytest tests/registry/capability_scanners/test_context_utilization_scanner.py -v
pytest tests/registry/capability_scanners/test_resource_profiler_scanner.py -v
pytest tests/registry/capability_scanners/test_bottleneck_detector_scanner.py -v
pytest tests/registry/capability_scanners/test_comparative_analyzer_scanner.py -v
```

### Integration Tests

```bash
# Test auto-discovery and monitor integration
pytest tests/registry/test_introspection_scanners_integration.py -v
```

---

## Monitoring Scanner Health

Check scanner state:

```bash
cat ~/.kloros/scanner_state.json | jq '.InferencePerformanceScanner'
```

View recent gaps:

```bash
tail ~/.kloros/curiosity_feed.json | jq 'select(.category | contains("introspection"))'
```

---

## Future Enhancements

1. **Metrics Collection Automation**
   - Add instrumentation to zooids to auto-emit metrics
   - Currently relies on manual metric logging

2. **Adaptive Thresholds**
   - Learn thresholds from historical data
   - Currently uses static thresholds

3. **Cross-Scanner Correlation**
   - Detect relationships between metrics
   - E.g., "slow inference when GPU util low"

4. **Real-Time Alerts**
   - Emit observations for critical bottlenecks
   - Currently only generates capability gaps

---

## Troubleshooting

**Scanner not running:**
- Check `scanner_state.json` for quarantine status
- Verify metrics files exist (scanners gracefully skip if missing)
- Check logs: `grep "inference_perf" ~/.kloros/logs/*.log`

**No gaps generated:**
- Verify metrics files have recent data (7-day window)
- Check thresholds aren't too strict
- Ensure MIN_SAMPLES requirements met

**High scan cost:**
- Reduce `schedule_weight` to run less frequently
- Check metrics file sizes (large files slow parsing)

---

## Streaming Architecture (Production)

### Overview

The introspection scanners run in streaming mode for production deployment:

```
ChemBus OBSERVATION → IntrospectionDaemon → [5 Scanners] → CAPABILITY_GAP → CuriosityCore
                            ↓
                      ObservationCache
                      (5min rolling window)
```

### Components

**IntrospectionDaemon** (`src/kloros/introspection/introspection_daemon.py`)
- Single process subscribing to ChemBus OBSERVATION topic
- Maintains shared ObservationCache (5min rolling window)
- Runs 5 scanners in thread pool executor
- Micro-batch analysis every 5 seconds
- Timeout protection (30s per scanner)
- Immediate CapabilityGap emission

**ObservationCache** (`src/kloros/introspection/observation_cache.py`)
- Thread-safe rolling window cache
- Automatic pruning of stale observations
- Custom time window queries
- Memory-bounded (10,000 observations max)

### Resource Efficiency

**vs File-Based Approach:**
- ⚡ **Latency**: 5s vs 30min (360x faster)
- 💾 **I/O**: Zero disk reads vs constant file polling
- 🔌 **Connections**: 1 ZMQ socket vs 5
- 🧵 **Processes**: 1 vs 5
- 💰 **Memory**: Shared cache vs 5 independent caches

### Deployment

**Installation:**
```bash
# Install systemd service
./scripts/install_introspection_daemon.sh

# Start daemon
sudo systemctl start kloros-introspection

# Check status
sudo systemctl status kloros-introspection

# View logs
journalctl -u kloros-introspection -f
```

**Configuration:**

Environment variables in `/etc/systemd/system/kloros-introspection.service`:
- `KLR_CHEM_XSUB`: ChemBus XSUB endpoint (default: tcp://127.0.0.1:5556)
- `KLR_CHEM_XPUB`: ChemBus XPUB endpoint (default: tcp://127.0.0.1:5557)

**Health Monitoring:**
```bash
# Check scan count
journalctl -u kloros-introspection | grep "Scan cycle"

# Check gap emission
journalctl -u kloros-introspection | grep "Emitted gap"

# Check cache size
journalctl -u kloros-introspection | grep "cache_size"
```

### Failure Isolation

Each scanner runs with:
- **Timeout protection**: 30s max execution time
- **Exception isolation**: Scanner crash doesn't affect others
- **Graceful degradation**: Failed scans logged, daemon continues

Scanner failures automatically emit OBSERVATION events that trigger quarantine investigation.

### Migration from File-Based

Scanners support both modes for backwards compatibility:

```python
# Legacy file-based mode
scanner = InferencePerformanceScanner(
    metrics_path=Path("/home/kloros/.kloros/metrics/inference_metrics.jsonl")
)

# Streaming mode (production)
scanner = InferencePerformanceScanner(
    cache=observation_cache
)
```

The daemon automatically uses streaming mode. File-based mode remains available for testing and development.
