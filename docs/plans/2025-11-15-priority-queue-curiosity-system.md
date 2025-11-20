# Priority Queue Curiosity System

**Date**: 2025-11-15
**Status**: Approved for Implementation
**Context**: Infinite processing loop caused by questions stuck in feed with null evidence_hash, failing VALUE_THRESHOLD checks, and no removal mechanism

## Executive Summary

Replace file-based polling curiosity processor with chemical signal priority queue system. Questions flow as ZMQ messages with priority-based routing, intelligent archival based on skip reasons, and pattern detection for systemic issues.

**Current Problem:**
- Questions generated without `evidence_hash` (capability_discovery, chaos questions)
- VALUE_THRESHOLD=1.5 too high for some question types (capability gaps: ratio=1.23)
- Processor polls feed every 20 seconds, checking same questions repeatedly
- No mechanism to remove low-value questions → infinite loop
- 180+ log entries per hour from futile processing cycles

**Solution:**
- Chemical signals for 4 priority levels (CRITICAL/HIGH/MEDIUM/LOW)
- Evidence hash computed at question creation time
- Context-dependent thresholds per question category
- Skip reasons tracked, questions archived to category-specific files
- Archive pattern detection: large file = systemic issue worth investigating
- Opportunistic rehydration when main queues empty

---

## Architecture Overview

### Core Concept: Chemical Priority Queues

Use existing KLoROS chemical bus with priority-differentiated signals. Questions flow as chemical messages, archives provide persistence and pattern detection.

### Signal Structure

```
Priority Signals (ZMQ pub/sub):
├─ Q_CURIOSITY_CRITICAL  (ratio > 3.0, system health issues)
├─ Q_CURIOSITY_HIGH      (ratio > 2.0)
├─ Q_CURIOSITY_MEDIUM    (ratio > 1.0, context-dependent)
└─ Q_CURIOSITY_LOW       (ratio > 0.5, context-dependent)

Pattern Detection:
└─ Q_CURIOSITY_ARCHIVED  (emitted when question archived)

Persistent Archives:
├─ ~/.kloros/archives/low_value.jsonl           (ratio < threshold)
├─ ~/.kloros/archives/already_processed.jsonl   (dedup hits)
├─ ~/.kloros/archives/resource_blocked.jsonl    (governor blocked)
└─ ~/.kloros/archives/missing_deps.jsonl        (dependency issues)
```

### Processing Flow

```
1. Question Generator (capability_discovery, chaos, integration)
   ↓ compute evidence_hash from sorted evidence
   ↓ determine category (capability_gap, chaos, integration, discovery)
   ↓ lookup context-dependent threshold
   ↓ calculate priority from value/cost ratio
   ↓
2. QuestionPrioritizer.prioritize_and_emit()
   ↓ ratio > 3.0 → Q_CURIOSITY_CRITICAL
   ↓ ratio > 2.0 → Q_CURIOSITY_HIGH
   ↓ ratio > threshold → Q_CURIOSITY_MEDIUM
   ↓ ratio > 0.5 → Q_CURIOSITY_LOW
   ↓ ratio < 0.5 → archive(low_value)
   ↓
3. curiosity_processor.py (event-driven)
   ↓ polls signals in priority order (CRITICAL → HIGH → MEDIUM → LOW)
   ↓ processes question through intent generation
   ↓ on skip: determine reason, archive with category
   ↓
4. ArchiveManager
   ↓ append to category-specific .jsonl
   ↓ emit Q_CURIOSITY_ARCHIVED
   ↓ check file size threshold
   ↓ if threshold hit: emit pattern investigation question
   ↓ if main queues empty: rehydrate from largest archive
```

### Memory and Performance

**Before:**
- Poll curiosity_feed.json every 20 seconds
- Load all questions from disk each cycle
- 3 cycles/minute × 0.3s = 54s CPU per hour checking same 3 questions
- 180 log entries/hour (cycle start/end messages)

**After:**
- Event-driven: sleep until signal arrives
- No disk I/O in hot path
- Process only when questions available
- 0 CPU when queues empty
- Minimal logging (only on processing, not polling)

---

## Component Design

### Component 1: QuestionPrioritizer

**File**: `/home/kloros/src/registry/question_prioritizer.py` (NEW)

