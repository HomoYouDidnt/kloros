"""TUMIX data models for committee-based reasoning."""
from typing import Dict, Any, List, Optional, Literal, Tuple
from dataclasses import dataclass, field


AggMethod = Literal["majority", "conf_weighted", "judge_llm"]


@dataclass
class AgentGenome:
    """Configuration for a single agent in a committee."""
    id: str
    prompt_style: str = "default"
    tools: Dict[str, bool] = field(default_factory=dict)
    planner: Literal["cot", "plan_exec", "reAct", "toolformer", "deep_planner"] = "cot"
    temp: float = 0.7
    depth: int = 1
    reflection_steps: int = 0
    latency_budget_ms: int = 5000
    mutation_rate: float = 0.1
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CommitteeGenome:
    """Configuration for a committee of agents."""
    id: str
    members: List[AgentGenome]
    k: int  # Committee size
    comms_rounds: int = 1  # 1-3 rounds of communication
    aggregation: AggMethod = "majority"
    diversity_penalty_coeff: float = 0.2
    judge_agent_id: Optional[str] = None  # Only used if aggregation="judge_llm"


@dataclass
class Trial:
    """A trial task for committee evaluation."""
    task_id: str
    inputs: Dict[str, Any]
    eval_fns: List[str]  # Names in registry


@dataclass
class CommitteeRunResult:
    """Result of running a committee on a trial."""
    committee_id: str
    task_id: str
    votes: List[Tuple[str, float]]  # [(agent_id, confidence)]
    outputs_by_agent: Dict[str, Any]
    aggregated_output: Any
    tools_used: Dict[str, int]
    latency_ms: int
    diag: Dict[str, Any]  # Disagreement entropy, comm logs, etc.


@dataclass
class FitnessReport:
    """Fitness report for a committee run."""
    score: float
    components: Dict[str, float]  # {"acc":..., "robust":..., "consistency":..., "cost":-...}
    stability: Dict[str, float]  # bootstrap_agree, perturb_delta, ECE/Brier
    intra_similarity: float


@dataclass
class MixGroupResult:
    """Result of intra-group play in TUMIX."""
    champion_idx: int
    metrics: Dict[str, float]
    lineage: List[int]  # Indices of members used to compose champion
