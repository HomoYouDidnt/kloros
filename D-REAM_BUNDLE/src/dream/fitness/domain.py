from dataclasses import dataclass
from typing import Dict, Mapping, Optional, List
import statistics
from .composite import CompositeFitness

@dataclass
class DomainFitness:
    """
    D-REAM domain fitness with financial metrics.

    Provides static methods for calculating domain-specific metrics:
    - Sharpe ratio (risk-adjusted returns)
    - Maximum drawdown
    - Portfolio turnover
    """
    weights: Mapping[str, float] = None
    constraints: Optional[Dict[str, Dict[str, float]]] = None
    penalty: float = 0.0

    def __post_init__(self):
        if self.weights is None:
            self.weights = {"reward": 1.0, "novelty": 0.1, "safety": -1.0}
        if self.constraints is None:
            self.constraints = {"safety": {"max": 0.0}, "novelty": {"min": 0.0}}
        self._inner = CompositeFitness(self.weights, constraints=self.constraints, penalty=self.penalty)

    def score(self, values: Mapping[str, float]) -> float:
        """Delegate to inner CompositeFitness."""
        return self._inner.score(values)

    @staticmethod
    def calculate_sharpe(returns: List[float], risk_free_rate: float = 0.0) -> float:
        """
        Calculate Sharpe ratio.

        Args:
            returns: List of period returns
            risk_free_rate: Risk-free rate (default 0.0)

        Returns:
            Sharpe ratio (mean excess return / std dev of returns)
        """
        if len(returns) < 2:
            return 0.0

        mean_return = statistics.mean(returns)
        std_return = statistics.stdev(returns)

        if std_return == 0:
            return 0.0

        return (mean_return - risk_free_rate) / std_return

    @staticmethod
    def calculate_drawdown(values: List[float]) -> float:
        """
        Calculate maximum drawdown.

        Args:
            values: List of portfolio values over time

        Returns:
            Maximum drawdown as fraction of peak value
        """
        if len(values) < 2:
            return 0.0

        peak = values[0]
        max_dd = 0.0

        for v in values[1:]:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)

        return max_dd

    @staticmethod
    def calculate_turnover(old_positions: List[float], new_positions: List[float]) -> float:
        """
        Calculate portfolio turnover.

        Args:
            old_positions: Old position weights (must sum to ~1.0)
            new_positions: New position weights (must sum to ~1.0)

        Returns:
            Turnover as sum of abs changes divided by 2
        """
        if len(old_positions) != len(new_positions):
            raise ValueError("Position lists must have same length")

        total_change = sum(abs(new - old) for old, new in zip(old_positions, new_positions))
        return total_change / 2.0
