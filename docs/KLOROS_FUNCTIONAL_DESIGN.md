# KLoROS Functional Design Document

**Version**: 2.0  
**Date**: 2025-11-07  
**Status**: Production  
**Last Major Update**: D-REAM Autonomous Evolution (Nov 7, 2025)

---

## 1. System Overview

### 1.1 Mission Statement

KLoROS is an autonomous AI assistant with self-improvement capabilities through Darwinian evolution. The system learns from experience, evolves specialized components (zooids) to handle operational niches, and continuously optimizes performance without human intervention.

### 1.2 Core Capabilities

1. **Voice Interaction** - Natural language conversation via microphone/speakers
2. **Autonomous Evolution** - Self-modification through D-REAM genetic algorithms
3. **Adaptive Learning** - Memory systems with episodic recall and semantic understanding
4. **Fitness-Based Selection** - PHASE testing infrastructure for objective performance measurement
5. **Multi-Model LLM** - Specialized models for different reasoning tasks
6. **Self-Awareness** - Introspection tools and consciousness modeling

---

## 2. Architecture

### 2.1 System Layers

```
┌──────────────────────────────────────────────────────────────┐
│                    USER INTERACTION LAYER                     │
├──────────────────────────────────────────────────────────────┤
│  Voice I/O │ Text I/O │ Visual (planned) │ Physical (planned)│
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│                   COGNITIVE PROCESSING LAYER                  │
├──────────────────────────────────────────────────────────────┤
│  LLM Inference │ Memory │ Reasoning │ Tool Synthesis │ RAG   │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│                  AUTONOMOUS EVOLUTION LAYER                   │
├──────────────────────────────────────────────────────────────┤
│         D-REAM Engine │ PHASE Testing │ Lifecycle Mgmt       │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│                     INFRASTRUCTURE LAYER                      │
├──────────────────────────────────────────────────────────────┤
│  Systemd Services │ File Storage │ GPU Management │ Network  │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Component Map

**ASTRAEA** (Autopoietic Spatial-Temporal Reasoning Architecture)
- Voice pipeline: STT (Whisper), TTS (XTTS2), VAD
- LLM routing: qwen2.5 (live), deepseek-r1 (think), qwen-coder (code)
- Memory: Episodic-semantic dual system with idle reflection
- Consciousness: Affective core with fatigue modeling

**D-REAM** (Darwinian-RZero Evolution & Anti-collapse Module)
- Genome engine: Niche-specific mutation operators
- Spawner: Template-based code generation with SHA256 hashing
- Selector: Niche pressure + novelty scoring
- Lifecycle: DORMANT → PROBATION → ACTIVE → RETIRED

**PHASE** (Phased Heuristic Adaptive Scheduling Engine)
- Consumer daemon: Queue-based workload executor
- Workload drivers: Synthetic traffic generators
- Fitness calculator: Composite performance scoring
- Sandbox: Subprocess isolation with timeouts

**SPICA** (Self-Progressive Intelligent Cognitive Archetype)
- Template LLM design pattern
- Migration 60% complete
- Future: Type hierarchy and CI gates

---

## 3. D-REAM Functional Specification

### 3.1 Evolution Cycle

**Objective**: Continuous improvement of operational components through natural selection

**Cycle Frequency**:
- Spawn: Hourly (via klr-dream-spawn.timer)
- Select: Daily at 02:55 UTC (via klr-phase-enqueue.timer)
- Graduate: Daily at 00:15 UTC (via klr-lifecycle-cycle.timer)

**Inputs**:
- Niche definitions (5 niches in queue_management ecosystem)
- Policy parameters (lifecycle_policy.json)
- Parent genomes (for lineage tracking)

**Outputs**:
- New zooid variants (Python modules)
- Fitness measurements (phase_fitness.jsonl)
- Population updates (niche_map.json)

### 3.2 Genetic Operators

**Mutation (genomes.py)**:
```python
def mutate_params(niche: str) -> dict:
    """Generate phenotype parameters for a variant."""
    # Base parameters (all niches)
    params = {
        "poll_interval_sec": random.uniform(0.5, 5.0),
        "batch_size": random.choice([10, 20, 50, 100]),
        "timeout_sec": random.choice([5, 10, 30, 60]),
        "log_level": random.choice(["INFO", "DEBUG", "WARNING"])
    }
    
    # Niche-specific parameters
    if niche == "latency_monitoring":
        params.update({
            "p95_threshold_ms": random.choice([100, 200, 500, 1000]),
            "window_size": random.choice([20, 50, 100]),
            "alert_percentile": random.choice([90, 95, 99])
        })
    # ... other niches
    
    return params
