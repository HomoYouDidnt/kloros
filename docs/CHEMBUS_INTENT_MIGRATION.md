# ChemBus Intent Migration Guide

**Migration Status**: In Progress
**Created**: 2025-11-17
**Purpose**: Document mapping of file-based intents to direct ChemBus signal emission

## Overview

KLoROS is migrating from file-based intent routing to pure ChemBus signal emission. Currently, components write intent JSON files to `/home/kloros/.kloros/intents/`, which `intent_router.py` watches and converts to ChemBus signals. The target architecture eliminates this transitional layer.

### Current State

**Intent Files in Queue**: 44,638 files (as of 2025-11-17 16:11)
**Intent Router Status**: Active (running), processing ~100 files/minute
**Directory Size**: 488KB

## Intent Type to ChemBus Signal Mapping

### Curiosity Investigation Intents

All curiosity-related intents map to **`Q_CURIOSITY_INVESTIGATE`** signal:

| Intent Type | ChemBus Signal | Priority | Ecosystem | Source File |
|-------------|----------------|----------|-----------|-------------|
| `curiosity_investigate` | `Q_CURIOSITY_INVESTIGATE` | 6 | introspection | curiosity_processor.py:223 |
| `curiosity_propose_fix` | `Q_CURIOSITY_INVESTIGATE` | 7 | introspection | curiosity_processor.py:220 |
| `curiosity_find_substitute` | `Q_CURIOSITY_INVESTIGATE` | 5 | introspection | curiosity_processor.py:226 |
| `curiosity_explore` | `Q_CURIOSITY_INVESTIGATE` | 4 | introspection | curiosity_processor.py:229 |
| `discover.module` | `Q_CURIOSITY_INVESTIGATE` | normal | introspection | intent_router.py:66 |
| `reinvestigate` | `Q_CURIOSITY_INVESTIGATE` | normal | introspection | intent_router.py:66 |

**Signal Payload Structure**:
```python
{
    "question": str,           # The investigation question
    "question_id": str,        # Unique question identifier
    "priority": str,           # "critical" | "high" | "normal" | "low"
    "evidence": List[str],     # Supporting evidence
    "hypothesis": str,         # Working hypothesis
    "capability_key": str,     # Capability being investigated
    "action_class": str        # "investigate" | "propose_fix" | "find_substitute" | "explore"
}
```

### Integration & Remediation Intents

| Intent Type | ChemBus Signal | Priority | Ecosystem | Source File |
|-------------|----------------|----------|-----------|-------------|
| `integration_fix` | `Q_INTEGRATION_FIX` | 9 | queue_management | curiosity_processor.py:1412 |
| `spica_spawn_request` | `Q_SPICA_SPAWN` | 8 | experimentation | curiosity_processor.py:1452 |

**Q_INTEGRATION_FIX Payload**:
```python
{
    "reason": str,             # Description of integration issue
    "priority": int,           # 9 (always high priority)
    "hypothesis": str,         # Root cause hypothesis
    "suggested_fix": Dict,     # Fix configuration
    "domain": str              # Domain context
}
```

**Q_SPICA_SPAWN Payload**:
```python
{
    "reason": str,             # Reason for spawning SPICA
    "priority": int,           # 8 (default)
    "config": Dict,            # SPICA configuration
    "timeout_seconds": int     # Execution timeout
}
```

### Special Cases

#### Scanner Execution

**Intent Type**: `run_scanner`
**Action**: Direct subprocess execution (not converted to signal)
**Handler**: intent_router.py:85-117

```python
subprocess.run([
    "/home/kloros/.venv/bin/python3",
    "-m",
    f"src.registry.capability_scanners.{scanner_name}_scanner"
], timeout=60)
```

#### Alert Intents (UNMAPPED)

**Intent Type**: `alert_gpu_oom`
**Status**: ⚠️ NOT CURRENTLY MAPPED
**Issue**: Causes dead letter queue entries
**Recommendation**: Create `Q_GPU_OOM_ALERT` signal or map to existing alert signal

## Migration Strategy

### Phase 1: Mapping Completion ✅

- [x] Identify all intent types currently in use
- [x] Map to existing ChemBus signals
- [x] Document unmapped intent types
- [x] Create this migration guide

### Phase 2: Code Conversion 🔄

Replace file writes with direct signal emission:

