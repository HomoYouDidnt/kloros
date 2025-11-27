from __future__ import annotations
from typing import List, Dict, Optional
import numpy as np
import hashlib

from .base import ActionChannel
from src.cognition.basal_ganglia.types import Context, ActionCandidate


class ToolChannel(ActionChannel):
    def __init__(
        self,
        tool_registry: Optional[List[str]] = None,
        tool_descriptions: Optional[Dict[str, str]] = None,
        embedding_dim: int = 384,
    ):
        self.tool_registry = tool_registry or []
        self.tool_descriptions = tool_descriptions or {}
        self.embedding_dim = embedding_dim
        self._embedding_cache: Dict[str, np.ndarray] = {}

    @property
    def name(self) -> str:
        return "tool"

    def get_candidates(self, context: Context) -> List[ActionCandidate]:
        candidates = []
        for tool_id in self.tool_registry:
            desc = self.tool_descriptions.get(tool_id, tool_id)
            embedding = self._embed(desc)
            candidates.append(
                ActionCandidate(
                    channel=self.name,
                    action_id=tool_id,
                    context_embedding=embedding,
                    metadata={"description": desc},
                )
            )
        return candidates

    def compute_d1(self, context_embedding: np.ndarray, candidate: ActionCandidate) -> float:
        if np.linalg.norm(context_embedding) == 0 or np.linalg.norm(candidate.context_embedding) == 0:
            return 0.5
        similarity = np.dot(context_embedding, candidate.context_embedding) / (
            np.linalg.norm(context_embedding) * np.linalg.norm(candidate.context_embedding)
        )
        return float(np.clip((similarity + 1) / 2, 0.0, 1.0))

    def _embed(self, text: str) -> np.ndarray:
        if text in self._embedding_cache:
            return self._embedding_cache[text]

        words = text.lower().split()
        embedding = np.zeros(self.embedding_dim, dtype=np.float32)

        for word in words:
            h = hashlib.sha256(word.encode()).digest()
            seed = int.from_bytes(h[:4], "big")
            rng = np.random.RandomState(seed)
            word_vec = rng.randn(self.embedding_dim).astype(np.float32)
            embedding += word_vec

        if len(words) > 0:
            embedding = embedding / len(words)

        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        self._embedding_cache[text] = embedding
        return embedding
