# KLoROS Subsystems

This document describes all major subsystems that make up KLoROS, how they work, and how they interact.

## Core Subsystems

### 1. Cognitive Actions (`cognitive_actions_subscriber.py`)

**Purpose:** High-level autonomous decision making and self-healing

**Process:** `kloros-cognitive-actions.service`

**What it does:**
- Listens for affective signals on ChemBus (AFFECT_RESOURCE_STRAIN, AFFECT_MEMORY_PRESSURE, etc.)
- Decides which cognitive action to take (throttle_investigations, optimize_performance, etc.)
- Uses cooldown timers to prevent action spam (5-minute default)
- Executes skills via SkillExecutor for complex problems

**ChemBus Signals Consumed:**
- `AFFECT_RESOURCE_STRAIN` (intensity ≥ 2.0) → triggers optimize_performance
- `AFFECT_MEMORY_PRESSURE` (intensity ≥ 2.0) → triggers memory investigation
- `AFFECT_INVESTIGATION_PRESSURE` → triggers investigation throttling

**ChemBus Signals Emitted:**
- `INVESTIGATION_THROTTLE_REQUEST` → asks orchestration to reduce investigation concurrency
- `SKILL_EXECUTION_COMPLETE` → reports autonomous healing outcomes
- `COGNITIVE_ACTION_TAKEN` → logs which action was executed

**Resource Usage:**
- Memory: ~40MB
- Threads: 1 main + ZMQ listeners
- CPU: Minimal (event-driven)

**Common Issues:**
- Cooldown prevents action when needed → adjust cooldown in code
- Skill execution fails → check skill_executions.db for history
- Actions not triggering → verify ChemBus signals are being emitted

---

### 2. Interoception (`interoception_daemon.py`)

**Purpose:** Continuous monitoring of system vitals (like a nervous system)

**Process:** `kloros-interoception.service`

**What it does:**
- Monitors system resources every 30 seconds (configurable)
- Tracks: CPU, memory, swap, GPU, disk I/O, thread counts
- Emits affective signals when thresholds exceeded
- Maintains historical metrics for trend analysis

**ChemBus Signals Emitted:**
- `AFFECT_RESOURCE_STRAIN` → when CPU > 80% or memory > 70%
- `AFFECT_MEMORY_PRESSURE` → when swap > 50%
- `VITALS_UPDATE` → periodic health report

**Thresholds:**
```python
CRITICAL_SWAP_PERCENT = 70        # Emit CRITICAL signal
WARNING_SWAP_PERCENT = 50         # Emit WARNING signal
CRITICAL_MEMORY_PERCENT = 85
WARNING_MEMORY_PERCENT = 70
CRITICAL_CPU_PERCENT = 90
WARNING_CPU_PERCENT = 80
```

**Resource Usage:**
- Memory: ~30MB
- Threads: 1 main + periodic collectors
- CPU: <1% (sampling overhead)

**Common Issues:**
- Not emitting signals → check threshold configuration
- High overhead → increase monitoring interval
- Stale data → verify daemon is running

---

### 3. Investigation Consumer (`investigation_consumer_daemon.py`)

**Purpose:** Asynchronous investigation processing (the memory-hungry one)

**Process:** `kloros-investigation-consumer.service`

**What it does:**
- Pulls investigation tasks from queue
- Queries reasoning LLM (deepseek-r1:7b) for analysis
- Maintains thread pool for concurrent processing
- Accumulates memory over time (known issue)

**ChemBus Signals Consumed:**
- `INVESTIGATION_THROTTLE_REQUEST` → reduces max_concurrent_investigations
- `INVESTIGATION_PRIORITY_UPDATE` → adjusts queue priority

**Configuration:**
- `max_concurrent_investigations`: Default 10, throttleable to 1
- `max_retries`: 3
- `timeout_seconds`: 300

**Resource Usage (Normal):**
- Memory: ~500MB baseline
- Threads: 10-50 (depends on concurrency)
- CPU: Variable (LLM inference)

**Resource Usage (Under Pressure):**
- Memory: Can grow to 5-10GB
- Threads: Can accumulate to 500+ if investigations stack
- Swap: Major contributor to swap pressure

**Common Issues:**
- Thread accumulation → restart service or throttle concurrency
- Memory leak → investigations not completing, threads held open
- Queue backup → too many investigations queued, not draining fast enough

**Remediation Actions:**
- Throttle: Emit `INVESTIGATION_THROTTLE_REQUEST` with `requested_concurrency: 1`
- Restart: `systemctl restart kloros-investigation-consumer.service`
- Clear queue: Not yet implemented (would require queue access)

