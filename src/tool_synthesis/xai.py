"""Explainable AI (XAI) tracing for tool routing and execution.

Provides model-agnostic attribution and decision logging without chain-of-thought.
All explanations are derived from observable signals: scores, rules, events, taxonomy.
"""

from __future__ import annotations
from typing import List, Dict, Callable, Any, Optional
from .logging import log


def token_importance(
    text: str,
    scorer: Callable[[str], float],
    max_tokens: int = 30
) -> List[Dict[str, Any]]:
    """
    Model-agnostic LIME-style token attribution.

    For each token, measures importance by removing it and observing score drop.
    This is post-hoc perturbation analysis, not model internals.

    Args:
        text: Input text to analyze
        scorer: Function that scores text → float (0..1), should be cached/fast
        max_tokens: Maximum tokens to analyze (performance limit)

    Returns:
        List of {"token": str, "weight": float} sorted by importance.
        Weights sum to 1.0 for UI normalization.

    Example:
        >>> scorer = lambda t: 0.8 if "error" in t else 0.3
        >>> token_importance("check error logs", scorer)
        [{"token": "error", "weight": 0.625}, {"token": "logs", "weight": 0.25}, ...]
    """
    toks = text.split()
    toks = toks[:max_tokens]  # Performance bound

    if not toks:
        return []

    base_score = scorer(" ".join(toks))
    importances = []

    for i, token in enumerate(toks):
        # Remove this token and rescore
        perturbed = " ".join(toks[:i] + toks[i+1:])
        perturbed_score = scorer(perturbed) if perturbed else 0.0

        # Importance = how much score drops when token removed
        importance = max(0.0, base_score - perturbed_score)
        importances.append({"token": token, "weight": importance})

    # Normalize to sum = 1.0 for UI display
    total_weight = sum(x["weight"] for x in importances) or 1.0
    for item in importances:
        item["weight"] = round(item["weight"] / total_weight, 4)

    return sorted(importances, key=lambda z: z["weight"], reverse=True)


def log_routing_trace(
    intent: str,
    candidates: List[Dict[str, Any]],
    input_text: str,
    scorer: Callable[[str], float],
    decisions: Optional[List[Dict[str, Any]]] = None
) -> None:
    """
    Log routing phase XAI trace.

    Captures:
    - All candidate tools with scores and visibility
    - Token attribution (which words influenced the decision)
    - Decision steps (masking, preconditions, final selection)

    Args:
        intent: Detected user intent
        candidates: List of candidate tools with metadata:
            [{"tool": str, "score": float, "visible": bool, "mask_matched": bool, ...}]
        input_text: Original user input
        scorer: Scoring function for attribution
        decisions: Decision steps list, e.g.:
            [{"step": "masking", "why": "...", "result": "..."}]
    """
    # Compute token attribution (LIME-style)
    attribution = token_importance(input_text, scorer, max_tokens=30)

    # Find selected tool (highest score among visible)
    visible_candidates = [c for c in candidates if c.get("visible", True)]
    selected = max(visible_candidates, key=lambda c: c.get("score", 0.0), default=None)

    log(
        "xai.trace",
        phase="routing",
        intent=intent,
        tool_selected=selected.get("tool") if selected else None,
        candidates=candidates,
        attribution=attribution[:10],  # Top 10 most important tokens
        decisions=decisions or [],
        ok=True
    )


def log_execution_trace(
    intent: str,
    tool_selected: str,
    steps: List[Dict[str, Any]],
    params: Dict[str, Any],
    outcome: str = "success",
    error: Optional[str] = None
) -> None:
    """
    Log execution phase XAI trace.

    Captures:
    - Permission checks
    - Retry/fallback steps
    - Error taxonomy mapping
    - SLO gate decisions
    - Outcome summary

    Args:
        intent: User intent being executed
        tool_selected: Tool name@version
        steps: Execution steps, e.g.:
            [{"step": "permissions.network", "why": "...", "result": "ok"}]
        params: Sanitized tool parameters (secrets redacted)
        outcome: "success" | "failure" | "fallback"
        error: Error message if outcome is failure
    """
    log(
        "xai.trace",
        phase="execution",
        intent=intent,
        tool_selected=tool_selected,
        execution=steps,
        sanitized_params=params,
        outcome=outcome,
        error=error,
        ok=(outcome == "success")
    )


