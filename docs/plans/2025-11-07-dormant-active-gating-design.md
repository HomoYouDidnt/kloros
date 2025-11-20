# DORMANT → ACTIVE Gating Design

**Date:** 2025-11-07
**Status:** Design Complete
**Authors:** KLoROS Team

## 1. Purpose & Scope

### Motivation

The colony experienced uncontrolled zooid proliferation when newly generated candidates were deployed directly to production without evaluation. This design implements a safety gate preventing untested code from handling real incidents.

### Core Principle

**DORMANT is not "limited production" - it is "pre-production laboratory specimen."**

Newly generated zooids undergo temporal dilation testing in PHASE before production deployment. This prevents system-breaking proliferation while maintaining evolutionary pressure.

### Scope

This design covers:
- Lifecycle state model (DORMANT, PROBATION, ACTIVE, RETIRED)
- PHASE probation mechanics with 100-hour temporal dilation testing
- Production activation, monitoring, and quarantine
- Bioreactor integration with conservative evolution
- 24-hour orchestration timeline
- Implementation components and migration path

## 2. Lifecycle States & Transitions

### State Definitions

**DORMANT**
- Newly generated candidates in registry + PHASE queue
- Not evaluated yet
- Do NOT run in production
- Do NOT receive chemical signals
- Awaiting next PHASE batch window

**PROBATION**
- Currently undergoing PHASE evaluation
- Still NOT in production
- Being tested with 100 simulated hours of full traffic
- Generating synthetic fitness metrics in `phase_fitness.jsonl`

**ACTIVE**
- Promoted zooids running in production
- Subscribe to chemical signals matching their niche
- Handle real incidents
- Generate production fitness in `fitness_ledger.jsonl`
- Compete in bioreactor death matches

**RETIRED**
- Permanently removed from service
- Failed catastrophically or exceeded demotion ceiling
- Kept for lineage tracking and forensics

### State Transition Rules

**DORMANT → PROBATION**
- **Trigger:** PHASE batch begins, picks up queued candidates
- **Action:** Set `lifecycle_state="PROBATION"`, append to `phase.batches`

**PROBATION → ACTIVE (promote)**
- **Gates:**
  - `phase.fitness_mean ≥ policy.phase_threshold` (e.g., 0.70)
  - `phase.evidence ≥ policy.min_phase_evidence` (e.g., 50 observations)
  - `policy.prod_guard_failures == 0` (no catastrophic lineage failures)
- **Actions:**
  1. Update registry: `lifecycle_state="ACTIVE"`, set `promoted_ts`
  2. Write snapshot `niche_map.v{N}.json`
  3. Atomic write `niche_map.json` (tmp → fsync → rename)
  4. Start service (systemd or direct process)
  5. Verify heartbeat within 30 seconds
  6. If no heartbeat: rollback to DORMANT, log `rollback_no_heartbeat`
  7. Emit `event="zooid_state_change"` with full provenance

**PROBATION → DORMANT (retry)**
- **Trigger:** Insufficient evidence OR low fitness (not catastrophic)
- **Action:** Return to `DORMANT` for next batch, set `reason="insufficient_evidence|low_fitness"`

**PROBATION → RETIRED**
- **Trigger:** Catastrophic synthetic failure (e.g., error rate spike, stability breach)
- **Action:** Set `lifecycle_state="RETIRED"`, `retired_reason="synthetic_catastrophe"`

**ACTIVE → DORMANT (quarantine)**
- **Trigger:** Production hard-fail sentinel (N failures in M minutes, e.g., 3 in 15 minutes)
- **Actions:**
  1. Update registry: `lifecycle_state="DORMANT"`, increment `demotions`, set `reason="prod_guard_trip"`
  2. Stop service or set kill flag + drop SUB sockets
  3. Emit governance signal: `governance.quarantine` with zooid name and reason
  4. Start cooldown timer (no re-probation until `policy.quarantine_window_sec` elapses)

**ACTIVE → RETIRED**
- **Trigger:** Replaced by better winners + fails re-test, or `demotions ≥ policy.demotion_ceiling`
- **Action:** Set `lifecycle_state="RETIRED"`, `retired_reason="demotion_ceiling|superseded"`

### State Diagram

```
DORMANT ──(PHASE batch starts)──► PROBATION ──(fitness ≥ threshold)──► ACTIVE
   ▲                                   │                                  │
   │                                   │                                  │
   │        (fail / insufficient)      │         (N failures in M min)    │
   └───────────────────◄───────────────┘                                  │
                                                                           │
   ┌───────────────────────────────────────────────────────────────────────┘
   │
   ▼
RETIRED (demotion_ceiling | catastrophic)
```

## 3. Registry Schema

### Two-Tier Structure

**Niche-level indexes (fast lookups):**
```json
{
  "niches": {
    "latency_monitoring": {
      "active": ["latency_monitoring_1762539595_1"],
      "probation": ["latency_monitoring_1762539700_2"],
      "dormant": ["latency_monitoring_1762539800_3"],
      "retired": ["LatencyTracker_v1"]
    }
  }
}
```

