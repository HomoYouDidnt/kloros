# Streaming Curiosity Reasoning Pipeline

**Date**: 2025-11-15
**Status**: Approved for Implementation
**Context**: Memory spike in curiosity-core (1GB in 3 minutes) caused by batch processing 50 questions with ToT+Debate reasoning

## Executive Summary

Replace batch processing with streaming pipeline to reduce memory usage by 93% while maintaining reasoning quality. Questions flow through ToT+Debate reasoning one at a time with immediate garbage collection. Bounded buffer (20 questions) provides local VOI-based ranking.

**Current Problem**:
- `batch_reason(questions, top_n=50)` processes all 50 questions before returning
- Each question creates hypothesis trees (16 nodes) and debate transcripts
- All artifacts held in memory until batch completes
- Result: 1GB memory usage in 3 minutes, hitting service limit

**Solution**:
- Stream questions through reasoning pipeline one at a time
- Garbage collect hypothesis trees and debates after each question completes
- Maintain bounded buffer of 20 ReasonedQuestions for local ranking
- Memory peak: ~70MB vs 1GB+ = 93% reduction

---

## Architecture Overview

### Problem Statement

Current batch processing in curiosity_core.py:
```python
# Line 2229
reasoned_questions = reasoning.batch_reason(other_questions, top_n=min(len(other_questions), 50))
```

Issues:
1. Processes up to 50 questions with expensive ToT (Tree of Thought) + Debate
2. Each question generates:
   - Hypothesis tree: beam_width=4, max_depth=2 = 16 nodes
   - Debate transcripts: multi-agent simulation artifacts
   - VOI calculations, insights, followup questions
3. All held in memory until batch completes
4. Result: Memory spike to 1GB, service hits MemoryMax limit

### Solution: Streaming Pipeline

**Design Pattern**: Stream-and-Dispose with Bounded Buffer

```
Input: questions [q1, q2, ..., q50]
    ↓
stream_reason() generator (yields one at a time)
    ↓
StreamingBuffer (capacity=20)
    ↓ (when full)
Sort by VOI, emit top-10, clear buffer
    ↓
Generate followups (max 10 total across all batches)
```

**Memory Guarantees**:
- Active reasoning: 1 question (ToT tree + Debate) ≈ 50MB
- Buffer: 20 ReasonedQuestions (lightweight structs) ≈ 20MB
- **Total peak**: ~70MB vs current 1GB+ = **93% reduction**

**Ranking Quality**:
- Current: Global top-50 by VOI, return first 50
- Streaming: Local top-10 from each 20-question buffer
- Trade-off: Slightly lower ranking quality, but acceptable given buffer size

**Latency Improvement**:
- Current: Wait for all 50 questions to complete before processing any
- Streaming: Process high-VOI questions as soon as first buffer fills
- Result: Faster time-to-first-followup

---

## Component Design

### Component 1: CuriosityReasoning.stream_reason()

**File**: `/home/kloros/src/registry/curiosity_reasoning.py`
**Location**: Add after line 649 (after batch_reason method)

**Purpose**: Generator that yields ReasonedQuestion objects one at a time, allowing immediate garbage collection of reasoning artifacts.

**Implementation**:
```python
def stream_reason(self, questions: List[Any]) -> Iterator[ReasonedQuestion]:
    """
    Stream reasoned questions one at a time with automatic memory cleanup.

    Each question goes through full 7-stage reasoning pipeline:
    1. ToT hypothesis exploration
    2. Debate top hypotheses
    3. VOI calculation
    4. Reasoning mode routing
    5. Insight generation
    6. Confidence estimation
    7. Follow-up question generation

    After yielding, hypothesis trees and debate transcripts are garbage collected.
    Only the ReasonedQuestion survives in caller's buffer.

    Args:
        questions: List of CuriosityQuestion objects to process

    Yields:
        ReasonedQuestion objects in input order (unsorted)

    Memory:
        At most 1 question's reasoning artifacts in memory at a time.
        Intermediate data structures (trees, debates) freed after yield.
    """
    for question in questions:
        reasoned = self.reason_about_question(question)  # Full pipeline
        yield reasoned
        # After yield, Python GC reclaims:
        # - ToT hypothesis tree (16 nodes)
        # - Debate transcripts
        # - Intermediate scoring artifacts
```

