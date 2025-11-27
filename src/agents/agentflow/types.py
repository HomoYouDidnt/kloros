"""Data types for AgentFlow episodes and turns."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time


@dataclass
class TurnRecord:
    """Record of a single turn in an episode."""
    state_fp: str  # Fingerprint of state at turn start
    decision: Dict[str, Any]  # {tool, args, rationale, confidence}
    exec: Dict[str, Any]  # {artifacts, errors, latency, tool_calls}
    verify: Dict[str, Any]  # {pass, score, critique}
    cost: Dict[str, float]  # {tokens, latency_ms, tool_calls}
    timestamp: float = field(default_factory=time.time)


@dataclass
class EpisodeRecord:
    """Complete record of an episode with outcomes and rewards."""
    episode_id: str
    task_spec: Dict[str, Any]  # Original task specification
    turns: List[TurnRecord]
    outcome: Dict[str, Any]  # {success, metrics, final_answer}
    rewards: Dict[str, Any]  # {trajectory_R, per_turn_A}
    safety: Dict[str, Any]  # {petri_incidents, blocked_ops}
    planner_hints: List[str] = field(default_factory=list)  # ACE bullets used
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class TaskSpec:
    """Specification for a task to be executed."""
    query: str
    domain: str = "general"
    max_turns: int = 1
    budgets: Dict[str, float] = field(default_factory=lambda: {
        "latency_ms": 5000,
        "tool_calls": 4,
        "tokens": 3500
    })
    require_verification: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
