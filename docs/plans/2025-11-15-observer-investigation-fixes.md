# Observer & Investigation System Fixes

**Date**: 2025-11-15
**Status**: Approved for Implementation
**Context**: KLoROS Observer detecting issues but investigation/remediation pipeline has 5 critical failures

## Executive Summary

Observer successfully detects kernel errors, service failures, and disabled systemd units. Investigation pipeline has 5 critical issues preventing effective remediation:

1. **Systemd investigations fail** - Confidence 0.0-0.3, can't read unit files
2. **Dead letter recovery incomplete** - 114 historical failures never investigated
3. **False positive errors** - INFO-level logs trigger operational error investigations
4. **Memory pressure** - Curiosity-core at 99% capacity (506MB/512MB)
5. **Duplicate question loop** - Same questions repeat with null evidence_hash

All 5 issues have validated remediation approaches ready for implementation.

---

## Issue A: Systemd Investigation Capability

### Problem

GenericInvestigationHandler completes systemd service investigations with "success": true but confidence 0.0-0.3. Root cause: Cannot access systemd unit files to understand what services do.

Example failed investigation:
```json
{
  "question": "What does judge-final.service do? Is it important?",
  "confidence": 0.0,
  "key_findings": ["The evidence provided does not include any specific details"]
}
```

### Solution: Specialized SystemdServiceInvestigator

**Architecture**:
- Create `registry/systemd_investigator.py` with SystemdServiceInvestigator class
- Route `systemd_audit_*` question_ids to this handler in investigation_consumer_daemon.py
- Reuse pattern from ModuleInvestigator (LLM-powered deep analysis)

**Evidence Gathering**:
1. Read unit file from `/lib/systemd/system/<service>` and `/etc/systemd/system/<service>`
2. Parse: ExecStart (what command runs), Description, Documentation, Dependencies
3. Check if binary exists and is executable
4. Read man pages for the command (if available)
5. Analyze service type (oneshot, forking, simple, notify)

**LLM Analysis**:
- Prompt: "Based on this systemd unit configuration, explain: 1) What this service does, 2) Whether it's important for an AI system, 3) Recommendation to enable/disable"
- Return structured result with confidence score

**Integration Points**:
- File: `src/kloros/orchestration/investigation_consumer_daemon.py:196-208`
- Add routing logic: `if question_id.startswith("systemd_audit_"): use SystemdServiceInvestigator`

**Success Criteria**:
- Systemd audit investigations complete with confidence > 0.7
- Investigations include actual service description and recommendations

---

## Issue B: Dead Letter Recovery

### Problem

DeadLetterMonitor initializes with current file size as baseline, ignoring all pre-existing dead letters. 114 historical failed intents from 11:07 race condition never investigated.

Current behavior:
```python
# sources.py:457
self._last_check_size = 0  # Should process existing on startup
```

### Solution: Startup Processing

**Modification to DeadLetterMonitor**:
1. Keep `_last_check_size = 0` on initialization
2. First iteration of `stream()` will detect all existing entries as "new"
3. Add startup detection flag to emit single aggregated event

**Implementation**:
```python
class DeadLetterMonitor:
    def __init__(self):
        self._last_check_size = 0  # Start at 0 to catch historical
        self._startup_complete = False

    def stream(self):
        # First check after startup
        if not self._startup_complete and self.dlq_path.exists():
            initial_size = self.dlq_path.stat().st_size
            if initial_size > 0:
                # Count all historical entries
                count = count_lines(self.dlq_path)
                yield Event(
                    type="error_critical",
                    data={"message": f"Found {count} historical dead letters on startup"}
                )
            self._last_check_size = initial_size
            self._startup_complete = True

        # Normal monitoring continues...
```

**Success Criteria**:
- Observer restart processes all existing dead letters
- Single aggregated event emitted for historical backlog
- Ongoing monitoring continues as before

---

## Issue C: False Positive Error Detection

### Problem

JournaldSource uses keyword matching ("exception", "error", "fail") without checking log level. INFO-level logs trigger operational error investigations.

False positive example:
```
[INFO] registry.curiosity_core: [exception_monitor] Generated 0 chat-related questions
```
Keyword "exception" → classified as error_operational → priority 9 investigation

### Solution: Priority-Based Filtering