**Purpose**: Centralized logic for evidence hash computation, priority determination, and chemical signal emission.

**Implementation**:

```python
class QuestionPrioritizer:
    """
    Compute evidence hashes and emit questions to appropriate priority queues.

    Replaces ad-hoc priority logic scattered across question generators.
    Ensures all questions have evidence_hash set before entering system.
    """

    def __init__(self, chem_pub: ChemPub):
        self.chem_pub = chem_pub

        # Context-dependent thresholds
        self.thresholds = {
            'capability_gap': 1.0,      # Lower bar for capability discovery
            'chaos_engineering': 1.5,   # Higher bar for chaos experiments
            'integration': 2.0,         # Highest bar for integration fixes
            'discovery': 0.8            # Lowest bar for exploration
        }

    def compute_evidence_hash(self, evidence: List[str]) -> str:
        """
        Deterministic hash from sorted evidence list.

        Ensures evidence order doesn't affect hash, enabling deduplication.
        """
        evidence_str = "|".join(sorted(evidence))
        return hashlib.sha256(evidence_str.encode()).hexdigest()[:16]

    def _detect_category(self, question: CuriosityQuestion) -> str:
        """Infer question category from ID, hypothesis, or capability_key."""
        if question.id.startswith('enable.'):
            return 'capability_gap'
        elif question.id.startswith('chaos.'):
            return 'chaos_engineering'
        elif question.hypothesis.startswith(('ORPHANED_', 'UNINITIALIZED_', 'DUPLICATE_')):
            return 'integration'
        elif question.id.startswith('discover.'):
            return 'discovery'
        else:
            return 'unknown'

    def _is_critical(self, question: CuriosityQuestion) -> bool:
        """Check if question represents critical system issue regardless of ratio."""
        # Self-healing failures with 0% success rate
        if 'healing_rate:0.00' in question.evidence:
            return True

        # Missing critical capabilities (e.g., health monitoring)
        if question.capability_key in ['health.monitor', 'error.detection']:
            return True

        return False

    def prioritize_and_emit(self, question: CuriosityQuestion):
        """
        Compute hash, determine priority, emit to appropriate chemical signal.

        Main entry point for all question generators.
        """
        # Set evidence hash if not already set
        if not question.evidence_hash:
            question.evidence_hash = self.compute_evidence_hash(question.evidence)

        # Context-dependent threshold
        category = self._detect_category(question)
        threshold = self.thresholds.get(category, 1.5)

        ratio = question.value_estimate / max(question.cost, 0.01)

        # Determine priority signal
        if ratio > 3.0 or self._is_critical(question):
            signal = "Q_CURIOSITY_CRITICAL"
        elif ratio > 2.0:
            signal = "Q_CURIOSITY_HIGH"
        elif ratio > threshold:
            signal = "Q_CURIOSITY_MEDIUM"
        elif ratio > 0.5:
            signal = "Q_CURIOSITY_LOW"
        else:
            # Too low value - archive immediately
            archive_mgr = ArchiveManager(Path.home() / '.kloros' / 'archives', self.chem_pub)
            archive_mgr.archive_question(question, 'low_value')
            return

        # Emit to chemical bus
        self.chem_pub.emit(signal, question.to_dict(), ecosystem='introspection')
        logger.info(f"[prioritizer] Emitted {question.id} to {signal} (ratio={ratio:.2f}, category={category})")
```

**Key Points:**
- All question generators use this instead of emitting directly
- Guarantees evidence_hash is set
- Context-dependent thresholds prevent VALUE_THRESHOLD bottleneck
- Critical detection overrides ratio for urgent issues

---

### Component 2: ArchiveManager

**File**: `/home/kloros/src/registry/curiosity_archive_manager.py` (NEW)

**Purpose**: Persist skipped questions to category-specific files, detect patterns via file size, rehydrate opportunistically.

**Implementation**:

