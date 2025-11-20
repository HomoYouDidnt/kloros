class FrozenJudges:
    """Frozen, deterministic scorers for candidate evaluation."""

    def __init__(self, weights):
        self.w = weights

    def score(self, metrics: dict) -> float:
        """Compute weighted score from metrics."""
        s = 0.0
        for k, w in self.w.items():
            s += w * float(metrics.get(k, 0.0))
        return max(0.0, min(1.0, s))
