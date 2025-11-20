#!/usr/bin/env python3
"""
PHASE Post-Run Analyzer: Bridge PHASE results to Curiosity System.

Analyzes PHASE results and feeds them into the existing CuriosityCore
for unified degradation detection and escalation.

Flow:
1. PHASE completes → phase_report.jsonl written
2. This analyzer runs automatically
3. Trigger CuriosityCore to scan:
   - PHASE metrics (via CapabilityMatrix)
   - D-REAM performance trends
   - System resource state
4. CuriosityCore generates questions
5. High-value questions trigger Config Tuning escalation

Integration:
- Called by PHASE completion handler or systemd After= dependency
- Uses existing CuriosityCore instead of duplicating logic
- Converts CuriosityQuestions to escalation triggers
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime

# Import existing curiosity infrastructure
sys.path.insert(0, str(Path(__file__).parent.parent))
from registry.curiosity_core import (
    CuriosityCore,
    PerformanceMonitor,
    SystemResourceMonitor,
    CuriosityQuestion,
    ActionClass
)
from registry.capability_evaluator import CapabilityEvaluator

logger = logging.getLogger(__name__)


@dataclass
class EscalationSummary:
    """Summary of escalations triggered from curiosity questions."""
    status: str
    questions_generated: int
    high_value_questions: int
    escalations_armed: int
    questions: List[Dict[str, Any]]
    timestamp: float
    duration_s: float


class PHASEAnalyzer:
    """
    Bridge PHASE to CuriosityCore for unified degradation detection.

    Instead of duplicating detection logic, this delegates to CuriosityCore
    which already monitors:
    - D-REAM performance trends
    - System resource pressure
    - Capability health

    Converts high-value CuriosityQuestions into escalation triggers.
    """

    def __init__(self):
        self.curiosity = CuriosityCore()
        self.capability_eval = CapabilityEvaluator()
        self.escalation_threshold = 0.6  # Questions with value/cost > 0.6 trigger escalation

    def _question_to_symptom_kind(self, question: CuriosityQuestion) -> str:
        """Convert CuriosityQuestion to symptom kind for Observer ledger."""
        # Map question hypotheses to symptom kinds
        hypothesis_lower = question.hypothesis.lower()

        if "oom" in hypothesis_lower or "memory" in hypothesis_lower:
            return "vllm_oom"
        elif "latency" in hypothesis_lower:
            return "latency_regression"
        elif "throughput" in hypothesis_lower or "performance" in hypothesis_lower:
            return "throughput_drop"
        elif "pass_rate" in hypothesis_lower or "accuracy" in hypothesis_lower:
            return "pass_rate_drop"
        elif "gpu" in hypothesis_lower:
            return "gpu_saturation"
        elif "cpu" in hypothesis_lower:
            return "cpu_saturation"
        else:
            return "capability_degraded"

    def _record_question_as_symptom(self, question: CuriosityQuestion) -> bool:
        """
        Record a CuriosityQuestion as a symptom in Observer ledger.

        Returns:
            True if escalation flag was armed, False otherwise
        """
        try:
            from src.observer.symptoms import record_symptom, should_escalate, set_escalation_flag
            from src.kloros.orchestration.metrics import symptoms_total, escalation_flag_gauge
        except ImportError:
            logger.warning("Observer symptoms module not available")
            return False

        symptom_kind = self._question_to_symptom_kind(question)

        # Extract values from evidence if available
        current_value = 0.0
        baseline_value = 0.0
        delta_pct = 0.0

        for ev in question.evidence:
            if ":" in ev:
                key, val = ev.split(":", 1)
                try:
                    if "current" in key or "recent" in key:
                        current_value = float(val.split()[0])
                    elif "baseline" in key:
                        baseline_value = float(val.split()[0])
                    elif "degradation" in key or "delta" in key:
                        delta_pct = float(val.strip("%").split()[0])
                except (ValueError, IndexError):
                    pass

        # Map severity from question value
        if question.value_estimate >= 0.8:
            severity = "critical"
        elif question.value_estimate >= 0.6:
            severity = "warning"
        else:
            severity = "info"

        # Record symptom
        record_symptom(
            kind=symptom_kind,
            domain=question.capability_key or "system",
            severity=severity,
            current_value=current_value,
            baseline_value=baseline_value,
            delta_pct=delta_pct,
            hypothesis=question.hypothesis,
            question=question.question,
            value_estimate=question.value_estimate,
            cost_estimate=question.cost
        )
        symptoms_total.labels(kind=symptom_kind).inc()

        logger.warning(
            f"Curiosity signal: {question.hypothesis} (value={question.value_estimate:.2f}, "
            f"cost={question.cost:.2f}, action={question.action_class.value})"
        )

        # Check escalation threshold
        if should_escalate(symptom_kind):
            logger.critical(f"Escalation threshold reached for {symptom_kind} - arming flag")
            set_escalation_flag(symptom_kind)
            escalation_flag_gauge.labels(kind=symptom_kind).set(1)
            return True

        return False

    def analyze(self) -> EscalationSummary:
        """
        Main analysis: Trigger CuriosityCore and convert high-value questions to escalations.

        Returns:
            EscalationSummary with questions and escalation status
        """
        import time
        start_time = time.time()

        logger.info("[phase_analyzer] Starting post-PHASE curiosity scan")

        # Step 1: Evaluate capabilities (PHASE tests update this)
        try:
            capability_matrix = self.capability_eval.evaluate_all()
            logger.info(f"[phase_analyzer] Evaluated {len(capability_matrix.capabilities)} capabilities")
        except Exception as e:
            logger.error(f"[phase_analyzer] Failed to evaluate capabilities: {e}")
            capability_matrix = None

        # Step 2: Generate curiosity questions (D-REAM, resources, capabilities)
        try:
            if capability_matrix:
                feed = self.curiosity.generate_questions_from_matrix(
                    capability_matrix,
                    include_performance=True,
                    include_resources=True
                )
            else:
                # If capability eval failed, just do performance + resources
                perf_monitor = PerformanceMonitor()
                resource_monitor = SystemResourceMonitor()

                questions = []
                questions.extend(perf_monitor.generate_performance_questions())
                questions.extend(resource_monitor.generate_resource_questions())

                from registry.curiosity_core import CuriosityFeed
                feed = CuriosityFeed(questions=questions)

            logger.info(f"[phase_analyzer] Generated {len(feed.questions)} curiosity questions")

            # Write feed to disk for KLoROS consumption
            self.curiosity.feed = feed
            self.curiosity.write_feed_json()

        except Exception as e:
            logger.error(f"[phase_analyzer] Failed to generate questions: {e}")
            return EscalationSummary(
                status="error",
                questions_generated=0,
                high_value_questions=0,
                escalations_armed=0,
                questions=[],
                timestamp=time.time(),
                duration_s=time.time() - start_time
            )

        # Step 3: Filter high-value questions and trigger escalations
        high_value_questions = [
            q for q in feed.questions
            if (q.value_estimate / max(q.cost, 0.01)) >= self.escalation_threshold
        ]

        escalations_armed = 0
        for question in high_value_questions:
            if self._record_question_as_symptom(question):
                escalations_armed += 1

        # Summary
        summary = EscalationSummary(
            status="complete",
            questions_generated=len(feed.questions),
            high_value_questions=len(high_value_questions),
            escalations_armed=escalations_armed,
            questions=[q.to_dict() for q in high_value_questions],
            timestamp=time.time(),
            duration_s=time.time() - start_time
        )

        logger.info(
            f"[phase_analyzer] Complete: {len(feed.questions)} questions, "
            f"{len(high_value_questions)} high-value, {escalations_armed} escalations armed"
        )

        return summary


def main():
    """CLI entry point for post-PHASE analysis."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    analyzer = PHASEAnalyzer()
    result = analyzer.analyze()

    # Print summary
    summary_dict = {
        "status": result.status,
        "questions_generated": result.questions_generated,
        "high_value_questions": result.high_value_questions,
        "escalations_armed": result.escalations_armed,
        "questions": result.questions,
        "timestamp": result.timestamp,
        "duration_s": result.duration_s
    }
    print(json.dumps(summary_dict, indent=2))

    # Exit code: 0 if no escalations, 1 if escalations armed
    return 0 if result.escalations_armed == 0 else 1


if __name__ == "__main__":
    exit(main())