```python
class ArchiveManager:
    """
    Manage category-specific archives for skipped questions.

    Archival reasons:
    - low_value: ratio < threshold (low priority but might become relevant)
    - already_processed: dedup hit (evidence unchanged, already investigated)
    - resource_blocked: ResourceGovernor blocked (system constraints)
    - missing_deps: Dependencies not available (blocked on external factors)

    Pattern detection: Large file = many questions in same category = systemic issue.
    """

    def __init__(self, archive_dir: Path, chem_pub: ChemPub):
        self.archive_dir = archive_dir
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.chem_pub = chem_pub

        self.archives = {
            'low_value': archive_dir / 'low_value.jsonl',
            'already_processed': archive_dir / 'already_processed.jsonl',
            'resource_blocked': archive_dir / 'resource_blocked.jsonl',
            'missing_deps': archive_dir / 'missing_deps.jsonl'
        }

        # Threshold for pattern investigation
        self.thresholds = {
            'low_value': 10,           # 10+ low-value questions → why are valuations off?
            'resource_blocked': 5,     # 5+ blocked → resource pressure issue
            'already_processed': 50,   # Natural accumulation - just purge old
            'missing_deps': 8          # 8+ blocked on deps → dependency chain issue
        }

    def archive_question(self, question: CuriosityQuestion, reason: str):
        """
        Append question to category archive, emit pattern signal if threshold hit.

        Args:
            question: Question to archive
            reason: Category (low_value, already_processed, resource_blocked, missing_deps)
        """
        archive_file = self.archives.get(reason)
        if not archive_file:
            logger.warning(f"[archive_mgr] Unknown archive category: {reason}")
            return

        # Append to archive
        with open(archive_file, 'a') as f:
            json.dump(question.to_dict(), f)
            f.write('\n')

        # Emit archived signal for pattern detection
        self.chem_pub.emit("Q_CURIOSITY_ARCHIVED", {
            'question_id': question.id,
            'reason': reason,
            'archive_file': str(archive_file),
            'timestamp': datetime.now().isoformat()
        }, ecosystem='introspection')

        # Check threshold for pattern investigation
        count = self._count_entries(archive_file)
        if count >= self.thresholds.get(reason, 999):
            self._emit_pattern_investigation(reason, count)

        logger.info(f"[archive_mgr] Archived {question.id} to {reason} ({count} entries)")

    def _count_entries(self, archive_file: Path) -> int:
        """Count lines in archive file."""
        if not archive_file.exists():
            return 0
        with open(archive_file, 'r') as f:
            return sum(1 for line in f if line.strip())

    def _emit_pattern_investigation(self, category: str, count: int):
        """
        Emit high-priority question about why this archive is growing.

        Example: "Why are 10 questions being classified as low_value?
        Should thresholds be adjusted?"
        """
        pattern_question = CuriosityQuestion(
            id=f"pattern.archive.{category}",
            hypothesis=f"SYSTEMIC_ISSUE_{category.upper()}",
            question=f"Why are {count} questions being archived as '{category}'? "
                     f"Is there a systemic issue with {category} categorization or thresholds?",
            evidence=[
                f"archive_category:{category}",
                f"count:{count}",
                f"threshold:{self.thresholds.get(category)}",
                f"timestamp:{datetime.now().isoformat()}"
            ],
            action_class=ActionClass.INVESTIGATE,
            autonomy=2,  # Propose, don't auto-fix
            value_estimate=0.8,  # High value - systemic issue
            cost=0.3,
            status=QuestionStatus.READY,
            capability_key=f"curiosity.{category}"
        )

        # Emit at HIGH priority
        self.chem_pub.emit("Q_CURIOSITY_HIGH", pattern_question.to_dict(), ecosystem='introspection')
        logger.warning(f"[archive_mgr] Pattern detected: {count} questions in {category} archive")

    def rehydrate_opportunistic(self, main_feed_size: int):
        """
        When main queues empty (< 5 questions), pull from archives.

        Largest archive first = emergent priority (most systemic issues).
        """
        if main_feed_size >= 5:
            return

        # Find largest archive
        archive_sizes = {cat: self._count_entries(path)
                        for cat, path in self.archives.items()}

        if not archive_sizes or max(archive_sizes.values()) == 0:
            return

        largest_category = max(archive_sizes, key=archive_sizes.get)
        largest_file = self.archives[largest_category]

        # Pull top 3 from largest archive
        questions = self._read_archive(largest_file, limit=3)

        for q in questions:
            # Re-emit at LOW priority for reconsideration
            self.chem_pub.emit("Q_CURIOSITY_LOW", q, ecosystem='introspection')

        logger.info(f"[archive_mgr] Rehydrated {len(questions)} questions from {largest_category} "
                   f"(idle-time opportunistic)")

    def _read_archive(self, archive_file: Path, limit: int = 3) -> List[Dict]:
        """Read first N questions from archive."""
        questions = []
        with open(archive_file, 'r') as f:
            for i, line in enumerate(f):
                if i >= limit:
                    break
                if line.strip():
                    questions.append(json.loads(line))
        return questions

    def purge_old_entries(self, category: str, max_age_days: int = 7):
        """Remove entries older than max_age_days from archive."""
        archive_file = self.archives.get(category)
        if not archive_file or not archive_file.exists():
            return

        cutoff = datetime.now() - timedelta(days=max_age_days)

        # Read all entries, filter by age
        kept = []
        removed = 0

        with open(archive_file, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                created = datetime.fromisoformat(entry.get('created_at', cutoff.isoformat()))
                if created > cutoff:
                    kept.append(line)
                else:
                    removed += 1

        # Rewrite archive
        with open(archive_file, 'w') as f:
            f.writelines(kept)

        logger.info(f"[archive_mgr] Purged {removed} entries from {category} (older than {max_age_days}d)")
```

