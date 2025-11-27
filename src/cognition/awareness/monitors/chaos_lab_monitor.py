"""
Chaos Lab Monitor - Self-healing failure detection.

Monitors Chaos Lab results and generates curiosity questions about poor self-healing.
"""

import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, Any, List

from .base_types import (
    CuriosityQuestion,
    QuestionStatus,
    ActionClass,
)

logger = logging.getLogger(__name__)


class ChaosLabMonitor:
    """
    Monitors Chaos Lab results and generates curiosity questions about poor self-healing.

    Purpose:
        Detect repeated healing failures and spawn D-REAM experiments
        to improve self-healing capabilities

    Outcomes:
        - Identifies components with low healing scores (<70%)
        - Detects high MTTR scenarios (>5s)
        - Generates questions about systematic healing failures
    """

    def __init__(
        self,
        history_path: Path = Path("/home/kloros/.kloros/chaos_history.jsonl"),
        metrics_path: Path = Path("/home/kloros/.kloros/dream_chaos_metrics.jsonl"),
        prioritizer=None
    ):
        self.history_path = history_path
        self.metrics_path = metrics_path
        self.lookback_experiments = 20
        self.signals_skipped_disabled = 0
        self.prioritizer = prioritizer

    def _is_target_disabled(self, target: str) -> bool:
        """Check if a chaos scenario target is for a disabled system."""
        if any(keyword in target.lower() for keyword in ['dream', 'rag']):
            dream_enabled = os.getenv('KLR_ENABLE_DREAM_EVOLUTION', '1') == '1'
            if not dream_enabled:
                return True

        if any(keyword in target.lower() for keyword in ['tts', 'audio']):
            return True

        return False

    def scan_healing_failures(self) -> Dict[str, List[Dict]]:
        """Scan recent chaos experiments for systematic healing failures."""
        failures_by_scenario = defaultdict(list)

        if not self.history_path.exists():
            return failures_by_scenario

        try:
            with open(self.history_path, 'r') as f:
                experiments = [json.loads(line) for line in f if line.strip()]

            by_scenario = defaultdict(list)
            for exp in experiments:
                spec_id = exp.get("spec_id")
                by_scenario[spec_id].append(exp)

            for spec_id, exps in by_scenario.items():
                recent = exps[-self.lookback_experiments:]

                healed_count = sum(1 for e in recent if e.get("outcome", {}).get("healed"))
                healing_rate = healed_count / len(recent) if recent else 0

                avg_score = sum(e.get("score", 0) for e in recent) / len(recent) if recent else 0

                if healing_rate < 0.3 or avg_score < 50:
                    failures_by_scenario[spec_id].extend(recent)

        except Exception as e:
            logger.error(f"[chaos_monitor] Failed to scan failures: {e}")

        return dict(failures_by_scenario)

    def generate_chaos_questions(self) -> List[CuriosityQuestion]:
        """Generate curiosity questions from chaos lab failures."""
        failures = self.scan_healing_failures()

        emitted_count = 0
        questions = []

        for spec_id, experiments in failures.items():
            if len(experiments) < 3:
                continue

            healed_count = sum(1 for e in experiments if e.get("outcome", {}).get("healed"))
            healing_rate = healed_count / len(experiments)
            avg_score = sum(e.get("score", 0) for e in experiments) / len(experiments)

            mttrs = [e.get("outcome", {}).get("duration_s", 0) for e in experiments]
            avg_mttr = sum(mttrs) / len(mttrs) if mttrs else 0

            target = experiments[0].get("target", "unknown")
            mode = experiments[0].get("mode", "unknown")

            if self._is_target_disabled(target):
                logger.info(
                    f"[chaos_monitor] Healing failure expected for disabled system: "
                    f"{spec_id} (target={target}, rate={healing_rate:.1%}, score={avg_score:.1f})"
                )
                self.signals_skipped_disabled += 1
                continue

            hypothesis = f"POOR_SELF_HEALING_{spec_id.upper().replace('-', '_')}"
            question = (
                f"Why is self-healing failing for {spec_id} ({target}/{mode})? "
                f"Healing rate: {healing_rate:.1%}, avg score: {avg_score:.0f}/100, "
                f"avg MTTR: {avg_mttr:.1f}s over {len(experiments)} experiments. "
                f"How can I improve recovery mechanisms?"
            )

            evidence = [
                f"scenario:{spec_id}",
                f"target:{target}",
                f"mode:{mode}"
            ]

            if healing_rate < 0.1 or avg_score < 30:
                value = 0.95
            elif healing_rate < 0.3 or avg_score < 50:
                value = 0.85
            else:
                value = 0.70

            q = CuriosityQuestion(
                id=f"chaos.healing_failure.{spec_id}",
                hypothesis=hypothesis,
                question=question,
                evidence=evidence,
                action_class=ActionClass.PROPOSE_FIX,
                autonomy=3,
                value_estimate=value,
                cost=0.5,
                status=QuestionStatus.READY,
                capability_key=f"self_healing.{target}"
            )

            if self.prioritizer is not None:
                self.prioritizer.prioritize_and_emit(q)
                emitted_count += 1
            else:
                questions.append(q)

        logger.info(f"[chaos_monitor] Emitted {emitted_count} chaos questions via prioritizer")

        return questions
