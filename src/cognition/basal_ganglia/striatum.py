from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict
from collections import deque
import numpy as np
import hashlib

from src.cognition.basal_ganglia.types import Context, ActionCandidate
from src.cognition.basal_ganglia.channels.base import ActionChannel


@dataclass
class StriatumConfig:
    embedding_dim: int = 384
    novelty_threshold: float = 0.7
    history_size: int = 1000


class Striatum:
    """
    Input nucleus - transforms context into channel activations.

    Receives context, generates candidates from each channel,
    computes D1/D2 activations, and flags novel contexts.
    """

    def __init__(
        self,
        channels: List[ActionChannel],
        embedding_dim: int = 384,
        novelty_threshold: float = 0.7,
        history_size: int = 1000,
    ):
        self.channels = {ch.name: ch for ch in channels}
        self.embedding_dim = embedding_dim
        self.novelty_threshold = novelty_threshold
        self.context_history: deque = deque(maxlen=history_size)
        self._query_history: deque = deque(maxlen=history_size)

    def process(self, context: Context) -> List[ActionCandidate]:
        """Transform context into scored action candidates."""
        context_embedding = self._embed_context(context)

        is_novel = self._check_novelty(context.query, context_embedding)
        self._query_history.append(context.query)

        candidates = []
        for channel in self.channels.values():
            channel_candidates = channel.get_candidates(context)
            for candidate in channel_candidates:
                candidate.direct_activation = channel.compute_d1(
                    context_embedding, candidate
                )
                candidate.indirect_activation = channel.compute_d2(
                    context_embedding, candidate
                )
                candidate.is_novel_context = is_novel
                candidates.append(candidate)

        self.context_history.append(context_embedding)
        return candidates

    def _embed_context(self, context: Context) -> np.ndarray:
        """Generate embedding for context."""
        text = context.query
        h = hashlib.sha256(text.encode()).digest()
        seed = int.from_bytes(h[:4], "big")
        rng = np.random.RandomState(seed)
        embedding = rng.randn(self.embedding_dim).astype(np.float32)
        return embedding / np.linalg.norm(embedding)

    def _check_novelty(self, query: str, embedding: np.ndarray) -> bool:
        """Check if context is novel compared to history.

        Args:
            query: Current query string to check for novelty
            embedding: Context embedding (reserved for future embedding-based novelty checks)
        """
        if len(self._query_history) < 5:
            return True

        max_similarity = 0.0

        for hist_query in list(self._query_history)[-50:]:
            sim = self._query_similarity(query, hist_query)
            max_similarity = max(max_similarity, sim)

        return max_similarity < self.novelty_threshold

    def _query_similarity(self, query1: str, query2: str) -> float:
        """Calculate similarity between two query strings using word overlap."""
        words1 = set(query1.lower().split())
        words2 = set(query2.lower().split())

        if not words1 or not words2:
            return 1.0 if query1 == query2 else 0.0

        intersection = len(words1 & words2)
        max_len = max(len(words1), len(words2))

        return float(intersection / max_len) if max_len > 0 else 0.0

    def get_context_embedding(self, context: Context) -> np.ndarray:
        """Public method to get embedding for a context."""
        return self._embed_context(context)
