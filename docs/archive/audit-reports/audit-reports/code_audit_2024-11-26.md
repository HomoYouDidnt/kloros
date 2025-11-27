# KLoROS Code Audit Report
**Date:** 2024-11-26
**Auditor:** Claude Code

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Overall Health** | Good (improvements needed) |
| **Python Files** | 619 (active) |
| **Lines of Code** | ~141,000 |
| **Test Files** | 58 (active) |
| **Critical Issues** | 3 |
| **High Priority** | 6 |
| **Medium Priority** | 8 |
| **Deprecated Code** | 258MB in `_deprecated/` |

---

## Work Completed This Session

### Import Standardization
- Fixed **219 `src.kloros.*` imports** across 121 files → now use `kloros.*`
- Fixed **7 `src.registry.*` imports** → now use `kloros.mind.cognition.*`

### D-REAM System Tearout
- Moved `src/dream/` (164 files) → `_deprecated/dream/`
- Moved `src/kloros/dream/` (12 files) → `_deprecated/kloros_dream/`
- Stubbed `chamber_mapper.py` and `progressive_skill_orchestrator.py`

### Service Deprecation
- Moved 6 D-REAM/PHASE systemd services to `_deprecated/systemd-services/`:
  - `klr-dream-spawn.service`
  - `klr-lifecycle-cycle.service`
  - `klr-phase-consumer.service`
  - `klr-phase-enqueue.service`
  - `klr-tournament-consumer.service`
  - `klr-winner-deployer.service`

---

## Critical Issues (Fix First)

### 1. Broken D-REAM Imports (3 files)

These files still reference the deprecated D-REAM system and will fail on import:

**File:** `kloros/orchestration/tournament_consumer_daemon.py`
```
Line 262: from dream.dream_config_loader import get_dream_config
Line 341: from dream.evaluators.chamber_batch_evaluator import ChamberBatchEvaluator
```

**File:** `kloros/orchestration/autonomous_loop.py`
```
Line 243: from src.dream.config_tuning.runner import ConfigTuningRunner
```

**File:** `self_heal/actions_integration.py`
```
Line 13: from src.dream.deploy.patcher import ChangeRequest, PatchManager
```

**Fix:** Add stub classes like done in `chamber_mapper.py` and `progressive_skill_orchestrator.py`

---

## High Priority Issues

### 2. Shell Injection Risk - `shell=True` (6 active files)

Using `shell=True` with subprocess can allow command injection if any part of the command comes from user input.

| File | Line |
|------|------|
| `config/models_config.py` | 108 |
| `tts/piper_stream.py` | 159 |
| `dev_agent/tools/sandbox.py` | 28 |
| `tools/system_diagnostic.py` | 41 |
| `selfcoder/selfcoder.py` | 9 |
| `selfcoder/api.py` | 5, 9, 13 |

**Fix:** Replace with `subprocess.run(cmd_list, shell=False)` and split commands into lists.

### 3. Pickle Deserialization Risk (4 files)

`pickle.load()` can execute arbitrary code if the pickle file is tampered with.

| File | Line |
|------|------|
| `kloros/daemons/integration_monitor_daemon.py` | 257 |
| `kloros/daemons/exploration_scanner_daemon.py` | 352 |
| `kloros/daemons/knowledge_discovery_daemon.py` | 318 |
| `kloros/daemons/capability_discovery_daemon.py` | 302 |

**Fix:** Replace with JSON serialization for daemon state persistence.

### 4. Eval/Exec Usage (8 active files)

Dynamic code execution can be dangerous if input is not properly validated.

| File | Count |
|------|-------|
| `kloros/interfaces/voice/knowledge_service.py` | 2 |
| `test_kloros_memory.py` | 2 |
| `kloros/mind/memory/logger.py` | 1 |
| `dev_agent/tools/sandbox.py` | 1 |
| `dream_lab/orchestrator.py` | 1 |
| `tts/piper_stream.py` | 1 |
| `kloros/orchestration/evidence_plugins/documentation.py` | 2 |
| `kloros/mind/consciousness/meta_agent_daemon.py` | 3 |

