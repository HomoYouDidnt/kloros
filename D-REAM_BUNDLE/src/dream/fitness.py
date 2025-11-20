#!/usr/bin/env python3
"""
D-REAM Composite Fitness Module
Multi-objective fitness scoring with hard constraints and regime aggregation.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import statistics as st
import logging

logger = logging.getLogger(__name__)


@dataclass
class FitnessWeights:
    """Weights for multi-objective fitness components."""
    perf: float = 1.0        # main performance metric (domain-defined)
    stability: float = 0.5   # variance/robustness across regimes
    maxdd: float = 3.0       # drawdown or catastrophic penalty
    turnover: float = 0.1    # churn/complexity penalty
    corr: float = 0.2        # correlation penalty vs champion set
    risk: float = 1.0        # domain risk proxy (e.g., CVaR, error rate)

    @classmethod
    def from_dict(cls, d: Dict[str, float]) -> 'FitnessWeights':
        """Create from config dictionary."""
        return cls(**{k: v for k, v in d.items() if k in cls.__annotations__})


class CompositeFitness:
    """Multi-objective fitness function with constraints."""

    def __init__(self, weights: FitnessWeights, hard_caps: Optional[Dict[str, float]] = None):
        """
        Initialize composite fitness function.

        Args:
            weights: Component weights for fitness calculation
            hard_caps: Hard constraints that result in infeasible solutions
        """
        self.w = weights
        self.hard = hard_caps or {}

    def score(self, metrics: Dict[str, float]) -> float:
        """
        Calculate composite fitness score.

        Args:
            metrics: Dictionary of metric values

        Returns:
            Composite fitness score (or -inf if constraints violated)
        """
        # Check hard constraints -> infeasible
        for metric_name, cap_value in self.hard.items():
            metric_val = metrics.get(metric_name, 0)
            # For negative metrics (penalties), check if they exceed cap
            if metric_name in ['maxdd', 'risk'] and metric_val > cap_value:
                logger.warning(f"Hard constraint violated: {metric_name}={metric_val:.3f} > {cap_value}")
                return float("-inf")

        # Calculate weighted composite score
        score_components = [
            ("perf", self.w.perf * metrics.get("perf", 0.0)),
            ("stability", self.w.stability * metrics.get("stability", 0.0)),
            ("-maxdd", -self.w.maxdd * metrics.get("maxdd", 0.0)),
            ("-turnover", -self.w.turnover * metrics.get("turnover", 0.0)),
            ("-corr", -self.w.corr * metrics.get("corr", 0.0)),
            ("-risk", -self.w.risk * metrics.get("risk", 0.0))
        ]

        total_score = sum(value for _, value in score_components)

        logger.debug(f"Fitness components: {dict(score_components)}, total={total_score:.3f}")
        return total_score

    def aggregate(self, regime_metrics: List[Dict[str, float]]) -> Dict[str, float]:
        """
        Aggregate metrics across multiple regimes.

        Args:
            regime_metrics: List of metrics for each regime

        Returns:
            Aggregated metrics including stability measure
        """
        if not regime_metrics:
            return {"score": float("-inf")}

        # Extract performance values for stability calculation
        perfs = [m.get("perf", 0) for m in regime_metrics]

        # Calculate averages for each metric across regimes
        all_keys = set().union(*[set(m.keys()) for m in regime_metrics])
        agg = {}

        for key in all_keys:
            values = [m.get(key, 0) for m in regime_metrics]
            agg[key] = sum(values) / len(values)

        # Add stability metric (negative std dev of performance)
        if len(perfs) > 1:
            agg["stability"] = -st.pstdev(perfs)
        else:
            agg["stability"] = 0.0

        # Add worst-case metrics for risk management
        agg["worst_perf"] = min(perfs)
        agg["best_perf"] = max(perfs)

        # Calculate final composite score
        agg["score"] = self.score(agg)

        # Add metadata
        agg["n_regimes"] = len(regime_metrics)

        logger.info(f"Aggregated {len(regime_metrics)} regimes: score={agg['score']:.3f}, "
                   f"avg_perf={agg.get('perf', 0):.3f}, stability={agg['stability']:.3f}")

        return agg


class DomainFitness:
    """Domain-specific fitness extensions."""

    @staticmethod
    def calculate_sharpe(returns: List[float], risk_free: float = 0.0) -> float:
        """Calculate Sharpe ratio for financial domains."""
        if not returns or len(returns) < 2:
            return 0.0
        mean_return = st.mean(returns)
        std_return = st.stdev(returns)
        if std_return == 0:
            return 0.0
        return (mean_return - risk_free) / std_return

    @staticmethod
    def calculate_drawdown(values: List[float]) -> float:
        """Calculate maximum drawdown."""
        if not values:
            return 0.0
        peak = values[0]
        max_dd = 0.0
        for val in values:
            if val > peak:
                peak = val
            dd = (peak - val) / peak if peak != 0 else 0
            max_dd = max(max_dd, dd)
        return max_dd

    @staticmethod
    def calculate_turnover(positions_old: List[float], positions_new: List[float]) -> float:
        """Calculate portfolio turnover."""
        if len(positions_old) != len(positions_new):
            return 1.0
        return sum(abs(p_new - p_old) for p_old, p_new in zip(positions_old, positions_new)) / 2.0


def create_fitness_from_config(config: Dict) -> CompositeFitness:
    """
    Factory function to create fitness from config.

    Args:
        config: Configuration dictionary with 'weights' and optional 'hard_caps'

    Returns:
        Configured CompositeFitness instance
    """
    weights = FitnessWeights.from_dict(config.get("weights", {}))
    hard_caps = config.get("hard_caps", {})
    return CompositeFitness(weights, hard_caps)


def evaluate_fitness(episode_result: Dict[str, any], genome: 'Genome') -> 'FitnessMetrics':
    """
    Evaluate fitness from episode results for D-REAM evolution.

    Args:
        episode_result: Episode execution results
        genome: Genome being evaluated

    Returns:
        FitnessMetrics with computed fitness score
    """
    from .dream_types import FitnessMetrics

    metrics = FitnessMetrics(
        genome_id=genome.id,
        generation=genome.generation,
        success_rate=1.0 if episode_result.get("success", False) else 0.0,
        avg_latency_ms=episode_result.get("latency_ms", 0),
        avg_tokens=episode_result.get("tokens", 0),
        petri_incidents=1 if episode_result.get("petri_blocked", False) else 0,
        petri_blocks=1 if episode_result.get("petri_blocked", False) else 0,
        verifier_score=episode_result.get("verifier_score", 0.0),
        user_feedback=episode_result.get("user_feedback", 0.0),
        episodes=1
    )

    # Compute fitness using built-in method
    metrics.compute_fitness()

    return metrics
