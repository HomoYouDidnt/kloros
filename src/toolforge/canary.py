"""Canary deployment controller for safe tool rollout."""
from typing import Dict, Any, Optional
import json
import os
import time


class CanaryController:
    """Controls shadow testing and canary promotion of tools."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize canary controller.

        Args:
            config: Configuration dict
        """
        self.config = config or {}

        # Promotion thresholds
        self.min_success_delta_pp = self.config.get("min_success_delta_pp", 3.0)
        self.max_latency_delta_pct = self.config.get("max_latency_delta_pct", 5.0)
        self.max_incidents = self.config.get("max_incidents", 0)
        self.min_samples = self.config.get("min_samples", 100)

        # Shadow traffic percentage
        self.shadow_traffic_pct = self.config.get("shadow_traffic_pct", 0.05)

        # Results storage
        self.results_dir = self.config.get("results_dir", os.path.expanduser("~/.kloros/toolforge/shadow_results"))
        os.makedirs(self.results_dir, exist_ok=True)

    def should_promote(self, stats: Dict[str, Any]) -> bool:
        """Check if tool should be promoted based on shadow test stats.

        Args:
            stats: Shadow test statistics
                - success_delta_pp: Success rate delta in percentage points
                - p95_latency_delta_pct: P95 latency delta as percentage
                - incidents: Number of safety incidents
                - samples: Number of shadow test samples

        Returns:
            True if tool should be promoted
        """
        # Check minimum sample size
        if stats.get("samples", 0) < self.min_samples:
            return False

        # Check success rate improvement
        success_delta = stats.get("success_delta_pp", 0)
        if success_delta < self.min_success_delta_pp:
            return False

        # Check latency regression
        latency_delta = stats.get("p95_latency_delta_pct", 0)
        if latency_delta > self.max_latency_delta_pct:
            return False

        # Check incidents (must be zero)
        incidents = stats.get("incidents", 0)
        if incidents > self.max_incidents:
            return False

        return True

    def run_shadow(
        self,
        tool_name: str,
        traffic_pct: Optional[float] = None
    ) -> Dict[str, Any]:
        """Run tool in shadow mode.

        Args:
            tool_name: Name of tool to shadow test
            traffic_pct: Percentage of traffic to shadow (0.0-1.0)

        Returns:
            Shadow run result
        """
        pct = traffic_pct or self.shadow_traffic_pct

        # Create shadow run record
        run_id = f"{tool_name}_{int(time.time())}"
        result_file = os.path.join(self.results_dir, f"{run_id}.jsonl")

        result = {
            "ok": True,
            "tool_name": tool_name,
            "run_id": run_id,
            "traffic_pct": pct,
            "result_file": result_file,
            "started_at": time.time()
        }

        # TODO: Wire to inference proxy
        # - Copy inputs at configured percentage
        # - Run both baseline and candidate tool
        # - Log results for comparison
        # - Track latency, success rate, incidents

        return result

    def collect_stats(self, run_id: str) -> Dict[str, Any]:
        """Collect statistics from shadow run.

        Args:
            run_id: Shadow run ID

        Returns:
            Statistics dict
        """
        result_file = os.path.join(self.results_dir, f"{run_id}.jsonl")

        if not os.path.exists(result_file):
            return {
                "error": "Results not found",
                "samples": 0
            }

        # Parse results
        baseline_successes = 0
        candidate_successes = 0
        baseline_latencies = []
        candidate_latencies = []
        incidents = 0
        samples = 0

        with open(result_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                record = json.loads(line)
                samples += 1

                # Track success rates
                if record.get("baseline_success", False):
                    baseline_successes += 1
                if record.get("candidate_success", False):
                    candidate_successes += 1

                # Track latencies
                if "baseline_latency_ms" in record:
                    baseline_latencies.append(record["baseline_latency_ms"])
                if "candidate_latency_ms" in record:
                    candidate_latencies.append(record["candidate_latency_ms"])

                # Track incidents
                if record.get("candidate_incident", False):
                    incidents += 1

        # Compute statistics
        baseline_success_rate = baseline_successes / samples if samples > 0 else 0
        candidate_success_rate = candidate_successes / samples if samples > 0 else 0
        success_delta_pp = (candidate_success_rate - baseline_success_rate) * 100

        # Compute latency percentiles
        baseline_p95 = self._percentile(baseline_latencies, 0.95) if baseline_latencies else 0
        candidate_p95 = self._percentile(candidate_latencies, 0.95) if candidate_latencies else 0

        if baseline_p95 > 0:
            latency_delta_pct = ((candidate_p95 - baseline_p95) / baseline_p95) * 100
        else:
            latency_delta_pct = 0

        return {
            "samples": samples,
            "baseline_success_rate": baseline_success_rate,
            "candidate_success_rate": candidate_success_rate,
            "success_delta_pp": success_delta_pp,
            "baseline_p95_latency_ms": baseline_p95,
            "candidate_p95_latency_ms": candidate_p95,
            "p95_latency_delta_pct": latency_delta_pct,
            "incidents": incidents
        }

    def _percentile(self, values: list, p: float) -> float:
        """Compute percentile.

        Args:
            values: List of values
            p: Percentile (0.0-1.0)

        Returns:
            Percentile value
        """
        if not values:
            return 0.0

        sorted_values = sorted(values)
        index = int(p * len(sorted_values))
        index = max(0, min(len(sorted_values) - 1, index))

        return sorted_values[index]

    def promote(self, tool_name: str, run_id: str) -> Dict[str, Any]:
        """Promote tool to production based on shadow test results.

        Args:
            tool_name: Tool name
            run_id: Shadow run ID

        Returns:
            Promotion result
        """
        stats = self.collect_stats(run_id)

        if self.should_promote(stats):
            # TODO: Update tool registry/routing to use new tool
            return {
                "promoted": True,
                "tool_name": tool_name,
                "run_id": run_id,
                "stats": stats
            }
        else:
            return {
                "promoted": False,
                "tool_name": tool_name,
                "run_id": run_id,
                "stats": stats,
                "reason": self._get_rejection_reason(stats)
            }

    def _get_rejection_reason(self, stats: Dict[str, Any]) -> str:
        """Get reason for rejecting promotion.

        Args:
            stats: Statistics dict

        Returns:
            Rejection reason
        """
        reasons = []

        if stats.get("samples", 0) < self.min_samples:
            reasons.append(f"Insufficient samples ({stats['samples']} < {self.min_samples})")

        if stats.get("success_delta_pp", 0) < self.min_success_delta_pp:
            reasons.append(f"Success delta too low ({stats['success_delta_pp']:.1f}pp < {self.min_success_delta_pp}pp)")

        if stats.get("p95_latency_delta_pct", 0) > self.max_latency_delta_pct:
            reasons.append(f"Latency regression ({stats['p95_latency_delta_pct']:.1f}% > {self.max_latency_delta_pct}%)")

        if stats.get("incidents", 0) > self.max_incidents:
            reasons.append(f"Safety incidents ({stats['incidents']} > {self.max_incidents})")

        return "; ".join(reasons) if reasons else "Unknown"


def should_promote(stats: Dict[str, Any]) -> bool:
    """Check if tool should be promoted (convenience function).

    Args:
        stats: Shadow test statistics

    Returns:
        True if should promote
    """
    controller = CanaryController()
    return controller.should_promote(stats)