**Key Points:**
- Category-specific archives enable targeted pattern detection
- File size threshold triggers meta-questions about archival patterns
- Opportunistic rehydration keeps system busy during idle periods
- Periodic purging prevents infinite archive growth

---

### Component 3: Modified Processor Loop

**File**: `/home/kloros/src/kloros/orchestration/curiosity_processor.py` (MODIFIED)

**Changes:**

```python
# Add at top of file
USE_PRIORITY_QUEUES = os.getenv("KLR_USE_PRIORITY_QUEUES", "1") == "1"

class CuriosityProcessorDaemon:
    def __init__(self):
        # ... existing init ...

        if USE_PRIORITY_QUEUES:
            # Subscribe to priority signals
            self.subscribers = {
                'critical': ChemSub(topic="Q_CURIOSITY_CRITICAL"),
                'high': ChemSub(topic="Q_CURIOSITY_HIGH"),
                'medium': ChemSub(topic="Q_CURIOSITY_MEDIUM"),
                'low': ChemSub(topic="Q_CURIOSITY_LOW")
            }

            self.archive_mgr = ArchiveManager(
                Path.home() / '.kloros' / 'archives',
                self.chem_pub
            )

        self.cycle_count = 0

    def run(self):
        if USE_PRIORITY_QUEUES:
            self._run_priority_queue_loop()
        else:
            self._run_file_polling_loop()  # Legacy

    def _run_priority_queue_loop(self):
        """Event-driven processing from priority signals."""
        logger.info("[curiosity_processor] Starting priority queue loop")

        while self.running:
            # Poll in priority order: CRITICAL → HIGH → MEDIUM → LOW
            question_dict = None
            priority_level = None

            for level, subscriber in [('critical', self.subscribers['critical']),
                                     ('high', self.subscribers['high']),
                                     ('medium', self.subscribers['medium']),
                                     ('low', self.subscribers['low'])]:
                try:
                    signal, facts = subscriber.recv(timeout_ms=100)
                    if signal:
                        question_dict = facts
                        priority_level = level
                        break
                except Exception as e:
                    continue

            if not question_dict:
                # No questions in any queue
                # Check if should rehydrate from archives
                main_feed_size = sum(1 for _ in self._estimate_queue_size())
                self.archive_mgr.rehydrate_opportunistic(main_feed_size)

                time.sleep(1)  # Sleep briefly, then check again
                continue

            # Process question
            self.cycle_count += 1
            logger.info(f"[curiosity_processor] Cycle {self.cycle_count}: "
                       f"Processing {question_dict['id']} (priority={priority_level})")

            try:
                result = self._process_question(question_dict)

                if result['action'] == 'skip':
                    # Archive with reason
                    q = CuriosityQuestion(**question_dict)
                    self.archive_mgr.archive_question(q, result['reason'])

            except Exception as e:
                logger.error(f"[curiosity_processor] Error processing {question_dict['id']}: {e}")

    def _process_question(self, question_dict: Dict) -> Dict:
        """
        Process single question, return action and reason.

        Returns:
            {'action': 'emit_intent' | 'skip', 'reason': str}
        """
        qid = question_dict['id']
        hypothesis = question_dict.get('hypothesis', '')
        action_class = question_dict['action_class']
        value = question_dict['value_estimate']
        cost = question_dict['cost']
        evidence = question_dict.get('evidence', [])

        ratio = value / max(cost, 0.01)

        # Evidence-based deduplication
        should_investigate = _should_investigate_with_new_evidence(qid, evidence)
        if not should_investigate:
            return {'action': 'skip', 'reason': 'already_processed'}

        # Check if already spawned
        already_spawned = _has_spawned_curiosity(qid)
        if already_spawned:
            return {'action': 'skip', 'reason': 'already_processed'}

        # Check ResourceGovernor for high-autonomy questions
        if question_dict.get('autonomy', 2) >= 3:
            try:
                governor = ResourceGovernor()
                can_spawn, reason = governor.can_spawn()
                if not can_spawn:
                    return {'action': 'skip', 'reason': 'resource_blocked'}
            except Exception as e:
                logger.error(f"ResourceGovernor check failed: {e}")

        # Check for missing dependencies
        if self._has_missing_dependencies(question_dict):
            return {'action': 'skip', 'reason': 'missing_deps'}

        # Process through intent generation
        intent = _question_to_intent(question_dict)
        self._write_intent_file(intent)

        # Mark as processed
        _mark_question_processed(qid, evidence=evidence)

        return {'action': 'emit_intent', 'reason': 'processed'}

    def _has_missing_dependencies(self, question: Dict) -> bool:
        """Check if question has unresolved dependencies."""
        capability_key = question.get('capability_key', '')

        # Check if capability depends on other missing capabilities
        if capability_key.startswith('agent.'):
            # Agent capabilities need playwright or similar
            if not shutil.which('playwright'):
                return True

        if capability_key.startswith('module.'):
            # Module capabilities need src path to exist
            module_path = Path(f"/home/kloros/src/{capability_key.replace('.', '/')}")
            if not module_path.exists():
                return True

        return False

    def _estimate_queue_size(self) -> int:
        """Estimate total questions waiting across all queues."""
        # Approximate by checking each subscriber's pending messages
        # (ZMQ doesn't expose queue depth directly)
        count = 0
        for subscriber in self.subscribers.values():
            try:
                signal, facts = subscriber.recv(timeout_ms=0)
                if signal:
                    count += 1
                    # Put it back (this is crude - ideally ZMQ would let us peek)
            except:
                pass
        return count
```

