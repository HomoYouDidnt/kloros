# GPU Canary System - Hardening & Escalation

## Hardening Improvements Implemented

### 1. Port Collision Guard

**Problem**: If canary port (9011) is already in use, canary start would fail silently.

**Solution**: Auto-increment port detection (9011-9015)

```python
def _find_free_port() -> int:
    """Find a free port in range [CANARY_PORT_BASE, CANARY_PORT_BASE + MAX_OFFSET]."""
    for offset in range(CANARY_PORT_MAX_OFFSET + 1):
        port = CANARY_PORT_BASE + offset
        if not _can_listen(port):
            logger.info(f"Selected free canary port: {port}")
            return port
    
    logger.error(f"All canary ports busy ({CANARY_PORT_BASE}-{CANARY_PORT_BASE + CANARY_PORT_MAX_OFFSET})")
    return None
```

**Benefits**:
- Automatic failover to alternate ports
- Bounded search (9011-9015)
- Logged port selection for audit trail

### 2. Cooldown Enforcement

**Problem**: Without cooldown, rapid canary runs could exceed daily budget.

**Solution**: 6-hour cooldown between quiesced canaries (configurable via `KLR_CANARY_COOLDOWN_HOURS`)

```python
def _check_cooldown() -> tuple[bool, str]:
    """Check if we're within cooldown period since last canary."""
    cooldown_file = BUDGET_DIR / "last_canary.json"
    if not cooldown_file.exists():
        return (True, "No previous canary")
    
    last_run = data.get("timestamp", 0)
    elapsed_hours = (time.time() - last_run) / 3600.0
    
    if elapsed_hours < COOLDOWN_HOURS:
        remaining = COOLDOWN_HOURS - elapsed_hours
        return (False, f"Cooldown active: {remaining:.1f}h remaining")
    
    return (True, f"Cooldown satisfied: {elapsed_hours:.1f}h since last run")
```

**Cooldown file**: `/home/kloros/.kloros/maintenance/last_canary.json`

```json
{
  "timestamp": 1730234567.89,
  "date": "2025-10-29T14:30:00+00:00"
}
```

**Benefits**:
- Prevents budget exhaustion from rapid runs
- Only applies to quiesced path (spare GPU path has no cooldown)
- Returns clear error message when cooldown active

### 3. Service Name Verification

**Problem**: Code referenced `vllm.service` but production uses `judge.service`.

**Solution**: Updated all references to `judge.service`

```python
def _stop_prod_vllm() -> bool:
    """Stop production VLLM service."""
    logger.info("Stopping production VLLM (judge.service)")
    return _run(["sudo", "systemctl", "stop", "judge.service"]).returncode == 0
```

**Verification**:
```bash
systemctl status judge.service --no-pager | head -3
```

## Automatic Escalation Mechanism

### Overview

Automatically escalate from predictive to canary mode when the same symptom repeats N times in 24 hours.

**Policy**: 3 occurrences in 24 hours triggers escalation

### Components

#### 1. Escalation Manager (`/home/kloros/src/kloros/orchestration/escalation_manager.py`)

Tracks symptom history and manages escalation flags.

**Key Functions**:

```python
def record_symptom(subsystem: str, symptom: str, context: dict):
    """Record symptom occurrence for escalation tracking."""
    
def check_escalation_needed(subsystem: str, symptom: str) -> tuple[bool, int, str]:
    """Check if escalation is needed based on symptom history."""
    
def set_escalation_flag(reason: str, symptom_count: int):
    """Set flag to trigger canary mode for next maintenance window."""
    
def clear_escalation_flag():
    """Clear flag after successful canary run."""
```

#### 2. Symptom History

**File**: `/home/kloros/.kloros/flags/symptom_history.jsonl`

**Format**:
```json
{"timestamp": 1730234567.89, "subsystem": "vllm", "symptom": "oom_events", "context": {...}}
{"timestamp": 1730238167.89, "subsystem": "vllm", "symptom": "oom_events", "context": {...}}
{"timestamp": 1730241767.89, "subsystem": "vllm", "symptom": "oom_events", "context": {...}}
```

**Retention**: 24-hour rolling window

#### 3. Escalation Flag