**Key Points**:
- Reuses existing `reason_about_question()` - no changes to reasoning logic
- Generator pattern enables memory cleanup through natural Python GC
- Yields in input order - sorting happens in caller's buffer

---

### Component 2: StreamingBuffer Helper Class

**File**: `/home/kloros/src/registry/curiosity_core.py`
**Location**: Add before line 2215 (before BRAINMODS REASONING section)

**Purpose**: Bounded buffer that accumulates ReasonedQuestions and emits top-10 by VOI when full.

**Implementation**:
```python
class StreamingBuffer:
    """
    Bounded buffer for streaming VOI-based ranking.

    Accumulates ReasonedQuestions up to capacity, then sorts by VOI
    and returns top-10. Provides local ranking without holding entire batch.

    Memory: At most `capacity` ReasonedQuestions (lightweight structs).
    """

    def __init__(self, capacity: int = 20):
        """
        Args:
            capacity: Buffer size before flushing (default 20)
        """
        self.capacity = capacity
        self.buffer: List[ReasonedQuestion] = []

    def add(self, item: ReasonedQuestion) -> Optional[List[ReasonedQuestion]]:
        """
        Add ReasonedQuestion to buffer.

        When buffer reaches capacity, sorts by VOI and returns top-10.

        Args:
            item: ReasonedQuestion to add

        Returns:
            Top-10 by VOI if buffer full, else None
        """
        self.buffer.append(item)

        if len(self.buffer) >= self.capacity:
            return self.flush()
        return None

    def flush(self) -> List[ReasonedQuestion]:
        """
        Sort buffer by VOI descending, return top-10, clear buffer.

        Returns:
            Top-10 ReasonedQuestions by VOI score
        """
        self.buffer.sort(key=lambda x: x.voi_score, reverse=True)
        top_10 = self.buffer[:10]
        self.buffer.clear()
        return top_10

    def get_remaining(self) -> List[ReasonedQuestion]:
        """
        Get any remaining questions without clearing buffer.
        Used for final flush when stream exhausted.

        Returns:
            Top-10 from remaining buffer by VOI
        """
        if not self.buffer:
            return []

        self.buffer.sort(key=lambda x: x.voi_score, reverse=True)
        return self.buffer[:10]
```

**Design Rationale**:
- Capacity=20: Balance between ranking quality and memory usage
- Top-10 emission: Matches existing MAX_FOLLOWUP_QUESTIONS_PER_CYCLE limit
- Flush-on-full: Automatic memory management, no manual tracking

---

### Component 3: Modified Reasoning Loop

**File**: `/home/kloros/src/registry/curiosity_core.py`
**Location**: Replace lines 2228-2252 (batch_reason call and processing)

**Current Code**:
```python
# Line 2229
reasoned_questions = reasoning.batch_reason(other_questions, top_n=min(len(other_questions), 50))

# Lines 2240-2252: Process all reasoned questions at once
for rq in reasoned_questions:
    if hasattr(rq.original_question, 'value_estimate'):
        rq.original_question.value_estimate = rq.voi_score

questions = discovery_questions + [rq.original_question for rq in reasoned_questions]

# Lines 2254-2277: Extract followups from all reasoned questions
```