**Key Changes:**
- Event-driven: sleep when queues empty, wake on signal
- Poll priority signals in order: CRITICAL → HIGH → MEDIUM → LOW
- Skip reasons tracked, questions archived instead of re-queued
- No file I/O in hot path
- Opportunistic rehydration during idle periods

---

## Migration Strategy

### Phase 1: Deploy New Components (No Breaking Changes)

**Files to Add:**
- `/home/kloros/src/registry/question_prioritizer.py`
- `/home/kloros/src/registry/curiosity_archive_manager.py`
- `/home/kloros/src/scripts/migrate_curiosity_to_priority_queues.py`

**Deployment:**
```bash
# No service restarts needed - new modules don't affect existing system
git add src/registry/question_prioritizer.py
git add src/registry/curiosity_archive_manager.py
git add src/scripts/migrate_curiosity_to_priority_queues.py
git commit -m "feat(curiosity): Add priority queue components (no breaking changes)"
```

### Phase 2: One-Time Migration Script

**Script**: `/home/kloros/src/scripts/migrate_curiosity_to_priority_queues.py`

```python
#!/usr/bin/env python3
"""
Migrate existing curiosity_feed.json to priority-based chemical signals.

Run once during deployment to transition from file-based to queue-based system.
"""

import sys
import json
import shutil
from pathlib import Path
from datetime import datetime

sys.path.insert(0, '/home/kloros/src')

from registry.question_prioritizer import QuestionPrioritizer
from registry.curiosity_core import CuriosityQuestion
from kloros.orchestration.chem_bus_v2 import ChemPub

CURIOSITY_FEED = Path.home() / '.kloros' / 'curiosity_feed.json'

def migrate_existing_feed():
    """Migrate curiosity_feed.json to priority-based chemical signals."""

    if not CURIOSITY_FEED.exists():
        print("No existing curiosity_feed.json - nothing to migrate")
        return

    with open(CURIOSITY_FEED, 'r') as f:
        feed = json.load(f)

    questions = feed.get('questions', [])
    if not questions:
        print("curiosity_feed.json is empty - nothing to migrate")
        return

    print(f"Migrating {len(questions)} questions from curiosity_feed.json...")

    prioritizer = QuestionPrioritizer(ChemPub())

    migrated_count = 0

    for question_dict in questions:
        q = CuriosityQuestion(**question_dict)

        # Compute hash for null-hash questions
        if q.evidence_hash is None:
            q.evidence_hash = prioritizer.compute_evidence_hash(q.evidence)
            print(f"  Computed hash for {q.id}: {q.evidence_hash}")

        # Emit to appropriate priority queue
        prioritizer.prioritize_and_emit(q)
        migrated_count += 1
        print(f"  Migrated {q.id}")

    # Backup old feed
    backup_path = CURIOSITY_FEED.parent / f'curiosity_feed.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    shutil.copy(CURIOSITY_FEED, backup_path)
    print(f"\nBacked up old feed to {backup_path}")

    # Clear feed (new system uses chemical signals)
    with open(CURIOSITY_FEED, 'w') as f:
        json.dump({
            'questions': [],
            'generated_at': datetime.now().isoformat(),
            'count': 0
        }, f, indent=2)

    print(f"\nMigration complete: {migrated_count} questions migrated to priority queues")
    print("Old feed cleared (backup preserved)")

if __name__ == '__main__':
    migrate_existing_feed()
```

