#!/usr/bin/env python3
"""
ProcessedQuestionFilter - Intelligent question lifecycle management

Filters processed questions based on lifecycle rules to enable computational
autopoiesis: questions are re-examined after appropriate cooldown periods.

Design: docs/plans/2025-11-06-curiosity-feed-filtering-design.md
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Import CuriosityQuestion from curiosity_core
try:
    from .curiosity_core import CuriosityQuestion
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from curiosity_core import CuriosityQuestion


class ProcessedQuestionFilter:
    """
    Filters processed questions based on lifecycle rules.

    Enables computational autopoiesis by allowing questions to be
    re-examined after appropriate cooldown periods.

    Lifecycle Rules:
    - Structural integration: 30 days (wiring can break with code changes)
    - Performance monitoring: 3 days (performance can degrade)
    - Resource pressure: 1 day (resources are dynamic)
    - Investigation/discovery: 7 days (insights evolve)
    - Test failures: 0 days (test state changes frequently)
    """

    def __init__(
        self,
        processed_path: Path = Path("/home/kloros/.kloros/processed_questions.jsonl")
    ):
        """
        Initialize filter with processed questions state.

        Args:
            processed_path: Path to processed_questions.jsonl
        """
        self.processed_path = processed_path
        self._processed_cache: Dict[str, Dict] = {}  # {question_id: {timestamp, evidence_hash}}
        self._load_processed_state()

    def _load_processed_state(self) -> None:
        """
        Load processed questions into memory cache.

        Reads processed_questions.jsonl and builds {question_id: {timestamp, evidence_hash}} map.
        Handles missing/corrupted files gracefully (fail-open).
        """
        if not self.processed_path.exists():
            logger.debug(f"[filter] No processed questions file found at {self.processed_path}")
            return

        try:
            with open(self.processed_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue

                    try:
                        entry = json.loads(line)
                        qid = entry.get("question_id")
                        processed_at = entry.get("processed_at", 0)
                        evidence_hash = entry.get("evidence_hash")

                        if qid:
                            # Keep most recent processing if duplicate entries
                            if qid not in self._processed_cache or processed_at > self._processed_cache[qid].get("timestamp", 0):
                                self._processed_cache[qid] = {
                                    "timestamp": processed_at,
                                    "evidence_hash": evidence_hash
                                }
                    except json.JSONDecodeError:
                        logger.warning(f"[filter] Skipping malformed JSON at line {line_num}")
                        continue

            logger.info(f"[filter] Loaded {len(self._processed_cache)} processed questions")

        except Exception as e:
            logger.warning(f"[filter] Failed to load processed questions, continuing with empty cache: {e}")
            self._processed_cache = {}

    def _get_cooldown_days(self, question: CuriosityQuestion) -> int:
        """
        Determine cooldown period based on question type.

        Args:
            question: CuriosityQuestion to classify

        Returns:
            Cooldown period in days (0, 1, 3, 7, or 30)
        """
        try:
            action_class = question.action_class if hasattr(question, 'action_class') else None
            hypothesis = question.hypothesis if hasattr(question, 'hypothesis') else ""
            evidence = question.evidence if hasattr(question, 'evidence') else []

            # Type 1: Structural Integration Issues (30 days)
            if action_class and hasattr(action_class, 'value'):
                action_value = action_class.value
            else:
                action_value = str(action_class) if action_class else ""

            if action_value == "propose_fix" and (
                hypothesis.startswith("UNINITIALIZED_COMPONENT_") or
                hypothesis.startswith("ORPHANED_QUEUE_") or
                hypothesis.startswith("DUPLICATE_")
            ):
                return 30

            # Type 5: Test Failures (0 days - regenerate immediately)
            if any("test" in str(ev).lower() or "pytest" in str(ev).lower() for ev in evidence):
                return 0

            # Type 3: Resource Pressure (1 day)
            resource_keywords = ["swap", "memory", "gpu", "cpu", "disk"]
            if any(keyword in hypothesis.lower() for keyword in resource_keywords):
                return 1
            if any(keyword in str(ev).lower() for keyword in resource_keywords for ev in evidence):
                return 1

            # Type 2: Performance Monitoring (3 days)
            perf_keywords = ["latency", "throughput", "pass_rate", "accuracy", "performance"]
            if any(keyword in hypothesis.lower() for keyword in perf_keywords):
                return 3
            if any(keyword in str(ev).lower() for keyword in perf_keywords for ev in evidence):
                return 3

            # Type 4: Investigation & Discovery (7 days - default)
            if action_value in ["investigate", "find_substitute"]:
                return 7

            # Default fallback: 7 days
            return 7

        except Exception as e:
            logger.warning(f"[filter] Error determining cooldown for {question.id}: {e}, using default 7 days")
            return 7

    def should_regenerate(self, question: CuriosityQuestion) -> bool:
        """
        Check if question should be regenerated.

        For UNDISCOVERED_MODULE questions: Uses evidence hash comparison
        For other questions: Uses time-based cooldown

        Args:
            question: CuriosityQuestion to check

        Returns:
            True if question should be included (new or evidence changed)
            False if question should be filtered out (same evidence already processed)
        """
        try:
            qid = question.id

            # New question - not in processed cache
            if qid not in self._processed_cache:
                return True

            # Evidence-based filtering for module discovery (context changes matter)
            if "UNDISCOVERED_MODULE" in question.hypothesis:
                new_hash = question.evidence_hash
                cached = self._processed_cache[qid]
                old_hash = cached.get("evidence_hash")

                if new_hash and old_hash:
                    if new_hash == old_hash:
                        logger.debug(f"[filter] {qid}: Same evidence hash {new_hash[:8]}..., skipping")
                        return False
                    else:
                        logger.info(f"[filter] {qid}: Evidence changed ({old_hash[:8]}... -> {new_hash[:8]}...), re-investigating")
                        return True

                logger.debug(f"[filter] {qid}: Missing evidence hash, allowing through")
                return True

            # COOLDOWN BYPASS (2025-11-16): Allow all questions through until convergence
            # Rationale: New actionability analysis deployed, need to re-investigate
            # all questions with new logic before implementing cooldowns
            logger.debug(f"[filter] {qid}: Cooldown bypass active - allowing through")
            return True

        except Exception as e:
            logger.warning(f"[filter] Error checking regeneration for {question.id}: {e}, allowing through")
            return True  # Fail-open: if check fails, include question

    def filter_questions(
        self,
        questions: List[CuriosityQuestion]
    ) -> List[CuriosityQuestion]:
        """
        Filter questions list, removing those still in cooldown.

        Args:
            questions: List of CuriosityQuestion objects

        Returns:
            Filtered list with only regeneratable questions
        """
        if not questions:
            return []

        original_count = len(questions)
        filtered_questions = []

        # Track filtering statistics by lifecycle type
        stats = {
            "structural": {"filtered": 0, "kept": 0},
            "performance": {"filtered": 0, "kept": 0},
            "resource": {"filtered": 0, "kept": 0},
            "investigation": {"filtered": 0, "kept": 0},
            "test": {"filtered": 0, "kept": 0},
            "default": {"filtered": 0, "kept": 0}
        }

        for question in questions:
            if self.should_regenerate(question):
                filtered_questions.append(question)

                # Track kept questions
                cooldown = self._get_cooldown_days(question)
                if cooldown == 30:
                    stats["structural"]["kept"] += 1
                elif cooldown == 3:
                    stats["performance"]["kept"] += 1
                elif cooldown == 1:
                    stats["resource"]["kept"] += 1
                elif cooldown == 0:
                    stats["test"]["kept"] += 1
                else:
                    stats["investigation"]["kept"] += 1
            else:
                # Track filtered questions
                cooldown = self._get_cooldown_days(question)
                if cooldown == 30:
                    stats["structural"]["filtered"] += 1
                elif cooldown == 3:
                    stats["performance"]["filtered"] += 1
                elif cooldown == 1:
                    stats["resource"]["filtered"] += 1
                elif cooldown == 0:
                    stats["test"]["filtered"] += 1
                else:
                    stats["investigation"]["filtered"] += 1

        filtered_count = original_count - len(filtered_questions)

        if filtered_count > 0:
            logger.info(f"[filter] Filtered {filtered_count}/{original_count} questions still in cooldown")

            # Log breakdown by type
            for qtype, counts in stats.items():
                if counts["filtered"] > 0 or counts["kept"] > 0:
                    logger.info(f"[filter]   {qtype}: filtered={counts['filtered']}, kept={counts['kept']}")

        return filtered_questions


if __name__ == "__main__":
    # Self-test
    logging.basicConfig(level=logging.INFO)

    print("=== ProcessedQuestionFilter Self-Test ===\n")

    filter_obj = ProcessedQuestionFilter()
    print(f"Loaded {len(filter_obj._processed_cache)} processed questions")

    if filter_obj._processed_cache:
        print("\nSample processed questions:")
        for i, (qid, data) in enumerate(list(filter_obj._processed_cache.items())[:5]):
            timestamp = data.get("timestamp", 0)
            evidence_hash = data.get("evidence_hash", "N/A")
            age_days = (time.time() - timestamp) / 86400 if timestamp else 0
            print(f"  {qid}: {age_days:.1f} days old (hash: {evidence_hash})")
