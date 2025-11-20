# genome.py — AgentGenome & BehavioralPhenotype for zooids
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Literal, Optional
from enum import Enum
import time

class EcologicalRole(str, Enum):
    STABILIZER = "stabilizer"
    MONITOR    = "monitor"
    CLEANER    = "cleaner"
    PREDICTOR  = "predictor"
    CONTROLLER = "controller"
    SYNTHESIZER= "synthesizer"
    MEDIATOR   = "mediator"

class LifecycleState(str, Enum):
    PLURIPOTENT    = "pluripotent"
    DIFFERENTIATED = "differentiated"
    ACTIVE         = "active"
    DORMANT        = "dormant"
    PRUNED         = "pruned"

@dataclass
class BehavioralPhenotype:
    latency_budget_ms: int
    throughput_target_qps: float
    safety_guardrails: List[str]
    cooperation_style: Literal["leader","support","peer"]
    communication_protocols: List[str]  # e.g. ["chem://Q_*", "chem://synth.*"]

@dataclass
class AgentGenome:
    # Identity
    name: str
    ecosystem: str                  # e.g. "queue_management"
    niche: str                      # e.g. "flow_regulation"
    ecological_role: EcologicalRole # e.g. EcologicalRole.STABILIZER

    # Relationships
    collaborators: List[str] = field(default_factory=list)
    competitors:  List[str] = field(default_factory=list)

    # Lifecycle
    birth_generation: int = 0
    last_active_ts: float = field(default_factory=lambda: time.time())
    dormancy_threshold_ticks: int = 30
    state: LifecycleState = LifecycleState.DIFFERENTIATED

    # Code & Execution
    module_code: str = ""          # source payload
    entrypoint: str = "main:run"   # module:function
    sandbox_profile: str = "default"
    required_caps: List[str] = field(default_factory=list)
    phenotype: BehavioralPhenotype | None = None

    # Fitness
    fitness_scores: Dict[str, float] = field(default_factory=dict)  # keyed by PHASE ids
    composite_fitness: float = 0.0
