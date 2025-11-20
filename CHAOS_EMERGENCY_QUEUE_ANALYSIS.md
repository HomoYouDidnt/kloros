# Chaos Emergency Queue Backlog Analysis
**Date**: 2025-11-19 00:30 EST
**Issue**: Investigation timeouts filling emergency queue to capacity (60/60)

---

## Executive Summary

**Root Cause**: Chaos scenarios for disabled systems (D-REAM, TTS) are failing to heal, generating investigation questions that timeout because the target systems aren't running.

**Impact**: Emergency queue stuck at 60/60 capacity, all slots filled with uninvestigatable chaos healing failures.

**Solution**: Disable chaos scenarios for systems that are disabled/refactoring (D-REAM, TTS).

---

## Problem Flow

```
1. Chaos scenarios run for D-REAM/TTS targets
   ↓
2. Scenarios fail to heal (systems disabled)
   ↓
3. Chaos monitor emits CAPABILITY_GAP signals
   ↓
4. Investigation questions created: "chaos.healing_failure.{spec_id}"
   ↓
5. Investigation consumer tries to investigate
   ↓
6. Investigations timeout after 300s (no target system to investigate)
   ↓
7. Timed-out investigations queued as EMERGENCY
   ↓
8. Emergency queue fills to 60 (max capacity)
   ↓
9. Queue stuck - new failures can't be processed
```

---

## Data Analysis

### Chaos Scenario Results (Last 1000 Entries)

**Successfully Healing** (2 scenarios):
- `validator_low_context` (validator) - healed=true
- `validator_ultra_strict` (validator) - healed=true

**Failing to Heal** (11 scenarios - ALL D-REAM/TTS related):

| Scenario | Target | Count | Status |
|----------|--------|-------|--------|
| quota_exceeded_synth | rag.synthesis | 17 | healed=false |
| synth_timeout_hard | rag.synthesis | 3 | healed=false |
| synth_intermittent | rag.synthesis | 3 | healed=false |
| synth_timeout_easy | rag.synthesis | 2 | healed=false |
| composite_validator_timeout | validator+rag.synthesis | 3 | healed=false |
| tts_timeout | tts | 3 | healed=false |
| tts_latency_spike | tts | 2 | healed=false |
| beep_echo | audio.beep | 3 | healed=false |
| cpu_oom | dream.domain:cpu | 3 | healed=false |
| gpu_oom_dream | dream.domain:cpu | 3 | healed=false |
| corrupt_dream_candidate | dream.candidate | 3 | healed=false |

**Pattern**: All failing scenarios target D-REAM components (RAG synthesis, dream domains, dream candidates) or TTS subsystem.

---

## Investigation Timeout Evidence

Sample investigation for `chaos.healing_failure.tts_timeout`:

```json
{
  "source": "runtime_logs",
  "evidence_type": "service_status",
  "content": {
    "service": "kloros-orchestrator",
    "active": false,
    "enabled": false,
    "output": ""
  }
}
```

**Finding**: Investigation consumer checks if orchestrator is running, finds it's disabled, cannot gather meaningful evidence, times out after 300s.

---

## Current Emergency Queue Status

```
active emergencies: 60 (FULL)
```

Recent emergency entries (last 10 minutes):
- chaos.healing_failure.synth_timeout_hard
- chaos.healing_failure.composite_validator_timeout
- chaos.healing_failure.gpu_oom_dream
- chaos.healing_failure.quota_exceeded_synth
- chaos.healing_failure.synth_intermittent
- chaos.healing_failure.beep_echo
- chaos.healing_failure.tts_timeout
- chaos.healing_failure.cpu_oom
- chaos.healing_failure.corrupt_dream_candidate

**Observation**: Queue is at capacity (60), new failures continue being queued but count stays at 60 (FIFO replacement).

---

## Impact Assessment

### Resource Waste
- **Investigation time**: 300s × 60 = 18,000s (5 hours) of accumulated timeout time
- **CPU cycles**: Wasted on uninvestigatable questions
- **Queue capacity**: Emergency queue full, potentially blocking real emergencies

### Missing Decomposition Strategy
```
[investigation_consumer] No decomposition strategy for question type: chaos.healing_failure.composite_validator_timeout
```

When investigations timeout, the system tries to decompose them but has no decomposition strategy for chaos healing failures.

