# Curiosity Feed Filtering Design

**Date:** 2025-11-06
**Status:** Approved
**Problem:** Orchestrator NOOP loop - processing 34 stale questions every tick

## Problem Statement

The orchestrator enters a NOOP loop where it processes 34 curiosity questions every tick but skips all of them because they're already processed and too recent to reprocess (1 day old, need 7 days). This wastes CPU cycles and clutters logs.

**Root Cause:**
- `curiosity_feed.json` contains questions generated Nov 4
- All processed Nov 5 but `spawned=False`
- Questions too recent to reprocess (`age_ok=False`)
- `curiosity_core.py` regenerates same questions without checking processed state
- Result: Every tick processes 34 → skips 34 → NOOP

## Solution Overview

Make `curiosity_core.py` aware of processed questions and filter them intelligently during generation using a new `ProcessedQuestionFilter` class.

## Architecture

Add filtering stage to generation pipeline:

```
Capability Matrix → Monitors Generate Questions → Aggregate
    ↓
Brainmods Reasoning (VOI scoring)
    ↓
ProcessedQuestionFilter ← reads processed_questions.jsonl
    ↓
Filtered Feed → Write curiosity_feed.json
```

### Design Principles

1. **Separation of Concerns**: Filter is separate class, not embedded in CuriosityCore
2. **Smart Filtering**: Uses `action_class` + evidence to determine regeneration rules
3. **Computational Autopoiesis**: All questions eventually regenerate after appropriate cooldown
4. **Non-Breaking**: Filtering is optional - if it fails, fall back to unfiltered questions
5. **Stateless Operation**: Filter reads state on-demand, no internal persistence

## Question Lifecycle Rules

Questions are classified by `action_class` and evidence context to determine cooldown periods:

### Type 1: Structural Integration Issues
- **Trigger**: `action_class == "propose_fix"` AND hypothesis starts with `UNINITIALIZED_COMPONENT_`, `ORPHANED_QUEUE_`, or `DUPLICATE_`
- **Cooldown**: 30 days
- **Rationale**: Fixed wiring can break with code changes; system should periodically verify structural integrity (autopoiesis)

### Type 2: Performance Monitoring
- **Trigger**: Questions from `PerformanceMonitor` (evidence contains performance metrics)
- **Cooldown**: 3 days
- **Rationale**: Performance can degrade; needs regular monitoring without spam

### Type 3: Resource Pressure
- **Trigger**: Questions from `SystemResourceMonitor` (swap, memory, GPU)
- **Cooldown**: 1 day
- **Rationale**: Resource issues are highly dynamic, need frequent checking

### Type 4: Investigation & Discovery
- **Trigger**: `action_class == "investigate"` OR `action_class == "find_substitute"`
- **Cooldown**: 7 days (default window)
- **Rationale**: Investigations yield new insights as system evolves

### Type 5: Test Failures
- **Trigger**: Questions from `TestResultMonitor`
- **Cooldown**: 0 days (regenerate immediately if test still failing)
- **Rationale**: Test state changes frequently, needs real-time awareness

### Default Fallback
- **Cooldown**: 7 days for unclassified questions

## ProcessedQuestionFilter Class

**Location:** `/home/kloros/src/registry/processed_question_filter.py`

### Class Structure

```python
class ProcessedQuestionFilter:
    """
    Filters processed questions based on lifecycle rules.

    Enables computational autopoiesis by allowing questions to be
    re-examined after appropriate cooldown periods.
    """

    def __init__(
        self,
        processed_path: Path = Path("/home/kloros/.kloros/processed_questions.jsonl")
    ):
        self.processed_path = processed_path
        self._processed_cache = {}  # {question_id: processed_timestamp}
        self._load_processed_state()

    def _load_processed_state(self) -> None:
        """Load processed questions into memory cache."""
        # Read processed_questions.jsonl, build {qid: timestamp} map

    def _get_cooldown_days(self, question: CuriosityQuestion) -> int:
        """Determine cooldown period based on question type."""
        # Implements the 5 lifecycle rules
        # Returns: 30, 3, 1, 7, or 0 days

    def should_regenerate(self, question: CuriosityQuestion) -> bool:
        """Check if question should be regenerated."""
        # If not processed → True (new question)
        # If processed → check if cooldown expired

    def filter_questions(
        self,
        questions: List[CuriosityQuestion]
    ) -> List[CuriosityQuestion]:
        """Filter questions list, removing those still in cooldown."""
        # Main entry point
        # Returns filtered list + logs statistics
```

### Key Methods

- **`_load_processed_state()`**: Reads JSONL on initialization, builds question_id → timestamp map
- **`_get_cooldown_days()`**: Encapsulates lifecycle rules, returns cooldown period
- **`should_regenerate()`**: Decision logic for single question
- **`filter_questions()`**: Batch processing with logging

## Integration with CuriosityCore

**File:** `/home/kloros/src/registry/curiosity_core.py`

**Location:** In `CuriosityCore.generate_questions_from_matrix()`, after brainmods reasoning (around line 2214)