```

**Selection (batch_selector.py)**:
```python
def score_candidate(reg: dict, zooid: dict, niche: str) -> float:
    """Score DORMANT zooid for PROBATION promotion."""
    pressure = 1.0 / (1 + len(reg['niches'][niche]['active']))
    novelty = _novelty_score(zooid['phenotype'])
    return 0.7 * pressure + 0.3 * novelty
```

**Fitness (queue_latency.py)**:
```python
def calculate_fitness(p95_ms: float, error_rate: float, throughput_qps: float) -> float:
    """Composite fitness from test metrics."""
    latency_score = 1.0 - min(1.0, p95_ms / 1000.0)
    reliability_score = 1.0 - error_rate
    throughput_score = min(1.0, throughput_qps / 100.0)
    return latency_score * reliability_score * throughput_score
```

### 3.3 Lifecycle States

```
DORMANT → PROBATION → ACTIVE → RETIRED
   ↑          ↓          ↓         ↑
   └──────────┴──────────┴─────────┘
     (spawn)  (phase)  (prod)  (demote)
```

**DORMANT**:
- Freshly spawned, untested
- Awaits selection
- No resource allocation

**PROBATION**:
- Selected for testing
- PHASE workload execution
- Fitness measurement
- Gate: composite_phase_fitness ≥ 0.70

**ACTIVE**:
- Deployed to production
- Systemd service running
- Continuous monitoring
- Production fitness tracked
- Gate: ok_rate ≥ 0.95 over 20 samples

**RETIRED**:
- Demoted from ACTIVE
- Failed production fitness
- Historical record maintained

### 3.4 Template System

**Location**: `/home/kloros/src/zooids/templates/{niche}/base.py.j2`

**Rendering**:
```python
def render_template(niche: str, params: dict) -> str:
    """Render Jinja2 template with phenotype parameters."""
    template = Path(f"templates/{niche}/base.py.j2").read_text()
    for key, value in params.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template
```

**Genome Hashing**:
```python
def genome_hash(code: str, phenotype: dict) -> str:
    """SHA256 hash of code + phenotype for deduplication."""
    combined = code + json.dumps(phenotype, sort_keys=True)
    return "sha256:" + hashlib.sha256(combined.encode()).hexdigest()
