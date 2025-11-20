"""
CapabilityDiscoveryMonitor - Orchestrates capability gap detection.

Coordinates scanner execution, prioritization, and question generation.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.registry.capability_scanners.base import (
    CapabilityScanner,
    CapabilityGap,
    ScannerMetadata
)
from src.registry.question_prioritizer import QuestionPrioritizer

try:
    from src.kloros.orchestration.chem_bus_v2 import ChemPub
except ImportError:
    from kloros.orchestration.chem_bus_v2 import ChemPub

logger = logging.getLogger(__name__)


class CapabilityDiscoveryMonitor:
    """
    Orchestrates capability discovery through pluggable scanners.

    Responsibilities:
    - Discover and register scanners
    - Schedule scanner execution
    - Track scanner state
    - Generate curiosity questions from gaps
    """

    def __init__(
        self,
        scanner_state_path: Path = Path("/home/kloros/.kloros/scanner_state.json"),
        operation_patterns_path: Path = Path("/home/kloros/.kloros/operation_patterns.jsonl")
    ):
        """Initialize monitor and load persisted state."""
        self.scanner_state_path = scanner_state_path
        self.operation_patterns_path = operation_patterns_path

        self.scanner_state = self._load_scanner_state()
        self.operation_patterns = self._load_operation_patterns()

        self.scanners: List[CapabilityScanner] = []
        self._discover_scanners()

        self.chem_pub = ChemPub()
        self.prioritizer = QuestionPrioritizer(self.chem_pub)
        logger.info("[capability_monitor] Using QuestionPrioritizer for question emission")

        logger.info(f"[capability_monitor] Initialized with {len(self.scanners)} scanners")

    def _load_scanner_state(self) -> Dict[str, Dict[str, Any]]:
        """Load scanner state from disk."""
        if not self.scanner_state_path.exists():
            return {}

        try:
            with open(self.scanner_state_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[capability_monitor] Failed to load scanner state: {e}")
            return {}

    def _load_operation_patterns(self) -> Dict[str, List[Dict[str, Any]]]:
        """Load operation patterns from disk (7-day window)."""
        if not self.operation_patterns_path.exists():
            return {}

        patterns = {}
        cutoff = time.time() - (7 * 86400)

        try:
            with open(self.operation_patterns_path, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        timestamp = entry.get('timestamp', 0)
                        if timestamp >= cutoff:
                            operation = entry.get('operation', 'unknown')
                            if operation not in patterns:
                                patterns[operation] = []
                            patterns[operation].append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"[capability_monitor] Failed to load operation patterns: {e}")

        return patterns

    def _discover_scanners(self) -> None:
        """Auto-discover scanner classes from capability_scanners package."""
        from src.registry import capability_scanners
        import inspect

        discovered = []

        for name in dir(capability_scanners):
            obj = getattr(capability_scanners, name)

            if (inspect.isclass(obj) and
                issubclass(obj, CapabilityScanner) and
                obj is not CapabilityScanner):

                try:
                    scanner = obj()
                    metadata = scanner.get_metadata()

                    if metadata.name in self.scanner_state:
                        state = self.scanner_state[metadata.name]
                        scanner.last_run = state.get('last_run', 0.0)
                        scanner.suspended = state.get('suspended', False)
                    else:
                        scanner.last_run = 0.0
                        scanner.suspended = False

                    discovered.append(scanner)
                    logger.info(f"[capability_monitor] Discovered scanner: {metadata.name}")

                except Exception as e:
                    logger.warning(f"[capability_monitor] Failed to instantiate {name}: {e}")

        self.scanners = discovered
        logger.info(f"[capability_monitor] Discovered {len(discovered)} scanners")

    def _calculate_frequency_score(self, gap: CapabilityGap) -> float:
        """
        Calculate frequency score (0.0-1.0) based on operation patterns.

        Higher score = operation happens frequently, need is urgent.
        """
        operation = gap.metadata.get('operation')
        if not operation or operation not in self.operation_patterns:
            return 0.1

        patterns = self.operation_patterns[operation]
        count = len(patterns)

        frequency_score = min(count / 10.0, 1.0)

        if gap.metadata.get('reactive', False):
            frequency_score = min(frequency_score + 0.3, 1.0)

        return frequency_score

    def _calculate_priority_score(
        self,
        frequency: float,
        voi: float,
        alignment: float,
        cost: float
    ) -> float:
        """
        Calculate hybrid priority score.

        Formula: (frequency * 0.3) + (voi * 0.35) + (alignment * 0.25) + ((1-cost) * 0.1)

        Returns score 0.0-1.0.
        """
        priority = (
            (frequency * 0.3) +
            (voi * 0.35) +
            (alignment * 0.25) +
            ((1.0 - cost) * 0.1)
        )

        return max(0.0, min(priority, 1.0))

    def generate_capability_questions(self) -> List[Any]:
        """
        Generate curiosity questions from capability gaps.

        Steps:
        1. Run scanners that should_run
        2. Collect capability gaps
        3. Score gaps with hybrid prioritization
        4. Convert top N gaps to CuriosityQuestions
        5. Emit via QuestionPrioritizer

        Returns empty list (questions emitted as signals, not returned).
        """
        from src.registry.curiosity_core import CuriosityQuestion, ActionClass

        all_gaps = []

        for scanner in self.scanners:
            metadata = scanner.get_metadata()

            if getattr(scanner, 'suspended', False):
                logger.debug(f"[capability_monitor] Skipping suspended scanner: {metadata.name}")
                continue

            idle_budget = 5.0
            if not scanner.should_run(
                last_run=getattr(scanner, 'last_run', 0.0),
                idle_budget=idle_budget
            ):
                logger.debug(f"[capability_monitor] Skipping {metadata.name} (not scheduled)")
                continue

            try:
                logger.info(f"[capability_monitor] Running scanner: {metadata.name}")
                gaps = scanner.scan()
                all_gaps.extend(gaps)

                scanner.last_run = time.time()

            except Exception as e:
                logger.warning(f"[capability_monitor] Scanner {metadata.name} failed: {e}")

        if not all_gaps:
            logger.info("[capability_monitor] No capability gaps detected")
            return []

        scored_gaps = []
        for gap in all_gaps:
            frequency = self._calculate_frequency_score(gap)
            voi = 0.5
            alignment = gap.alignment_score
            cost = gap.install_cost

            priority = self._calculate_priority_score(frequency, voi, alignment, cost)

            scored_gaps.append((priority, gap))

        scored_gaps.sort(key=lambda x: x[0], reverse=True)

        top_gaps = scored_gaps[:10]

        emitted_count = 0
        for priority, gap in top_gaps:
            question_id = self._generate_question_id(gap)

            q = CuriosityQuestion(
                id=question_id,
                hypothesis=f"MISSING_CAPABILITY_{gap.category}_{gap.name}",
                question=f"Should I acquire {gap.name} to improve {gap.category} capabilities?",
                evidence=[
                    gap.reason,
                    f"type:{gap.type}",
                    f"category:{gap.category}",
                    f"alignment:{gap.alignment_score:.2f}",
                    f"install_cost:{gap.install_cost:.2f}",
                    f"priority:{priority:.2f}"
                ],
                action_class=ActionClass.FIND_SUBSTITUTE,
                value_estimate=priority,
                cost=gap.install_cost,
                capability_key=f"{gap.category}.{gap.name}"
            )

            self.prioritizer.prioritize_and_emit(q)
            emitted_count += 1

        logger.info(f"[capability_monitor] Emitted {emitted_count} capability questions via prioritizer")

        self._save_scanner_state()

        return []

    def _generate_question_id(self, gap: CapabilityGap) -> str:
        """Generate unique question ID for capability gap."""
        import hashlib
        content = f"{gap.type}:{gap.category}:{gap.name}"
        hash_digest = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"capability.{gap.category}.{hash_digest}"

    def _save_scanner_state(self) -> None:
        """Save scanner state to disk."""
        state = {}
        for scanner in self.scanners:
            metadata = scanner.get_metadata()
            state[metadata.name] = {
                'last_run': getattr(scanner, 'last_run', 0.0),
                'suspended': getattr(scanner, 'suspended', False)
            }

        try:
            tmp_path = Path(str(self.scanner_state_path) + '.tmp')
            with open(tmp_path, 'w') as f:
                json.dump(state, f, indent=2)
            tmp_path.rename(self.scanner_state_path)

            logger.debug(f"[capability_monitor] Saved scanner state")

        except Exception as e:
            logger.warning(f"[capability_monitor] Failed to save scanner state: {e}")
