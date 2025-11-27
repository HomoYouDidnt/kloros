"""
Metric Quality Monitor - Fake/placeholder metric detection.

Detects fake/placeholder metrics in tournament results.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from .base_types import (
    CuriosityQuestion,
    QuestionStatus,
    ActionClass,
)

logger = logging.getLogger(__name__)


class MetricQualityMonitor:
    """
    Detects fake/placeholder metrics in tournament results.

    Generates questions when:
    - All tournament candidates have identical metrics
    - Results contain placeholder values (0.95, 150.0, etc.)
    - Zero variance across candidates (no actual comparison)
    - Investigations complete but produce no actionable insights
    """

    def __init__(
        self,
        orchestrator_log_path: Path = Path("/home/kloros/logs/orchestrator")
    ):
        self.orchestrator_log_path = orchestrator_log_path
        self.lookback_minutes = 60

        self.placeholder_patterns = {
            0.95, 150.0, 300.0, 512.0, 25.0, 100
        }

    def scan_recent_experiments(self) -> List[Dict[str, Any]]:
        """Scan orchestrator logs for completed experiments with suspicious metrics."""
        suspicious_experiments = []

        if not self.orchestrator_log_path.exists():
            return suspicious_experiments

        experiments_log = self.orchestrator_log_path / "curiosity_experiments.jsonl"
        if not experiments_log.exists():
            return suspicious_experiments

        import time
        cutoff_time = time.time() - (self.lookback_minutes * 60)

        try:
            with open(experiments_log, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        entry = json.loads(line)

                        ts_str = entry.get("ts", "")
                        if not ts_str:
                            continue

                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00')).timestamp()

                        if ts < cutoff_time:
                            continue

                        intent = entry.get("intent", {})
                        data = intent.get("data", {})
                        result = data.get("experiment_result", {})

                        if result.get("status") != "complete":
                            continue

                        if result.get("mode") != "tournament":
                            continue

                        artifacts = result.get("artifacts", {})
                        tournament = artifacts.get("tournament", {})
                        results = tournament.get("results", {})

                        if not results:
                            continue

                        aggregated = results.get("aggregated_by_instance", {})

                        if self._has_suspicious_metrics(aggregated, data):
                            suspicious_experiments.append({
                                "question_id": data.get("question_id", "unknown"),
                                "hypothesis": data.get("hypothesis", "unknown"),
                                "timestamp": ts,
                                "total_candidates": result.get("total_candidates", 0),
                                "aggregated_metrics": aggregated,
                                "reason": self._classify_suspicion(aggregated)
                            })

                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.debug(f"[metric_quality] Failed to parse experiment entry: {e}")
                        continue

        except Exception as e:
            logger.warning(f"[metric_quality] Failed to scan experiments log: {e}")

        return suspicious_experiments

    def _has_suspicious_metrics(self, aggregated: Dict[str, Any], question_data: Dict[str, Any]) -> bool:
        """Check if aggregated metrics look fake/placeholder."""
        if not aggregated:
            return False

        all_metrics = []
        for instance_id, metrics in aggregated.items():
            if not isinstance(metrics, dict):
                continue

            all_metrics.append({
                "pass_rate": metrics.get("pass_rate"),
                "latency": metrics.get("avg_latency_p50_ms"),
                "exact_match": metrics.get("avg_exact_match_mean")
            })

        if len(all_metrics) < 2:
            return False

        first = all_metrics[0]
        if all(m == first for m in all_metrics):
            return True

        placeholder_count = 0
        for metric_dict in all_metrics:
            for value in metric_dict.values():
                if value in self.placeholder_patterns:
                    placeholder_count += 1

        total_values = len(all_metrics) * 3
        if placeholder_count / total_values > 0.5:
            return True

        all_perfect = all(m.get("pass_rate") == 1.0 for m in all_metrics)
        latencies = [m.get("latency") for m in all_metrics if m.get("latency") is not None]

        if all_perfect and len(set(latencies)) == 1:
            return True

        return False

    def _classify_suspicion(self, aggregated: Dict[str, Any]) -> str:
        """Classify why metrics are suspicious."""
        if not aggregated:
            return "empty_results"

        all_metrics = []
        for metrics in aggregated.values():
            if isinstance(metrics, dict):
                all_metrics.append(metrics)

        if not all_metrics:
            return "no_metrics"

        first = all_metrics[0]
        if all(m == first for m in all_metrics):
            return "identical_metrics_all_candidates"

        has_placeholders = any(
            any(v in self.placeholder_patterns for v in m.values() if isinstance(v, (int, float)))
            for m in all_metrics
        )

        if has_placeholders:
            return "placeholder_values_detected"

        return "zero_variance_suspicious"

    def generate_quality_questions(self) -> List[CuriosityQuestion]:
        """Generate questions about suspicious metric quality."""
        questions = []

        suspicious = self.scan_recent_experiments()

        if not suspicious:
            return questions

        logger.info(f"[metric_quality] Found {len(suspicious)} experiments with suspicious metrics")

        by_reason = {}
        for exp in suspicious:
            reason = exp["reason"]
            if reason not in by_reason:
                by_reason[reason] = []
            by_reason[reason].append(exp)

        for reason, experiments in by_reason.items():
            if len(experiments) < 2:
                continue

            question_ids = [e["question_id"] for e in experiments[:3]]

            if reason == "identical_metrics_all_candidates":
                hypothesis = "FAKE_TOURNAMENT_METRICS"
                question = (
                    f"I ran {len(experiments)} investigations but all tournament candidates "
                    f"produced identical metrics. Why am I not actually comparing anything? "
                    f"Examples: {', '.join(question_ids)}. "
                    f"Do I need domain-specific evaluators instead of placeholder tests?"
                )
                value = 0.95
                cost = 0.2

            elif reason == "placeholder_values_detected":
                hypothesis = "PLACEHOLDER_TEST_METRICS"
                question = (
                    f"I detected placeholder values (0.95, 150ms, etc.) in {len(experiments)} "
                    f"tournament results. Am I running mock tests instead of real evaluations? "
                    f"Examples: {', '.join(question_ids)}."
                )
                value = 0.90
                cost = 0.2

            else:
                hypothesis = "LOW_QUALITY_METRICS"
                question = (
                    f"Tournament metrics show zero variance across candidates in {len(experiments)} "
                    f"experiments. I'm not learning anything from these investigations. "
                    f"Examples: {', '.join(question_ids)}."
                )
                value = 0.85
                cost = 0.2

            evidence = [
                f"pattern:{reason}",
                f"affected_investigations:{len(experiments)}",
                f"examples:{','.join(question_ids[:3])}"
            ]

            q = CuriosityQuestion(
                id=f"meta.metric_quality.{reason}",
                hypothesis=hypothesis,
                question=question,
                evidence=evidence,
                action_class=ActionClass.PROPOSE_FIX,
                autonomy=3,
                value_estimate=value,
                cost=cost,
                status=QuestionStatus.READY,
                capability_key="meta.evaluation_quality"
            )

            questions.append(q)

        return questions