---

## Root Cause

### Why are chaos scenarios still running for disabled systems?

**Chaos scenarios from yesterday** (2025-11-18 14:*) generated healing failure signals that:
1. Created investigation questions
2. Those questions are still being processed today
3. They timeout because target systems are disabled
4. Timed-out investigations fill emergency queue

The chaos scenarios themselves may not be actively running NOW, but the **healing failure signals from past runs** are still generating investigation questions.

---

## Recommended Solutions

### Option 1: Disable D-REAM/TTS Chaos Scenarios (RECOMMENDED)

Since D-REAM and TTS are disabled/refactoring, chaos scenarios for these targets cannot heal and should be disabled.

**Implementation**:
- Find where chaos scenarios are configured
- Disable/comment out scenarios targeting:
  - `rag.synthesis`
  - `dream.domain:*`
  - `dream.candidate`
  - `tts`
  - `audio.beep`
  - `validator+rag.synthesis` (composite)

**Benefit**: Prevents future waste of investigation resources on uninvestigatable failures.

### Option 2: Filter Known-Disabled Systems in Chaos Monitor

Modify `/home/kloros/src/kloros/monitors/chaos_monitor_daemon.py` to:
- Check if target system is in disabled list
- Skip emitting CAPABILITY_GAP for disabled system healing failures
- Log as INFO instead: "Healing failure expected for disabled system: {spec_id}"

**Disabled systems list**:
- D-REAM (KLR_ENABLE_DREAM_EVOLUTION=0)
- TTS (system not running)
- RAG synthesis (part of D-REAM)

### Option 3: Clear Emergency Queue Backlog

Immediate relief:
- Restart investigation-consumer service to clear in-memory emergency queue
- This won't prevent new chaos healing failures from being queued

**Command**:
```bash
sudo systemctl restart kloros-investigation-consumer.service
```

**Note**: This is a temporary fix - Option 1 or 2 is needed to prevent recurrence.

### Option 4: Add Decomposition Strategy for Chaos Healing Failures

Add a decomposition strategy in investigation consumer for `chaos.healing_failure.*` question types to break them into smaller investigatable pieces.

**Complexity**: HIGH - requires understanding why healing failed, which is impossible if target system is disabled.

---

## Recommended Action Plan

1. **Immediate**: Clear emergency queue (Option 3)
   ```bash
   sudo systemctl restart kloros-investigation-consumer.service
   ```

2. **Short-term**: Filter disabled systems in chaos monitor (Option 2)
   - Modify chaos_monitor_daemon.py
   - Check environment variables (KLR_ENABLE_DREAM_EVOLUTION, etc.)
   - Skip CAPABILITY_GAP emission for disabled targets

3. **Long-term**: Disable chaos scenarios for disabled systems (Option 1)
   - Find chaos scenario configuration
   - Comment out D-REAM/TTS scenarios
   - Re-enable when systems are back online

---

## Files Involved

- `/home/kloros/src/kloros/monitors/chaos_monitor_daemon.py` - Emits CAPABILITY_GAP for healing failures
- `/home/kloros/.kloros/chaos_history.jsonl` - Chaos experiment results
- Investigation consumer (service: kloros-investigation-consumer.service)
- Emergency queue (in-memory, capacity: 60)

---

## Verification Commands

**Check emergency queue status**:
```bash
sudo journalctl --since "5 minutes ago" --no-pager | grep "active emergencies"
```

**Check chaos scenario targets**:
```bash
tail -100 /home/kloros/.kloros/chaos_history.jsonl | jq -r '.target' | sort | uniq
```

**Check investigation timeouts**:
```bash
sudo journalctl --since "30 minutes ago" --no-pager | grep "TIMEOUT" | grep "chaos.healing_failure"
```

---

## Conclusion

The emergency queue is stuck at capacity (60/60) because chaos scenarios for disabled systems (D-REAM, TTS) are generating healing failure signals that create uninvestigatable questions. These investigations timeout after 300s and fill the emergency queue.

**Immediate action**: Restart investigation consumer to clear backlog.
**Permanent fix**: Either disable chaos scenarios for disabled systems OR filter them in chaos monitor.

The validator-only scenarios (validator_low_context, validator_ultra_strict) are healing successfully, confirming the issue is specific to D-REAM/TTS targets.
