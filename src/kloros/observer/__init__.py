"""
KLoROS Observer - Streaming event collection and intent generation.

The Observer is the reactive, continuous component that:
- Watches logs, files, metrics in real-time
- Generates intents and suggestions based on rules
- Posts them to ~/.kloros/intents/ for orchestrator consumption

The Orchestrator remains the only component that executes actions.
This maintains safety: Observer proposes, Orchestrator disposes.
"""

__version__ = "0.1.0"

from .sources import Event, JournaldSource, InotifySource, MetricsSource
from .rules import RuleEngine, Intent
from .emit import IntentEmitter
# NOTE: Don't import Observer from run.py to avoid RuntimeWarning when
# running as `python -m src.kloros.observer.run`

__all__ = [
    "Event",
    "JournaldSource",
    "InotifySource",
    "MetricsSource",
    "RuleEngine",
    "Intent",
    "IntentEmitter",
]