**New Code**:
```python
# Stream questions through reasoning with bounded buffer
buffer = StreamingBuffer(capacity=20)
follow_up_count = 0
all_reasoned = []  # Collect for final question list update

logger.info(f"[curiosity_core] Streaming {len(other_questions)} questions through reasoning...")

for reasoned_q in reasoning.stream_reason(other_questions):
    # Add to buffer, check if flush needed
    top_batch = buffer.add(reasoned_q)

    # Also collect for final question list (lightweight)
    all_reasoned.append(reasoned_q)

    # Process top-10 batch if buffer flushed
    if top_batch:
        logger.info(f"[curiosity_core] Processing top-10 batch from buffer (total followups: {follow_up_count})")

        for rq in top_batch:
            if follow_up_count >= MAX_FOLLOWUP_QUESTIONS_PER_CYCLE:
                logger.info(f"Reached followup limit ({MAX_FOLLOWUP_QUESTIONS_PER_CYCLE}), stopping generation")
                break

            # Check unresolvable detection
            investigation_result = {
                'confidence': rq.confidence,
                'evidence': rq.follow_up_questions if rq.follow_up_questions else []
            }

            if not self.should_generate_followup({'id': rq.original_question.id}, investigation_result):
                logger.debug(f"[curiosity_core] Skipping followup generation for {rq.original_question.id} (unresolvable)")
                continue

            # Generate followups
            if rq.follow_up_questions:
                logger.info(f"[curiosity_core] Generating {len(rq.follow_up_questions)} "
                          f"follow-up questions for {rq.original_question.id}")

                for follow_up_dict in rq.follow_up_questions[:3]:
                    if follow_up_count >= MAX_FOLLOWUP_QUESTIONS_PER_CYCLE:
                        logger.info(f"Reached followup limit ({MAX_FOLLOWUP_QUESTIONS_PER_CYCLE}), stopping generation")
                        break

                    # Convert to CuriosityQuestion and add to feed
                    # (existing conversion logic from lines 2280-2305)
                    follow_up_count += 1

        # Early exit if we hit followup limit
        if follow_up_count >= MAX_FOLLOWUP_QUESTIONS_PER_CYCLE:
            break

# Process any remaining questions in buffer
if follow_up_count < MAX_FOLLOWUP_QUESTIONS_PER_CYCLE:
    remaining = buffer.get_remaining()
    if remaining:
        logger.info(f"[curiosity_core] Processing {len(remaining)} remaining questions from buffer")
        # (same processing logic as above)

# Update original questions with VOI scores
for rq in all_reasoned:
    if hasattr(rq.original_question, 'value_estimate'):
        rq.original_question.value_estimate = rq.voi_score

# Boost discovery question priority
for dq in discovery_questions:
    dq.value_estimate = 0.95

# Combine and return
questions = discovery_questions + [rq.original_question for rq in all_reasoned]
```

**Key Changes**:
1. Replace `batch_reason()` with `stream_reason()` generator
2. Add StreamingBuffer to accumulate and rank incrementally
3. Process top-10 batches as buffer flushes (every 20 questions)
4. Collect all_reasoned for final question list update (lightweight)
5. Early exit when MAX_FOLLOWUP_QUESTIONS_PER_CYCLE reached

---

## Data Flow

### Phase 1: Stream Input → Reasoning (Continuous)

```
Input: other_questions [q1, q2, ... q50]
    ↓
stream_reason() generator
    ↓
Process q1:
  - ToT hypothesis exploration (beam search, creates tree)
  - Debate top 3 hypotheses (multi-agent simulation)
  - VOI calculation
  - Routing, insights, confidence, followups
    ↓
yield ReasonedQuestion(q1)
    [Hypothesis tree freed by GC]
    [Debate transcripts freed by GC]
    ↓
buffer.add(rq1) → None (buffer size = 1/20)
    ↓
all_reasoned.append(rq1)  # Lightweight struct
```

### Phase 2: Buffer Fills → Emit Top-10 by VOI

```
... continue streaming q2, q3, ... q20 ...
    ↓
buffer.add(rq20) → buffer.flush()
    ↓
Sort 20 questions by VOI descending:
  [rq14(voi=0.92), rq3(voi=0.87), rq7(voi=0.81), ...]
    ↓
Return top-10 → top_batch
    ↓
buffer.clear()  # Free 20 ReasonedQuestions
    ↓
Process top_batch (10 questions):
  For each rq in top-10:
    - Check should_generate_followup() (unresolvable detection)
    - Generate up to 3 followups per question
    - Stop at MAX_FOLLOWUP_QUESTIONS_PER_CYCLE (10 total)
    - Add followups to questions list
    ↓
If follow_up_count >= 10: break (stop consuming stream)
Else: continue streaming q21, q22, ...
```

### Phase 3: Stream Exhausted → Final Flush

```
All questions processed, buffer has < 20 remaining
    ↓
buffer.get_remaining() → Sort and return top-10
    ↓
Process final batch (if under followup limit)
    ↓
Update all original questions with VOI scores:
  for rq in all_reasoned:
    rq.original_question.value_estimate = rq.voi_score
    ↓
Combine: discovery_questions + [rq.original_question for rq in all_reasoned]
    ↓
Return sorted question list
```

### Memory State Throughout Pipeline