---

### 4. ChemBus (Message Bus)

**Purpose:** Inter-process communication using ZeroMQ

**Architecture:**
- Publisher: `ChemPub` (sends signals)
- Subscriber: `ChemSub` (receives signals)
- Transport: ZeroMQ PUB/SUB pattern
- Endpoints: `ipc:///tmp/kloros_chembus.ipc` or TCP

**Signal Format:**
```python
{
    "signal": "AFFECT_RESOURCE_STRAIN",
    "ecosystem": "interoception",
    "intensity": 2.5,           # 0.0-5.0 scale
    "timestamp": 1700000000.0,
    "facts": {
        "cpu_percent": 85.0,
        "memory_percent": 72.0
    }
}
```

**Signal Intensity Levels:**
- 0.0-1.0: Informational
- 1.0-2.0: Noteworthy
- 2.0-3.0: Warning (triggers actions)
- 3.0-4.0: Critical (immediate action)
- 4.0-5.0: Emergency (system at risk)

**Common Signals:**
- `AFFECT_*`: Affective/emotional signals (high-level state)
- `VITALS_*`: Health monitoring signals
- `INVESTIGATION_*`: Investigation system signals
- `SKILL_*`: Skill execution signals

---

## Data Flows

### Memory Pressure Detection Flow
```
Interoception monitors swap
    ↓
Swap > 50% detected
    ↓
Emit AFFECT_MEMORY_PRESSURE (intensity=2.5)
    ↓
Cognitive Actions receives signal
    ↓
Checks cooldown (5 min)
    ↓
Executes optimize_performance()
    ↓
Detects swap > 10GB || mem > 70%
    ↓
Loads memory-optimization skill
    ↓
Queries SkillTracker for past effectiveness
    ↓
Sends to deepseek with problem context
    ↓
Receives action plan (JSON)
    ↓
SkillAutoExecutor executes if safe
    ↓
Collects metrics before/after
    ↓
Records outcome in skill_executions.db
    ↓
Emits SKILL_EXECUTION_COMPLETE
```

### Investigation Pressure Flow
```
User/system requests investigation
    ↓
Investigation queued in RabbitMQ/Redis
    ↓
Investigation consumer pulls task
    ↓
Creates new thread for processing
    ↓
Queries deepseek-r1:7b (allocates memory)
    ↓
Thread completes → should release memory
    ↓
BUT: Threads sometimes leak, accumulate
    ↓
Thread count grows: 50 → 200 → 500+
    ↓
Memory grows: 500MB → 2GB → 8GB
    ↓
Swap usage increases
    ↓
Interoception detects → emits AFFECT_RESOURCE_STRAIN
    ↓
Cognitive actions throttles investigations
    ↓
Thread growth slows but damage done
    ↓
Need restart to fully recover
```

## Process Inventory

Current KLoROS processes:
```bash
ps aux | grep -E "(cognitive_actions|interoception|investigation_consumer)" | grep -v grep

kloros  12345  /home/kloros/.venv/bin/python consciousness/cognitive_actions_subscriber.py
kloros  12346  /home/kloros/.venv/bin/python monitoring/interoception_daemon.py
kloros  12347  /home/kloros/.venv/bin/python investigations/investigation_consumer_daemon.py
```

Check process health:
```bash
systemctl status kloros-cognitive-actions.service
systemctl status kloros-interoception.service
systemctl status kloros-investigation-consumer.service
```

View recent logs:
```bash
sudo journalctl -u kloros-cognitive-actions.service --since "10 minutes ago"
sudo journalctl -u kloros-interoception.service --since "10 minutes ago"
sudo journalctl -u kloros-investigation-consumer.service --since "10 minutes ago"
```

## Health Metrics

**Normal State:**
- Swap usage: <30% (<4GB)
- Memory usage: <60% (<19GB of 32GB)
- CPU: <30%
- Investigation threads: <100
- Cognitive actions cooldown: Minimal skips

**Warning State:**
- Swap usage: 30-70% (4-10GB)
- Memory usage: 60-80% (19-25GB)
- CPU: 30-70%
- Investigation threads: 100-300
- Cognitive actions: Some skips due to cooldown

**Critical State:**
- Swap usage: >70% (>10GB)
- Memory usage: >80% (>25GB)
- CPU: >70%
- Investigation threads: >300
- Cognitive actions: Frequent interventions

**System at Risk:**
- Swap usage: >95% (>13GB)
- Memory usage: >90% (>29GB)
- System unresponsive
- OOM killer may activate
- Investigation consumer likely cause
