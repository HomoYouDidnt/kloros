# SystemHealthMonitor Deprecation and Migration Notes

**Date**: 2025-11-26
**Status**: DEPRECATED (warnings added, not deleted yet)
**Replacement**: InteroceptionDaemon

## Overview

SystemHealthMonitor has been deprecated in favor of InteroceptionDaemon, which provides better architecture (consciousness domain), UMN signal emission, appraisal system integration, and component heartbeat monitoring.

## Files Modified

1. `/home/kloros/src/self_heal/system_monitor.py`
   - Added deprecation warning to module docstring
   - Added comprehensive deprecation notice to class docstring
   - Added runtime DeprecationWarning to `__init__()` method
   - Added deprecation print statements

2. `/home/kloros/src/self_heal/__init__.py`
   - Added inline comment marking SystemHealthMonitor as deprecated

3. `/home/kloros/docs/audits/integration_action_plan.md`
   - Struck through SystemHealthMonitor initialization task
   - Added note about deprecation in favor of InteroceptionDaemon

## Callers Analysis

**Result**: No active callers found

- No Python files instantiate `SystemHealthMonitor()`
- No config files reference it
- Only exported via `self_heal.__init__.py` but not used elsewhere

## Functionality Comparison

### Overlap (Already in InteroceptionDaemon)

- ✅ Monitors swap usage with thresholds
- ✅ Monitors memory/RAM usage
- ✅ Uses psutil for system metrics
- ✅ Runs in background monitoring loop
- ✅ Thread counting

### SystemHealthMonitor Unique Features (Need Migration)

#### 1. `_check_duplicate_processes()` - Lines 123-144

**Function**: Checks for duplicate `kloros_voice` processes and triggers healing

**Implementation**:
```python
def _check_duplicate_processes(self):
    """Check for duplicate kloros_voice processes."""
    kloros_procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        cmdline = ' '.join(proc.info['cmdline'] or [])
        if 'kloros_voice' in cmdline:
            kloros_procs.append(proc)

    if len(kloros_procs) > 1:
        self._trigger_healing(
            kind="duplicate_process",
            severity="warning",
            context={"process_count": len(kloros_procs)}
        )
```

**Migration Path**:
- Add similar process detection to InteroceptionDaemon
- Emit `CAPABILITY_GAP` or new signal type `PROCESS_DUPLICATE` via UMN
- Alternative: Add to a new process health monitor that emits UMN signals

#### 2. `_check_stuck_processes()` - Lines 146-163

**Function**: Checks for processes stuck in D state (uninterruptible disk sleep)

**Implementation**:
```python
def _check_stuck_processes(self) -> int:
    """Check for processes stuck in D state.

    Returns:
        Number of stuck processes found
    """
    stuck_count = 0
    for proc in psutil.process_iter(['status', 'name']):
        if proc.info['status'] == psutil.STATUS_DISK_SLEEP:
            stuck_count += 1
    return stuck_count
```

**Usage**: Triggers healing if `stuck_count > 3`

**Migration Path**:
- Add to InteroceptionDaemon's `get_system_metrics()`
- Emit `AFFECT_RESOURCE_STRAIN` when stuck process count exceeds threshold
- Consider adding process name information to facts

#### 3. Direct Playbook Execution - Lines 165-200

**Function**: Loads and executes healing playbooks directly

**Components**:
- `load_playbooks()` from `/home/kloros/self_heal_playbooks.yaml`
- `HealExecutor` for execution
- `Guardrails` for safety checks
- `HealthProbes` for validation
- `_trigger_healing()` method that:
  - Deduplicates events via `_events_triggered` list
  - Finds matching playbooks
  - Executes playbook
  - Logs success/failure

**Migration Path**:
- InteroceptionDaemon emits UMN signals instead of executing directly
- A separate healing consumer (possibly in self_heal module) should:
  - Subscribe to InteroceptionDaemon's affective signals
  - Load playbooks
  - Execute healing actions
  - This follows proper separation of concerns (monitoring vs. healing)

## InteroceptionDaemon Advantages

