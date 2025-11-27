"""KLoROS self-healing subsystem.

Event-driven healing: detect → triage → fix → validate → rollback → learn.
"""

from .events import HealEvent, mk_event
from .heal_bus import HealBus
from .policy import Guardrails
from .health import HealthProbes
from .playbook_dsl import load_playbooks
from .executor import HealExecutor, HealingExecutor
from .outcomes import OutcomesLogger
from .triage import TriageEngine
from .system_monitor import SystemHealthMonitor

__all__ = [
    "HealEvent",
    "mk_event",
    "HealBus",
    "Guardrails",
    "HealthProbes",
    "load_playbooks",
    "HealExecutor",
    "HealingExecutor",  # Alias for HealExecutor
    "OutcomesLogger",
    "TriageEngine",
    "SystemHealthMonitor",  # DEPRECATED: Use InteroceptionDaemon instead
]
