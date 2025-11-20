"""RA³ - Reasoning as Action Abstractions.

Elevates frequently successful multi-step tool chains into abstract actions (macros)
that reduce latency, improve stability, and simplify safety gating.
"""

from .types import Macro, MacroLibrary, MacroTrace, MacroSelection
from .library import get_default_library, create_macro
from .policy import MacroPolicy
from .expander import expand_macro
from .telemetry import track_macro_execution, get_macro_stats

__all__ = [
    "Macro",
    "MacroLibrary",
    "MacroTrace",
    "MacroSelection",
    "get_default_library",
    "create_macro",
    "MacroPolicy",
    "expand_macro",
    "track_macro_execution",
    "get_macro_stats",
]