**Zooid-level objects (source of truth):**
```json
{
  "zooids": {
    "latency_monitoring_1762539595_1": {
      "name": "latency_monitoring_1762539595_1",
      "ecosystem": "queue_management",
      "niche": "latency_monitoring",
      "lifecycle_state": "ACTIVE",
      "entered_ts": 1762539595.0,
      "promoted_ts": 1762539700.0,
      "last_transition_ts": 1762539700.0,
      "demotions": 0,
      "probation_attempts": 1,
      "reason": "spawned_by_bioreactor_v8",
      "retired_reason": null,

      "genome_hash": "sha256:abc123...",
      "parent_lineage": ["LatencyTracker_v1"],
      "signed_at": 1762539595.0,
      "signature": "hmac-sha256:...",

      "phase": {
        "batches": ["2025-11-07T03:10Z-LIGHT"],
        "evidence": 52,
        "fitness_mean": 0.89,
        "fitness_ci95": [0.85, 0.93],
        "last_ts": 1762539680.0,
        "started_ts": 1762539600.0,
        "completed_ts": 1762539680.0
      },

      "prod": {
        "evidence": 143,
        "ok_rate": 0.92,
        "ttr_ms_mean": 420,
        "last_ts": 1762539800.0
      },

      "policy": {
        "source": "niche",
        "phase_threshold": 0.70,
        "min_phase_evidence": 50,
        "prod_guard_failures": 0,
        "decay": { "phase_half_life_sec": 43200 },
        "demotion_ceiling": 2,
        "quarantine_window_sec": 900
      }
    }
  },

  "genomes": {
    "sha256:abc123...": "latency_monitoring_1762539595_1"
  }
}
```

### Consistency Rules

1. **Index-Object Sync:** Each name in niche indexes must exist in `zooids` with matching `lifecycle_state`
2. **Genome Uniqueness:** `genomes` map must be bijective (one hash → one zooid)
3. **State Authority:** `zooids[name].lifecycle_state` is source of truth; indexes are views
4. **Atomic Updates:** All mutations follow: build in memory → validate → snapshot → atomic write

## 4. PHASE Probation Mechanics

### PHASE Batch Window

**Scheduled Windows:**
- **DEEP:** Daily 3-7 AM window (4 hours)
- **LIGHT:** 10-minute on-demand bursts during 7 AM - 11 PM

**Batch Start Process:**
1. PHASE Orchestrator discovers all DORMANT candidates in registry
2. Transition: DORMANT → PROBATION (atomic registry update)
3. Append batch ID to `phase.batches` (e.g., `"2025-11-07T03:10Z-LIGHT"`)
4. Set `phase.started_ts`

### Temporal Dilation Testing

**Simulated Duration:** 100 hours of full traffic compressed into real-time evaluation

**Synthetic Workload:**
- Accelerated incident rates
- Stress spikes, jitter, unpredictable bursts
- Multi-domain cross-load patterns
- Rare edge-case sequences (cascading failures, rapid signal bursts)

**Workload Profile Example:**
```json
{
  "workload_profile_id": "QMG-100h-full-traffic-v3",
  "seed": 90210,
  "simulated_hours": 100,
  "incident_mix": {
    "spike": 0.25,
    "stall": 0.15,
    "latency": 0.60
  },
  "anomalies": ["burst_jitter", "cascade_fail"]
}
```

### Generated Metrics

**Per-candidate PHASE entry:**
```json
{
  "schema_version": "phase_fitness:v1",
  "ts": 1762539595.0,
  "ecosystem": "queue_management",
  "niche": "latency_monitoring",
  "candidate": "latency_monitoring_1762539595_1",
  "phase_batch": "2025-11-07T03:10Z-LIGHT",
  "workload_profile_id": "QMG-100h-full-traffic-v3",
  "seed": 90210,
  "simulated_hours": 100,
  "incident_mix": {"spike": 0.25, "stall": 0.15, "latency": 0.60},
  "anomalies": ["burst_jitter", "cascade_fail"],

  "metrics": {
    "p95_ms": 420,
    "throughput_qps": 68.5,
    "error_rate": 0.02
  },

  "scores": {
    "latency": 0.88,
    "throughput": 0.85,
    "errors": 0.94
  },

  "composite_weights": {
    "latency": 0.4,
    "throughput": 0.35,
    "errors": 0.25
  },

  "composite_phase_fitness": 0.89,
  "decay_w": 0.73
}
```

**Written to:** `~/.kloros/lineage/phase_fitness.jsonl`

### Graduation Calculation

**At PHASE window end (07:00 or LIGHT burst completion):**

1. **Aggregate:** All PROBATION entries for each candidate
2. **Decay:** Apply exponential time decay (12-hour half-life):
   ```python
   weight = 2.0 ** (-age_seconds / half_life_seconds)
   ```
3. **Compute:** Weighted mean fitness and confidence interval
4. **Update Registry:**
   - `phase.fitness_mean` = EWMA across all observations
   - `phase.evidence` = total observation count
   - `phase.fitness_ci95` = 95% confidence interval
   - `phase.completed_ts` = current timestamp

5. **Check Gates:**
   - `phase.fitness_mean ≥ policy.phase_threshold` (e.g., 0.70)
   - `phase.evidence ≥ policy.min_phase_evidence` (e.g., 50)
   - `policy.prod_guard_failures == 0`

6. **Execute Transition:**
   - **Pass:** PROBATION → ACTIVE (promote)
   - **Fail (insufficient):** PROBATION → DORMANT (retry next batch)
   - **Fail (catastrophic):** PROBATION → RETIRED

## 5. Production Activation & Monitoring

### Activation Process (PROBATION → ACTIVE)

When graduation gates pass:

**1. Registry Update:**
```python
# Atomic sequence
snapshot_path = write_snapshot(reg, version=N)
reg.zooids[name].lifecycle_state = "ACTIVE"
reg.zooids[name].promoted_ts = time.time()
reg.zooids[name].last_transition_ts = time.time()
reg.index.active.add(name)
reg.index.probation.remove(name)
atomic_write(reg)  # tmp → fsync → rename
```

