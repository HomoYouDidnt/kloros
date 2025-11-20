"""
Shadow Testing for Tool Selection

A/B tests candidate tools against baseline in dry-run mode to measure
comparative performance before promotion.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Dict, Any, Optional
import random
import time


@dataclass
class ShadowOutcome:
    """Result of a shadow A/B test comparing candidate vs baseline."""
    ok: bool  # Whether shadow test completed
    reward: float  # Candidate reward
    latency_ms: int  # Total test time
    baseline_reward: float  # Baseline reward
    delta: float  # Candidate - baseline reward difference


class ShadowRunner:
    """
    Run candidate tool in shadow (dry-run) mode and compare vs baseline.

    Shadow testing allows safe evaluation of new tools without risking
    production side effects. Both baseline and candidate are executed
    in dry-run mode, and their outcomes are compared.

    Usage:
        runner = ShadowRunner(traffic_share=0.2, dry_run=True)

        if runner.should_shadow():
            outcome = runner.run_once(
                query="check GPU status",
                baseline_plan={"tool": "gpu_status_v1", "inputs": {}},
                candidate_plan={"tool": "gpu_status_v2", "inputs": {}},
                executor=my_tool_executor,
                scorer=compute_reward
            )
            if outcome:
                print(f"Delta: {outcome.delta:.3f}")
    """

    def __init__(self, traffic_share: float = 0.2, dry_run: bool = True):
        """
        Initialize shadow runner.

        Args:
            traffic_share: Fraction of requests to shadow test (0.0-1.0)
            dry_run: Whether to enforce dry-run mode (no side effects)
        """
        self.traffic_share = traffic_share
        self.dry_run = dry_run

    def should_shadow(self) -> bool:
        """
        Decide whether to run shadow test for this request.

        Returns:
            True with probability = traffic_share
        """
        return random.random() < self.traffic_share

    def run_once(
        self,
        query: str,
        baseline_plan: Dict[str, Any],
        candidate_plan: Dict[str, Any],
        executor: Callable[[str, Dict[str, Any], bool], Dict[str, Any]],
        scorer: Callable[[Dict[str, Any]], float],
    ) -> Optional[ShadowOutcome]:
        """
        Execute shadow A/B test: run both baseline and candidate, compare.

        Args:
            query: User query/intent
            baseline_plan: {"tool": name, "inputs": {...}}
            candidate_plan: {"tool": name, "inputs": {...}}
            executor: Function that runs tool and returns result dict
                     Signature: (tool_name, inputs, dry_run) -> result
            scorer: Function that computes reward from result
                   Signature: (result) -> reward in [0, 1]

        Returns:
            ShadowOutcome with comparison metrics, or None if skipped

        Executor must return dict with at least:
            {"ok": bool, "latency_ms": int, "hops": int, "text": str, ...}

        Scorer converts result to reward in [0.0, 1.0].
        """
        if not self.should_shadow():
            return None

        t0 = time.time()

        try:
            # Execute baseline in dry-run
            base_res = executor(
                baseline_plan["tool"],
                baseline_plan.get("inputs", {}),
                dry_run=True
            )

            # Execute candidate in dry-run
            cand_res = executor(
                candidate_plan["tool"],
                candidate_plan.get("inputs", {}),
                dry_run=True
            )

            latency_ms = int((time.time() - t0) * 1000)

            # Compute rewards
            base_r = scorer(base_res)
            cand_r = scorer(cand_res)

            return ShadowOutcome(
                ok=True,
                reward=cand_r,
                latency_ms=latency_ms,
                baseline_reward=base_r,
                delta=cand_r - base_r,
            )

        except Exception as e:
            print(f"[shadow] Test failed: {e}")
            return ShadowOutcome(
                ok=False,
                reward=0.0,
                latency_ms=int((time.time() - t0) * 1000),
                baseline_reward=0.0,
                delta=0.0,
            )