**Journald Priority Levels** (syslog standard):
- 0 = emerg, 1 = alert, 2 = crit, 3 = err, 4 = warning
- 5 = notice, 6 = info, 7 = debug

**Python logging → syslog mapping**:
- ERROR → 3 (err)
- WARNING → 4 (warning)
- INFO → 6 (info)
- DEBUG → 7 (debug)

**Implementation**:
```python
# sources.py:JournaldSource.stream()
for entry in journal:
    priority = int(entry.get('PRIORITY', 6))  # Default to INFO
    message = entry.get('MESSAGE', '')

    # Only check keywords if priority indicates actual error/warning
    if priority <= 4:  # warning or higher severity
        # Apply keyword matching logic
        if any(keyword in message.lower() for keyword in error_keywords):
            event_type = "error_critical" if priority <= 2 else "error_operational"
    else:
        # INFO/DEBUG logs never trigger error classification
        continue
```

**Success Criteria**:
- INFO-level logs with "exception" keyword ignored
- Only WARNING/ERROR/CRITICAL logs trigger error classification
- Observer stops detecting curiosity-core INFO logs as operational errors

---

## Issue D: Memory Pressure

### Problem

kloros-curiosity-core-consumer at 99% capacity:
- Memory: 506.8MB used / 512MB limit (5.1MB available)
- Swap: 202.6MB used
- Generating 50 follow-up questions per cycle
- Filter shows 90/100 questions in cooldown (churning on same questions)

### Solution: Two-Pronged (Immediate + Root Cause)

**1. Immediate Relief - Raise Memory Limit**:
```ini
# /etc/systemd/system/kloros-curiosity-core-consumer.service
[Service]
MemoryMax=1G  # Increase from 512M to 1G
```

**2. Root Cause - Reduce Question Generation**:

File: `src/registry/curiosity_core.py` (question generation logic)

Current behavior: Generates 1 follow-up per parent question (can create 50+ per cycle)

New behavior:
```python
# curiosity_core.py
MAX_FOLLOWUP_QUESTIONS_PER_CYCLE = 10  # Hard limit

def generate_followup_questions(self, parent_questions):
    followups = []
    for parent in parent_questions:
        if len(followups) >= MAX_FOLLOWUP_QUESTIONS_PER_CYCLE:
            logger.info(f"Reached followup limit ({MAX_FOLLOWUP_QUESTIONS_PER_CYCLE}), stopping generation")
            break
        # Generate followup...
        followups.append(...)
    return followups
```

**3. Memory Monitoring**:
```python
# curiosity_core_consumer_daemon.py
import psutil

def check_memory():
    mem = psutil.Process().memory_info()
    mem_mb = mem.rss / 1024 / 1024

    if mem_mb > 900:  # 90% of 1GB
        logger.warning(f"Memory usage high: {mem_mb}MB, pruning old questions")
        prune_old_questions(max_age_hours=24)
```

**Success Criteria**:
- Memory usage stays below 800MB under normal operation
- Swap usage drops to near-zero
- Question generation limited to 10 followups/cycle

---

## Issue E: Duplicate Question Loop

### Problem

Curiosity feed contains duplicate/orphaned questions with null evidence_hash, preventing deduplication:
- 3 duplicate_responsibility questions (same components appearing twice)
- 7 orphaned_queue followup questions
- All have "status": "ready" but can't be deduplicated

Root cause: Low-confidence debate results → followup generation → followup has no evidence → low confidence → infinite loop

### Solution: Unresolvable Question Detection

**Pattern Recognition**:
1. Question type = followup (parent_question set)
2. Confidence < 0.6 after investigation
3. Evidence count < 2 (insufficient information)
4. Question asks "What additional evidence would help verify..."

→ This indicates question cannot be answered with available evidence

**Implementation**:

File: `src/registry/curiosity_core.py`

```python
def should_generate_followup(self, parent_question, investigation_result):
    """
    Decide if followup generation is productive.

    Avoid infinite loops where questions can't be answered with available evidence.
    """
    # Check if parent was already a followup
    if parent_question.get('id', '').endswith('.followup'):
        # Followup of followup → getting too deep
        confidence = investigation_result.get('confidence', 0)
        evidence_count = len(investigation_result.get('evidence', []))

        if confidence < 0.6 and evidence_count < 2:
            # Mark as unresolvable instead of generating more followups
            logger.info(f"Parent question {parent_question['id']} unresolvable (low confidence, insufficient evidence)")
            mark_question_unresolvable(parent_question['id'])
            return False

    return True
```

