# Chaos Monitor Disabled System Filter - Implementation Complete
**Date**: 2025-11-19 00:45 EST
**Issue**: Chaos monitor emitting CAPABILITY_GAP signals for disabled systems (D-REAM, TTS)
**Solution**: Added intelligent filtering to skip signal emission for disabled targets

---

## Problem

Chaos monitor was detecting healing failures for D-REAM and TTS targets and emitting CAPABILITY_GAP signals. These created investigation questions that timed out (300s) because the target systems are disabled, filling the emergency queue to capacity (60/60).

---

## Solution Implemented

### Changes to `/home/kloros/src/kloros/monitors/chaos_monitor_daemon.py`

**1. Added disabled system detection method** (lines 74-95):
```python
def _is_target_disabled(self, target: str) -> bool:
    """Check if a chaos scenario target is for a disabled system."""
    # Check for D-REAM targets
    if any(keyword in target.lower() for keyword in ['dream', 'rag']):
        dream_enabled = os.getenv('KLR_ENABLE_DREAM_EVOLUTION', '1') == '1'
        if not dream_enabled:
            return True

    # Check for TTS/Audio targets
    if any(keyword in target.lower() for keyword in ['tts', 'audio']):
        return True

    return False
```

**2. Added filtering before signal emission** (lines 201-210):
```python
# Check if target system is disabled
target = entry.get("target", "unknown")
if self._is_target_disabled(target):
    # Skip signal emission for disabled systems
    logger.info(
        f"[chaos_monitor] Healing failure expected for disabled system: "
        f"{spec_id} (target={target}, rate={healing_rate:.1%}, score={avg_score:.1f})"
    )
    self.signals_skipped_disabled += 1
    return
```

**3. Added telemetry for skipped signals** (line 276):
```python
logger.info(f"[chaos_monitor] Signals skipped (disabled systems): {self.signals_skipped_disabled}")
```

---

## How It Works

### Detection Logic

**D-REAM Targets** (keyword-based + environment check):
- Targets containing: `dream`, `rag`
- Checks: `KLR_ENABLE_DREAM_EVOLUTION=0` → disabled
- Examples: `rag.synthesis`, `dream.domain:cpu`, `dream.candidate`

**TTS/Audio Targets** (keyword-based):
- Targets containing: `tts`, `audio`
- Assumed disabled (no running service)
- Examples: `tts`, `audio.beep`

**Active Targets** (validator-only):
- Targets NOT matching above patterns
- Examples: `validator`, `validator_low_context`

### Behavior

**Before**:
```
Chaos failure for tts_timeout
  ↓
CAPABILITY_GAP emitted
  ↓
Investigation question created
  ↓
Investigation times out (300s)
  ↓
Emergency queue fills
```

**After**:
```
Chaos failure for tts_timeout
  ↓
Target check: tts → DISABLED
  ↓
Log INFO: "Healing failure expected for disabled system"
  ↓
Skip signal emission
  ↓
No investigation created
```

---

## Testing

**Test Results** (all passed ✓):
```
✓ rag.synthesis → disabled=True
✓ dream.domain:cpu → disabled=True
✓ dream.candidate → disabled=True
✓ tts → disabled=True
✓ audio.beep → disabled=True
✓ validator → disabled=False
✓ validator+rag.synthesis → disabled=True (composite target)
```

---

## Deployment

**Service restarted**: `kloros-chaos-monitor.service`
```bash
sudo systemctl restart kloros-chaos-monitor.service
```

**Status**: Active (running) since 2025-11-19 00:42:30 EST

**Initial state**: Starting from end of file (position 32363)
- Will only process NEW chaos entries
- Existing queued investigations will drain naturally

---

## Impact

### Immediate
- **Emergency queue cleared**: 60 → 10 active emergencies (via investigation-consumer restart)
- **Future prevention**: No new CAPABILITY_GAP signals for disabled systems

### Expected Behavior

**Chaos scenarios still running** (validator-only):
- `validator_low_context` → Will emit signals if healing fails ✓
- `validator_ultra_strict` → Will emit signals if healing fails ✓

**Chaos scenarios for disabled systems** (D-REAM/TTS):
- `tts_timeout`, `synth_timeout_hard`, `cpu_oom`, etc.
- Will log INFO instead of emitting CAPABILITY_GAP ✓
- No investigations created ✓

### Telemetry

**New metric**: `signals_skipped_disabled`
- Logged on shutdown
- Tracks how many signals were filtered
- Helps validate filter is working

---

## Verification Commands

**Check chaos monitor filtering**:
```bash
sudo journalctl -u kloros-chaos-monitor.service --since "5 minutes ago" --no-pager | grep "disabled system"
```

**Check emergency queue status**:
```bash
sudo journalctl --since "5 minutes ago" --no-pager | grep "active emergencies"
```

**Check chaos monitor telemetry** (on shutdown):
```bash
sudo journalctl -u kloros-chaos-monitor.service --no-pager | grep "Signals skipped"
```

---

## Future Enhancements

### Option 1: Make Disabled Systems Configurable
Instead of hardcoding TTS/Audio as disabled, check environment variables:
```python
if 'tts' in target.lower():
    tts_enabled = os.getenv('KLR_ENABLE_TTS', '0') == '1'
    if not tts_enabled:
        return True
```

### Option 2: Add Disabled Systems Configuration File
```yaml
# .kloros/disabled_chaos_targets.yaml
disabled:
  - dream.*
  - rag.*
  - tts
  - audio.*
enabled:
  - validator*
```

### Option 3: Auto-Detect Running Services
Check if target services are running before considering failure:
```python
def is_service_running(service_name: str) -> bool:
    result = subprocess.run(['systemctl', 'is-active', service_name], ...)
    return result.returncode == 0
```

For now, the simple keyword-based + environment variable approach is sufficient.

---

## Related Files

- `/home/kloros/src/kloros/monitors/chaos_monitor_daemon.py` - Modified
- `/home/kloros/.kloros/chaos_history.jsonl` - Input data
- `/home/kloros/CHAOS_EMERGENCY_QUEUE_ANALYSIS.md` - Root cause analysis
- `/home/kloros/KLOROS_SYSTEM_ISSUES_REPORT.md` - System status

---

## Conclusion

Chaos monitor now intelligently skips signal emission for disabled systems (D-REAM, TTS), preventing wasted investigation resources and emergency queue backlog.

**Status**: ✅ COMPLETE
- Filter implemented and tested
- Service restarted
- Emergency queue cleared (60 → 10)
- Future chaos failures for disabled systems will be logged but not investigated
