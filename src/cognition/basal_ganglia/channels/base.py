from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List
import numpy as np

from src.cognition.basal_ganglia.types import Context, ActionCandidate


class ActionChannel(ABC):
    """
    Base class for action channels.

    Each channel represents a domain of actions (tools, agents, responses, etc.)
    and provides candidates with D1/D2 activation scores.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Channel identifier."""
        pass

    @abstractmethod
    def get_candidates(self, context: Context) -> List[ActionCandidate]:
        """Generate action candidates for this context."""
        pass

    def compute_d1(self, context_embedding: np.ndarray, candidate: ActionCandidate) -> float:
        """
        Compute Direct pathway (D1) activation.

        Default: cosine similarity between context and candidate embeddings.
        Override for channel-specific logic.
        """
        if np.linalg.norm(context_embedding) == 0 or np.linalg.norm(candidate.context_embedding) == 0:
            return 0.5
        similarity = np.dot(context_embedding, candidate.context_embedding) / (
            np.linalg.norm(context_embedding) * np.linalg.norm(candidate.context_embedding)
        )
        return float(np.clip((similarity + 1) / 2, 0.0, 1.0))

    def compute_d2(self, context_embedding: np.ndarray, candidate: ActionCandidate) -> float:
        """
        Compute Indirect pathway (D2) activation.

        Default: inverse of D1 with baseline.
        Override for channel-specific surround inhibition.
        """
        d1 = self.compute_d1(context_embedding, candidate)
        return float(np.clip(1.0 - d1 + 0.3, 0.1, 1.0))