**2. Service Start:**
```bash
systemctl start zooid-latency_monitoring@latency_monitoring_1762539595_1
# or direct process spawn with double-tap safeguard
```

**3. Signal Subscription (ZMQ prefix matching):**
```python
# Correct: byte-prefix, no wildcards/schemes
subscribe_topics = [
    b"Q_LATENCY_SPIKE",  # exact topic
    b"Q_"                # prefix for all Q_* signals
]
ctx = zmq.Context()
sub = ctx.socket(zmq.SUB)
sub.connect("tcp://127.0.0.1:5556")
for topic in subscribe_topics:
    sub.subscribe(topic)
```

**4. Heartbeat Verification:**
- Wait up to 30 seconds for first heartbeat
- If missing: rollback to DORMANT, log `service_action="rollback_no_heartbeat"`

**5. Event Emission:**
```json
{
  "event": "zooid_state_change",
  "zooid": "latency_monitoring_1762539595_1",
  "niche": "latency_monitoring",
  "from": "PROBATION",
  "to": "ACTIVE",
  "reason": "graduation",
  "genome_hash": "sha256:abc123...",
  "parent_lineage": ["LatencyTracker_v1"],
  "lifecycle_prev_ts": 80.0,
  "service_action": "systemd_start",
  "phase_fit": 0.89,
  "phase_ev": 52,
  "prod_ok": null,
  "prod_ev": 0
}
```

### Production Operation

**Incident Handling:**
1. Zooid receives chemical signal (ZMQ SUB)
2. Processes incident
3. Emits OBSERVATION event:
   ```json
   {
     "event": "observation",
     "ts": 1762539595.0,
     "incident_id": "incident_1762539595_0",
     "zooid": "latency_monitoring_1762539595_1",
     "niche": "latency_monitoring",
     "ecosystem": "queue_management",
     "ok": true,
     "ttr_ms": 420,
     "signature": "hmac-sha256:..."
   }
   ```

**Central Ledger Writer:**
- Subscribes to OBSERVATION events
- Validates HMAC signature (prevents self-report gaming)
- Appends to fitness ledger (atomic write):

**Fitness Ledger Path (standardized):**
```bash
export KLR_FITNESS_LEDGER=/home/kloros/.kloros/lineage/fitness_ledger.jsonl
```

**Fitness Entry Format:**
```json
{
  "ts": 1762539595.0,
  "incident_id": "incident_1762539595_0",
  "zooid": "latency_monitoring_1762539595_1",
  "niche": "latency_monitoring",
  "ecosystem": "queue_management",
  "ok": true,
  "ttr_ms": 420
}
```

**Continuous Monitoring:**
- Rolling window updater refreshes `prod.*` fields in registry
- Atomic registry updates every N observations (e.g., every 10)
- Updates: `prod.ok_rate`, `prod.ttr_ms_mean`, `prod.evidence`, `prod.last_ts`

### Quarantine Guard (ACTIVE → DORMANT)

**Trigger Detection:**
```python
def check_quarantine_trigger(zooid_name, window_sec=900):
    """
    Check if N failures occurred in last M minutes.
    Example: 3 failures in 15 minutes (900 seconds)
    """
    now = time.time()
    cutoff = now - window_sec

    recent_failures = [
        row for row in fitness_ledger
        if row["zooid"] == zooid_name
        and row["ts"] >= cutoff
        and row["ok"] is False
    ]

    threshold = 3  # from policy.prod_guard_failures threshold
    return len(recent_failures) >= threshold, len(recent_failures)
```

**Quarantine Actions:**

1. **Registry Update (atomic):**
   ```python
   reg.zooids[name].lifecycle_state = "DORMANT"
   reg.zooids[name].demotions += 1
   reg.zooids[name].reason = "prod_guard_trip"
   reg.zooids[name].policy.prod_guard_failures = failure_count
   reg.zooids[name].last_transition_ts = time.time()
   reg.index.active.remove(name)
   reg.index.dormant.add(name)
   atomic_write(reg)
   ```

2. **Service Stop:**
   ```bash
   systemctl stop zooid-latency_monitoring@latency_monitoring_1762539595_1
   # or set kill flag + drop SUB sockets
   ```

3. **Governance Signal:**
   ```python
   ChemPub().emit(
       "governance.quarantine",
       "colony",
       1.0,
       {
           "zooid": name,
           "reason": "prod_guard_trip",
           "failure_count": failure_count,
           "window_sec": 900,
           "ts": time.time()
       }
   )
   ```

4. **Cooldown Enforcement:**
   - No re-entry to PROBATION until `policy.quarantine_window_sec` elapses
   - Track: `reg.zooids[name].quarantine_until = now + policy.quarantine_window_sec`
   - Exponential backoff on repeated demotions: `cooldown *= 2 ** demotions`

**Demotion Ceiling:**
```python
if reg.zooids[name].demotions >= reg.zooids[name].policy.demotion_ceiling:
    reg.zooids[name].lifecycle_state = "RETIRED"
    reg.zooids[name].retired_reason = "demotion_ceiling"
    reg.index.dormant.remove(name)
    reg.index.retired.add(name)
```

## 6. Bioreactor Integration with Lifecycle

### Modified Evolution Cycle

The bioreactor now works with lifecycle states instead of direct registry insertion.

**Bioreactor Tick (lifecycle-aware):**