**Run Migration:**
```bash
python3 /home/kloros/src/scripts/migrate_curiosity_to_priority_queues.py
```

### Phase 3: Update Question Generators

**Files to Modify:**
- `/home/kloros/src/registry/capability_discovery_monitor.py` - Use QuestionPrioritizer
- `/home/kloros/src/registry/curiosity_core.py` - Use QuestionPrioritizer for chaos questions

**Changes:**
```python
# capability_discovery_monitor.py
from registry.question_prioritizer import QuestionPrioritizer

class CapabilityDiscoveryMonitor:
    def __init__(self):
        # ... existing init ...
        self.prioritizer = QuestionPrioritizer(self.chem_pub)

    def _generate_capability_questions(self, gaps: List[CapabilityGap]) -> List[CuriosityQuestion]:
        questions = []
        for gap in gaps:
            # ... existing question creation ...
            q = CuriosityQuestion(
                id=question_id,
                hypothesis=f"MISSING_CAPABILITY_{gap.category}_{gap.name}",
                question=f"Should I acquire {gap.name}...",
                evidence=[...],
                # evidence_hash will be computed by prioritizer
                action_class=ActionClass.FIND_SUBSTITUTE,
                ...
            )

            # Emit via prioritizer instead of appending to list
            self.prioritizer.prioritize_and_emit(q)

        return []  # No longer return list - questions emitted as signals
```

### Phase 4: Enable Priority Queue Mode

**Set Environment Variable:**
```bash
echo 'KLR_USE_PRIORITY_QUEUES=1' >> /etc/kloros/environment
```

**Restart Processor:**
```bash
systemctl restart kloros-curiosity-processor
```

**Monitor:**
```bash
journalctl -u kloros-curiosity-processor -f | grep -E "priority|queue|archive"
```

### Rollback Plan

**If Issues Detected Within 24 Hours:**

```bash
# 1. Disable priority queues
echo 'KLR_USE_PRIORITY_QUEUES=0' >> /etc/kloros/environment

# 2. Restore backup feed
BACKUP=$(ls -t ~/.kloros/curiosity_feed.backup.*.json | head -1)
cp $BACKUP ~/.kloros/curiosity_feed.json

# 3. Restart processor
systemctl restart kloros-curiosity-processor

# 4. Verify legacy mode
journalctl -u kloros-curiosity-processor -n 50 | grep "Starting file polling loop"
```

**Notes:**
- Questions in ZMQ queues at rollback time will be lost
- They will regenerate from capability_discovery and other sources
- Backed up feed provides safety net

---

## Success Metrics

### Before (File-Based Polling)

**Performance:**
- Poll frequency: 3 cycles/minute (every 20 seconds)
- CPU usage: 54 seconds/hour checking same questions
- Log entries: 180/hour (60 cycle start + 60 cycle end + 60 diagnostic)
- Disk I/O: 180 reads/hour of curiosity_feed.json

