"""Production Polish for D-REAM (Phases 8-9)

Implements:
- Dashboard backpressure (auto-archive low-fitness proposals when >M pending)
- Per-strategy cooldowns (prevent spamming same strategy)
- Tool-call histograms (track tool usage patterns)
- XAI runner-up explanations (why alternative strategies were rejected)
"""

import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# Dashboard backpressure thresholds
MAX_PENDING_PROPOSALS = 100  # Archive when >100 pending
MIN_FITNESS_FOR_KEEP = 0.3  # Archive proposals below this fitness

# Cooldown settings (seconds)
STRATEGY_COOLDOWN_SEC = 300  # 5 minutes between same strategy invocations
AGGRESSIVE_COOLDOWN_SEC = 600  # 10 minutes for strategies that spam


@dataclass
class StrategyInvocation:
    """Record of a strategy invocation."""
    strategy_name: str
    timestamp: float
    fitness_score: float
    latency_ms: int
    cost_usd: float
    tools_used: List[str]


@dataclass
class XAIRunnerUpExplanation:
    """XAI explanation for why a runner-up was rejected."""
    strategy_name: str
    fitness_score: float
    rejection_reason: str
    compared_to_winner: str
    fitness_delta: float  # How much worse than winner


class ProductionPolish:
    """Production polish features for D-REAM."""

    def __init__(
        self,
        dashboard_archive_path: str = "/home/kloros/var/dream/archived_proposals.jsonl",
        cooldown_tracking_path: str = "/home/kloros/var/dream/strategy_cooldowns.json"
    ):
        """Initialize production polish.

        Args:
            dashboard_archive_path: Path to archived proposals
            cooldown_tracking_path: Path to cooldown tracking file
        """
        self.dashboard_archive_path = Path(dashboard_archive_path)
        self.cooldown_tracking_path = Path(cooldown_tracking_path)

        # Ensure directories exist
        self.dashboard_archive_path.parent.mkdir(parents=True, exist_ok=True)
        self.cooldown_tracking_path.parent.mkdir(parents=True, exist_ok=True)

        # Tool usage histogram
        self.tool_histogram: Dict[str, int] = Counter()

        # Strategy invocation history
        self.invocation_history: List[StrategyInvocation] = []

        # Load existing cooldowns
        self.strategy_cooldowns = self._load_cooldowns()

    def _load_cooldowns(self) -> Dict[str, float]:
        """Load strategy cooldowns from disk.

        Returns:
            Dict mapping strategy name to last invocation timestamp
        """
        if not self.cooldown_tracking_path.exists():
            return {}

        try:
            with open(self.cooldown_tracking_path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning("[polish] Failed to load cooldowns: %s", e)
            return {}

    def _save_cooldowns(self):
        """Save strategy cooldowns to disk."""
        try:
            with open(self.cooldown_tracking_path, 'w') as f:
                json.dump(self.strategy_cooldowns, f, indent=2)
        except Exception as e:
            logger.warning("[polish] Failed to save cooldowns: %s", e)

    def check_strategy_cooldown(
        self,
        strategy_name: str,
        aggressive: bool = False
    ) -> Tuple[bool, Optional[float]]:
        """Check if strategy is on cooldown.

        Args:
            strategy_name: Strategy to check
            aggressive: Use aggressive cooldown (longer)

        Returns:
            Tuple of (is_cooled_down, seconds_remaining)
        """
        cooldown_duration = AGGRESSIVE_COOLDOWN_SEC if aggressive else STRATEGY_COOLDOWN_SEC

        if strategy_name not in self.strategy_cooldowns:
            return True, None

        last_invocation = self.strategy_cooldowns[strategy_name]
        elapsed = time.time() - last_invocation
        remaining = cooldown_duration - elapsed

        if remaining <= 0:
            return True, None

        logger.info(
            "[polish] Strategy '%s' on cooldown for %.1f more seconds",
            strategy_name,
            remaining
        )
        return False, remaining

    def record_strategy_invocation(
        self,
        strategy_name: str,
        fitness_score: float,
        latency_ms: int,
        cost_usd: float,
        tools_used: List[str]
    ):
        """Record a strategy invocation.

        Args:
            strategy_name: Strategy name
            fitness_score: Fitness score achieved
            latency_ms: Latency in milliseconds
            cost_usd: Cost in USD
            tools_used: List of tools used
        """
        invocation = StrategyInvocation(
            strategy_name=strategy_name,
            timestamp=time.time(),
            fitness_score=fitness_score,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            tools_used=tools_used
        )

        self.invocation_history.append(invocation)

        # Update cooldown
        self.strategy_cooldowns[strategy_name] = time.time()
        self._save_cooldowns()

        # Update tool histogram
        for tool in tools_used:
            self.tool_histogram[tool] += 1

        logger.info(
            "[polish] Recorded invocation: %s (fitness=%.3f, latency=%dms, cost=$%.4f)",
            strategy_name,
            fitness_score,
            latency_ms,
            cost_usd
        )

    def get_tool_histogram(self, top_n: int = 10) -> List[Tuple[str, int]]:
        """Get tool usage histogram.

        Args:
            top_n: Number of top tools to return

        Returns:
            List of (tool_name, usage_count) sorted by count descending
        """
        return self.tool_histogram.most_common(top_n)

    def apply_dashboard_backpressure(
        self,
        pending_proposals: List[Dict],
        pending_ids: List[str]
    ) -> Tuple[List[Dict], List[Dict]]:
        """Apply dashboard backpressure.

        Auto-archives low-fitness proposals when queue is full.

        Args:
            pending_proposals: List of pending proposal dicts
            pending_ids: List of proposal IDs

        Returns:
            Tuple of (kept_proposals, archived_proposals)
        """
        if len(pending_proposals) <= MAX_PENDING_PROPOSALS:
            # Queue not full, keep all
            return pending_proposals, []

        logger.warning(
            "[polish] Dashboard queue full (%d > %d), applying backpressure",
            len(pending_proposals),
            MAX_PENDING_PROPOSALS
        )

        # Sort by fitness score (descending)
        proposals_with_fitness = [
            (p, p.get("fitness_score", p.get("metrics", {}).get("fitness", 0.0)))
            for p in pending_proposals
        ]

        sorted_proposals = sorted(
            proposals_with_fitness,
            key=lambda x: x[1],
            reverse=True
        )

        # Keep top MAX_PENDING_PROPOSALS, archive rest
        kept = [p for p, _ in sorted_proposals[:MAX_PENDING_PROPOSALS]]
        archived = [p for p, fitness in sorted_proposals[MAX_PENDING_PROPOSALS:]]

        # Also archive any low-fitness proposals even if under limit
        final_kept = []
        for proposal in kept:
            fitness = proposal.get("fitness_score", proposal.get("metrics", {}).get("fitness", 0.0))
            if fitness >= MIN_FITNESS_FOR_KEEP:
                final_kept.append(proposal)
            else:
                archived.append(proposal)

        # Write archived to disk
        if archived:
            self._archive_proposals(archived)

        logger.info(
            "[polish] Backpressure: kept %d, archived %d proposals",
            len(final_kept),
            len(archived)
        )

        return final_kept, archived

    def _archive_proposals(self, proposals: List[Dict]):
        """Archive proposals to disk.

        Args:
            proposals: List of proposals to archive
        """
        try:
            with open(self.dashboard_archive_path, 'a') as f:
                for proposal in proposals:
                    archive_entry = {
                        "timestamp": time.time(),
                        "reason": "dashboard_backpressure",
                        "proposal": proposal
                    }
                    f.write(json.dumps(archive_entry) + '\n')

            logger.info("[polish] Archived %d proposals to %s", len(proposals), self.dashboard_archive_path)
        except Exception as e:
            logger.error("[polish] Failed to archive proposals: %s", e)

    def generate_xai_runnerup_explanations(
        self,
        winner_strategy: str,
        winner_fitness: float,
        all_results: Dict[str, Dict]
    ) -> List[XAIRunnerUpExplanation]:
        """Generate XAI explanations for runner-up strategies.

        Args:
            winner_strategy: Name of winning strategy
            winner_fitness: Fitness of winner
            all_results: Dict mapping strategy name to result dict

        Returns:
            List of XAIRunnerUpExplanation for each runner-up
        """
        explanations = []

        for strategy_name, result in all_results.items():
            if strategy_name == winner_strategy:
                continue  # Skip winner

            fitness = result.get("fitness", result.get("score", 0.0))
            fitness_delta = winner_fitness - fitness

            # Determine rejection reason
            if fitness_delta > 0.3:
                reason = f"Significantly lower fitness ({fitness:.3f} vs {winner_fitness:.3f})"
            elif fitness_delta > 0.1:
                reason = f"Moderately lower fitness ({fitness:.3f} vs {winner_fitness:.3f})"
            elif result.get("latency_ms", 0) > result.get("timeout_ms", float('inf')):
                reason = f"Exceeded timeout ({result['latency_ms']}ms)"
            elif result.get("cost_usd", 0.0) > result.get("budget_usd", float('inf')):
                reason = f"Exceeded cost budget (${result['cost_usd']:.4f})"
            else:
                reason = f"Slightly lower fitness ({fitness:.3f} vs {winner_fitness:.3f})"

            explanation = XAIRunnerUpExplanation(
                strategy_name=strategy_name,
                fitness_score=fitness,
                rejection_reason=reason,
                compared_to_winner=winner_strategy,
                fitness_delta=fitness_delta
            )

            explanations.append(explanation)

        # Sort by fitness delta (closest competitors first)
        explanations.sort(key=lambda x: x.fitness_delta)

        return explanations

    def get_invocation_stats(self) -> Dict[str, Any]:
        """Get statistics on strategy invocations.

        Returns:
            Dict with invocation statistics
        """
        if not self.invocation_history:
            return {
                "total_invocations": 0,
                "strategies": {},
                "avg_fitness": 0.0,
                "avg_latency_ms": 0,
                "total_cost_usd": 0.0
            }

        # Aggregate by strategy
        strategy_stats = defaultdict(lambda: {
            "count": 0,
            "total_fitness": 0.0,
            "total_latency": 0,
            "total_cost": 0.0,
            "tools_used": Counter()
        })

        for inv in self.invocation_history:
            stats = strategy_stats[inv.strategy_name]
            stats["count"] += 1
            stats["total_fitness"] += inv.fitness_score
            stats["total_latency"] += inv.latency_ms
            stats["total_cost"] += inv.cost_usd
            stats["tools_used"].update(inv.tools_used)

        # Compute averages
        result = {
            "total_invocations": len(self.invocation_history),
            "strategies": {},
            "avg_fitness": sum(i.fitness_score for i in self.invocation_history) / len(self.invocation_history),
            "avg_latency_ms": sum(i.latency_ms for i in self.invocation_history) / len(self.invocation_history),
            "total_cost_usd": sum(i.cost_usd for i in self.invocation_history)
        }

        for strategy_name, stats in strategy_stats.items():
            result["strategies"][strategy_name] = {
                "count": stats["count"],
                "avg_fitness": stats["total_fitness"] / stats["count"],
                "avg_latency_ms": stats["total_latency"] / stats["count"],
                "total_cost_usd": stats["total_cost"],
                "top_tools": stats["tools_used"].most_common(5)
            }

        return result
