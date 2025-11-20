"""Macro expander - converts macros into executable steps."""
from typing import Dict, Any, List, Optional
from .types import Macro


def expand_macro(macro: Macro, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Expand a macro into concrete executable steps.

    Args:
        macro: Macro to expand
        params: Parameters for macro execution

    Returns:
        List of executable steps with resolved arguments
    """
    expanded_steps = []

    for step in macro.steps:
        # Create a copy of the step
        expanded_step = {
            "tool": step["tool"],
            "args": {}
        }

        # Resolve arguments (substitute parameters)
        for arg_key, arg_value in step.get("args", {}).items():
            if isinstance(arg_value, str) and arg_value.startswith("{") and arg_value.endswith("}"):
                # Parameter substitution
                param_name = arg_value[1:-1]  # Remove { }
                if param_name in params:
                    expanded_step["args"][arg_key] = params[param_name]
                else:
                    # Keep placeholder if parameter not provided
                    expanded_step["args"][arg_key] = arg_value
            else:
                # Copy value as-is
                expanded_step["args"][arg_key] = arg_value

        expanded_steps.append(expanded_step)

    return expanded_steps


def validate_macro_preconditions(macro: Macro, context: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Check if macro preconditions are satisfied.

    Args:
        macro: Macro to check
        context: Current context (state, task info, etc.)

    Returns:
        Tuple of (satisfied: bool, reason: Optional[str])
    """
    preconds = macro.preconds

    # Check domain match
    if "domain" in preconds:
        required_domain = preconds["domain"]
        context_domain = context.get("domain", "")
        if required_domain != context_domain:
            return False, f"Domain mismatch: required={required_domain}, got={context_domain}"

    # Check query type
    if "query_type" in preconds:
        required_type = preconds["query_type"]
        context_type = context.get("query_type", "")
        if required_type != context_type:
            return False, f"Query type mismatch: required={required_type}, got={context_type}"

    # Check intent
    if "intent" in preconds:
        required_intent = preconds["intent"]
        context_intent = context.get("intent", "")
        if required_intent != context_intent:
            return False, f"Intent mismatch: required={required_intent}, got={context_intent}"

    # Check minimum query length if specified
    if "min_query_length" in preconds:
        min_length = preconds["min_query_length"]
        query = context.get("query", "")
        if len(query) < min_length:
            return False, f"Query too short: min={min_length}, got={len(query)}"

    # All preconditions satisfied
    return True, None


def estimate_macro_cost(macro: Macro, params: Dict[str, Any]) -> Dict[str, float]:
    """Estimate execution cost for a macro.

    Args:
        macro: Macro to estimate
        params: Execution parameters

    Returns:
        Cost estimate dict with latency_ms, tool_calls, tokens
    """
    # Use macro budgets as cost estimate
    # In a more sophisticated version, this would use historical data
    return {
        "latency_ms": macro.budgets.get("latency_ms", 4000),
        "tool_calls": macro.budgets.get("tool_calls", len(macro.steps)),
        "tokens": macro.budgets.get("tokens", 3500)
    }
