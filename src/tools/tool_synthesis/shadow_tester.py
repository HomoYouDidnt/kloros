"""
Shadow Testing Infrastructure for Tool Synthesis

A/B tests quarantined tools without side effects before promotion.
"""

import json
import random
import time
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class ShadowResult:
    """Result from a shadow test execution."""
    tool_name: str
    timestamp: str
    baseline_result: str
    shadow_result: str
    latency_baseline_ms: float
    latency_shadow_ms: float
    match: bool  # Did shadow match baseline?
    error: Optional[str]


class ShadowTester:
    """
    A/B test quarantined tools without side effects.

    Runs new tools in shadow mode on a percentage of traffic,
    comparing results to baseline tools or no-tool responses.
    """

    def __init__(self, root_dir: str = "/home/kloros/.kloros"):
        self.root = Path(root_dir)
        self.shadow_dir = self.root / "shadow"
        self.shadow_dir.mkdir(exist_ok=True)

        # Shadow routing config: tool_name -> percent
        self.shadow_routing = {}

        # Shadow results log
        self.results_log = self.shadow_dir / "shadow_results.jsonl"

    def enable_shadow(self, tool_name: str, percent: float = 0.1) -> None:
        """
        Enable shadow testing for a tool at X% of requests.

        Args:
            tool_name: Tool to shadow test
            percent: Percentage of traffic (0.0 to 1.0)
        """
        if percent < 0 or percent > 1:
            raise ValueError("Percent must be between 0 and 1")

        self.shadow_routing[tool_name] = percent
        print(f"[shadow] Enabled shadow testing for '{tool_name}' at {percent*100:.1f}% traffic")

    def disable_shadow(self, tool_name: str) -> None:
        """Disable shadow testing for a tool."""
        if tool_name in self.shadow_routing:
            del self.shadow_routing[tool_name]
            print(f"[shadow] Disabled shadow testing for '{tool_name}'")

    def should_shadow(self, tool_name: str) -> bool:
        """
        Determine if this request should shadow-test the tool.

        Returns:
            True if should run shadow test
        """
        percent = self.shadow_routing.get(tool_name, 0)
        return random.random() < percent

    def run_shadow(self, tool_name: str, kloros_instance, context: str,
                   baseline_result: Optional[str] = None) -> Optional[ShadowResult]:
        """
        Run tool in shadow mode and compare to baseline.

        Args:
            tool_name: Tool to shadow test
            kloros_instance: KLoROS instance
            context: Query context
            baseline_result: Baseline result to compare against

        Returns:
            ShadowResult if shadow executed, None if skipped
        """
        if not self.should_shadow(tool_name):
            return None

        try:
            from ..introspection_tools import IntrospectionToolRegistry
            from .governance import SynthesisGovernance

            governance = SynthesisGovernance()

            # Load tool from quarantine
            tool_status = governance.get_tool_status(tool_name)
            if not tool_status or tool_status['status'] != 'quarantine':
                print(f"[shadow] Tool '{tool_name}' not in quarantine, skipping shadow test")
                return None

            registry = IntrospectionToolRegistry()
            quarantine_tool = registry.get_tool(f"quarantine/{tool_name}")

            if not quarantine_tool:
                print(f"[shadow] Could not load quarantine tool: {tool_name}")
                return None

            # Run baseline (if not provided)
            baseline_start = time.time()
            if baseline_result is None:
                baseline_result = f"No baseline for {tool_name}"
            baseline_latency = (time.time() - baseline_start) * 1000

            # Run shadow (READ-ONLY, no side effects)
            shadow_start = time.time()
            try:
                shadow_result = quarantine_tool.execute(kloros_instance)
                shadow_error = None
            except Exception as e:
                shadow_result = f"Error: {e}"
                shadow_error = str(e)
            shadow_latency = (time.time() - shadow_start) * 1000

            # Compare results (simple text match for now)
            match = self._compare_results(baseline_result, shadow_result)

            result = ShadowResult(
                tool_name=tool_name,
                timestamp=datetime.now().isoformat(),
                baseline_result=baseline_result[:200],  # Truncate for storage
                shadow_result=shadow_result[:200],
                latency_baseline_ms=baseline_latency,
                latency_shadow_ms=shadow_latency,
                match=match,
                error=shadow_error
            )

            # Log shadow result
            self._log_shadow_result(result)

            print(f"[shadow] Shadow test for '{tool_name}': "
                  f"match={match}, latency={shadow_latency:.1f}ms, error={shadow_error is not None}")

            return result

        except Exception as e:
            print(f"[shadow] Shadow test failed for '{tool_name}': {e}")
            return None


    def enable_versioned_shadow(self, tool_name: str, baseline_version: str,
                                shadow_version: str, percent: float = 0.1) -> None:
        """
        Enable A/B testing between two versions of a tool.

        Args:
            tool_name: Tool name
            baseline_version: Production version
            shadow_version: New version to test
            percent: Percentage of traffic to send to shadow version
        """
        key = f"{tool_name}@{shadow_version}"
        self.shadow_routing[key] = {
            "baseline_version": baseline_version,
            "shadow_version": shadow_version,
            "percent": percent
        }
        print(f"[shadow] Enabled A/B test: {tool_name}@{baseline_version} vs {shadow_version} ({percent*100:.0f}% shadow)")

    def flip_traffic(self, tool_name: str, shadow_version: str, new_percent: float) -> None:
        """
        Change traffic split for version A/B test.

        Args:
            tool_name: Tool name
            shadow_version: Shadow version
            new_percent: New percentage for shadow version
        """
        key = f"{tool_name}@{shadow_version}"
        if key in self.shadow_routing:
            self.shadow_routing[key]["percent"] = new_percent
            print(f"[shadow] Traffic split updated: {key} now at {new_percent*100:.0f}%")
        else:
            print(f"[shadow] No shadow routing found for {key}")

    def promote_shadow_to_production(self, tool_name: str, shadow_version: str) -> None:
        """
        Promote shadow version to 100% production traffic.

        Args:
            tool_name: Tool name
            shadow_version: Shadow version to promote
        """
        self.flip_traffic(tool_name, shadow_version, 1.0)
        print(f"[shadow] Promoted {tool_name}@{shadow_version} to 100% production")

    def compare_version_metrics(self, tool_name: str, baseline_version: str,
                                shadow_version: str) -> Dict:
        """
        Compare telemetry metrics between two versions.

        Args:
            tool_name: Tool name
            baseline_version: Baseline version
            shadow_version: Shadow version

        Returns:
            Dict with comparison metrics
        """
        from .telemetry import get_telemetry_collector

        collector = get_telemetry_collector()
        baseline = collector.get_metrics(tool_name, baseline_version)
        shadow = collector.get_metrics(tool_name, shadow_version)

        if not baseline:
            baseline = collector.load_metrics_from_file(tool_name, baseline_version)
        if not shadow:
            shadow = collector.load_metrics_from_file(tool_name, shadow_version)

        if not baseline or not shadow:
            return {"error": "Missing metrics for one or both versions"}

        comparison = {
            "tool": tool_name,
            "baseline_version": baseline_version,
            "shadow_version": shadow_version,
            "baseline_calls": baseline.calls,
            "shadow_calls": shadow.calls,
            "baseline_error_rate": baseline.error_rate(),
            "shadow_error_rate": shadow.error_rate(),
            "baseline_p95_latency_ms": baseline.p95_latency(),
            "shadow_p95_latency_ms": shadow.p95_latency(),
            "latency_improvement": None,
            "error_rate_improvement": None,
        }

        # Calculate improvements
        if baseline.p95_latency() and shadow.p95_latency():
            improvement = ((baseline.p95_latency() - shadow.p95_latency()) / 
                          baseline.p95_latency()) * 100
            comparison["latency_improvement"] = f"{improvement:.1f}%"

        if baseline.calls > 0:
            error_improvement = ((baseline.error_rate() - shadow.error_rate()) / 
                               max(baseline.error_rate(), 0.001)) * 100
            comparison["error_rate_improvement"] = f"{error_improvement:.1f}%"

        return comparison

    def _compare_results(self, baseline: str, shadow: str) -> bool:
        """
        Compare baseline and shadow results.

        Returns:
            True if results are similar enough
        """
        # Simple comparison: check if key terms overlap
        baseline_lower = baseline.lower()
        shadow_lower = shadow.lower()

        # Check for error conditions
        if "error" in shadow_lower and "error" not in baseline_lower:
            return False

        # Check for similar length (within 50%)
        if abs(len(baseline) - len(shadow)) > max(len(baseline), len(shadow)) * 0.5:
            return False

        # For now, any non-error shadow result is considered a match
        return "error" not in shadow_lower

    def _log_shadow_result(self, result: ShadowResult) -> None:
        """Log shadow result to file."""
        try:
            with open(self.results_log, 'a') as f:
                f.write(json.dumps(asdict(result)) + '\n')
        except Exception as e:
            print(f"[shadow] Failed to log result: {e}")

    def get_shadow_stats(self, tool_name: str) -> Dict:
        """
        Get shadow test statistics for a tool.

        Args:
            tool_name: Tool to get stats for

        Returns:
            Dict with accuracy, latency, error rate, sample count
        """
        if not self.results_log.exists():
            return {"error": "No shadow results logged"}

        results = []
        with open(self.results_log, 'r') as f:
            for line in f:
                try:
                    result = json.loads(line.strip())
                    if result['tool_name'] == tool_name:
                        results.append(result)
                except:
                    continue

        if not results:
            return {"error": f"No shadow results for {tool_name}"}

        # Calculate statistics
        total = len(results)
        matches = sum(1 for r in results if r['match'])
        errors = sum(1 for r in results if r['error'] is not None)
        avg_latency = sum(r['latency_shadow_ms'] for r in results) / total

        return {
            "tool_name": tool_name,
            "sample_count": total,
            "accuracy": matches / total if total > 0 else 0,
            "error_rate": errors / total if total > 0 else 0,
            "avg_latency_ms": round(avg_latency, 2),
            "match_count": matches,
            "error_count": errors
        }

    def meets_promotion_threshold(self, tool_name: str,
                                  min_samples: int = 10,
                                  min_accuracy: float = 0.8,
                                  max_error_rate: float = 0.2) -> Tuple[bool, str]:
        """
        Check if shadow results meet promotion threshold.

        Args:
            tool_name: Tool to check
            min_samples: Minimum number of shadow tests
            min_accuracy: Minimum accuracy ratio
            max_error_rate: Maximum error rate

        Returns:
            Tuple of (meets_threshold, reason)
        """
        stats = self.get_shadow_stats(tool_name)

        if "error" in stats:
            return False, stats["error"]

        if stats['sample_count'] < min_samples:
            return False, f"Insufficient samples: {stats['sample_count']} < {min_samples}"

        if stats['accuracy'] < min_accuracy:
            return False, f"Accuracy too low: {stats['accuracy']:.2%} < {min_accuracy:.0%}"

        if stats['error_rate'] > max_error_rate:
            return False, f"Error rate too high: {stats['error_rate']:.2%} > {max_error_rate:.0%}"

        return True, f"Shadow tests passed ({stats['sample_count']} samples, {stats['accuracy']:.2%} accuracy)"