def sanitize_params(params: Any) -> Dict[str, Any]:
    """
    Redact secrets from parameters for XAI logging.

    Uses existing SECRET_PATTERNS from logging module.

    Args:
        params: Raw parameters (dict, dataclass, or dict-like)

    Returns:
        Sanitized dict with secrets replaced by "****"
    """
    import re
    from .logging import redact_secrets_str

    # Convert to dict
    if hasattr(params, "dict"):
        d = params.dict()
    elif hasattr(params, "__dict__"):
        d = params.__dict__.copy()
    else:
        d = dict(params) if params else {}

    # Redact keys that look like secrets
    secret_key_pattern = re.compile(r"(api[_-]?key|token|secret|password|auth)", re.I)

    sanitized = {}
    for k, v in d.items():
        if secret_key_pattern.search(k):
            sanitized[k] = "****"
        elif isinstance(v, str):
            # Redact string values using existing patterns
            sanitized[k] = redact_secrets_str(v)
        else:
            sanitized[k] = v

    return sanitized


def build_routing_decisions(
    candidates: List[Dict[str, Any]],
    masking_rule: Optional[str] = None,
    selected_tool: Optional[str] = None
) -> List[Dict[str, str]]:
    """
    Build decision steps for routing phase.

    Captures masking rules, precondition checks, and final selection logic.

    Args:
        candidates: List of candidate tools with visibility info
        masking_rule: Optional rule that determined visibility
        selected_tool: Tool that was ultimately selected

    Returns:
        List of decision step dicts for logging
    """
    decisions = []

    # Masking summary (not individual entries for each tool)
    if masking_rule and candidates:
        visible_count = sum(1 for c in candidates if c.get("visible", True))
        hidden_count = len(candidates) - visible_count

        # Single summary instead of 50+ identical entries
        decisions.append({
            "step": "masking",
            "why": f"Applied visibility rules: {masking_rule}",
            "result": f"{visible_count} visible, {hidden_count} filtered from {len(candidates)} total tools"
        })

    # Precondition checks (only if any actually exist)
    precondition_checks = [c for c in candidates if c.get("preconditions")]
    if precondition_checks:
        passed = sum(1 for c in precondition_checks if c.get("preconditions_met", True))
        decisions.append({
            "step": "preconditions",
            "why": "Checked runtime preconditions for applicable tools",
            "result": f"{passed}/{len(precondition_checks)} tools ready"
        })

    # Final selection
    if selected_tool:
        visible_candidates = [c for c in candidates if c.get("visible", True)]
        if visible_candidates:
            top_candidate = max(visible_candidates, key=lambda x: x.get("score", 0.0))
            decisions.append({
                "step": "select",
                "why": f"Highest semantic similarity score ({top_candidate.get('score', 0.0):.3f}) among visible tools",
                "result": selected_tool
            })

    return decisions


def build_execution_steps(
    permission_checks: Optional[List[Dict[str, Any]]] = None,
    retries: Optional[List[Dict[str, Any]]] = None,
    fallbacks: Optional[List[Dict[str, Any]]] = None,
    slo_checks: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, str]]:
    """
    Build execution steps for XAI trace.

    Args:
        permission_checks: Permission check results
        retries: Retry attempts
        fallbacks: Fallback invocations
        slo_checks: SLO gate checks

    Returns:
        Ordered list of execution steps
    """
    steps = []

    # Permission checks
    if permission_checks:
        for check in permission_checks:
            steps.append({
                "step": f"permissions.{check.get('type', 'unknown')}",
                "why": check.get("rule", ""),
                "result": check.get("result", "ok")
            })

    # Retry attempts
    if retries:
        for retry in retries:
            steps.append({
                "step": "retry",
                "why": retry.get("reason", ""),
                "result": f"attempt={retry.get('attempt', 1)}, backoff={retry.get('backoff_ms', 0)}ms"
            })

    # Fallback invocations
    if fallbacks:
        for fallback in fallbacks:
            steps.append({
                "step": "fallback",
                "why": fallback.get("reason", ""),
                "result": fallback.get("fallback_tool", "unknown")
            })

    # SLO checks
    if slo_checks:
        for check in slo_checks:
            steps.append({
                "step": "slo_gate",
                "why": f"threshold={check.get('threshold', 0.0)}",
                "result": f"score={check.get('score', 0.0)}, {check.get('result', 'ok')}"
            })

    return steps