**Before (File-based)**:
```python
intent = {
    "intent_type": "curiosity_investigate",
    "priority": 6,
    "data": {
        "question": "Why is service failing?",
        "question_id": "q_1234",
        "evidence": ["Error log X"],
        "hypothesis": "Resource exhaustion"
    }
}
intent_path = INTENT_DIR / f"{ts}_{intent['intent_type']}_{sha}.json"
intent_path.write_text(json.dumps(intent))
```

**After (Direct ChemBus)**:
```python
from kloros.orchestration.chem_bus_v2 import ChemPub

chem_pub = ChemPub()
chem_pub.emit(
    signal="Q_CURIOSITY_INVESTIGATE",
    ecosystem="introspection",
    intensity=1.0,
    facts={
        "question": "Why is service failing?",
        "question_id": "q_1234",
        "priority": "normal",
        "evidence": ["Error log X"],
        "hypothesis": "Resource exhaustion",
        "action_class": "investigate"
    }
)
```

### Phase 3: Deprecation Plan 📋

1. **Convert all intent writers**:
   - `curiosity_processor.py:_write_intent_file()` (primary source)
   - Search for other `INTENT_DIR.write_text()` calls

2. **Test signal flow**:
   - Verify subscribers receive signals correctly
   - Monitor for dropped messages
   - Validate payload formats

3. **Remove intent_router**:
   - Stop `kloros-intent-router.service`
   - Archive `/home/kloros/.kloros/intents/` directory
   - Remove `intent_router.py` from codebase
   - Update systemd dependencies

4. **Clean up**:
   - Remove `INTENT_DIR` references
   - Delete intent file generation code
   - Update documentation

## Code Locations

### Intent Writers

| File | Function | Line | Intent Types |
|------|----------|------|--------------|
| `curiosity_processor.py` | `_write_intent_file()` | 1273 | All curiosity types |
| `curiosity_processor.py` | Integration fix write | 1511 | `integration_fix` |
| `curiosity_processor.py` | SPICA spawn write | 1533 | `spica_spawn_request` |

### Intent Router (To Be Removed)

| File | Purpose | Status |
|------|---------|--------|
| `intent_router.py` | Watch intent directory, convert to signals | ⚠️ Transitional |
| `kloros-intent-router.service` | Systemd service | ⚠️ To be stopped |

## Testing Checklist

- [ ] Verify all ChemSub subscribers are active
- [ ] Test Q_CURIOSITY_INVESTIGATE signal emission
- [ ] Test Q_INTEGRATION_FIX signal emission
- [ ] Test Q_SPICA_SPAWN signal emission
- [ ] Monitor for signal delivery failures
- [ ] Validate payload compatibility with existing subscribers
- [ ] Ensure no message loss during transition
- [ ] Test priority-based routing still works
- [ ] Verify all intent writers converted
- [ ] Confirm no new intent files being created
- [ ] Archive existing intent backlog
- [ ] Remove intent_router service dependency

## Risks & Mitigation

### Risk: Message Loss During Transition

**Mitigation**:
- Keep intent_router running during initial deployment
- Monitor both file creation and signal emission
- Verify double-delivery doesn't cause issues

### Risk: Payload Format Mismatch

**Mitigation**:
- Document expected payload formats
- Test all subscriber handlers
- Use schema validation where possible

### Risk: Priority Semantics Change

**Mitigation**:
- Map numeric priorities (4-10) to string priorities ("low", "normal", "high", "critical")
- Verify curiosity_processor priority queue still works

### Risk: Scanner Execution Pattern

**Mitigation**:
- Decide if scanner execution should become a signal
- Or maintain as direct subprocess call
- Document decision rationale

## Next Steps

1. Complete Phase 2: Convert `curiosity_processor._write_intent_file()` to direct signal emission
2. Map unmapped intent types (`alert_gpu_oom`, etc.)
3. Test signal flow end-to-end
4. Archive intent file backlog (44k+ files)
5. Remove intent_router once verified stable

## References

- **CHEM_PROXY_MIGRATION.md**: Documents completed proxy consolidation
- **chem_proxy.py**: ZMQ forwarder (XSUB/XPUB pattern)
- **chem_bus_v2.py**: ChemSub/ChemPub wrapper classes
- **signal_router_v2.py**: Signal type registry

---

Last Updated: 2025-11-17
Author: Claude (claude-sonnet-4-5-20250929)
Status: Phase 1 Complete, Phase 2 In Progress
