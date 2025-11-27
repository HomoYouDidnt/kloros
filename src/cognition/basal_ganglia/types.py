from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Any
import numpy as np
import time


@dataclass
class Context:
    query: str
    conversation_history: List[dict] = field(default_factory=list)
    user_profile: Optional[dict] = None
    stakes_level: float = 0.5
    novelty_score: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class ActionCandidate:
    channel: str
    action_id: str
    context_embedding: np.ndarray
    direct_activation: float = 0.0
    indirect_activation: float = 0.0
    is_novel_context: bool = False
    metadata: dict = field(default_factory=dict)

    @property
    def competition_degree(self) -> float:
        return self.direct_activation / max(self.indirect_activation, 0.01)


@dataclass
class DopamineSignal:
    delta: float
    source: str
    timestamp: float
    expected_reward: float = 0.0
    actual_reward: float = 0.0

    @property
    def is_burst(self) -> bool:
        return self.delta > 0

    @property
    def is_dip(self) -> bool:
        return self.delta < 0


@dataclass
class Outcome:
    success: bool
    latency_ms: float = 0.0
    user_feedback: Optional[float] = None
    tokens_used: Optional[int] = None
    error_message: Optional[str] = None

    @property
    def reward(self) -> float:
        r = 0.0
        r += 0.5 if self.success else 0.0
        if self.user_feedback is not None:
            r += self.user_feedback * 0.3
        latency_penalty = min(self.latency_ms / 5000, 0.2)
        r -= latency_penalty
        if self.tokens_used:
            efficiency = 1.0 - min(self.tokens_used / 10000, 1.0)
            r += efficiency * 0.1
        return np.clip(r, -1.0, 1.0)


@dataclass
class SelectionResult:
    selected: ActionCandidate
    runner_up: Optional[ActionCandidate] = None
    competition_margin: float = 0.0
    deliberation_requested: bool = False
    deliberation_reason: str = ""
    selection_method: str = "competition"
