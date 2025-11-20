from dataclasses import dataclass
from typing import Dict, Optional, Mapping, List
import statistics

@dataclass
class CompositeFitness:
    """
    Composite fitness with hard caps and aggregation support.

    Args:
        weights: FitnessWeights object or Mapping of objective names to weights
        hard_caps: Optional dict of objective names to maximum allowed values
        constraints: Optional dict like {"novelty":{"min":0.1}, "safety":{"max":0.0}}
        penalty: Penalty value for constraint violations (default 0.0)
    """
    weights: Mapping[str, float]
    hard_caps: Optional[Dict[str, float]] = None
    constraints: Optional[Dict[str, Dict[str, float]]] = None
    penalty: float = 0.0

    def score(self, values: Mapping[str, float]) -> float:
        """
        Calculate weighted fitness score.

        Returns -inf if any hard_caps are exceeded.
        """
        # Check hard caps first
        if self.hard_caps:
            for obj, cap in self.hard_caps.items():
                if obj in values and values[obj] > cap:
                    return float('-inf')

        # Calculate weighted score
        s = 0.0

        # Handle FitnessWeights object with .items() method
        if hasattr(self.weights, 'items'):
            weights_iter = self.weights.items()
        else:
            weights_iter = self.weights.items()

        # Penalty metrics (higher is worse) should be negated
        PENALTY_METRICS = {'maxdd', 'turnover', 'corr', 'risk'}

        for k, w in weights_iter:
            v = float(values.get(k, 0.0))
            # Negate weight for penalty metrics
            effective_w = -w if k in PENALTY_METRICS else w
            s += effective_w * v

            # Apply soft constraints if provided
            if self.constraints and k in self.constraints:
                c = self.constraints[k]
                if "min" in c and v < c["min"]:
                    s -= abs(self.penalty)
                if "max" in c and v > c["max"]:
                    s -= abs(self.penalty)

        return s

    def aggregate(self, regime_metrics: List[Dict[str, float]]) -> Dict[str, float]:
        """
        Aggregate metrics across multiple regimes.

        Computes mean for each metric and adds 'stability' as negative std dev.

        Args:
            regime_metrics: List of metric dicts from different regimes

        Returns:
            Aggregated metrics with 'stability' added
        """
        if not regime_metrics:
            return {}

        # Collect all metric names
        all_keys = set()
        for m in regime_metrics:
            all_keys.update(m.keys())

        agg = {}
        for key in all_keys:
            values = [m.get(key, 0.0) for m in regime_metrics]
            agg[key] = statistics.mean(values)

        # Add stability as negative std dev of perf
        if 'perf' in agg:
            perf_values = [m.get('perf', 0.0) for m in regime_metrics]
            if len(perf_values) > 1:
                std_dev = statistics.stdev(perf_values)
                agg['stability'] = -std_dev
            else:
                agg['stability'] = 0.0

        return agg