**File**: `/home/kloros/.kloros/flags/escalate_canary.json`

**Format**:
```json
{
  "escalated": true,
  "reason": "Escalation triggered: 3 oom_events in last 24h (threshold: 3)",
  "timestamp": 1730234567.89,
  "symptom_count": 3
}
```

**Lifecycle**:
1. Observer detects symptom → records to history
2. Check history: 3+ occurrences → set escalation flag
3. Orchestrator checks flag → sets `KLR_CANARY_MODE=canary` for next run
4. After successful canary → clear flag, restore `MODE=predictive`

### Integration with D-REAM

**Observer Flow** (proposed):
```python
# In Observer when OOM detected
from src.kloros.orchestration.escalation_manager import record_symptom, should_escalate_to_canary

# Record symptom
record_symptom("vllm", "oom_events", {"count": oom_count, "timestamp": now})

# Check if escalation needed
escalate, reason = should_escalate_to_canary("vllm", "oom_events")

if escalate:
    logger.warning(f"Auto-escalation triggered: {reason}")
    # Orchestrator will pick up escalation flag on next run
```

**Orchestrator Flow** (proposed):
```python
# In Orchestrator before invoking ConfigTuningRunner
from src.kloros.orchestration.escalation_manager import check_escalation_flag, clear_escalation_flag

state = check_escalation_flag()
if state and state.escalated:
    # Temporarily set canary mode for this run only
    os.environ["KLR_CANARY_MODE"] = "canary"
    logger.warning(f"Running in canary mode due to: {state.reason}")
    
    # Run config tuning...
    result = runner.run(intent_data)
    
    # If successful, clear escalation flag
    if result.promoted:
        clear_escalation_flag()
        os.environ["KLR_CANARY_MODE"] = "predictive"  # Restore default
```

### Manual Testing

**Simulate symptom escalation**:
```bash
cd /home/kloros

# Record 3 symptoms
for i in {1..3}; do
    python3 src/kloros/orchestration/escalation_manager.py vllm oom_events
    sleep 1
done

# Check escalation flag
cat .kloros/flags/escalate_canary.json

# Clear flag
python3 << 'PYEOF'
import sys
sys.path.insert(0, '/home/kloros')
from src.kloros.orchestration.escalation_manager import clear_escalation_flag
clear_escalation_flag()
print("✓ Escalation flag cleared")
PYEOF
```

## Day-1 Acceptance Test

**Script**: `/home/kloros/tools/day1_acceptance.sh`

**What it tests**:
1. Predictive mode sanity (no downtime)
2. Budget ledger creation and limits
3. Lock mechanism (free/held state)
4. Configuration verification
5. Audit trail setup
6. Unit tests (8 tests)

**Run**:
```bash
sudo -u kloros bash /home/kloros/tools/day1_acceptance.sh
```

**Expected output**:
```
==========================================
Day-1 Acceptance: ALL TESTS PASSED ✓
==========================================
```

## Monitoring Commands

### Budget Usage
```bash
# Check today's budget
jq . /home/kloros/.kloros/maintenance/gpu_budget_$(date +%Y%m%d).json

# Example output:
{
  "seconds_used": 42.5
}
```

### Cooldown Status
```bash
# Check last canary run
jq . /home/kloros/.kloros/maintenance/last_canary.json

# Example output:
{
  "timestamp": 1730234567.89,
  "date": "2025-10-29T14:30:00+00:00"
}

# Check if cooldown active (manual calculation)
python3 << 'PYEOF'
import json, time
from pathlib import Path

cooldown_file = Path("/home/kloros/.kloros/maintenance/last_canary.json")
if cooldown_file.exists():
    data = json.loads(cooldown_file.read_text())
    elapsed_h = (time.time() - data["timestamp"]) / 3600.0
    cooldown_h = 6  # from KLR_CANARY_COOLDOWN_HOURS
    
    if elapsed_h < cooldown_h:
        print(f"⚠️  Cooldown active: {cooldown_h - elapsed_h:.1f}h remaining")
    else:
        print(f"✓ Cooldown satisfied: {elapsed_h:.1f}h since last run")
else:
    print("✓ No previous canary (cooldown not applicable)")
PYEOF
```

