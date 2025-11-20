"""Validator adapter for emitting heal events."""

from typing import Optional
from ..events import mk_event


def emit_low_context(heal_bus, tool_name: str, confidence: float):
    """Emit event when validator rejects tool due to low context match.

    Args:
        heal_bus: HealBus instance (or None if not initialized)
        tool_name: Name of rejected tool
        confidence: Confidence score that failed threshold
    """
    if not heal_bus:
        return

    event = mk_event(
        source="validator",
        kind="low_context_overlap",
        severity="warn",
        tool_name=tool_name,
        confidence=confidence
    )

    heal_bus.emit(event)
