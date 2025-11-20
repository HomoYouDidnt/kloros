"""D-REAM Chaos Lab - Systematic failure injection and self-healing testing.

Injects controlled failures, observes healing responses, grades outcomes,
and evolves curriculum for continuous improvement.
"""

from .spec import FailureSpec, load_specs
from .orchestrator import ChaosOrchestrator
from .observers import TraceObserver
from .grading import grade_outcome
from .sandbox import Sandbox

__all__ = [
    "FailureSpec",
    "load_specs",
    "ChaosOrchestrator",
    "TraceObserver",
    "grade_outcome",
    "Sandbox",
]