**Cleanup Existing Duplicates**:
```python
# One-time cleanup in curiosity_core_consumer_daemon.py startup
def cleanup_duplicate_questions():
    """Remove duplicate/orphaned questions from feed on startup."""
    feed = load_curiosity_feed()

    # Remove questions with null evidence_hash
    feed['questions'] = [q for q in feed['questions'] if q.get('evidence_hash') is not None]

    # Remove duplicate capability_key entries (keep highest VOI)
    seen_keys = {}
    unique_questions = []
    for q in feed['questions']:
        key = q.get('capability_key')
        if key not in seen_keys or q.get('value_estimate', 0) > seen_keys[key]:
            seen_keys[key] = q.get('value_estimate', 0)
            unique_questions.append(q)

    feed['questions'] = unique_questions
    save_curiosity_feed(feed)
```

**Success Criteria**:
- No questions with null evidence_hash in feed
- Duplicate_responsibility questions consolidated (3 → 1)
- Orphaned_queue followups stop regenerating
- Feed size stabilizes instead of growing unbounded

---

## Implementation Plan

### Phase 1: Critical Fixes (Immediate)
1. **Issue C - False Positives** (30 min)
   - Modify JournaldSource priority filtering
   - Restart Observer
   - Verify no more false positives

2. **Issue D - Memory Pressure** (15 min)
   - Raise memory limit to 1GB
   - Restart curiosity-core-consumer
   - Immediate relief

### Phase 2: Investigation Quality (2-3 hours)
3. **Issue A - SystemdInvestigator** (2 hours)
   - Create registry/systemd_investigator.py
   - Add routing in investigation_consumer_daemon.py
   - Test with 5 disabled services

4. **Issue B - Dead Letter Recovery** (30 min)
   - Modify DeadLetterMonitor startup behavior
   - Restart Observer
   - Verify historical dead letters processed

### Phase 3: Performance Optimization (1-2 hours)
5. **Issue D - Question Generation Limit** (1 hour)
   - Add MAX_FOLLOWUP_QUESTIONS_PER_CYCLE
   - Add memory monitoring

6. **Issue E - Duplicate Cleanup** (1 hour)
   - Implement unresolvable question detection
   - Run one-time cleanup
   - Monitor feed size

### Testing Strategy
- Each fix deployed independently with verification
- Monitor for 10 minutes between phases
- Rollback plan: systemctl restart services with old code

---

## Success Metrics

**Before**:
- Systemd investigations: 0.0-0.3 confidence
- Dead letters: 114 unprocessed
- False positives: Every 60 seconds (curiosity-core logs)
- Memory: 506MB/512MB (99% usage)
- Curiosity feed: 10 questions (many duplicates with null hash)

**After**:
- Systemd investigations: >0.7 confidence with actionable recommendations
- Dead letters: All processed within 5 minutes of Observer startup
- False positives: Zero (only WARNING+ logs trigger errors)
- Memory: <800MB/1GB (80% usage, no swap)
- Curiosity feed: <20 unique questions (no duplicates, all with evidence_hash)

---

## Files Modified

1. `/home/kloros/src/registry/systemd_investigator.py` - NEW
2. `/home/kloros/src/kloros/orchestration/investigation_consumer_daemon.py` - Routing logic
3. `/home/kloros/src/kloros/observer/sources.py` - JournaldSource priority, DeadLetterMonitor startup
4. `/home/kloros/src/registry/curiosity_core.py` - Followup limits, unresolvable detection
5. `/home/kloros/src/kloros/orchestration/curiosity_core_consumer_daemon.py` - Cleanup, monitoring
6. `/etc/systemd/system/kloros-curiosity-core-consumer.service` - Memory limit

---

## Rollback Plan

Each fix is independent and can be rolled back individually:
- **Issue A/B/C**: `git revert <commit>` + `systemctl restart kloros-observer klr-investigation-consumer`
- **Issue D**: Restore MemoryMax=512M, restart service
- **Issue E**: Restore curiosity_feed.json from backup

No database migrations, all changes in application logic and config.