**1. Generate DORMANT Candidates:**
```python
new_cands = differentiate(niche, ecosystem, m=3)
for c in new_cands:
    z = to_registry_obj(
        c,
        lifecycle_state="DORMANT",
        entered_ts=now,
        reason=f"spawned_by_bioreactor_v{VERSION}",
        genome_hash=compute_genome_hash(c)
    )
    reg.add_or_update(z)
    reg.index.dormant.add(z.name)
```

**2. Death Match (ACTIVE only):**
```python
# Load all ACTIVE defenders (including recent graduates)
active_names = reg.index.active.list(niche)
active_defenders = [reg.zooids[n] for n in active_names]

# Tournament among ACTIVE population
winners = select_winners(
    active_defenders,
    prod_rows,
    phase_rows,
    now,
    k=2  # top 2 winners for polymorphism
)
```

**3. Conservative ACTIVE Set Update:**
```python
# Identify losers
losers = set(active_names) - {w.name for w in winners}
survivors = set(active_names) - losers

# Policy-driven loser handling (prevent oscillation)
for n in losers:
    z = reg.zooids[n]
    if should_retire(z):  # e.g., lost twice in last K ticks
        retire(reg, n, reason="repeated_tournament_loss")
    else:
        survivors.add(n)  # keep as polymorph for stability

# Update ACTIVE index (union of survivors + winners)
new_active = sorted(set(survivors) | {w.name for w in winners})
reg.index.active.set(niche, new_active)
```

**4. PHASE Queue (de-duplicated):**
```python
for c in new_cands:
    # Skip if genome_hash already exists in any state
    if c.genome_hash in reg.genomes:
        logger.info(f"Skipping duplicate genome: {c.genome_hash[:12]}")
        continue

    # Enqueue for PHASE evaluation
    append_atomic(PHASE_QUEUE, {
        "schema_version": "phase_queue:v1",
        "ts": now,
        "candidate": c.name,
        "ecosystem": ecosystem,
        "niche": niche,
        "genome_hash": c.genome_hash,
        "workload_profile_id": "QMG-100h-full-traffic-v3",
        "seed": random_seed(),
        "status": "queued"
    })
```

**5. Atomic Registry Update:**
```python
snapshot_then_atomic_write(reg)
```

**Key Behaviors:**
- **Stable Polymorphism:** Winners survive, losers evaluated by policy before removal
- **Graduate Competition:** PROBATION→ACTIVE promotions automatically join next tournament
- **No Duplicate Work:** genome_hash de-duplication prevents redundant PHASE evaluation
- **Conservative Churn:** Only explicit policy-driven retirements, no mass replacements

## 7. Daily Orchestration Timeline

### 24-Hour Colony Cycle

```
00:00 - Bioreactor Evolution Cycle
      - Acquire lock: ~/.kloros/locks/colony_cycle.lock
      - Death matches among ACTIVE population
      - Generate new DORMANT candidates
      - Update registry (snapshot + atomic write)
      - Enqueue to PHASE queue
      - Conservative loser handling (policy-driven retirement)
      - Release lock
      - Emit signal: ~/.kloros/signals/bioreactor_idle

03:00 - PHASE Window Start
      - Acquire lock
      - D-REAM Evolution pauses
      - PHASE Orchestrator discovers DORMANT candidates
      - Batch transition: DORMANT → PROBATION (atomic registry update)
      - Temporal dilation testing begins (100 simulated hours)
      - Release lock

03:00-07:00 - PHASE Evaluation (DEEP window)
      - Synthetic workload: stress spikes, jitter, edge cases
      - Generate phase_fitness.jsonl entries
      - Multi-domain cross-load, rare sequences
      - Update PROBATION zooids' phase.* metrics
      - Continuous logging with provenance

07:00 - PHASE Window End
      - Acquire lock
      - Emit signal: /tmp/phase_complete_{timestamp}
      - Emit signal: ~/.kloros/signals/phase_done
      - PHASE Graduator checks all PROBATION candidates
      - Apply gates: fitness_mean ≥ threshold AND evidence ≥ minimum
      - Promote: PROBATION → ACTIVE
        - Start services
        - Subscribe signals (ZMQ prefix matching)
        - Verify heartbeat within 30s
        - Rollback if missing heartbeat
      - Fail: PROBATION → DORMANT (retry) or → RETIRED (catastrophic)
      - Emit signal: ~/.kloros/signals/promotions_done
      - Release lock

07:00-23:59 - Colony Runtime
      - ACTIVE zooids handle production incidents
      - Zooids emit OBSERVATION events
      - Central ledger-writer appends fitness_ledger.jsonl (atomic)
      - Rolling window monitoring updates prod.* fields
      - Quarantine guards active (N failures in M minutes)
      - PHASE LIGHT bursts: 10-min on-demand evaluations
        - Gated: only if no active colony_cycle.lock
        - Prevents registry thrash during bioreactor/graduator work

Continuous - Quarantine Monitoring
      - Per-incident failure tracking (rolling window)
      - Trigger: N failures in M minutes → ACTIVE → DORMANT
        - Stop service or drop SUB sockets
        - Emit governance.quarantine signal
        - Enforce cooldown before re-probation
        - Exponential backoff on repeated demotions
      - Ceiling: demotions ≥ threshold → RETIRED
```

### Orchestration Coordination

**Signal Files:**
- `~/.kloros/signals/bioreactor_idle` - Written at 02:59, allows PHASE start
- `~/.kloros/signals/phase_done` - Written at 07:00, allows graduator start
- `~/.kloros/signals/promotions_done` - Written after promotions complete

