"""
LinUCB Contextual Bandit for Tool Selection

Implements Linear Upper Confidence Bound algorithm for learning which tools
work best in different contexts, using query embeddings as features.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class LinUCBArm:
    """
    Single arm (tool) in LinUCB bandit.

    Maintains sufficient statistics for computing UCB scores:
    - A: d×d matrix (feature covariance)
    - b: d×1 vector (reward-weighted features)
    """
    name: str
    d: int
    A: np.ndarray = field(init=False)  # d×d
    b: np.ndarray = field(init=False)  # d×1

    def __post_init__(self):
        """Initialize with identity matrix and zero vector."""
        self.A = np.eye(self.d)
        self.b = np.zeros((self.d, 1))

    def theta(self) -> np.ndarray:
        """Compute parameter estimate: θ = A⁻¹b"""
        return np.linalg.solve(self.A, self.b)

    def ucb(self, x: np.ndarray, alpha: float) -> float:
        """
        Compute Upper Confidence Bound score.

        UCB = x^T θ + α√(x^T A⁻¹ x)

        Args:
            x: Feature vector (query embedding)
            alpha: Exploration parameter

        Returns:
            UCB score (higher = better candidate)
        """
        x = x.reshape(-1, 1)
        Ainv = np.linalg.inv(self.A)
        mean = float((x.T @ Ainv @ self.b).item())
        bonus = float((alpha * np.sqrt(x.T @ Ainv @ x)).item())
        return mean + bonus

    def update(self, x: np.ndarray, reward: float):
        """
        Update statistics after observing reward.

        A ← A + xx^T
        b ← b + r·x
        """
        x = x.reshape(-1, 1)
        self.A += x @ x.T
        self.b += reward * x


@dataclass
class LinUCBBandit:
    """
    LinUCB Contextual Bandit for multi-armed tool selection.

    Each "arm" is a tool. Context is query embedding. Learns which tools
    perform best in different contexts over time.
    """
    d: int  # Feature dimension
    alpha: float = 1.0  # Exploration parameter
    warm_start_reward: float = 0.5  # Initial reward for new tools
    arms: Dict[str, LinUCBArm] = field(default_factory=dict)

    def ensure_arm(self, name: str):
        """
        Lazily create arm for tool if not exists.

        Warm starts with pseudo-observation to avoid cold start.
        """
        if name not in self.arms:
            self.arms[name] = LinUCBArm(name=name, d=self.d)
            # Warm start with pseudo-observation (x = unit vector)
            x0 = np.zeros((self.d,))
            x0[0] = 1.0
            self.arms[name].update(x0, self.warm_start_reward)

    def rank(self, x: np.ndarray, candidates: List[str]) -> List[Tuple[str, float]]:
        """
        Rank candidate tools by UCB score for given context.

        Args:
            x: Context vector (query embedding)
            candidates: List of tool names to rank

        Returns:
            List of (tool_name, ucb_score) tuples, sorted descending
        """
        for c in candidates:
            self.ensure_arm(c)
        scored = [(c, self.arms[c].ucb(x, self.alpha)) for c in candidates]
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored

    def observe(self, tool: str, x: np.ndarray, reward: float):
        """
        Update bandit after observing tool execution outcome.

        Args:
            tool: Name of tool executed
            x: Context vector used
            reward: Reward in [0, 1] (from compute_reward)
        """
        self.ensure_arm(tool)
        self.arms[tool].update(x, reward)


def compute_reward(
    success: bool,
    latency_ms: int | None = None,
    tool_hops: int | None = None
) -> float:
    """
    Compute reward signal from execution outcome metrics.

    Reward components:
    - Base: 1.0 if success, 0.0 if failure
    - Latency penalty: -min(latency/5000, 0.5) (slower = worse)
    - Tool hop penalty: -min((hops-1)*0.05, 0.3) (more hops = worse)

    Args:
        success: Whether tool execution succeeded
        latency_ms: Execution time in milliseconds
        tool_hops: Number of tool calls in chain

    Returns:
        Reward in [0.0, 1.0]
    """
    r = 1.0 if success else 0.0

    if latency_ms is not None:
        # Penalize slowness up to -0.5
        r -= min(latency_ms / 5000.0, 0.5)

    if tool_hops is not None:
        # Penalize multiple hops up to -0.3
        r -= min(max(tool_hops - 1, 0) * 0.05, 0.3)

    return max(0.0, min(1.0, r))
