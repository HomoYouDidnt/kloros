"""Adapters for emitting heal events from KLoROS components."""

from .validator import emit_low_context
from .kloros_rag import emit_synth_timeout
from .audio import emit_beep_echo

__all__ = [
    "emit_low_context",
    "emit_synth_timeout",
    "emit_beep_echo",
]
