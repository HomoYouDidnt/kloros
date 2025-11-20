"""
Tool registry with visibility masking support.

Provides routing sanity checks for masked vs public tools.
"""

from typing import Dict, Any


def visible_to(intent: str, ctx: dict, mf: dict) -> bool:
    """
    Check if a tool is visible for the given intent and context.

    Args:
        intent: User intent/query string
        ctx: Context dictionary (can include user, mode, etc.)
        mf: Tool manifest dictionary

    Returns:
        True if tool is visible, False if masked
    """
    vis = mf.get("deployment", {}).get("visibility", "public")

    if vis == "masked":
        rules = mf.get("deployment", {}).get("mask_rules", [])
        if not rules:
            return False  # Masked with no rules = hidden
        
        # Check if any rule matches the intent (rule is substring of intent)
        return any(r in intent for r in rules)

    return True  # Public tools are always visible
