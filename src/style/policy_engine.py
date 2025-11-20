"""Style policy engine: Rule-based technique selection with no manual dials.

Selects appropriate tone based on context signals (affect, task, stakes, continuity)
with built-in rate-limiting and cooldown to prevent overuse.
"""

import re
from typing import Optional
from .context_classifier import Context


# Cooldown configuration
MIN_TURNS_BETWEEN_STYLE = 2  # Never style consecutive turns
FAILURE_COOLDOWN_TURNS = 3  # No style for N turns after failure


def _is_structured_output(text: str) -> bool:
    """Detect if response contains structured test/diagnostic output.

    Args:
        text: Response text

    Returns:
        True if structured output detected
    """
    # Check for common structured output markers
    markers = [
        r'^\s*=+\s*.+?\s*=+\s*$',  # Section headers: === Audio ===
        r'[✓✗❌✅]',                 # Status symbols
        r'^\s*[-•]\s+\w+.*:',      # Bullet points with labels
        r'^\s*\d+\.\s+\w+.*:',     # Numbered lists with labels
        r'^[\U0001F300-\U0001F9FF].+:',  # Emoji headers: 🎵 Audio:
        r'^\s*[•·]\s+',            # Any bullet points
        r'^\s*●.+\.service\s+-\s+',  # systemctl status: ● service.name -
        r'^\s*(Loaded|Active|Main PID|Tasks|Memory|CPU|CGroup):',  # systemctl fields
    ]

    for pattern in markers:
        if re.search(pattern, text, re.MULTILINE):
            return True

    return False


def choose_technique(ctx: Context, response_text: str = "") -> Optional[str]:
    """Choose style technique based on context (rule-based, no sliders).

    Policy gates (in order):
    1. Hard safety gates (high stakes, frustrated user, ops tasks)
    2. Cooldown gates (recent failure, rate limit)
    3. Budget gate (token bucket)
    4. Positive selection (playful + low stakes → technique)
    5. Special handling (structured output → natural summary)

    Args:
        ctx: Classified context
        response_text: The response text to check for structured output

    Returns:
        Technique name or None (no styling)
    """
    # === Special Case: Structured Output ===
    # Always naturalize structured test/diagnostic output regardless of context
    if response_text and _is_structured_output(response_text):
        return "natural_summary"
    # === Hard Safety Gates ===

    # Gate 1: High stakes → no style (user needs clear info)
    if ctx.stakes == "high":
        return None

    # Gate 2: Frustrated user → no snark (acknowledge friction)
    if ctx.affect == "frustrated":
        return None

    # Gate 3: Operational tasks → no style (diagnostics/repairs need clarity)
    if ctx.task_type in ["diagnostic", "repair"]:
        return None

    # === Cooldown Gates ===

    # Gate 4: Recent failure → cooldown window (don't gloat after errors)
    if ctx.recent_failure:
        # Check if we're still in cooldown window
        if hasattr(ctx, 'turns_since_failure'):
            if ctx.turns_since_failure < FAILURE_COOLDOWN_TURNS:
                return None
        else:
            # First turn after failure → start cooldown
            return None

    # Gate 5: Rate limiting (never style consecutive turns)
    if ctx.turn_idx - ctx.last_styled_turn < MIN_TURNS_BETWEEN_STYLE:
        return None

    # === Budget Gate ===

    # Gate 6: Token bucket (prevents overuse within session)
    if not ctx.style_budget.consume(1):
        return None

    # === Positive Selection ===

    # Playful + low stakes → allow one stylistic move
    if ctx.affect == "playful" and ctx.stakes == "low":
        # Update last styled turn (successful application)
        # This will be persisted to kloros_instance by caller
        return "backhanded_compliment"

    # Neutral + chat + low stakes → occasionally allow understated wit
    if ctx.affect == "neutral" and ctx.task_type == "chat" and ctx.stakes == "low":
        # More conservative: only 1 in 3 eligible turns
        if ctx.turn_idx % 3 == 0:
            return "understated_disaster"

    # Explanation requests → deadpan delivery (dry facts)
    if ctx.task_type == "explanation":
        # Deadpan is just pass-through, but signals intent
        return "deadpan"

    # Default: no styling
    return None


def get_policy_summary(ctx: Context) -> dict:
    """Get policy decision summary for debugging/telemetry.

    Args:
        ctx: Classified context

    Returns:
        Dict with gates and decisions
    """
    gates = {
        "high_stakes": ctx.stakes == "high",
        "frustrated": ctx.affect == "frustrated",
        "operational_task": ctx.task_type in ["diagnostic", "repair"],
        "recent_failure": ctx.recent_failure,
        "rate_limited": (ctx.turn_idx - ctx.last_styled_turn) < MIN_TURNS_BETWEEN_STYLE,
        "budget_exhausted": ctx.style_budget.tokens < 1,
    }

    # Determine if we reached positive selection
    reached_selection = not any(gates.values())

    return {
        "gates": gates,
        "reached_selection": reached_selection,
        "affect": ctx.affect,
        "task_type": ctx.task_type,
        "stakes": ctx.stakes,
        "turn_idx": ctx.turn_idx,
        "last_styled_turn": ctx.last_styled_turn,
        "budget_tokens": ctx.style_budget.tokens,
    }


__all__ = ["choose_technique", "get_policy_summary", "MIN_TURNS_BETWEEN_STYLE", "FAILURE_COOLDOWN_TURNS"]
