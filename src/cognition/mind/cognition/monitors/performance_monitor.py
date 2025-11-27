"""
Performance Monitor - D-REAM experiment performance tracking.

Monitors D-REAM experiment performance from summary.json files.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

from .base_types import (
    CuriosityQuestion,
    QuestionStatus,
    ActionClass,
    PerformanceTrend,
)

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """
    Monitors D-REAM experiment performance from summary.json files.

    Purpose:
        Enable KLoROS to detect performance degradation trends and generate
        questions about optimization opportunities

    Outcomes:
        - Scans recent D-REAM summaries
        - Detects pass rate drops, latency increases, accuracy degradation
        - Generates performance-based curiosity questions
    """

    def __init__(self, artifacts_dir: Path = Path("/home/kloros/artifacts/dream")):
        """Initialize performance monitor."""
        self.artifacts_dir = artifacts_dir

    def scan_experiment_summaries(
        self,
        experiment: str,
        max_summaries: int = 10
    ) -> PerformanceTrend:
        """Scan recent summaries for a specific experiment."""
        trend = PerformanceTrend(experiment=experiment)

        exp_dir = self.artifacts_dir / experiment
        if not exp_dir.exists():
            logger.warning(f"[performance_monitor] Experiment directory not found: {exp_dir}")
            return trend

        summary_files = []
        for ts_dir in exp_dir.iterdir():
            if ts_dir.is_dir():
                summary_path = ts_dir / "summary.json"
                if summary_path.exists():
                    try:
                        ts = int(ts_dir.name)
                        summary_files.append((ts, summary_path))
                    except ValueError:
                        continue

        summary_files.sort(reverse=True)
        summary_files = summary_files[:max_summaries]

        for ts, summary_path in reversed(summary_files):
            try:
                with open(summary_path, 'r') as f:
                    summary = json.load(f)

                trend.recent_summaries.append(summary)

                best_metrics = summary.get("best_metrics")
                if best_metrics and isinstance(best_metrics, dict):
                    if "tournament" in best_metrics:
                        tournament = best_metrics["tournament"]
                        if isinstance(tournament, dict) and "results" in tournament:
                            results = tournament["results"]
                            total = results.get("total_replicas", 0)
                            passed = results.get("passed", 0)
                            if total > 0:
                                pass_rate = passed / total
                                trend.pass_rate_trend.append(pass_rate)

                    latency = best_metrics.get("latency_p50_ms", 0)
                    if latency > 0:
                        trend.latency_trend.append(latency)

                    accuracy = best_metrics.get("exact_match_mean", 0)
                    if accuracy > 0:
                        trend.accuracy_trend.append(accuracy)

            except Exception as e:
                logger.error(f"[performance_monitor] Failed to load {summary_path}: {e}")
                continue

        return trend

    def generate_performance_questions(
        self,
        experiments: Optional[List[str]] = None
    ) -> List[CuriosityQuestion]:
        """Generate curiosity questions from performance trends."""
        questions = []

        if experiments is None:
            experiments = []
            if self.artifacts_dir.exists():
                for exp_dir in self.artifacts_dir.iterdir():
                    if exp_dir.is_dir():
                        has_summaries = any(
                            (ts_dir / "summary.json").exists()
                            for ts_dir in exp_dir.iterdir()
                            if ts_dir.is_dir()
                        )
                        if has_summaries:
                            experiments.append(exp_dir.name)

        for experiment in experiments:
            trend = self.scan_experiment_summaries(experiment)

            if not trend.recent_summaries:
                continue

            degradation = trend.detect_degradation()
            if degradation:
                q = self._question_for_performance_degradation(experiment, degradation, trend)
                if q:
                    questions.append(q)

        return questions

    def _question_for_performance_degradation(
        self,
        experiment: str,
        degradation: str,
        trend: PerformanceTrend
    ) -> Optional[CuriosityQuestion]:
        """Generate question for detected performance degradation."""
        degradation_type, amount = degradation.split(":", 1)

        latest_summary = trend.recent_summaries[-1]
        best_params = latest_summary.get("best_params", {})

        if degradation_type == "pass_rate_drop":
            hypothesis = f"{experiment.upper()}_PASS_RATE_DEGRADATION"
            question = (
                f"Why did {experiment} pass rate drop by {amount}? "
                f"Current params: {best_params}. Should I spawn a remediation experiment?"
            )
            action_class = ActionClass.PROPOSE_FIX
            value = 0.9
            cost = 0.5

        elif degradation_type == "latency_increase":
            hypothesis = f"{experiment.upper()}_LATENCY_REGRESSION"
            question = (
                f"Why did {experiment} latency increase by {amount}? "
                f"Can adjusting {list(best_params.keys())} improve performance?"
            )
            action_class = ActionClass.INVESTIGATE
            value = 0.7
            cost = 0.4

        elif degradation_type == "accuracy_drop":
            hypothesis = f"{experiment.upper()}_ACCURACY_DEGRADATION"
            question = (
                f"Why did {experiment} accuracy drop by {amount}? "
                f"Is this a data quality issue or parameter drift?"
            )
            action_class = ActionClass.INVESTIGATE
            value = 0.8
            cost = 0.3

        else:
            return None

        evidence = [
            f"experiment:{experiment}",
            f"degradation:{degradation}",
            f"recent_runs:{len(trend.recent_summaries)}",
            f"params:{','.join(best_params.keys())}"
        ]

        if trend.pass_rate_trend:
            evidence.append(f"pass_rate_recent:{trend.pass_rate_trend[-1]:.2f}")
        if trend.latency_trend:
            evidence.append(f"latency_recent:{trend.latency_trend[-1]:.2f}ms")
        if trend.accuracy_trend:
            evidence.append(f"accuracy_recent:{trend.accuracy_trend[-1]:.2f}")

        return CuriosityQuestion(
            id=f"performance.{experiment}.{degradation_type}",
            hypothesis=hypothesis,
            question=question,
            evidence=evidence,
            action_class=action_class,
            autonomy=3,
            value_estimate=value,
            cost=cost,
            status=QuestionStatus.READY,
            capability_key=f"dream.{experiment}"
        )