```

### 3.5 PHASE Testing

**Workload Profile**: QMG-100h-full-traffic-v3

**Test Execution**:
1. Consumer daemon tails phase_queue.jsonl
2. Reads batch entry: {batch_id, niche, candidates, duration_sec, workload_profile}
3. For each candidate:
   - Spawns subprocess with workload driver
   - Injects PYTHONPATH environment
   - Enforces timeout (30s)
   - Captures stdout (JSON metrics)
4. Writes fitness to phase_fitness.jsonl

**Metrics Collected**:
- p95_ms: 95th percentile latency (milliseconds)
- error_rate: Fraction of failed requests (0.0-1.0)
- throughput_qps: Queries per second
- composite: Calculated fitness score (0.0-1.0)

**Sandbox Configuration**:
- Python interpreter: /usr/bin/python3
- Timeout: 30 seconds
- Environment: PYTHONPATH=/home/kloros/src
- Isolation: subprocess.run() with timeout

---

## 4. Data Models

### 4.1 Zooid Structure

```json
{
  "name": "latency_monitoring_1762556418_0",
  "ecosystem": "queue_management",
  "niche": "latency_monitoring",
  "lifecycle_state": "DORMANT",
  "genome_hash": "sha256:00fb3299b6b1a569389c5a1b49602c906f4f5237045bce147b533fa3ac5d67a7",
  "parent_lineage": [],
  "created_ts": 1762556418.037049,
  "promoted_to_probation_ts": null,
  "promoted_to_active_ts": null,
  "retired_ts": null,
  "phase_fitness": null,
  "phase_evidence": 0,
  "prod_ok_rate": 0.0,
  "prod_ok_rate_window": [],
  "prod_evidence": 0,
  "quarantine_ts": null,
  "quarantine_count": 0,
  "last_failure_ts": null,
  "demotion_count": 0,
  "probation_retry_count": 0,
  "last_probation_exit_ts": null,
  "metadata": {},
  "phenotype": {
    "poll_interval_sec": 3.78,
    "batch_size": 100,
    "timeout_sec": 10,
    "log_level": "INFO",
    "p95_threshold_ms": 200,
    "window_size": 100,
    "alert_percentile": 90
  }
}
```

### 4.2 Registry Structure

```json
{
  "version": 47,
  "last_updated": 1762556418.038645,
  "zooids": {
    "latency_monitoring_1762556418_0": { /* zooid object */ }
  },
  "niches": {
    "latency_monitoring": {
      "ecosystem": "queue_management",
      "dormant": ["latency_monitoring_1762556418_0", "..."],
      "probation": ["latency_monitoring_1762555436_0", "..."],
      "active": [],
      "retired": []
    }
  },
  "genomes": {
    "sha256:00fb...": "latency_monitoring_1762556418_0"
  },
  "ecosystems": {
    "queue_management": {
      "niches": ["latency_monitoring", "flow_regulation", "..."]
    }
  }
}
```

### 4.3 Journal Entries

**dream_spawn.jsonl**:
```json
{
  "ts": 1762556418.037049,
  "event": "dream_spawn",
  "zooid": "latency_monitoring_1762556418_0",
  "niche": "latency_monitoring",
  "ecosystem": "queue_management",
  "genome_hash": "sha256:00fb...",
  "phenotype": { /* params */ }
}
```

**phase_fitness.jsonl**:
```json
{
  "ts": 1762556219.9225252,
  "batch_id": "2025-11-07T17:48Z-QUICK",
  "niche": "latency_monitoring",
  "candidate": "latency_monitoring_1762555436_2",
  "composite_phase_fitness": 0.103,
  "workload_profile_id": "QMG-100h-full-traffic-v3",
  "p95_ms": 0.0,
  "error_rate": 0.0,
  "throughput_qps": 10.3
}
```

---

## 5. User Interface

### 5.1 Voice Interaction

**Wake Word**: "KLoROS"
**STT Engine**: Whisper (tiny model for low latency)
**TTS Engine**: XTTS2 (voice cloning)
**VAD**: WebRTC Voice Activity Detection

**Conversation Flow**:
```
User speaks → VAD detects → STT transcribes → LLM processes → TTS responds
```

### 5.2 Text Interaction

**Claude Code Integration**: Full conversational interface via Claude Code CLI

### 5.3 Monitoring

**Commands**:
- `systemctl status kloros.service` - Voice assistant status
- `systemctl list-timers 'klr-*'` - Evolution cycle timers
- `journalctl -u klr-dream-spawn.service` - Spawn logs
- `tail -f ~/.kloros/lineage/*.jsonl` - Real-time journals
- Python scripts for registry queries

**Dashboards**: (Planned)
- Fitness over time
- Population demographics
- Niche occupancy
- Generational analysis

---

## 6. Configuration

### 6.1 Lifecycle Policy

**File**: `~/.kloros/config/lifecycle_policy.json`

**Key Parameters**:
- `spawn_candidates_per_tick: 3` - Variants per niche per spawn
- `spawn_min_active_per_niche: 2` - Minimum active zooids before spawning
- `spawn_max_dormant_per_niche: 12` - Maximum dormant population
- `phase_batch_size_per_niche: 6` - Candidates selected for PHASE testing
- `phase_threshold: 0.70` - Minimum fitness for PROBATION → ACTIVE
- `prod_ok_threshold: 0.95` - Minimum production ok_rate
- `prod_ok_window_n: 20` - Sample size for production fitness

### 6.2 Environment Variables

**File**: `/home/kloros/.kloros_env`

**D-REAM Relevant**:
- GPU assignment (CUDA_VISIBLE_DEVICES)
- Python path (PYTHONPATH=/home/kloros/src)
- Model paths

---

## 7. Operational Procedures

### 7.1 Manual Spawn

```bash
/home/kloros/bin/klr_dream_spawn_once
```

**Output**: List of spawned zooid names

### 7.2 Manual Selection

```bash
/home/kloros/bin/klr_phase_enqueue_once
```

**Output**: List of batches enqueued for PHASE testing

### 7.3 Monitoring Registry

```bash
python3 <<'EOF'
import json
reg = json.load(open("/home/kloros/.kloros/registry/niche_map.json"))
print(f"Version: {reg['version']}")
for state in ['DORMANT', 'PROBATION', 'ACTIVE', 'RETIRED']:
    count = sum(1 for z in reg['zooids'].values() if z['lifecycle_state'] == state)
    print(f"{state}: {count}")
EOF
```

### 7.4 Analyzing Fitness

```bash
grep "BATCH_ID" ~/.kloros/lineage/phase_fitness.jsonl | \
  python3 -c "import sys, json, statistics
results = [json.loads(line) for line in sys.stdin]
fitness = [r['composite_phase_fitness'] for r in results]
print(f'Tests: {len(results)}')
print(f'Mean: {statistics.mean(fitness):.3f}')
print(f'Median: {statistics.median(fitness):.3f}')
print(f'Min: {min(fitness):.3f}, Max: {max(fitness):.3f}')"
```

---

## 8. Failure Modes & Recovery

### 8.1 Consumer Daemon Crash

**Detection**: `systemctl status klr-phase-consumer.service` shows inactive
**Recovery**: Automatic via Restart=always in systemd unit
**Impact**: Delayed PHASE testing (queue accumulates)
**Mitigation**: Timer persistence ensures catch-up

### 8.2 Registry Corruption

**Detection**: JSON parse errors, invalid version numbers
**Recovery**: Manual restore from latest `.bak` snapshot
**Impact**: Loss of recent population changes
**Mitigation**: Frequent backups (future automation)

### 8.3 Spawn Failure

**Detection**: Timer execution fails, no new variants
**Recovery**: Manual spawn via bin script
**Impact**: Reduced genetic diversity
**Mitigation**: Timer retries (Persistent=true)

### 8.4 PHASE Test Timeout

**Detection**: Candidate fitness = 0.0 with "timeout" error
**Recovery**: Re-enqueue failed candidates (future enhancement)
**Impact**: Underestimated fitness, potential false negatives
**Mitigation**: Configured timeout > test duration

---

## 9. Performance Characteristics

### 9.1 Spawn Cycle

- **Latency**: ~500ms for 15 variants
- **Throughput**: 30 variants/second
- **Resource**: CPU-bound (template rendering + hashing)

### 9.2 PHASE Testing

- **Latency**: 10s per candidate (configurable)
- **Throughput**: 6 candidates/minute (sequential)
- **Resource**: CPU + network for synthetic workload

### 9.3 Registry Updates

- **Latency**: ~50ms (atomic write + fsync)
- **Throughput**: ~20 updates/second (limited by fsync)
- **Resource**: Disk I/O bound

---

## 10. Scalability

### 10.1 Current Limits

- **Zooids**: ~1000 per registry (JSON file size)
- **Niches**: 5 implemented, ~50 feasible
- **PHASE Tests**: Sequential, ~6/min
- **Ecosystems**: 1 active (queue_management)

### 10.2 Scaling Strategies

**Horizontal**:
- Multiple PHASE consumers (requires queue partitioning)
- Distributed registry (requires consensus protocol)
- Parallel workload drivers

**Vertical**:
- Larger registry (migrate to database)
- Faster PHASE tests (optimize workload profiles)
- More niches (template library expansion)

---

## 11. Security Considerations

### 11.1 Code Generation Risks

**Concern**: Spawner generates arbitrary Python code
**Mitigation**:
- Template-based (limited code surface)
- No eval/exec in spawner
- Genome hashing prevents injection

**Residual Risk**: Generated code runs in production without sandboxing

### 11.2 Subprocess Execution

**Concern**: PHASE tests execute arbitrary zooid code
**Mitigation**:
- subprocess.run() isolation
- No shell=True
- Timeout enforcement
- PYTHONPATH-only environment

**Residual Risk**: Zooid could consume resources within timeout

### 11.3 File System Access

**Concern**: Services run as kloros user with broad permissions
**Mitigation**:
- No sudo elevation
- Limited to /home/kloros
- Systemd sandboxing (future)

**Residual Risk**: Compromised zooid could access all kloros-owned files

---

## 12. Future Enhancements

### 12.1 Short Term (Q4 2025)

1. **Parallel PHASE Testing** - Worker pool for concurrent tests
2. **Fitness Visualization** - Grafana dashboard
3. **Registry Backups** - Automated snapshots
4. **Failure Alerting** - systemd watchdog + notifications
5. **More Niches** - Expand beyond queue_management

### 12.2 Medium Term (Q1 2026)

1. **Multi-Ecosystem Support** - Camera, greenhouse, physical
2. **Cross-Niche Evolution** - Horizontal gene transfer
3. **Real-Time Fitness** - Streaming metrics
4. **Automated Niche Discovery** - Unsupervised clustering
5. **SPICA Migration Complete** - Type-safe evolution

### 12.3 Long Term (2026+)

1. **Distributed PHASE** - Cloud-scale testing
2. **Multi-Registry** - Federated evolution
3. **Meta-Evolution** - Evolve evolution parameters
4. **Self-Modifying Templates** - Template evolution
5. **Agentic Zooids** - Tool-using specialized agents

---

## Appendix A: Glossary

- **D-REAM**: Darwinian-RZero Evolution & Anti-collapse Module
- **PHASE**: Phased Heuristic Adaptive Scheduling Engine
- **Zooid**: Specialized component evolved for a niche
- **Niche**: Ecological role within an ecosystem
- **Ecosystem**: Domain of operation (e.g., queue_management)
- **Genome**: Code + phenotype parameters
- **Phenotype**: Observable characteristics (parameter values)
- **Fitness**: Composite performance score (0.0-1.0)
- **Lifecycle State**: DORMANT, PROBATION, ACTIVE, or RETIRED

---

**Document Version**: 2.0  
**Last Updated**: 2025-11-07 18:10 EST  
**Author**: Claude Code (Sonnet 4.5)  
**Status**: Production
