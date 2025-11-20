#!/usr/bin/env python3
"""
QuestionPrioritizer - Compute evidence hashes and emit questions to priority queues.

Purpose:
    Centralized logic for evidence hash computation, priority determination, and
    chemical signal emission. Replaces ad-hoc priority logic scattered across
    question generators. Ensures all questions have evidence_hash set before
    entering the system.

Governance:
    - Tool-Integrity: Deterministic hashing, context-dependent thresholds
    - D-REAM-Allowed-Stack: Uses JSON and chemical signals, no unbounded loops
    - Autonomy Level 2: Determines priority, human decides processing
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING, Any

try:
    from kloros.orchestration.chem_bus_v2 import ChemPub
except ImportError:
    from orchestration.chem_bus_v2 import ChemPub

if TYPE_CHECKING:
    from registry.curiosity_core import CuriosityQuestion, ActionClass
    from registry.curiosity_archive_manager import ArchiveManager

logger = logging.getLogger(__name__)


class QuestionPrioritizer:
    """
    Compute evidence hashes and emit questions to appropriate priority queues.

    Replaces ad-hoc priority logic scattered across question generators.
    Ensures all questions have evidence_hash set before entering system.

    Attributes:
        chem_pub: Chemical publisher for emitting priority signals
        thresholds: Context-dependent value/cost ratio thresholds per category
    """

    def __init__(self, chem_pub: ChemPub):
        """
        Initialize prioritizer with chemical publisher.

        Args:
            chem_pub: ChemPub instance for emitting signals
        """
        self.chem_pub = chem_pub

        self.thresholds = {
            'capability_gap': 1.0,
            'chaos_engineering': 1.5,
            'integration': 2.0,
            'discovery': 0.8
        }

    def compute_evidence_hash(self, evidence: List[str]) -> str:
        """
        Deterministic SHA256 hash from sorted evidence list.

        Ensures evidence order doesn't affect hash, enabling deduplication.
        Hash is truncated to 16 characters for readability in logs.

        Args:
            evidence: List of evidence strings

        Returns:
            16-character hex hash (first 16 chars of SHA256)
        """
        evidence_str = "|".join(sorted(evidence))
        return hashlib.sha256(evidence_str.encode()).hexdigest()[:16]

    def _is_already_processed(self, evidence_hash: str) -> bool:
        """
        Check if question with this evidence hash was already processed.

        Prevents wasteful re-emission of questions that have already been
        processed, archived, or are in cooldown.

        Args:
            evidence_hash: 16-character hex hash to check

        Returns:
            True if hash exists in processed_questions.jsonl, False otherwise
        """
        processed_path = Path.home() / '.kloros' / 'processed_questions.jsonl'

        if not processed_path.exists():
            return False

        try:
            with open(processed_path, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get('evidence_hash') == evidence_hash:
                            return True
                    except (json.JSONDecodeError, KeyError):
                        continue
            return False
        except Exception as e:
            logger.warning(f"[prioritizer] Failed to check processed_questions: {e}")
            return False

    def _detect_category(self, question: Any) -> str:
        """
        Infer question category from ID, hypothesis, or capability_key.

        Categories determine threshold lookup and pattern detection.

        Args:
            question: CuriosityQuestion to categorize

        Returns:
            Category string: 'capability_gap', 'chaos_engineering',
                           'integration', 'discovery', or 'unknown'
        """
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

    def _is_critical(self, question: Any) -> bool:
        """
        Check if question represents critical system issue regardless of ratio.

        Critical issues override normal priority thresholds and get CRITICAL signal.

        Detection rules:
        - Self-healing failures with 0% success rate (healing_rate:0.00)
        - Missing critical capabilities (health.monitor, error.detection)

        Args:
            question: CuriosityQuestion to check

        Returns:
            True if question represents critical system issue
        """
        if 'healing_rate:0.00' in question.evidence:
            return True

        if question.capability_key in ['health.monitor', 'error.detection']:
            return True

        return False

    def prioritize_and_emit(self, question: Any) -> None:
        """
        Compute hash, determine priority, emit to appropriate chemical signal.

        Main entry point for all question generators. Implements priority logic:
        - ratio > 3.0 OR critical → Q_CURIOSITY_CRITICAL
        - ratio > 2.0 → Q_CURIOSITY_HIGH
        - ratio > threshold → Q_CURIOSITY_MEDIUM
        - ratio > 0.5 → Q_CURIOSITY_LOW
        - ratio < 0.5 → archive(low_value)

        Args:
            question: CuriosityQuestion to prioritize and emit
        """
        if not question.evidence_hash:
            question.evidence_hash = self.compute_evidence_hash(question.evidence)

        # DEDUPLICATION BYPASS (2025-11-16): Let downstream filters handle deduplication
        # Rationale: processed_question_filter.py has cooldown bypass logic for re-investigation
        # Prioritizer should only prioritize+emit, not filter
        # if self._is_already_processed(question.evidence_hash):
        #     logger.debug(
        #         f"[prioritizer] Skipped {question.id} - already processed "
        #         f"(hash={question.evidence_hash})"
        #     )
        #     return

        category = self._detect_category(question)
        threshold = self.thresholds.get(category, 1.5)

        ratio = question.value_estimate / max(question.cost, 0.01)

        if ratio > 3.0 or self._is_critical(question):
            signal = "Q_CURIOSITY_CRITICAL"
        elif ratio > 2.0:
            signal = "Q_CURIOSITY_HIGH"
        elif ratio > threshold:
            signal = "Q_CURIOSITY_MEDIUM"
        elif ratio > 0.5:
            signal = "Q_CURIOSITY_LOW"
        else:
            try:
                from registry.curiosity_archive_manager import ArchiveManager
            except ImportError:
                from curiosity_archive_manager import ArchiveManager

            archive_mgr = ArchiveManager(
                Path.home() / '.kloros' / 'archives',
                self.chem_pub
            )
            archive_mgr.archive_question(question, 'low_value')
            return

        self.chem_pub.emit(
            signal,
            ecosystem='introspection',
            facts=question.to_dict()
        )
        logger.info(
            f"[prioritizer] Emitted {question.id} to {signal} "
            f"(ratio={ratio:.2f}, category={category}, hash={question.evidence_hash})"
        )
