"""TUMIX: Committee-based multi-agent reasoning."""
from .types import (
    AgentGenome,
    CommitteeGenome,
    Trial,
    CommitteeRunResult,
    FitnessReport,
    MixGroupResult,
    AggMethod
)
from .aggregators import (
    majority_aggregate,
    conf_weighted_aggregate,
    judge_llm_aggregate,
    aggregate,
    disagreement_entropy
)
from .committee_runner import (
    AgentWorker,
    CommitteeRunner,
    SimpleTUMIXRunner
)

# Judge LLM (optional, requires Ollama)
try:
    from .judge import JudgeLLM, judge_llm_aggregate_real
    __all__ = [
        "AgentGenome",
        "CommitteeGenome",
        "Trial",
        "CommitteeRunResult",
        "FitnessReport",
        "MixGroupResult",
        "AggMethod",
        "majority_aggregate",
        "conf_weighted_aggregate",
        "judge_llm_aggregate",
        "aggregate",
        "disagreement_entropy",
        "AgentWorker",
        "CommitteeRunner",
        "SimpleTUMIXRunner",
        "JudgeLLM",
        "judge_llm_aggregate_real",
    ]
except ImportError:
    __all__ = [
        "AgentGenome",
        "CommitteeGenome",
        "Trial",
        "CommitteeRunResult",
        "FitnessReport",
        "MixGroupResult",
        "AggMethod",
        "majority_aggregate",
        "conf_weighted_aggregate",
        "judge_llm_aggregate",
        "aggregate",
        "disagreement_entropy",
        "AgentWorker",
        "CommitteeRunner",
        "SimpleTUMIXRunner",
    ]
