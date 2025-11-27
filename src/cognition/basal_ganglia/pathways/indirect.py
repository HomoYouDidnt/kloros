from __future__ import annotations
from typing import Dict, Tuple
import numpy as np
import hashlib

from src.cognition.basal_ganglia.types import ActionCandidate, DopamineSignal


class IndirectPathway:
    """
    D2 'NoGo' pathway - surround inhibition.

    Nonlinear inverted-U: moderate activation provides good inhibition,
    but too much causes over-inhibition (freezing).
    Strengthened by dopamine dips (omissions/punishments).
    """

    def __init__(
        self,
        learning_rate: float = 0.01,
        n_clusters: int = 100,
        peak: float = 0.6,
    ):
        self.learning_rate = learning_rate
        self.n_clusters = n_clusters
        self.peak = peak
        self.weights: Dict[Tuple[int, str], float] = {}

    def compute_activation(self, context_embedding: np.ndarray, candidate: ActionCandidate) -> float:
        """Inverted-U activation for surround inhibition."""
        key = self._key(candidate)
        weight = self.weights.get(key, 0.5)

        inverted_u = self._inverted_u(weight)
        surround = self._surround_signal(context_embedding, candidate)

        return float(np.clip(inverted_u * surround, 0.01, 1.0))

    def update(
        self,
        candidate: ActionCandidate,
        dopamine: DopamineSignal,
        lr_modifier: float = 1.0,
    ) -> None:
        """Update weights based on dopamine signal (dips only)."""
        if dopamine.delta >= 0:
            return

        key = self._key(candidate)
        current = self.weights.get(key, 0.5)
        effective_lr = self.learning_rate * lr_modifier

        self.weights[key] = float(np.clip(
            current - effective_lr * dopamine.delta,
            0.0,
            1.0
        ))

    def _inverted_u(self, x: float) -> float:
        """Inverted-U curve peaking at self.peak."""
        return float(1.0 - ((x - self.peak) ** 2) / (self.peak ** 2))

    def _surround_signal(self, context_emb: np.ndarray, candidate: ActionCandidate) -> float:
        """Surround inhibition signal - inhibit similar but not identical."""
        if np.linalg.norm(context_emb) == 0 or np.linalg.norm(candidate.context_embedding) == 0:
            return 0.5
        cos_sim = np.dot(context_emb, candidate.context_embedding) / (
            np.linalg.norm(context_emb) * np.linalg.norm(candidate.context_embedding)
        )
        return float((1 - abs(cos_sim)) * 0.5 + 0.5)

    def _key(self, candidate: ActionCandidate) -> Tuple[int, str]:
        """Generate (cluster, action_id) key."""
        cluster = self._cluster(candidate.context_embedding)
        return (cluster, candidate.action_id)

    def _cluster(self, embedding: np.ndarray) -> int:
        """Assign embedding to cluster via hash."""
        h = hashlib.md5(embedding.tobytes()).digest()
        return int.from_bytes(h[:2], "big") % self.n_clusters
