from __future__ import annotations
from typing import Dict, Tuple
import numpy as np
import hashlib

from src.cognition.basal_ganglia.types import ActionCandidate, DopamineSignal


class DirectPathway:
    """
    D1 'Go' pathway - facilitates selected actions.

    Linear relationship: higher activation = stronger facilitation.
    Strengthened by dopamine bursts (unexpected rewards).
    """

    def __init__(self, learning_rate: float = 0.01, n_clusters: int = 100):
        self.learning_rate = learning_rate
        self.n_clusters = n_clusters
        self.weights: Dict[Tuple[int, str], float] = {}

    def compute_activation(self, context_embedding: np.ndarray, candidate: ActionCandidate) -> float:
        """Linear activation: weight × context_similarity."""
        key = self._key(candidate)
        weight = self.weights.get(key, 0.5)

        similarity = self._context_similarity(context_embedding, candidate)
        return float(np.clip(weight * similarity, 0.0, 1.0))

    def update(
        self,
        candidate: ActionCandidate,
        dopamine: DopamineSignal,
        lr_modifier: float = 1.0,
    ) -> None:
        """Update weights based on dopamine signal (bursts only)."""
        if dopamine.delta <= 0:
            return

        key = self._key(candidate)
        current = self.weights.get(key, 0.5)
        effective_lr = self.learning_rate * lr_modifier

        self.weights[key] = float(np.clip(
            current + effective_lr * dopamine.delta,
            0.0,
            1.0
        ))

    def _key(self, candidate: ActionCandidate) -> Tuple[int, str]:
        """Generate (cluster, action_id) key."""
        cluster = self._cluster(candidate.context_embedding)
        return (cluster, candidate.action_id)

    def _cluster(self, embedding: np.ndarray) -> int:
        """Assign embedding to cluster via hash."""
        h = hashlib.md5(embedding.tobytes()).digest()
        return int.from_bytes(h[:2], "big") % self.n_clusters

    def _context_similarity(self, context_emb: np.ndarray, candidate: ActionCandidate) -> float:
        """Cosine similarity normalized to [0, 1]."""
        if np.linalg.norm(context_emb) == 0 or np.linalg.norm(candidate.context_embedding) == 0:
            return 0.5
        cos_sim = np.dot(context_emb, candidate.context_embedding) / (
            np.linalg.norm(context_emb) * np.linalg.norm(candidate.context_embedding)
        )
        return float((cos_sim + 1) / 2)
