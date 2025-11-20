"""Audio system adapter for emitting heal events."""

from typing import Optional
from ..events import mk_event


def emit_beep_echo(heal_bus, beep_type: str):
    """Emit event when beep causes echo loop.

    Args:
        heal_bus: HealBus instance (or None if not initialized)
        beep_type: Type of beep that caused echo (e.g., "indicator", "error")
    """
    if not heal_bus:
        return

    event = mk_event(
        source="audio",
        kind="beep_echo",
        severity="warn",
        beep_type=beep_type
    )

    heal_bus.emit(event)