```python
# After brainmods reasoning completes
except Exception as e:
    logger.warning(f"[curiosity_core] Brainmods reasoning failed, continuing without: {e}")

# NEW: Filter out questions still in cooldown period
try:
    from src.registry.processed_question_filter import ProcessedQuestionFilter

    question_filter = ProcessedQuestionFilter()
    original_count = len(questions)
    questions = question_filter.filter_questions(questions)
    filtered_count = original_count - len(questions)

    if filtered_count > 0:
        logger.info(f"[curiosity_core] Filtered {filtered_count} questions "
                   f"still in cooldown (kept {len(questions)})")
except Exception as e:
    logger.warning(f"[curiosity_core] Question filtering failed, "
                  f"continuing with unfiltered questions: {e}")
    # Fail-open: if filtering breaks, use all questions

self.feed = CuriosityFeed(questions=questions)
return self.feed
```

### Integration Points

- Runs after brainmods reasoning (filters VOI-scored questions)
- Fail-open: If filtering crashes, continues with unfiltered questions
- Logging: Tracks filtered count for observability
- Optional: Could add `KLR_DISABLE_QUESTION_FILTERING` env var

## Error Handling & Edge Cases

### Edge Cases Handled

1. **First Boot** (no processed_questions.jsonl):
   - `_load_processed_state()` handles missing file gracefully
   - All questions pass through (nothing to filter)

2. **Corrupted JSONL File**:
   - Try/except in `_load_processed_state()`
   - Log warning, continue with empty cache (fail-open)

3. **Malformed Question** (missing fields):
   - `_get_cooldown_days()` uses safe defaults
   - Falls back to 7-day window if classification fails

4. **Clock Skew / Time Travel**:
   - If `processed_at` is in future, treat as "just processed"
   - Prevents negative age calculations

5. **Filter Initialization Fails**:
   - CuriosityCore catches exception, continues unfiltered
   - System degrades gracefully (spam vs. crash)

### Logging Strategy

- **INFO**: Successful filtering with counts
- **WARNING**: Fallbacks (missing file, corruption)
- **DEBUG**: Per-question decisions (for troubleshooting)

## Expected Impact

### Before Implementation
- Feed contains: 34 questions (all stale)
- Orchestrator processes: 34 questions
- Orchestrator skips: 34 questions
- Result: NOOP every tick

### After Implementation
- Feed contains: 0-5 questions (only fresh/reprocessable)
- Orchestrator processes: 0-5 questions
- Orchestrator skips: 0 questions
- Result: No NOOP loops, CPU efficiency improved

### Log Changes

**Before:**
```
Processing 34 curiosity questions
Skipping 34 questions (processed=True, age_ok=False)
curiosity_processing_complete: experiments_spawned=0, skipped_processed=34
Orchestrator tick result: NOOP
```

**After:**
```
[curiosity_core] Filtered 29 questions still in cooldown (kept 5)
Processing 5 curiosity questions
curiosity_processing_complete: experiments_spawned=2, skipped_processed=0
Orchestrator tick result: SUCCESS
```

## Testing Strategy

### Unit Tests
- Test `_get_cooldown_days()` with each question type (5 types + default)
- Test `should_regenerate()` with various ages
- Test `_load_processed_state()` with missing/corrupted files

### Integration Tests
- Generate questions → filter → verify correct ones removed
- Test with real `processed_questions.jsonl` data
- Verify cooldown periods work correctly

### Edge Case Tests
- Missing `processed_questions.jsonl`
- Corrupted JSONL (invalid JSON, missing fields)
- Malformed questions (missing action_class, hypothesis)
- Time edge cases (future timestamps, very old timestamps)

## Deployment Plan

### Pre-Deployment
1. Disable kloros-orchestrator auto-restart
2. Shutdown kloros-orchestrator service
3. Verify no running orchestrator processes

### Implementation
1. Create `/home/kloros/src/registry/processed_question_filter.py`
2. Modify `/home/kloros/src/registry/curiosity_core.py`
3. Test filter initialization and basic filtering
4. Run integration test

### Post-Deployment
1. Restart kloros-orchestrator service
2. Monitor logs for filtering messages
3. Verify NOOP loops eliminated
4. Watch for any exceptions in filtering

### Rollback Plan
If filtering causes issues:
1. Comment out filtering code in `curiosity_core.py`
2. Restart orchestrator
3. System reverts to previous (NOOP) behavior

## Files Changed

### New Files
- `/home/kloros/src/registry/processed_question_filter.py` (~150 lines)

### Modified Files
- `/home/kloros/src/registry/curiosity_core.py` (~15 lines added)

## Success Criteria

1. ✅ Orchestrator logs show "Filtered N questions still in cooldown"
2. ✅ Number of questions in feed reduced from 34 to <10
3. ✅ No NOOP loops in orchestrator logs
4. ✅ Questions with different types respect their cooldown periods
5. ✅ System degrades gracefully if filtering fails (fail-open)

## Future Enhancements

### Potential Improvements
- Add `question_lifecycle` metadata to questions for explicit lifecycle control
- Expose cooldown periods as configurable env vars
- Add metrics: questions_filtered_count, questions_regenerated_count
- Create dashboard showing question lifecycle states

### Configuration Options
- `KLR_DISABLE_QUESTION_FILTERING=1` - Disable filtering entirely
- `KLR_STRUCTURAL_COOLDOWN_DAYS=30` - Override structural question cooldown
- `KLR_PERFORMANCE_COOLDOWN_DAYS=3` - Override performance question cooldown
- `KLR_RESOURCE_COOLDOWN_DAYS=1` - Override resource question cooldown

---

**Design Status:** Approved for implementation
**Next Step:** Implement ProcessedQuestionFilter class with TDD approach