1. **Better Architecture**: Lives in consciousness domain where self-monitoring belongs
2. **UMN Integration**: Emits signals for system-wide coordination
3. **Affective States**: Integrates with appraisal system for emotional awareness
4. **Component Health**: Monitors heartbeats from all zooids
5. **Investigation Tracking**: Monitors investigation success/failure rates
6. **Consciousness Modes**: Tracks affective lobotomy state
7. **More Sophisticated**: Uses `InteroceptiveMonitor` with exponential smoothing

## Migration Priority

### High Priority (Should Migrate Soon)

1. **Stuck Process Detection**: Important for system health, currently not monitored
2. **Duplicate Process Detection**: Important for kloros_voice stability

### Medium Priority (Can Wait)

3. **Direct Playbook Execution**: Better handled by separate healing consumer

## Recommended Migration Plan

### Phase 1: Add to InteroceptionDaemon

```python
def check_process_health(self) -> Dict[str, Any]:
    """Check for duplicate and stuck processes."""
    # Duplicate kloros_voice processes
    kloros_procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'kloros_voice' in cmdline:
                kloros_procs.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Stuck processes in D state
    stuck_count = 0
    stuck_names = []
    for proc in psutil.process_iter(['status', 'name']):
        try:
            if proc.info['status'] == psutil.STATUS_DISK_SLEEP:
                stuck_count += 1
                stuck_names.append(proc.info['name'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Emit signals if thresholds exceeded
    if len(kloros_procs) > 1:
        self.chem_pub.emit(
            signal="PROCESS_DUPLICATE",
            ecosystem="consciousness",
            intensity=1.5,
            facts={
                "process_name": "kloros_voice",
                "process_count": len(kloros_procs),
                "reason": "Multiple kloros_voice processes detected"
            }
        )

    if stuck_count > 3:
        self.chem_pub.emit(
            signal="AFFECT_RESOURCE_STRAIN",
            ecosystem="consciousness",
            intensity=1.5,
            facts={
                "stuck_process_count": stuck_count,
                "stuck_processes": stuck_names[:5],  # Top 5
                "reason": "High number of processes stuck in D state"
            }
        )

    return {
        "duplicate_kloros_voice": len(kloros_procs),
        "stuck_processes": stuck_count,
        "stuck_process_names": stuck_names[:5]
    }
```

### Phase 2: Create Healing Consumer (Optional)

If direct playbook execution is needed:

```python
# In src/self_heal/healing_consumer.py
class HealingConsumer:
    """Listens to UMN affective signals and executes healing playbooks."""

    def __init__(self):
        self.playbooks = load_playbooks("/home/kloros/self_heal_playbooks.yaml")
        self.executor = HealExecutor(Guardrails(), HealthProbes())

        # Subscribe to affective signals
        self.sub = UMNSub(
            topic="AFFECT_*",
            on_json=self.handle_affective_signal,
            zooid_name="healing_consumer",
            niche="healing"
        )
```

## Testing

### Deprecation Warning Test

```bash
python3 -c "
import warnings
warnings.simplefilter('always', DeprecationWarning)
import sys
sys.path.insert(0, '/home/kloros/src')
from self_heal import SystemHealthMonitor

class MockKLoROS:
    pass

monitor = SystemHealthMonitor(MockKLoROS())
"
```

**Expected Output**: DeprecationWarning printed to stderr

### Syntax Validation

```bash
python3 -m py_compile /home/kloros/src/self_heal/system_monitor.py
python3 -m py_compile /home/kloros/src/self_heal/__init__.py
```

**Status**: ✅ Both files pass syntax validation

## Timeline

- **2025-11-26**: Deprecation warnings added (this document)
- **Target for Migration**: Within 1-2 weeks
- **Target for Deletion**: After migration complete and verified in production

## References

- InteroceptionDaemon: `/home/kloros/src/kloros/mind/consciousness/interoception_daemon.py`
- SystemHealthMonitor: `/home/kloros/src/self_heal/system_monitor.py`
- Self-Heal Playbooks: `/home/kloros/self_heal_playbooks.yaml`