**Global Lock:**
```bash
# Acquire lock (fail fast if held)
flock -n ~/.kloros/locks/colony_cycle.lock -c "command..."

# Or in Python with timeout
import fcntl
with open(LOCK_PATH, 'w') as lock:
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    # ... critical section ...
```

**Clock Sanity Checks:**
```python
def check_ntp_skew():
    """Log NTP skew and abort if > 5 seconds."""
    result = subprocess.run(['ntpq', '-p'], capture_output=True)
    # Parse offset, log, assert < threshold
```

**LIGHT Burst Gating:**
```python
def can_run_light_burst():
    """Check if PHASE LIGHT can run without registry conflicts."""
    try:
        with open(LOCK_PATH, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return True
    except BlockingIOError:
        return False  # Lock held, skip LIGHT burst
```

## 8. Implementation Components & Files

### Core Components

**1. Registry Management** (`kloros/registry/lifecycle_registry.py`)
- Two-tier schema: niche indexes + zooid objects
- Global genome hash index for O(1) de-duplication
- Consistency reconciler (index ↔ object validation)
- Atomic write operations (snapshot → tmp → fsync → rename)
- Mutex-based coordination lock

**2. State Machine** (`kloros/lifecycle/state_machine.py`)
- State transition enforcement (DORMANT → PROBATION → ACTIVE → RETIRED)
- Promotion/demotion logic with policy gates
- Cooldown and exponential backoff management
- State change event emission with full provenance

**3. PHASE Integration** (`kloros/phase/graduator.py`)
- Batch discovery of DORMANT candidates
- Fitness aggregation with exponential decay (12-hour half-life)
- Graduation gate evaluation (fitness + evidence + confidence)
- Service start/stop with idempotent checks
- Heartbeat verification with 30-second SLO
- Rollback on missing heartbeat

**4. Bioreactor Enhancements** (`kloros/dream/bioreactor.py`)
- Lifecycle-aware tournament selection (ACTIVE only)
- Conservative loser handling with policy (hysteresis)
- PHASE queue management with genome_hash de-duplication
- Global coordination via signal files
- Idempotent tick (re-runs safe)

**5. Quarantine Monitor** (`kloros/observability/quarantine_monitor.py`)
- Rolling window failure tracking (configurable N-in-M)
- Trigger detection with timestamp window
- Service stop + governance signal emission
- Cooldown enforcement with exponential backoff
- Rate-limiting for quarantine signals (one per window)

**6. Central Ledger Writer** (`kloros/observability/ledger_writer.py`)
- OBSERVATION event subscription (ZMQ SUB)
- HMAC signature validation (prevents self-report gaming)
- Atomic append to fitness_ledger.jsonl (tmp → fsync → rename)
- Rolling window metric computation
- Registry prod.* field updates (atomic)
- Backpressure detection and shedding

**7. Coordination** (`kloros/orchestration/cycle_coordinator.py`)
- Signal file management (bioreactor_idle, phase_done, promotions_done)
- Clock sanity checks (NTP skew detection)
- Phase handoff verification
- LIGHT burst gating (lock check)
- Global lock acquisition/release

### Configuration Files

**1. Lifecycle Policy** (`~/.kloros/config/lifecycle_policy.json`)
```json
{
  "defaults": {
    "phase_threshold": 0.70,
    "min_phase_evidence": 50,
    "prod_guard_failures_threshold": 3,
    "quarantine_window_sec": 900,
    "demotion_ceiling": 2,
    "phase_half_life_sec": 43200,
    "heartbeat_slo_sec": 30
  },
  "niche_overrides": {
    "latency_monitoring": {
      "phase_threshold": 0.75,
      "comment": "Higher bar for latency-critical niche"
    }
  }
}
```

**2. Workload Profiles** (`~/.kloros/config/workload_profiles.json`)
```json
{
  "QMG-100h-full-traffic-v3": {
    "simulated_hours": 100,
    "incident_mix": {
      "spike": 0.25,
      "stall": 0.15,
      "latency": 0.60
    },
    "anomalies": ["burst_jitter", "cascade_fail"],
    "intensity": "high"
  },
  "QMG-24h-light-v1": {
    "simulated_hours": 24,
    "incident_mix": {
      "spike": 0.10,
      "stall": 0.05,
      "latency": 0.85
    },
    "anomalies": [],
    "intensity": "low"
  }
}
```

**3. HMAC Keys** (`~/.kloros/config/keys.json`)
```json
{
  "current": {
    "key_id": "hmac-2025-11-07",
    "algorithm": "hmac-sha256",
    "key": "base64-encoded-secret",
    "created_at": 1762539595.0
  },
  "rotation_policy": {
    "rotate_every_days": 90,
    "keep_old_keys": 2
  }
}
```

### Environment Variables

```bash
# Fitness configuration (already exists)
export KLR_W_PROD=0.6
export KLR_W_PHASE=0.4
export KLR_PROD_WINDOW_SEC=3600
export KLR_PHASE_WINDOW_SEC=86400
export KLR_MIN_PROD_CASES=3
export KLR_MIN_PHASE_CASES=3
export KLR_PHASE_HALF_LIFE_SEC=43200

# Lifecycle paths
export KLR_FITNESS_LEDGER=/home/kloros/.kloros/lineage/fitness_ledger.jsonl
export KLR_PHASE_LEDGER=/home/kloros/.kloros/lineage/phase_fitness.jsonl
export KLR_REGISTRY=/home/kloros/.kloros/registry/niche_map.json
export KLR_PHASE_QUEUE=/home/kloros/.kloros/lineage/phase_queue.jsonl

# Lifecycle policy
export KLR_PHASE_THRESHOLD=0.70
export KLR_MIN_PHASE_EVIDENCE=50
export KLR_QUARANTINE_WINDOW_SEC=900
export KLR_DEMOTION_CEILING=2
export KLR_HEARTBEAT_SLO_SEC=30
```

