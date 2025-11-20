"""Aggregation methods for committee voting."""
from typing import Dict, Any, List, Tuple, Optional
import math
from collections import Counter

# Import real judge (with fallback)
try:
    from .judge import JudgeLLM, judge_llm_aggregate_real
    JUDGE_LLM_AVAILABLE = True
except ImportError:
    JUDGE_LLM_AVAILABLE = False


def majority_aggregate(
    committee_genome: Any,
    outputs_by_agent: Dict[str, Any],
    comm_state: Dict[str, Any],
    judge_pool: Optional[Any] = None
) -> Tuple[Any, List[Tuple[str, float]]]:
    """Majority voting with confidence weighting.

    Args:
        committee_genome: CommitteeGenome configuration
        outputs_by_agent: Dict mapping agent_id to output dict
        comm_state: Communication state (rationales, artifacts)
        judge_pool: Optional judge pool (unused for majority)

    Returns:
        (aggregated_output, votes) where votes is [(agent_id, confidence)]
    """
    # Extract answers and confidences
    votes = []
    answers = []

    for agent_id, output in outputs_by_agent.items():
        answer = output.get("answer", output.get("output", ""))
        confidence = output.get("confidence", 0.5)
        votes.append((agent_id, confidence))
        answers.append((answer, confidence))

    if not answers:
        return None, votes

    # Count answers weighted by confidence
    answer_scores: Dict[str, float] = {}
    for answer, confidence in answers:
        # Normalize answer for comparison
        answer_key = str(answer).strip().lower()
        answer_scores[answer_key] = answer_scores.get(answer_key, 0.0) + confidence

    # Select answer with highest weighted score
    if not answer_scores:
        return answers[0][0], votes

    best_answer_key = max(answer_scores.items(), key=lambda x: x[1])[0]

    # Find original answer matching best key
    for answer, _ in answers:
        if str(answer).strip().lower() == best_answer_key:
            return answer, votes

    return answers[0][0], votes


def conf_weighted_aggregate(
    committee_genome: Any,
    outputs_by_agent: Dict[str, Any],
    comm_state: Dict[str, Any],
    judge_pool: Optional[Any] = None
) -> Tuple[Any, List[Tuple[str, float]]]:
    """Confidence-weighted aggregation using softmax.

    Args:
        committee_genome: CommitteeGenome configuration
        outputs_by_agent: Dict mapping agent_id to output dict
        comm_state: Communication state
        judge_pool: Optional judge pool (unused)

    Returns:
        (aggregated_output, votes)
    """
    votes = []
    answers_with_conf = []

    for agent_id, output in outputs_by_agent.items():
        answer = output.get("answer", output.get("output", ""))
        confidence = output.get("confidence", 0.5)
        votes.append((agent_id, confidence))
        answers_with_conf.append((answer, confidence))

    if not answers_with_conf:
        return None, votes

    # Compute softmax weights
    confidences = [conf for _, conf in answers_with_conf]
    max_conf = max(confidences) if confidences else 1.0

    # Numerical stability: subtract max before exp
    exp_confs = [math.exp(conf - max_conf) for conf in confidences]
    sum_exp = sum(exp_confs)
    weights = [exp_c / sum_exp for exp_c in exp_confs] if sum_exp > 0 else [1.0 / len(confidences)] * len(confidences)

    # For text outputs: return answer with highest weight
    # For numeric: compute weighted average
    answers = [ans for ans, _ in answers_with_conf]

    # Try numeric aggregation
    try:
        numeric_answers = [float(ans) for ans in answers]
        aggregated = sum(w * a for w, a in zip(weights, numeric_answers))
        return aggregated, votes
    except (ValueError, TypeError):
        # Text aggregation: return highest-weighted answer
        max_idx = weights.index(max(weights))
        return answers[max_idx], votes


def judge_llm_aggregate(
    committee_genome: Any,
    outputs_by_agent: Dict[str, Any],
    comm_state: Dict[str, Any],
    judge_pool: Optional[Any] = None
) -> Tuple[Any, List[Tuple[str, float]]]:
    """Judge LLM aggregation with real LLM or fallback heuristic.

    Uses actual Ollama LLM to judge committee outputs and select best answer.
    Falls back to heuristic if LLM unavailable or errors.

    Args:
        committee_genome: CommitteeGenome configuration
        outputs_by_agent: Dict mapping agent_id to output dict
        comm_state: Communication state
        judge_pool: Optional JudgeLLM instance

    Returns:
        (aggregated_output, votes)
    """
    # Try real LLM judge first
    if JUDGE_LLM_AVAILABLE:
        try:
            return judge_llm_aggregate_real(
                committee_genome,
                outputs_by_agent,
                comm_state,
                judge_pool
            )
        except Exception as e:
            print(f"[judge] LLM judge failed, using fallback: {e}")

    # Fallback heuristic
    votes = []
    answers_with_trace = []

    for agent_id, output in outputs_by_agent.items():
        answer = output.get("answer", output.get("output", ""))
        confidence = output.get("confidence", 0.5)
        trace = output.get("trace", "")
        votes.append((agent_id, confidence))
        answers_with_trace.append((answer, confidence, trace, agent_id))

    if not answers_with_trace:
        return None, votes

    # Heuristic: select answer with highest confidence and longest trace
    scored = [
        (answer, conf * (1 + len(trace) / 1000), agent_id)
        for answer, conf, trace, agent_id in answers_with_trace
    ]

    best = max(scored, key=lambda x: x[1])
    return best[0], votes


# Registry
AGG_MAP = {
    "majority": majority_aggregate,
    "conf_weighted": conf_weighted_aggregate,
    "judge_llm": judge_llm_aggregate
}


def aggregate(
    method: str,
    committee_genome: Any,
    outputs_by_agent: Dict[str, Any],
    comm_state: Dict[str, Any],
    judge_pool: Optional[Any] = None
) -> Tuple[Any, List[Tuple[str, float]]]:
    """Aggregate outputs using specified method.

    Args:
        method: Aggregation method ("majority", "conf_weighted", "judge_llm")
        committee_genome: CommitteeGenome configuration
        outputs_by_agent: Outputs from each agent
        comm_state: Communication state
        judge_pool: Optional judge pool

    Returns:
        (aggregated_output, votes)
    """
    agg_fn = AGG_MAP.get(method, majority_aggregate)
    return agg_fn(committee_genome, outputs_by_agent, comm_state, judge_pool)


def disagreement_entropy(votes: List[Tuple[str, float]]) -> float:
    """Compute disagreement entropy from votes.

    Args:
        votes: List of (agent_id, confidence) tuples

    Returns:
        Entropy value (higher = more disagreement)
    """
    if not votes:
        return 0.0

    # Normalize confidences to probabilities
    confidences = [conf for _, conf in votes]
    total = sum(confidences)

    if total == 0:
        return 0.0

    probs = [conf / total for conf in confidences]

    # Compute Shannon entropy
    entropy = -sum(p * math.log2(p) if p > 0 else 0 for p in probs)
    return entropy
