# Autonomous Curiosity Fix System Design

**Date**: 2025-11-04
**Status**: Validated Design
**Autonomy Level**: Medium (Sandbox + Manual Approval)

## Overview

Enable KLoROS to autonomously attempt fixes for integration issues discovered by the curiosity system, using SPICA instances for safe isolated testing.

## Problem Statement

The curiosity system currently:
- ✅ Discovers integration issues (orphaned queues, uninitialized components)
- ✅ Creates documentation reports
- ❌ Does NOT attempt autonomous fixes
- ❌ Requires manual implementation of all fixes

**Goal**: Make the system proactive by spawning autonomous fix attempts in isolated environments.

## Architecture

### High-Level Pipeline

```
Observer → Curiosity Processor → [Parallel Paths] → Orchestrator → Escrow
                                      ↓
                            ┌─────────┴─────────┐
                            ↓                   ↓
                    Integration Fix      SPICA Spawn
                    (Documentation)      (Autonomous Fix)
                            ↓                   ↓
                    Report Created       Sandbox Test
                            └─────────┬─────────┘
                                      ↓
                              Manual Approval Gate
```

### Components

**1. Curiosity Processor** (`/home/kloros/src/kloros/orchestration/curiosity_processor.py`)
- Routes high-autonomy questions (autonomy >= 3) to BOTH paths:
  - `integration_fix` intent → Documentation (existing behavior)
  - `spica_spawn_request` intent → Autonomous fix attempt (NEW)
- Low-autonomy questions (< 3) → Documentation only

**2. SPICA Spawner** (`/home/kloros/src/dream/config_tuning/spica_spawner.py`)
- Creates isolated filesystem clone from `/home/kloros/experiments/spica/template`
- Applies LLM-generated code patches
- Runs validation tests
- Auto-prunes instances after 3 days (existing retention policy)

**3. LLM Code Generator** (NEW - uses existing Ollama coder LLM)
- Reads curiosity question + evidence + analysis report
- Generates code patch to fix issue
- Returns patched file contents

**4. Orchestrator Handler** (`/home/kloros/src/kloros/orchestration/coordinator.py`)
- Processes `spica_spawn_request` intents
- Calls LLM to generate code patch
- Spawns SPICA instance with patch applied
- Runs tests in isolation
- On success → Escrow for manual approval
- On failure → Archive with error details

**5. Escrow System** (NEW - manual approval queue)
- Holds successful SPICA instances for review
- Allows manual inspection before merging to main
- Provides diff view and test results

## Autonomy Levels

| Level | Behavior |
|-------|----------|
| 1-2   | Documentation only (current behavior) |
| 3     | Parallel: Documentation + SPICA autonomous attempt |
| 4-5   | (Future) Auto-apply fixes that pass all validation |

## Intent Structure

### New Intent: `spica_spawn_request`

```json
{
  "intent_type": "spica_spawn_request",
  "priority": 8,
  "reason": "Autonomous fix attempt for integration issue",
  "data": {
    "question_id": "orphaned_queue_audio_buffer",
    "question": "Queue 'audio_buffer' produced but never consumed...",
    "hypothesis": "ORPHANED_QUEUE_AUDIO_BUFFER",
    "fix_context": {
      "evidence": ["Produced in: /home/kloros/src/audio/capture.py", ...],
      "analysis_report": "/home/kloros/.kloros/integration_issues/orphaned_queue_audio_buffer.md",
      "target_files": ["/home/kloros/src/audio/capture.py"],
      "proposed_changes": "Add consumer for audio_buffer queue"
    },
    "validation": {
      "run_tests": true,
      "test_command": "pytest tests/test_audio.py",
      "require_pass": true
    }
  },
  "generated_at": 1762293000.0,
  "emitted_by": "curiosity_processor_spica_router"
}
```

## LLM Code Generation

### Prompt Template

```
You are fixing an integration issue in KLoROS.

Issue: {question}
Hypothesis: {hypothesis}
Evidence:
{evidence}

Analysis Report:
{report_content}

Target File: {file_path}
Current Code:
```python
{file_content}
```

Generate a code patch that fixes this issue.
Output ONLY the complete patched file, no explanations or markdown.
```

### LLM Configuration
- Model: `qwen2.5:72b` (coder LLM from OLLAMA_HOST)
- Temperature: 0.2 (deterministic code generation)
- Max tokens: 8192 (handle large files)

## Safety Guardrails

1. **Isolation**: All changes applied in SPICA instance, never directly to main codebase
2. **Test Validation**: Must pass existing test suite before escrow
3. **Manual Approval**: Human must review before merging to production
4. **Auto-Rollback**: Test failures trigger automatic cleanup
5. **Retention Policy**: SPICA instances pruned after 3 days
6. **Deduplication**: Questions marked processed to prevent duplicate fix attempts

## Data Flow

```
1. Observer detects orphaned queue in audio/capture.py
   ↓
2. Curiosity processor creates question (autonomy=3)
   ↓
3. For autonomy >= 3, emit TWO intents:
   - integration_fix → Creates markdown report
   - spica_spawn_request → Triggers autonomous fix
   ↓
4. Orchestrator receives spica_spawn_request
   ↓
5. LLM generates code patch from context
   ↓
6. SPICA spawner creates isolated instance
   ↓
7. Apply patch to SPICA instance
   ↓
8. Run pytest in SPICA instance
   ↓
9a. Tests PASS → Move to escrow for review
9b. Tests FAIL → Archive with error, rollback
   ↓
10. Human reviews escrow, approves/rejects
```

## File Modifications Required

### New Files
1. `/home/kloros/src/dream/config_tuning/llm_code_generator.py` - LLM integration
2. `/home/kloros/src/kloros/orchestration/escrow_manager.py` - Manual approval queue

### Modified Files
1. `/home/kloros/src/kloros/orchestration/curiosity_processor.py` - Add SPICA routing
2. `/home/kloros/src/kloros/orchestration/coordinator.py` - Add spica_spawn_request handler
3. `/home/kloros/src/dream/config_tuning/spica_spawner.py` - Add code patch application

## Success Metrics

- **Proactivity**: Number of autonomous fix attempts per week
- **Success Rate**: % of SPICA tests that pass
- **Approval Rate**: % of successful fixes approved by human
- **Time Savings**: Hours saved vs manual implementation

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| LLM generates broken code | Isolated testing in SPICA + auto-rollback |
| Fix breaks other components | Full test suite required to pass |
| Resource exhaustion from many SPICA instances | Retention policy (max 10, prune after 3 days) |
| Security: malicious code injection | Code review in escrow before merge |

## Future Enhancements

1. **Level 4-5 Autonomy**: Auto-apply fixes for well-tested patterns
2. **Learning**: Track which fix patterns have high approval rates
3. **Multi-file fixes**: Handle fixes spanning multiple files
4. **Regression tests**: Auto-generate tests for fixed issues