**Stuck Questions:**
- `enable.agent.browser`: 0 intents emitted, infinite loop
- `enable.module.inference`: 0 intents emitted, skipped due to dedup
- `chaos.healing_failure.synth_timeout_hard`: 0 intents emitted, infinite loop

**Issues:**
- Questions with null `evidence_hash` cause cleanup to remove them on restart
- VALUE_THRESHOLD=1.5 too high for capability discovery (ratio 1.23 < 1.5)
- No removal mechanism → questions stuck indefinitely

### After (Priority Queue System)

**Performance:**
- Event-driven: 0 cycles when queues empty
- CPU usage: ~0 when idle, only processes when signals arrive
- Log entries: ~10-20/hour (only on actual processing)
- Disk I/O: 0 reads in hot path, occasional archive writes

**Question Flow:**
- `enable.agent.browser`: category=capability_gap, threshold=1.0, ratio=1.23 → Q_CURIOSITY_MEDIUM
- `enable.module.inference`: dedup hit → archived to already_processed.jsonl
- `chaos.healing_failure.synth_timeout_hard`: category=chaos, threshold=1.5, ratio=1.18 → Q_CURIOSITY_LOW

**Improvements:**
- All questions get `evidence_hash` at creation (QuestionPrioritizer)
- Context-dependent thresholds prevent VALUE_THRESHOLD bottleneck
- Archival removes low-value questions from active processing
- Pattern detection generates meta-questions when archives grow

### Quality Metrics

**Archive Pattern Detection:**
- If 10+ questions archive as `low_value` → emit pattern investigation
- If 5+ questions archive as `resource_blocked` → resource pressure issue
- Emergent priority via file size: largest archive = most systemic issues

**Opportunistic Rehydration:**
- Main queues < 5 questions → pull from largest archive
- Keeps system busy during idle periods
- Revisits low-value work when higher-priority work done

---

## Testing Strategy

### Unit Tests

**QuestionPrioritizer:**
- `test_compute_evidence_hash()` - deterministic, order-independent
- `test_context_dependent_thresholds()` - capability_gap uses 1.0, chaos uses 1.5
- `test_priority_signal_selection()` - ratio 3.5 → CRITICAL, 2.5 → HIGH, etc.
- `test_critical_override()` - healing_rate:0.00 → CRITICAL regardless of ratio

**ArchiveManager:**
- `test_archive_creation()` - creates category-specific files
- `test_pattern_detection()` - 10 low_value → emit pattern investigation
- `test_opportunistic_rehydration()` - main feed < 5 → pull from largest archive
- `test_purge_old_entries()` - removes entries older than 7 days

### Integration Tests

**End-to-End Flow:**
1. Create test question with null `evidence_hash`
2. Pass through QuestionPrioritizer
3. Verify `evidence_hash` computed
4. Verify emitted to correct priority signal
5. Processor receives and processes
6. On skip, verify archived to correct category
7. Verify Q_CURIOSITY_ARCHIVED emitted

**Migration:**
1. Create test curiosity_feed.json with 3 questions (2 with null hash)
2. Run migration script
3. Verify hashes computed for null-hash questions
4. Verify signals emitted to correct priorities
5. Verify backup created
6. Verify feed cleared

### Performance Testing

**Idle Behavior:**
1. Clear all queues
2. Monitor processor for 5 minutes
3. Verify 0 CPU usage (event-driven, not polling)
4. Verify no log spam

**Priority Ordering:**
1. Emit questions to all 4 priority levels simultaneously
2. Verify processor handles CRITICAL first, then HIGH, then MEDIUM, then LOW
3. Verify no starvation of lower priorities

**Archive Growth:**
1. Generate 10 low-value questions
2. Verify archived to low_value.jsonl
3. Verify pattern investigation emitted at threshold (10)
4. Verify meta-question has HIGH priority

---

## Implementation Plan

### Task 1: Create QuestionPrioritizer
**File**: `/home/kloros/src/registry/question_prioritizer.py`
**Subtasks:**
- Implement `compute_evidence_hash()` helper
- Implement context-dependent threshold logic
- Implement `prioritize_and_emit()` with ratio-based signal selection
- Add critical override for urgent questions
- Unit tests