### Escalation Status
```bash
# Check escalation flag
if [ -f /home/kloros/.kloros/flags/escalate_canary.json ]; then
    echo "⚠️  Escalation flag active:"
    jq . /home/kloros/.kloros/flags/escalate_canary.json
else
    echo "✓ No escalation flag (predictive mode)"
fi

# Check symptom history (last 5 entries)
tail -5 /home/kloros/.kloros/flags/symptom_history.jsonl | jq -c .
```

### Audit Trail
```bash
# Live monitoring
tail -f /home/kloros/out/orchestration/epochs/gpu_canary_$(date +%Y%m%d).jsonl

# Count events by type today
jq -r '.event' /home/kloros/out/orchestration/epochs/gpu_canary_$(date +%Y%m%d).jsonl | sort | uniq -c

# Example output:
#   2 canary_start
#   1 spare_gpu_path_selected
#   1 canary_spare_started
#   1 canary_stopped
```

## Production Checklist

Before going live:

- [x] Day-1 acceptance test passes
- [x] Port collision guard implemented
- [x] Cooldown enforcement active
- [x] judge.service name verified
- [x] Escalation mechanism ready
- [ ] Observer integration (record symptoms)
- [ ] Orchestrator integration (check escalation flags)
- [ ] Prometheus alerts configured
- [ ] Grafana dashboard for budget/cooldown/escalation

## Prometheus Metrics (Proposed)

Export these metrics for monitoring:

```python
# In gpu_canary_runner.py (proposed)
from prometheus_client import Counter, Gauge, Histogram

canary_runs_total = Counter('kloros_canary_runs_total', 'Total canary runs', ['result'])
canary_seconds_used = Gauge('kloros_gpu_canary_seconds_used', 'Seconds used today')
canary_restore_fail_total = Counter('kloros_canary_restore_fail_total', 'Failed restores')
canary_duration_seconds = Histogram('kloros_canary_duration_seconds', 'Canary duration')

# In run_canary():
canary_runs_total.labels(result='success').inc()
canary_seconds_used.set(_read_budget()["seconds_used"])
canary_duration_seconds.observe(elapsed)
```

## Safety Guarantees

All hardening improvements maintain the original safety guarantees:

1. **Bounded downtime**: Max 60s/night (enforced by budget + cooldown)
2. **Maintenance window**: 03:00-07:00 ET only (enforced by window check)
3. **Restore SLA**: 15s max (enforced by heartbeat check)
4. **Rate limiting**: Max 3 runs/24h + 6h cooldown per subsystem
5. **Audit trail**: All operations logged to JSONL

**New guarantees**:
- **Port collision**: Bounded failover (9011-9015)
- **Cooldown**: Minimum 6h between quiesced canaries
- **Auto-escalation**: Triggered only after 3+ symptoms in 24h

## Files Created/Modified

### Created
- `/home/kloros/src/kloros/orchestration/escalation_manager.py` - Auto-escalation logic
- `/home/kloros/tools/day1_acceptance.sh` - Acceptance test script
- `/home/kloros/docs/GPU_CANARY_HARDENING.md` - This document

### Modified
- `/home/kloros/src/spica/gpu_canary_runner.py`:
  - Added `_find_free_port()` for port collision guard
  - Added `_check_cooldown()` and `_record_canary_run()` for cooldown
  - Updated `_start_canary_vllm()` to return `(success, port)` tuple
  - Updated `run_canary()` to check cooldown and use dynamic port
  - Fixed service name references to `judge.service`

### Configuration
- Environment variables in `.kloros_env`:
  - `KLR_CANARY_COOLDOWN_HOURS=6` (new)
  - Port range defined by `KLR_CANARY_PORT` base (9011)

## Summary

The GPU canary system is now production-hardened with:

✓ **Port collision guard** (9011-9015 auto-failover)  
✓ **Cooldown enforcement** (6h between quiesced canaries)  
✓ **Service name verified** (judge.service)  
✓ **Auto-escalation mechanism** (3 symptoms → canary mode)  
✓ **Day-1 acceptance test** (all tests passing)

The system is ready for tonight's maintenance window. Default mode remains **predictive** (no downtime), with automatic escalation to **canary mode** when needed.