### Systemd Service Templates

**Zooid Service** (`/etc/systemd/system/zooid-{niche}@.service`)
```ini
[Unit]
Description=KLoROS Zooid: %I
After=network.target chem-proxy.service

[Service]
Type=simple
User=kloros
Environment="PYTHONPATH=/home/kloros/src"
ExecStart=/home/kloros/.venv/bin/python3 -m zooids.%i
Restart=on-failure
RestartSec=2s
StartLimitBurst=3
StartLimitInterval=60s

# Resource limits
CPUQuota=50%%
MemoryMax=512M
TasksMax=100

# Logging
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## 9. Observability & Events

### State Change Events

**Schema:**
```json
{
  "event": "zooid_state_change",
  "ts": 1762539700.0,
  "zooid": "latency_monitoring_1762539595_1",
  "niche": "latency_monitoring",
  "ecosystem": "queue_management",
  "from": "PROBATION",
  "to": "ACTIVE",
  "reason": "graduation",
  "genome_hash": "sha256:abc123...",
  "parent_lineage": ["LatencyTracker_v1"],
  "lifecycle_prev_ts": 80.0,
  "service_action": "systemd_start",
  "phase_fit": 0.89,
  "phase_ev": 52,
  "phase_ci95": [0.85, 0.93],
  "prod_ok": null,
  "prod_ev": 0
}
```

**Written to:** `~/.kloros/observability/lifecycle_events.jsonl`

### Governance Signals (Chemical)

**Quarantine:**
```python
ChemPub().emit(
    "governance.quarantine",
    "colony",
    1.0,
    {
        "zooid": "latency_monitoring_1762539595_1",
        "reason": "prod_guard_trip",
        "failure_count": 3,
        "window_sec": 900,
        "ts": 1762539800.0
    }
)
```

**Promotion:**
```python
ChemPub().emit(
    "governance.promotion",
    "colony",
    1.0,
    {
        "zooid": "latency_monitoring_1762539595_1",
        "from": "PROBATION",
        "to": "ACTIVE",
        "phase_fitness": 0.89,
        "ts": 1762539700.0
    }
)
```

**Backpressure:**
```python
ChemPub().emit(
    "governance.backpressure",
    "colony",
    1.0,
    {
        "component": "ledger_writer",
        "queue_depth": 1024,
        "ts": 1762539900.0
    }
)
```

### Dashboard Queries

**Current State Snapshot:**
```python
def get_niche_snapshot(ecosystem, niche):
    reg = load_registry()
    return {
        "active": reg.index.active.list(niche),
        "probation": reg.index.probation.list(niche),
        "dormant": reg.index.dormant.list(niche),
        "retired": reg.index.retired.list(niche)
    }
```

**Fitness Trends:**
```python
def get_fitness_trends(zooid_name, window_sec=86400):
    now = time.time()
    cutoff = now - window_sec

    prod_rows = [r for r in load_ledger(PROD_LEDGER)
                 if r["zooid"] == zooid_name and r["ts"] >= cutoff]

    phase_rows = [r for r in load_ledger(PHASE_LEDGER)
                  if r["candidate"] == zooid_name and r["ts"] >= cutoff]

    return {
        "prod_ok_rate": compute_ok_rate(prod_rows),
        "prod_ttr_p95": compute_p95(prod_rows, "ttr_ms"),
        "phase_fitness": compute_ewma(phase_rows, "composite_phase_fitness")
    }
```

**Lineage Tree:**
```python
def build_lineage_tree(zooid_name):
    reg = load_registry()
    z = reg.zooids[zooid_name]

    tree = {
        "name": z.name,
        "genome_hash": z.genome_hash,
        "lifecycle_state": z.lifecycle_state,
        "parents": []
    }

    for parent_name in z.parent_lineage:
        if parent_name in reg.zooids:
            tree["parents"].append(build_lineage_tree(parent_name))

    return tree
```

## 10. Security & Safety

### HMAC Signature Validation

**Signing OBSERVATION events:**
```python
import hmac
import hashlib
import json

