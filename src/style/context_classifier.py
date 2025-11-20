"""Context classification for style selection.

Classifies user queries by affect, task type, stakes, and continuity
to determine appropriate tone without manual dials.
"""

from typing import Optional
from dataclasses import dataclass


# Keyword heuristics for affect detection
NEGATIVE_KEYWORDS = {
    "ugh", "wtf", "broken", "doesn't work", "error", "fail", "crash",
    "help", "stuck", "freezing", "hanging", "slow", "issue", "problem",
    "bug", "wrong", "bad", "terrible"
}

PLAYFUL_KEYWORDS = {
    "lol", "lmao", "haha", "😂", "😉", "😄", "nice", "cool", "awesome"
}

# Task type keywords
DIAGNOSTIC_KEYWORDS = {
    "check", "test", "diagnose", "status", "what's wrong", "why",
    "investigate", "analyze", "debug", "trace"
}

REPAIR_KEYWORDS = {
    "fix", "repair", "restart", "reset", "recover", "restore",
    "reinstall", "rebuild", "reboot"
}

# High stakes keywords
HIGH_STAKES_KEYWORDS = {
    "data loss", "corrupted", "deleted", "lost", "security",
    "breach", "critical", "urgent", "emergency", "crashed"
}


class StyleBudget:
    """Token bucket for style rate-limiting.

    Accumulates tokens over time (1 token per 3 turns, max 2).
    Each style application costs 1 token.
    """

    def __init__(self):
        """Initialize with full budget."""
        self.tokens = 2
        self.turns_since_refill = 0

    def tick(self):
        """Call every turn to accumulate tokens."""
        self.turns_since_refill += 1
        if self.turns_since_refill >= 3:
            self.tokens = min(2, self.tokens + 1)
            self.turns_since_refill = 0

    def consume(self, n: int = 1) -> bool:
        """Attempt to consume n tokens.

        Args:
            n: Number of tokens to consume

        Returns:
            True if tokens were consumed, False if insufficient budget
        """
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False

    def reset(self):
        """Reset to full budget (for new conversations)."""
        self.tokens = 2
        self.turns_since_refill = 0


@dataclass
class Context:
    """Classified context for a user query."""
    affect: str  # "frustrated", "neutral", "playful"
    task_type: str  # "diagnostic", "repair", "chat", "explanation"
    stakes: str  # "high", "normal", "low"
    continuity: str  # "first_turn", "ongoing"
    recent_failure: bool  # Did last action fail?
    turn_idx: int  # Current turn number
    last_styled_turn: int  # Last turn where style was applied
    style_budget: StyleBudget  # Token bucket for rate-limiting


def detect_affect(query: str) -> str:
    """Detect user affect from query text.

    Args:
        query: User input text

    Returns:
        "frustrated", "neutral", or "playful"
    """
    s = query.lower()

    # Check for frustration indicators
    if any(k in s for k in NEGATIVE_KEYWORDS):
        return "frustrated"

    # Check for playful indicators
    if any(k in s for k in PLAYFUL_KEYWORDS):
        return "playful"

    return "neutral"


def classify_task(query: str) -> str:
    """Classify task type from query.

    Args:
        query: User input text

    Returns:
        "diagnostic", "repair", "chat", or "explanation"
    """
    s = query.lower()

    # Check for diagnostic intent
    if any(k in s for k in DIAGNOSTIC_KEYWORDS):
        return "diagnostic"

    # Check for repair intent
    if any(k in s for k in REPAIR_KEYWORDS):
        return "repair"

    # Check for explanation requests
    if any(word in s for word in ["explain", "what is", "how does", "describe", "tell me about"]):
        return "explanation"

    # Default to chat
    return "chat"


def assess_stakes(query: str, kloros_instance) -> str:
    """Assess stakes level from query and system state.

    Args:
        query: User input text
        kloros_instance: KLoROS instance (for error state inspection)

    Returns:
        "high", "normal", or "low"
    """
    s = query.lower()

    # High stakes keywords
    if any(k in s for k in HIGH_STAKES_KEYWORDS):
        return "high"

    # Check recent system errors (if available)
    if kloros_instance and hasattr(kloros_instance, '_recent_errors'):
        if len(kloros_instance._recent_errors) > 0:
            return "high"

    # Check if this is a diagnostic/repair task (medium stakes)
    task_type = classify_task(query)
    if task_type in ["diagnostic", "repair"]:
        return "normal"

    return "low"


def check_continuity(kloros_instance) -> str:
    """Check if this is first turn or ongoing conversation.

    Args:
        kloros_instance: KLoROS instance

    Returns:
        "first_turn" or "ongoing"
    """
    if not kloros_instance:
        return "first_turn"

    # Check conversation logger or turn counter
    if hasattr(kloros_instance, 'conversation_logger'):
        logger = kloros_instance.conversation_logger
        if hasattr(logger, 'turn_counter') and logger.turn_counter > 1:
            return "ongoing"

    return "first_turn"


def check_recent_failure(kloros_instance) -> bool:
    """Check if last action/tool invocation failed.

    Args:
        kloros_instance: KLoROS instance

    Returns:
        True if recent failure detected
    """
    if not kloros_instance:
        return False

    # Check last tool result
    if hasattr(kloros_instance, '_last_tool_result'):
        result = kloros_instance._last_tool_result
        if result and (result.startswith("❌") or "failed" in result.lower()):
            return True

    # Check error flag
    if hasattr(kloros_instance, '_recent_failure'):
        return bool(kloros_instance._recent_failure)

    return False


def classify_context(query: str, kloros_instance=None) -> Context:
    """Classify full context for style selection.

    Args:
        query: User input text
        kloros_instance: KLoROS instance (optional, for state inspection)

    Returns:
        Context object with all classification results
    """
    affect = detect_affect(query)
    task_type = classify_task(query)
    stakes = assess_stakes(query, kloros_instance)
    continuity = check_continuity(kloros_instance)
    recent_failure = check_recent_failure(kloros_instance)

    # Get turn tracking from instance
    if kloros_instance and hasattr(kloros_instance, '_style_turn_idx'):
        turn_idx = kloros_instance._style_turn_idx
    else:
        turn_idx = 0

    if kloros_instance and hasattr(kloros_instance, '_style_last_styled_turn'):
        last_styled_turn = kloros_instance._style_last_styled_turn
    else:
        last_styled_turn = -10  # Far in the past

    # Get or create style budget
    if kloros_instance and hasattr(kloros_instance, '_style_budget'):
        budget = kloros_instance._style_budget
        budget.tick()  # Accumulate tokens
    else:
        budget = StyleBudget()
        if kloros_instance:
            kloros_instance._style_budget = budget

    return Context(
        affect=affect,
        task_type=task_type,
        stakes=stakes,
        continuity=continuity,
        recent_failure=recent_failure,
        turn_idx=turn_idx,
        last_styled_turn=last_styled_turn,
        style_budget=budget,
    )


__all__ = [
    "Context",
    "StyleBudget",
    "classify_context",
    "detect_affect",
    "classify_task",
    "assess_stakes",
    "check_continuity",
    "check_recent_failure",
]
