#!/usr/bin/env python3
"""
ArchiveManager - Persist skipped questions to category-specific files.

Archival reasons:
- low_value: ratio < threshold (low priority but might become relevant)
- already_processed: dedup hit (evidence unchanged, already investigated)
- resource_blocked: ResourceGovernor blocked (system constraints)
- missing_deps: Dependencies not available (blocked on external factors)

Pattern detection: Large file = many questions in same category = systemic issue.

When archive threshold is hit, emit a HIGH-priority pattern investigation question
to understand why so many questions are being archived in that category.

Opportunistic rehydration: When main queues are empty (< 5 questions), pull from
archives to keep system busy during idle periods. Largest archive first = emergent
priority (most systemic issues).

Periodic purging prevents infinite archive growth. Old entries (default 7 days)
are removed to keep archives lean and relevant.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional

try:
    from src.registry.curiosity_core import CuriosityQuestion, ActionClass, QuestionStatus
except ImportError:
    from registry.curiosity_core import CuriosityQuestion, ActionClass, QuestionStatus

try:
    from kloros.orchestration.chem_bus_v2 import ChemPub
except ImportError:
    from orchestration.chem_bus_v2 import ChemPub

logger = logging.getLogger(__name__)


class ArchiveManager:
    """
    Manage category-specific archives for skipped questions.

    Questions are archived based on skip reasons. Each category has its own
    .jsonl file for persistence. When archives grow large, pattern investigation
    questions are emitted at HIGH priority to understand systemic issues.
    """

    def __init__(self, archive_dir: Path, chem_pub: ChemPub, consciousness=None):
        """
        Initialize ArchiveManager with archive directory and chemical bus.

        Args:
            archive_dir: Directory to store archive .jsonl files
            chem_pub: ChemPub instance for emitting signals
            consciousness: Optional IntegratedConsciousness instance for process_discovery events
        """
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.chem_pub = chem_pub
        self.consciousness = consciousness

        self.archives = {
            'low_value': self.archive_dir / 'low_value.jsonl',
            'already_processed': self.archive_dir / 'already_processed.jsonl',
            'resource_blocked': self.archive_dir / 'resource_blocked.jsonl',
            'missing_deps': self.archive_dir / 'missing_deps.jsonl',
            'intent_generation_error': self.archive_dir / 'intent_generation_error.jsonl'
        }

        self.thresholds = {
            'low_value': 10,
            'resource_blocked': 5,
            'already_processed': 50,
            'missing_deps': 8,
            'intent_generation_error': 10
        }

        self.pattern_emission_cooldown = 300
        self.last_pattern_emission = {}

    def archive_question(self, question: CuriosityQuestion, reason: str) -> None:
        """
        Append question to category archive, emit pattern signal if threshold hit.

        When a question is skipped (dedup, resource blocked, etc.), it is appended
        to the appropriate archive file. After appending, we check if the archive
        size has reached a threshold. If it has, we emit a HIGH-priority pattern
        investigation question to understand why.

        Args:
            question: Question to archive
            reason: Category (low_value, already_processed, resource_blocked, missing_deps)
        """
        archive_file = self.archives.get(reason)
        if not archive_file:
            logger.warning(f"[archive_mgr] Unknown archive category: {reason}")
            return

        with open(archive_file, 'a') as f:
            json.dump(question.to_dict(), f)
            f.write('\n')

        self.chem_pub.emit("Q_CURIOSITY_ARCHIVED",
                          ecosystem='introspection',
                          facts={
                              'question_id': question.id,
                              'reason': reason,
                              'archive_file': str(archive_file),
                              'timestamp': datetime.now().isoformat()
                          })

        count = self._count_entries(archive_file)
        if count >= self.thresholds.get(reason, 999):
            if not question.id.startswith("pattern.archive."):
                now = datetime.now().timestamp()
                last_emission = self.last_pattern_emission.get(reason, 0)
                if now - last_emission >= self.pattern_emission_cooldown:
                    self._emit_pattern_investigation(reason, count)
                    self.last_pattern_emission[reason] = now
                else:
                    logger.debug(f"[archive_mgr] Pattern emission cooldown active for {reason} (last: {int(now - last_emission)}s ago)")
            else:
                logger.debug(f"[archive_mgr] Skipping pattern investigation for meta-question: {question.id}")

        logger.info(f"[archive_mgr] Archived {question.id} to {reason} ({count} entries)")

    def _count_entries(self, archive_file: Path) -> int:
        """
        Count non-empty lines in archive file.

        Blank lines are ignored. Returns 0 if file doesn't exist.

        Args:
            archive_file: Path to archive file

        Returns:
            Number of entries in archive
        """
        if not archive_file.exists():
            return 0
        with open(archive_file, 'r') as f:
            return sum(1 for line in f if line.strip())

    def _emit_pattern_investigation(self, category: str, count: int) -> None:
        """
        Emit HIGH-priority question about why archive is growing.

        When an archive reaches a threshold (e.g., 10 low_value questions),
        we emit a meta-question at HIGH priority asking why this pattern
        is occurring. This drives systemic analysis and threshold tuning.

        Example: "Why are 10 questions being classified as low_value?
        Should thresholds be adjusted?"

        Args:
            category: Archive category that triggered pattern detection
            count: Number of entries in the archive
        """
        pattern_question = CuriosityQuestion(
            id=f"pattern.archive.{category}",
            hypothesis=f"SYSTEMIC_ISSUE_{category.upper()}",
            question=(f"Why are {count} questions being archived as '{category}'? "
                     f"Is there a systemic issue with {category} categorization or thresholds?"),
            evidence=[
                f"archive_category:{category}",
                f"count:{count}",
                f"threshold:{self.thresholds.get(category)}",
                f"timestamp:{datetime.now().isoformat()}"
            ],
            action_class=ActionClass.INVESTIGATE,
            autonomy=2,
            value_estimate=0.8,
            cost=0.3,
            status=QuestionStatus.READY,
            capability_key=f"curiosity.{category}"
        )

        self.chem_pub.emit("Q_CURIOSITY_HIGH",
                          ecosystem='introspection',
                          facts=pattern_question.to_dict())

        if self.consciousness:
            try:
                significance = min(1.0, count / self.thresholds.get(category, 10))
                self.consciousness.process_discovery(
                    discovery_type="pattern",
                    significance=significance,
                    context=f"Archive pattern in {category} category with {count} entries"
                )
            except Exception as e:
                logger.error(f"[archive_mgr] Failed to emit discovery event: {e}")

        logger.warning(f"[archive_mgr] Pattern detected: {count} questions in {category} archive")

    def rehydrate_opportunistic(self, main_feed_size: int) -> None:
        """
        When main queues empty (< 5 questions), pull from archives.

        Largest archive first = emergent priority (most systemic issues).
        Pull top 3 questions and re-emit at LOW priority for reconsideration.

        This keeps the system productively engaged during idle periods and
        allows re-examination of previously-skipped questions when higher-priority
        work has been completed.

        IMPORTANT: Questions are REMOVED from the archive after rehydration to
        prevent infinite loops. If they get re-archived, they won't be rehydrated
        again unless new evidence appears.

        Args:
            main_feed_size: Number of questions currently in main queues
        """
        if main_feed_size >= 5:
            return

        # Only rehydrate from low_value and resource_blocked
        # Never from already_processed (those are done) or missing_deps (can't be processed yet)
        archive_sizes = {cat: self._count_entries(path)
                        for cat, path in self.archives.items()
                        if cat not in ['already_processed', 'missing_deps']}

        if not archive_sizes or max(archive_sizes.values()) == 0:
            return

        largest_category = max(archive_sizes, key=archive_sizes.get)
        largest_file = self.archives[largest_category]

        questions = self._read_and_remove_from_archive(largest_file, limit=3)

        for q in questions:
            self.chem_pub.emit("Q_CURIOSITY_LOW",
                              ecosystem='introspection',
                              facts=q)

        logger.info(f"[archive_mgr] Rehydrated {len(questions)} questions from {largest_category} "
                   f"(idle-time opportunistic)")

    def _read_and_remove_from_archive(self, archive_file: Path, limit: int = 3) -> List[Dict]:
        """
        Read first N questions from archive and REMOVE them from the file.

        This prevents infinite rehydration loops where the same questions
        get pulled repeatedly. Questions are permanently removed from the
        archive after being emitted for reconsideration.

        Args:
            archive_file: Path to archive file
            limit: Maximum number of questions to read and remove

        Returns:
            List of question dictionaries that were removed
        """
        questions = []
        remaining = []

        if not archive_file.exists():
            return questions

        # Read all entries, separate top N from rest
        with open(archive_file, 'r') as f:
            for i, line in enumerate(f):
                if not line.strip():
                    continue
                if i < limit:
                    questions.append(json.loads(line))
                else:
                    remaining.append(line)

        # Rewrite file with only remaining entries
        with open(archive_file, 'w') as f:
            f.writelines(remaining)

        logger.debug(f"[archive_mgr] Removed {len(questions)} questions from {archive_file.name}, {len(remaining)} remain")
        return questions

    def _read_archive(self, archive_file: Path, limit: int = 3) -> List[Dict]:
        """
        Read first N questions from archive WITHOUT removing them.

        Use this for inspection/reporting. For rehydration, use
        _read_and_remove_from_archive() to prevent infinite loops.

        Args:
            archive_file: Path to archive file
            limit: Maximum number of questions to read

        Returns:
            List of question dictionaries
        """
        questions = []
        if not archive_file.exists():
            return questions

        with open(archive_file, 'r') as f:
            for i, line in enumerate(f):
                if i >= limit:
                    break
                if line.strip():
                    questions.append(json.loads(line))
        return questions

    def purge_old_entries(self, category: str, max_age_days: int = 7) -> None:
        """
        Remove entries older than max_age_days from archive.

        Reads all entries from the archive, filters by created_at timestamp,
        and rewrites the file with only recent entries. This prevents
        infinite archive growth.

        Args:
            category: Archive category to purge
            max_age_days: Maximum age of entries to keep (default 7 days)
        """
        archive_file = self.archives.get(category)
        if not archive_file or not archive_file.exists():
            return

        cutoff = datetime.now() - timedelta(days=max_age_days)

        kept = []
        removed = 0

        with open(archive_file, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                created_str = entry.get('created_at')
                if not created_str:
                    created = cutoff
                else:
                    try:
                        created = datetime.fromisoformat(created_str)
                    except (ValueError, TypeError):
                        created = cutoff

                if created > cutoff:
                    kept.append(line)
                else:
                    removed += 1

        with open(archive_file, 'w') as f:
            f.writelines(kept)

        logger.info(f"[archive_mgr] Purged {removed} entries from {category} (older than {max_age_days}d)")
