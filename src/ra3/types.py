"""RA³ type definitions."""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime


@dataclass
class Macro:
    """Multi-step action abstraction."""

    id: str
    name: str
    domain: str  # e.g., "voice", "rag", "code", "general"

    # Preconditions for macro applicability
    preconds: Dict[str, Any] = field(default_factory=dict)

    # Macro parameters (tunables)
    params: Dict[str, Any] = field(default_factory=dict)

    # Steps in the macro (list of tool calls)
    steps: List[Dict[str, Any]] = field(default_factory=list)

    # Verifier configuration
    verifier: Dict[str, Any] = field(default_factory=dict)

    # Resource budgets for the entire macro
    budgets: Dict[str, Any] = field(default_factory=lambda: {
        "latency_ms": 4000,
        "tool_calls": 4,
        "tokens": 3500
    })

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=lambda: {
        "created_at": datetime.now().timestamp(),
        "created_by": "seed",
        "version": "1.0",
        "tags": []
    })

    # Performance statistics
    stats: Dict[str, Any] = field(default_factory=lambda: {
        "uses": 0,
        "successes": 0,
        "failures": 0,
        "avg_latency_ms": 0.0,
        "avg_tokens": 0.0
    })

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.stats.get("uses", 0)
        if total == 0:
            return 0.0
        return self.stats.get("successes", 0) / total


@dataclass
class MacroLibrary:
    """Collection of macros."""

    id: str
    macros: List[Macro] = field(default_factory=list)
    lineage: Dict[str, Any] = field(default_factory=lambda: {
        "parent_id": None,
        "created_at": datetime.now().timestamp(),
        "version": "1.0"
    })

    def get_macro(self, macro_id: str) -> Optional[Macro]:
        """Get macro by ID."""
        for macro in self.macros:
            if macro.id == macro_id:
                return macro
        return None

    def get_macros_for_domain(self, domain: str) -> List[Macro]:
        """Get all macros for a specific domain."""
        return [m for m in self.macros if m.domain == domain]


@dataclass
class MacroSelection:
    """Result of macro selection."""

    macro_id: Optional[str]
    macro: Optional[Macro]
    params: Dict[str, Any]
    confidence: float
    reason: str


@dataclass
class MacroTrace:
    """Trace of macro execution for learning."""

    macro_id: str
    params: Dict[str, Any]
    outcome: Dict[str, Any]  # success, score, artifacts
    cost: Dict[str, float]   # latency_ms, tool_calls, tokens
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().timestamp()