### Task 2: Create ArchiveManager
**File**: `/home/kloros/src/registry/curiosity_archive_manager.py`
**Subtasks:**
- Implement category-specific archive files
- Implement `archive_question()` with pattern detection
- Implement `rehydrate_opportunistic()` for idle periods
- Implement `purge_old_entries()` for maintenance
- Unit tests

### Task 3: Migration Script
**File**: `/home/kloros/src/scripts/migrate_curiosity_to_priority_queues.py`
**Subtasks:**
- Load existing curiosity_feed.json
- Compute hashes for null-hash questions
- Emit to priority signals via QuestionPrioritizer
- Backup old feed
- Clear feed

### Task 4: Update Question Generators
**Files**:
- `/home/kloros/src/registry/capability_discovery_monitor.py`
- `/home/kloros/src/registry/curiosity_core.py` (chaos questions)

**Subtasks:**
- Import QuestionPrioritizer
- Replace direct emission with `prioritizer.prioritize_and_emit()`
- Remove manual evidence_hash computation (prioritizer handles it)

### Task 5: Modify Processor Loop
**File**: `/home/kloros/src/kloros/orchestration/curiosity_processor.py`
**Subtasks:**
- Add feature flag `USE_PRIORITY_QUEUES`
- Implement `_run_priority_queue_loop()` with event-driven polling
- Update `_process_question()` to return skip reasons
- Integrate ArchiveManager for skip handling
- Add opportunistic rehydration

### Task 6: Integration Testing
**Subtasks:**
- End-to-end test with all components
- Migration test with real curiosity_feed.json backup
- Performance test for idle behavior
- Priority ordering test
- Archive pattern detection test

---

## Deployment Timeline

**Day 1: Implementation**
- Tasks 1-2 (QuestionPrioritizer, ArchiveManager) - 4 hours
- Task 3 (Migration script) - 1 hour
- Task 4 (Update generators) - 2 hours
- Task 5 (Processor loop) - 3 hours
- Task 6 (Integration tests) - 2 hours

**Day 2: Deployment and Monitoring**
- Run migration script (5 minutes)
- Enable priority queue mode (2 minutes)
- Restart services (1 minute)
- Monitor for 4 hours
- Verify metrics (CPU, logs, archives)

**Day 3-4: Validation Period**
- 24-hour monitoring
- Check for regressions
- Validate archive pattern detection
- Confirm questions flowing correctly

**Day 5: Cleanup**
- Remove legacy polling code if validation successful
- Document final architecture
- Update runbooks

---

## Future Enhancements (Path to Approach C)

### Meta-Reasoning About Archives

Once priority queue system stable, add LLM-based pattern analysis:

```python
def analyze_archive_pattern(category: str, count: int):
    """Use LLM to reason about why archive is growing."""

    # Sample questions from archive
    samples = _sample_archive(category, n=5)

    prompt = f"""
    {count} curiosity questions have been archived as '{category}'.

    Sample questions:
    {json.dumps(samples, indent=2)}

    Why might this be happening? Suggest:
    1. Root cause of pattern
    2. Threshold adjustments
    3. System changes to reduce archival rate
    """

    analysis = llm.generate(prompt)

    # Emit meta-question with LLM insights
    emit_meta_question(analysis)
```

### Adaptive Thresholds

Learn optimal thresholds from outcomes:

```python
def adjust_thresholds_from_outcomes():
    """Analyze which questions led to successful intents vs. skipped."""

    # Track: (category, ratio) → outcome (intent_emitted vs. skipped)
    # Adjust thresholds to maximize useful work

    if capability_gap_success_rate > 0.8:
        lower_threshold('capability_gap')  # More questions being useful

    if chaos_skip_rate > 0.6:
        raise_threshold('chaos')  # Too many low-value chaos questions
```

### Self-Managing Curiosity

Curiosity system reasons about its own state:

```python
def emit_self_reflection_questions():
    """Curiosity about curiosity itself."""

    if idle_time > 1_hour:
        emit("Why haven't I been curious about anything for an hour?")

    if archive_growth_rate > threshold:
        emit("Am I archiving too many questions? Should I be more exploratory?")

    if question_diversity < 0.3:
        emit("I keep asking similar questions. Should I explore new areas?")
```

These enhancements build naturally on the priority queue foundation.
