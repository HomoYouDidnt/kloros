"""Deadlock Prevention for TUMIX Committee Voting

Prevents infinite loops and groupthink by detecting low-entropy votes
and invoking fallback mechanisms.

Requirements (Phase 6):
- Detect low entropy (all agents agreeing → potential groupthink)
- Invoke judge LLM once to break tie
- Fallback to majority if judge also agrees (prevent infinite loops)
- Never invoke judge more than once per vote
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
import math

logger = logging.getLogger(__name__)

# Entropy thresholds
LOW_ENTROPY_THRESHOLD = 0.3  # Below this, suspect groupthink
HIGH_AGREEMENT_THRESHOLD = 0.9  # Above this confidence similarity, suspect collapse


class DeadlockPreventionResult:
    """Result of deadlock prevention check."""

    def __init__(
        self,
        is_deadlocked: bool,
        reason: str,
        entropy: float,
        agreement_level: float,
        should_invoke_judge: bool
    ):
        """Initialize result.

        Args:
            is_deadlocked: True if deadlock detected
            reason: Human-readable reason
            entropy: Computed entropy value
            agreement_level: Agreement level (0-1)
            should_invoke_judge: True if judge should be invoked
        """
        self.is_deadlocked = is_deadlocked
        self.reason = reason
        self.entropy = entropy
        self.agreement_level = agreement_level
        self.should_invoke_judge = should_invoke_judge


def compute_vote_entropy(votes: List[Tuple[str, float]]) -> float:
    """Compute Shannon entropy from votes.

    Args:
        votes: List of (agent_id, confidence) tuples

    Returns:
        Entropy value (0 = perfect agreement, higher = more disagreement)
    """
    if not votes or len(votes) < 2:
        return 0.0

    # Normalize confidences to probabilities
    confidences = [conf for _, conf in votes]
    total = sum(confidences)

    if total == 0:
        return 0.0

    probs = [conf / total for conf in confidences]

    # Shannon entropy: H = -sum(p * log2(p))
    entropy = -sum(p * math.log2(p) if p > 0 else 0 for p in probs)

    # Normalize by max entropy (log2(n))
    max_entropy = math.log2(len(votes)) if len(votes) > 1 else 1.0
    normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0

    return normalized_entropy


def compute_agreement_level(votes: List[Tuple[str, float]]) -> float:
    """Compute agreement level from votes.

    High agreement = all confidences are similar (potential groupthink).

    Args:
        votes: List of (agent_id, confidence) tuples

    Returns:
        Agreement level (0-1, higher = more agreement)
    """
    if not votes or len(votes) < 2:
        return 1.0

    confidences = [conf for _, conf in votes]

    # Compute variance
    mean_conf = sum(confidences) / len(confidences)
    variance = sum((conf - mean_conf) ** 2 for conf in confidences) / len(confidences)

    # Convert variance to agreement (lower variance = higher agreement)
    # Use exponential decay to map variance to [0, 1]
    agreement = math.exp(-variance * 10)  # Scale factor 10 for sensitivity

    return agreement


def detect_deadlock(
    votes: List[Tuple[str, float]],
    outputs_by_agent: Dict[str, Any],
    judge_already_invoked: bool = False
) -> DeadlockPreventionResult:
    """Detect if committee is deadlocked.

    Deadlock conditions:
    1. Low entropy (< 0.3) → all agents agreeing → suspect groupthink
    2. High agreement (> 0.9) → all confidences similar → suspect collapse
    3. Judge already invoked → prevent infinite loops

    Args:
        votes: List of (agent_id, confidence) tuples
        outputs_by_agent: Dict mapping agent_id to output
        judge_already_invoked: True if judge was already invoked

    Returns:
        DeadlockPreventionResult
    """
    entropy = compute_vote_entropy(votes)
    agreement = compute_agreement_level(votes)

    # Case 1: Low entropy (all agreeing)
    if entropy < LOW_ENTROPY_THRESHOLD:
        if judge_already_invoked:
            # Judge already tried, fallback to majority
            logger.warning(
                "[deadlock] Low entropy (%.3f) after judge invocation, using majority fallback",
                entropy
            )
            return DeadlockPreventionResult(
                is_deadlocked=True,
                reason="Low entropy after judge invocation, using majority fallback",
                entropy=entropy,
                agreement_level=agreement,
                should_invoke_judge=False  # Already tried
            )
        else:
            # First time, invoke judge to break potential groupthink
            logger.info(
                "[deadlock] Low entropy (%.3f) detected, invoking judge once",
                entropy
            )
            return DeadlockPreventionResult(
                is_deadlocked=True,
                reason="Low entropy detected, invoking judge to break groupthink",
                entropy=entropy,
                agreement_level=agreement,
                should_invoke_judge=True
            )

    # Case 2: High agreement (potential collapse)
    if agreement > HIGH_AGREEMENT_THRESHOLD:
        # Check if all answers are identical (true collapse)
        unique_answers = set()
        for output in outputs_by_agent.values():
            answer = str(output.get("answer", output.get("output", ""))).strip().lower()
            unique_answers.add(answer)

        if len(unique_answers) == 1:
            # All agents gave identical answer
            if judge_already_invoked:
                logger.warning(
                    "[deadlock] All agents agree (agreement=%.3f) after judge, accepting consensus",
                    agreement
                )
                return DeadlockPreventionResult(
                    is_deadlocked=False,  # Accept consensus
                    reason="All agents agree after judge review",
                    entropy=entropy,
                    agreement_level=agreement,
                    should_invoke_judge=False
                )
            else:
                logger.info(
                    "[deadlock] High agreement (%.3f), invoking judge to verify consensus",
                    agreement
                )
                return DeadlockPreventionResult(
                    is_deadlocked=True,
                    reason="High agreement, judge verification needed",
                    entropy=entropy,
                    agreement_level=agreement,
                    should_invoke_judge=True
                )

    # No deadlock
    return DeadlockPreventionResult(
        is_deadlocked=False,
        reason="Normal voting, sufficient diversity",
        entropy=entropy,
        agreement_level=agreement,
        should_invoke_judge=False
    )


def apply_deadlock_prevention(
    votes: List[Tuple[str, float]],
    outputs_by_agent: Dict[str, Any],
    aggregation_method: str,
    committee_genome: Any,
    comm_state: Dict[str, Any],
    judge_pool: Optional[Any] = None,
    judge_invocation_count: int = 0
) -> Tuple[Any, List[Tuple[str, float]], Dict[str, Any]]:
    """Apply deadlock prevention to committee voting.

    Args:
        votes: Current votes
        outputs_by_agent: Outputs from agents
        aggregation_method: Current aggregation method
        committee_genome: Committee genome
        comm_state: Communication state
        judge_pool: Optional judge pool
        judge_invocation_count: Number of times judge was invoked

    Returns:
        Tuple of (aggregated_output, votes, diagnostic_info)
    """
    from .aggregators import aggregate

    # Detect deadlock
    result = detect_deadlock(
        votes,
        outputs_by_agent,
        judge_already_invoked=(judge_invocation_count > 0)
    )

    diagnostic = {
        "deadlock_detected": result.is_deadlocked,
        "deadlock_reason": result.reason,
        "entropy": result.entropy,
        "agreement_level": result.agreement_level,
        "judge_invocations": judge_invocation_count
    }

    if not result.is_deadlocked:
        # Normal aggregation
        output, votes_out = aggregate(
            aggregation_method,
            committee_genome,
            outputs_by_agent,
            comm_state,
            judge_pool
        )
        return output, votes_out, diagnostic

    # Deadlock detected
    if result.should_invoke_judge and judge_invocation_count == 0:
        # Invoke judge once
        logger.info("[deadlock] Invoking judge LLM to break deadlock")
        output, votes_out = aggregate(
            "judge_llm",  # Force judge aggregation
            committee_genome,
            outputs_by_agent,
            comm_state,
            judge_pool
        )

        diagnostic["judge_invoked"] = True
        return output, votes_out, diagnostic

    # Fallback to majority (judge already tried or shouldn't invoke)
    logger.info("[deadlock] Using majority fallback to prevent infinite loop")
    output, votes_out = aggregate(
        "majority",  # Force majority fallback
        committee_genome,
        outputs_by_agent,
        comm_state,
        judge_pool
    )

    diagnostic["fallback_used"] = "majority"
    return output, votes_out, diagnostic