def sign_observation(obs, key):
    """Sign observation with HMAC-SHA256."""
    canonical = json.dumps(obs, sort_keys=True)
    signature = hmac.new(
        key.encode('utf-8'),
        canonical.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return f"hmac-sha256:{signature}"

# In zooid
obs = {
    "event": "observation",
    "ts": time.time(),
    "incident_id": incident_id,
    "zooid": self.name,
    "ok": ok,
    "ttr_ms": ttr_ms
}
obs["signature"] = sign_observation(obs, HMAC_KEY)
ChemPub().emit("observation", "ledger", 1.0, obs)
```

**Validating in ledger writer:**
```python
def validate_observation(obs, key):
    """Verify HMAC signature on observation."""
    claimed_sig = obs.pop("signature", "")
    canonical = json.dumps(obs, sort_keys=True)
    expected_sig = sign_observation(obs, key)

    if not hmac.compare_digest(claimed_sig, expected_sig):
        raise SecurityError(f"Invalid signature for {obs['zooid']}")

    return obs
```

### Kill Switch

**Emergency quarantine all zooids:**
```bash
# Write kill switch signal
touch ~/.kloros/signals/emergency_stop

# All zooids check on each incident:
if os.path.exists(EMERGENCY_STOP):
    logger.critical("Emergency stop active, halting")
    sys.exit(1)
```

**Emergency rollback to known-good:**
```bash
# Restore snapshot
cp ~/.kloros/registry/niche_map.v5.json ~/.kloros/registry/niche_map.json

# Restart services
systemctl restart 'zooid-*'
```

### Resource Limits (Systemd)

Already included in service template:
- `CPUQuota=50%` - Max 50% of one core
- `MemoryMax=512M` - Hard memory limit
- `TasksMax=100` - Prevent fork bombs
- `RestartSec=2s`, `StartLimitBurst=3`, `StartLimitInterval=60s` - Prevent restart loops

### Audit Trail

**Immutable logs:**
```bash
# Use append-only attribute
chattr +a ~/.kloros/observability/lifecycle_events.jsonl
chattr +a ~/.kloros/lineage/fitness_ledger.jsonl
```

**Genome signatures:**
```python
def compute_genome_hash(genome):
    """Cryptographic hash of genome code + artifacts."""
    m = hashlib.sha256()
    m.update(genome.module_code.encode('utf-8'))
    m.update(json.dumps(genome.phenotype.__dict__, sort_keys=True).encode('utf-8'))
    return f"sha256:{m.hexdigest()}"
```

## 11. Testing Matrix & Rollback Plan

### Unit Tests

**Registry (`tests/lifecycle/test_registry.py`):**
- Consistency reconciler detects and fixes drift
- Atomic writer never leaves partial state
- Global genome index stays bijective
- Index–object sync maintained on all mutations

**State Machine (`tests/lifecycle/test_state_machine.py`):**
- All valid transitions succeed
- Invalid transitions rejected
- Cooldown prevents premature re-probation
- Exponential backoff computed correctly
- Demotion ceiling enforced

**Quarantine Window (`tests/observability/test_quarantine.py`):**
- N-in-M trigger detection accurate
- Rolling window computation correct
- Backoff multiplier applied
- Rate-limiting prevents signal spam

### Integration Tests

**PHASE Probation → Promotion (`tests/integration/test_probation_flow.py`):**
1. Create DORMANT candidate
2. Start PHASE batch (DORMANT → PROBATION)
3. Generate synthetic fitness (50+ observations)
4. Run graduator (PROBATION → ACTIVE)
5. Verify service started
6. Verify heartbeat received within SLO
7. Verify chemical subscription active

**Quarantine → Cooldown → Re-probation (`tests/integration/test_quarantine_flow.py`):**
1. Deploy ACTIVE zooid
2. Inject 3 failures in 15 minutes
3. Verify quarantine triggered (ACTIVE → DORMANT)
4. Verify service stopped
5. Verify governance signal emitted
6. Verify cooldown prevents immediate re-probation
7. Wait for cooldown expiry
8. Verify DORMANT candidate eligible for next PHASE batch

**Death Match with Graduates (`tests/integration/test_bioreactor_lifecycle.py`):**
1. Create ACTIVE population (existing defenders)
2. Generate new DORMANT candidates
3. Promote one via PHASE (PROBATION → ACTIVE)
4. Run bioreactor tick
5. Verify graduate included in tournament
6. Verify winners selected correctly
7. Verify losers handled per policy
8. Verify no duplicate genome_hash enqueued

### Load Tests

**PHASE Batch with 100 Candidates:**
- 100 DORMANT candidates across 5 niches
- 50+ synthetic observations per candidate
- Measure: graduation time, memory usage, registry write latency
- Assert: < 60 seconds end-to-end, < 1GB memory

**Concurrent Incident Handling:**
- 10 ACTIVE zooids handling 1000 incidents/sec
- Measure: OBSERVATION latency, ledger write throughput
- Assert: < 10ms p95 OBSERVATION latency, no backpressure

### Rollback Plan

**If lifecycle system fails catastrophically:**

1. **Stop all lifecycle controllers:**
   ```bash
   systemctl stop bioreactor phase-orchestrator graduator quarantine-monitor
   ```

2. **Restore last known-good registry:**
   ```bash
   cp ~/.kloros/registry/niche_map.v{N-1}.json ~/.kloros/registry/niche_map.json
   ```

3. **Restart only ACTIVE zooids:**
   ```bash
   # Extract active zooid names from snapshot
   jq -r '.ecosystems[].niches | to_entries[] | .value.active[]' niche_map.json | \
   while read zooid; do
       niche=$(echo $zooid | cut -d_ -f1-2)
       systemctl restart zooid-${niche}@${zooid}
   done
   ```

4. **Emergency mode - skip PHASE gating:**
   ```bash
   # Disable lifecycle enforcement temporarily
   export KLR_DISABLE_LIFECYCLE_GATING=1
   systemctl restart bioreactor
   ```

5. **Investigate root cause:**
   - Check lifecycle_events.jsonl for state transitions
   - Check fitness_ledger.jsonl for production data
   - Check systemd journals: `journalctl -u 'zooid-*'`
   - Check registry consistency

6. **Fix and re-enable:**
   ```bash
   unset KLR_DISABLE_LIFECYCLE_GATING
   systemctl restart bioreactor phase-orchestrator graduator quarantine-monitor
   ```

## 12. Migration Notes

### Upgrading Existing Registry

**Migration Script** (`scripts/migrate_niche_map.py`)
```python
#!/usr/bin/env python3
"""
Migrate existing niche_map.json to two-tier lifecycle schema.
"""
import json
from pathlib import Path
import time
import hashlib

OLD_REG = Path.home() / ".kloros/registry/niche_map.json"
NEW_REG = Path.home() / ".kloros/registry/niche_map.v2.json"

def compute_genome_hash_stub(name):
    """Generate placeholder hash for existing zooids."""
    return f"sha256:legacy_{hashlib.sha256(name.encode()).hexdigest()[:16]}"

def migrate():
    # Load old registry
    old = json.loads(OLD_REG.read_text())

    # Build new structure
    new = {
        "version": old.get("version", 0) + 1,
        "ecosystems": {},
        "zooids": {},
        "genomes": {}
    }

    for eco_name, eco_data in old["ecosystems"].items():
        new["ecosystems"][eco_name] = {
            "niches": {},
            "signals": eco_data.get("signals", {})
        }

        for niche_name, zooid_names in eco_data["niches"].items():
            # Create indexes
            new["ecosystems"][eco_name]["niches"][niche_name] = {
                "active": zooid_names,  # Assume all existing are ACTIVE
                "probation": [],
                "dormant": [],
                "retired": []
            }

            # Create zooid objects
            for zooid_name in zooid_names:
                genome_hash = compute_genome_hash_stub(zooid_name)

                new["zooids"][zooid_name] = {
                    "name": zooid_name,
                    "ecosystem": eco_name,
                    "niche": niche_name,
                    "lifecycle_state": "ACTIVE",
                    "entered_ts": time.time() - 86400,  # Backdated 1 day
                    "promoted_ts": time.time() - 86400,
                    "last_transition_ts": time.time() - 86400,
                    "demotions": 0,
                    "probation_attempts": 0,
                    "reason": "legacy_migration",
                    "retired_reason": None,
                    "genome_hash": genome_hash,
                    "parent_lineage": [],
                    "signed_at": time.time() - 86400,
                    "signature": "migrated",
                    "phase": {
                        "batches": [],
                        "evidence": 0,
                        "fitness_mean": 0.7,  # Neutral assumption
                        "fitness_ci95": None,
                        "last_ts": None,
                        "started_ts": None,
                        "completed_ts": None
                    },
                    "prod": {
                        "evidence": 0,
                        "ok_rate": 0.0,
                        "ttr_ms_mean": None,
                        "last_ts": None
                    },
                    "policy": {
                        "source": "default",
                        "phase_threshold": 0.70,
                        "min_phase_evidence": 50,
                        "prod_guard_failures": 0,
                        "decay": {"phase_half_life_sec": 43200},
                        "demotion_ceiling": 2,
                        "quarantine_window_sec": 900
                    }
                }

                new["genomes"][genome_hash] = zooid_name

    # Write backup of old
    backup = OLD_REG.with_suffix('.json.backup')
    backup.write_text(OLD_REG.read_text())
    print(f"Backed up old registry: {backup}")

    # Write new
    NEW_REG.write_text(json.dumps(new, indent=2))
    print(f"Wrote new registry: {NEW_REG}")

    # Consistency check
    from kloros.registry.lifecycle_registry import LifecycleRegistry
    reg = LifecycleRegistry.load(NEW_REG)
    issues = reg.check_consistency()
    if issues:
        print(f"WARNING: Consistency issues found: {issues}")
    else:
        print("✅ Consistency check passed")

    print("\nTo activate new registry:")
    print(f"  mv {NEW_REG} {OLD_REG}")

if __name__ == "__main__":
    migrate()
```

**Run migration:**
```bash
./scripts/migrate_niche_map.py
# Review output
mv ~/.kloros/registry/niche_map.v2.json ~/.kloros/registry/niche_map.json
```

### Backfilling Production Fitness

If production fitness ledger exists, backfill `prod.*` fields:
```python
def backfill_prod_metrics():
    reg = load_registry()
    ledger = load_ledger(PROD_LEDGER)

    for zooid_name, z in reg.zooids.items():
        rows = [r for r in ledger if r["zooid"] == zooid_name]
        if rows:
            ok_count = sum(1 for r in rows if r.get("ok"))
            z.prod.evidence = len(rows)
            z.prod.ok_rate = ok_count / len(rows)
            z.prod.ttr_ms_mean = compute_mean([r["ttr_ms"] for r in rows if r.get("ttr_ms")])
            z.prod.last_ts = max(r["ts"] for r in rows)

    atomic_write(reg)
```

## 13. Summary

This design implements a safety gate preventing untested code from reaching production. Key principles:

1. **DORMANT is pre-production** - new candidates never touch real incidents
2. **PHASE is the crucible** - 100 hours of temporal dilation testing
3. **Promotion requires proof** - fitness threshold + evidence minimum + confidence
4. **Quarantine prevents proliferation** - automatic demotion on failure patterns
5. **Evolution is conservative** - stable polymorphism, policy-driven retirement
6. **Observability is comprehensive** - every state change logged with provenance

The system prevents the proliferation disaster while maintaining evolutionary pressure through death matches and continuous production fitness tracking.

---

**Next Steps:**
1. Implement core components (registry, state machine, graduator)
2. Write unit and integration tests
3. Run migration script on existing registry
4. Deploy lifecycle controllers with monitoring
5. Validate with PHASE LIGHT bursts
6. Enable full 24-hour autonomous cycle
