from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Tuple
from collections import deque
import numpy as np
import hashlib
import time

from src.cognition.basal_ganglia.types import ActionCandidate, Outcome, DopamineSignal


@dataclass
class RunningStats:
    mean: float = 0.0
    count: int = 0

    def update(self, value: float) -> None:
        self.count += 1
        alpha = 1.0 / self.count
        self.mean += alpha * (value - self.mean)


class SubstantiaNigra:
    """
    Dopamine neuron population - generates reward prediction error.

    Core computation: δ = actual_reward - expected_reward
    Positive δ (burst) → strengthen Direct pathway
    Negative δ (dip) → strengthen Indirect pathway
    """

    def __init__(self, n_clusters: int = 100):
        self.n_clusters = n_clusters
        self.predictions: Dict[Tuple[int, str], RunningStats] = {}
        self.recent_signals: deque = deque(maxlen=100)

    def compute_signal(self, candidate: ActionCandidate, outcome: Outcome) -> DopamineSignal:
        """Compute dopamine signal from prediction error."""
        key = self._key(candidate)

        if key not in self.predictions:
            self.predictions[key] = RunningStats()

        stats = self.predictions[key]
        expected = stats.mean if stats.count > 0 else 0.0
        actual = outcome.reward

        confidence = min(stats.count / 10, 1.0)
        uncertainty_bonus = 1.0 + (1.0 - confidence) * 0.5

        delta = (actual - expected) * uncertainty_bonus

        signal = DopamineSignal(
            delta=float(delta),
            source=f"{candidate.channel}:{candidate.action_id}",
            timestamp=time.time(),
            expected_reward=expected,
            actual_reward=actual,
        )

        stats.update(actual)
        self.recent_signals.append(signal)

        return signal

    def _key(self, candidate: ActionCandidate) -> Tuple[int, str]:
        """Generate (cluster, action_id) key."""
        cluster = self._cluster(candidate.context_embedding)
        return (cluster, candidate.action_id)

    def _cluster(self, embedding: np.ndarray) -> int:
        """Assign embedding to cluster via hash."""
        h = hashlib.md5(embedding.tobytes()).digest()
        return int.from_bytes(h[:2], "big") % self.n_clusters
