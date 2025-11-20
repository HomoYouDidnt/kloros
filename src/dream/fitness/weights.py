from dataclasses import dataclass, field
from typing import Dict

@dataclass(frozen=True)
class FitnessWeights:
    """Fitness weights specified as keyword arguments."""
    perf: float = 0.0
    stability: float = 0.0
    maxdd: float = 0.0
    turnover: float = 0.0
    corr: float = 0.0
    risk: float = 0.0

    # Additional weights can be added via weights dict
    weights: Dict[str, float] = field(default_factory=dict)

    def get(self, name: str) -> float:
        """Get weight by name, checking both attributes and weights dict."""
        if hasattr(self, name) and name != 'weights':
            return getattr(self, name)
        return self.weights.get(name, 0.0)

    def objectives(self):
        """Return all non-zero objectives."""
        objs = []
        for attr in ['perf', 'stability', 'maxdd', 'turnover', 'corr', 'risk']:
            if getattr(self, attr) != 0.0:
                objs.append(attr)
        objs.extend(self.weights.keys())
        return tuple(objs)

    def items(self):
        """Iterate over (name, weight) pairs."""
        for attr in ['perf', 'stability', 'maxdd', 'turnover', 'corr', 'risk']:
            val = getattr(self, attr)
            if val != 0.0:
                yield attr, val
        yield from self.weights.items()