---

## Medium Priority Issues

### 5. Code Smells

| Issue | Count | Files |
|-------|-------|-------|
| TODO/FIXME/XXX comments | 87 | 44 |
| Broad `except:` handlers | 410+ | 100+ |
| Empty `pass` statements | 230 | 100+ |

**Notable TODO hotspots:**
- `toolforge/orchestrator.py` - 11 TODOs
- `kloros/orchestration/validation_loop.py` - 5 TODOs
- `component_self_study.py` - 5 TODOs

### 6. Orphan Files in Root Directory

28 Python files at `/home/kloros/src/` root level need organization:

**Test files (should move to `tests/`):**
- `test_hybrid_introspection.py`
- `test_umn_detailed_debug.py`
- `test_failed_study_events_schema.py`
- `test_components.py`
- `test_audio.py`
- `test_heartbeat_subscriber.py`
- `test_kloros_memory.py`
- `test_daemon_question_flow.py`
- `test_umn_callback_debug.py`
- `test_daemon_to_curiosity_e2e.py`
- `test_daemon_flow.py`
- `test_send_to_subscribed_topic.py`
- `test_failure_pattern_analysis.py`
- `test_proxy_config.py`
- `test_new_ports.py`
- `test_kloros_study_memory_bridge.py`

**Application files (should organize into modules):**
- `kloros_study_memory_bridge.py`
- `component_self_study.py`
- `evolutionary_deployment_system.py`
- `evolutionary_approval_system.py`
- `complete_dream_system.py`
- `dream_promotion_applier.py`
- `real_evolutionary_integration.py`

### 7. Testing Infrastructure Gaps

- No `pytest.ini` or `pyproject.toml` test configuration
- Tests scattered across codebase rather than centralized
- Only 17 files use pytest imports
- No coverage tooling configured

### 8. Deprecated Code Size

`_deprecated/` contains 258MB of code:
- `dream/` - Main D-REAM system (34 subdirectories)
- `kloros_dream/` - KLoROS D-REAM integration
- `dashboard/` - Old dashboard
- `dream-dashboard/` - D-REAM dashboard
- `dream_alerts/` - Alert system
- `umn_legacy/` - Old UMN bus
- `systemd-services/` - Deprecated services

---

## Metrics

```
Active Python Files:     619
Lines of Code:           ~141,000
Test Files:              58 (active)
Test Functions:          641
TODO Comments:           87
Shell=True Calls:        17 (6 active)
Pickle Loads:            4
Eval/Exec Calls:         28 (8 active)
Deprecated Code:         258MB
Environment Vars Used:   319 occurrences
```

---

## Prioritized Action Plan

### Quick Wins (< 1 day)
1. Fix 3 broken D-REAM imports with stubs
2. Move root test files to `tests/` directory

### Medium-term (1-5 days)
3. Replace `shell=True` with safe subprocess calls
4. Replace pickle with JSON serialization
5. Consolidate exception handling patterns

### Long-term (> 5 days)
6. Archive `_deprecated/` to separate repository
7. Set up pytest configuration and coverage reporting
8. Address TODO backlog (87 items)

---

## Files Modified This Session

### Stubbed for D-REAM Removal
- `/home/kloros/src/kloros/orchestration/chamber_mapper.py`
- `/home/kloros/src/kloros/orchestration/progressive_skill_orchestrator.py`

### Import Fixes Applied
- 121 files had `src.kloros.*` → `kloros.*` imports fixed
- 4 files had `src.registry.*` imports fixed

### Deprecated Services Moved
- 6 systemd service files → `_deprecated/systemd-services/`

### D-REAM Code Moved
- `src/dream/` → `_deprecated/dream/`
- `src/kloros/dream/` → `_deprecated/kloros_dream/`

---

## Next Steps for Tomorrow

1. **Fix critical imports** in the 3 files still referencing D-REAM
2. **Review security issues** - shell=True and pickle usage
3. **Organize root files** - move tests and consolidate scripts
4. **Consider archiving** the 258MB `_deprecated/` folder