**Before (Batch)**:
```
Reasoning 50 questions:
  - 50 hypothesis trees (16 nodes each) = ~40MB
  - 50 debate transcripts = ~30MB
  - 50 ReasonedQuestions = ~20MB
  - Intermediate artifacts = ~10MB
Total: ~100MB held until batch completes

After batch completes:
  - Only 50 ReasonedQuestions survive
  - Trees and debates freed
  - But peak was 100MB+ per batch
  - Multiple batches per cycle = 1GB spike
```

**After (Streaming)**:
```
At any moment:
  - 1 question under reasoning:
    - 1 hypothesis tree = ~0.8MB
    - 1 debate transcript = ~0.6MB
    - Intermediate artifacts = ~0.2MB
  - StreamingBuffer (20 ReasonedQuestions) = ~20MB
  - all_reasoned list (grows to 50) = ~50MB
Total peak: ~72MB (93% reduction)

Memory freed continuously:
  - After each yield, tree + debate GC'd
  - After each buffer flush, 20 questions cleared
  - Only lightweight structs accumulate
```

---

## Error Handling

**Stream Interruption**:
- If reasoning fails for a question, `reason_about_question()` returns minimal_reasoning fallback
- Stream continues, no interruption to other questions
- Buffer still flushes normally

**Early Exit on Followup Limit**:
- Generator naturally stops being consumed when followup limit reached
- Remaining questions in stream never reasoned (memory savings)
- all_reasoned list only contains questions processed so far

**Buffer Edge Cases**:
- Empty stream: buffer.get_remaining() returns empty list
- Stream < 20 questions: Never flushes, only get_remaining() called
- Multiple flushes: Each flush independent, no state carryover

---

## Testing Strategy

**Memory Verification**:
1. Monitor curiosity-core memory before/after change
2. Expect: <100MB stable instead of 1GB spike
3. Check swap usage: Should drop to near-zero

**Functional Verification**:
1. Question generation: Count should match (10 followups per cycle)
2. VOI ranking: Top questions should be high-value (subjective check)
3. Unresolvable detection: Still works (check for "unresolvable" logs)

**Performance Testing**:
1. Time-to-first-followup: Should improve (first buffer flush at q20 instead of q50)
2. Total cycle time: May slightly increase (overhead from buffer management)
3. CPU usage: Should remain similar (same reasoning logic)

---

## Rollback Plan

Changes are isolated to 2 files with clear rollback:

1. **curiosity_reasoning.py**: New method added, batch_reason() unchanged
   - Rollback: Remove stream_reason() method, no other changes needed

2. **curiosity_core.py**: Replace streaming loop with batch_reason() call
   - Rollback: Restore lines 2228-2277 from git history

**No database changes, no config changes, pure application logic**

Command:
```bash
git diff HEAD~1 src/registry/curiosity_reasoning.py src/registry/curiosity_core.py
# Review changes, then:
git revert <commit-hash>
sudo systemctl restart kloros-curiosity-core-consumer
```

---

## Success Metrics

**Before**:
- Memory: 1022MB/1G (100% usage, hitting limit)
- Followup generation: 69 in 1 second (limited to 10 by MAX_FOLLOWUP_QUESTIONS_PER_CYCLE)
- Swap: 202MB used

**After**:
- Memory: <200MB/1G (80% reduction, stable)
- Followup generation: Same 10 per cycle (behavior unchanged)
- Swap: Near-zero usage
- Time-to-first-followup: Faster (first flush at q20 instead of q50)

**Quality Metrics** (maintained):
- VOI ranking quality: Local top-10 from 20-question buffer
- Reasoning depth: Full 7-stage pipeline for all questions
- Unresolvable detection: Continues to work

---

## Implementation Notes

**Backward Compatibility**:
- `batch_reason()` method remains unchanged (not removed)
- Can switch back by changing one line in curiosity_core.py
- No changes to question data structures or schemas

**Future Enhancements**:
- Parallel reasoning: Process multiple questions concurrently with ThreadPoolExecutor
- Adaptive buffer size: Adjust capacity based on memory pressure
- VOI-based early stopping: Skip reasoning for low-value questions entirely

**Dependencies**:
- No new imports required
- Uses standard Python generators (Iterator from typing)
- StreamingBuffer is pure Python, no external dependencies
