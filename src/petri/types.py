"""PETRI types and data contracts."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class ToolExecutionPlan:
    """Represents a planned tool execution to be safety-checked."""

    tool_name: str
    args: Dict[str, Any]
    context: Dict[str, Any] = field(default_factory=dict)

    # Risk metadata
    risk_score: float = 0.0
    risk_tags: List[str] = field(default_factory=list)

    # Execution metadata
    plan_id: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().timestamp()


@dataclass
class PetriProbeOutcome:
    """Result of a single safety probe."""

    name: str
    ok: bool
    risk_score: float  # 0.0 = safe, 1.0+ = risky
    notes: Optional[str] = None
    artifacts: Optional[Dict[str, Any]] = None


@dataclass
class PetriReport:
    """Complete safety assessment report for a tool execution."""

    plan_id: str
    tool_name: str
    safe: bool
    total_risk: float
    outcomes: List[PetriProbeOutcome]
    limits_hit: Dict[str, Any] = field(default_factory=dict)
    exec_stats: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().timestamp()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "plan_id": self.plan_id,
            "tool_name": self.tool_name,
            "safe": self.safe,
            "total_risk": self.total_risk,
            "outcomes": [
                {
                    "name": o.name,
                    "ok": o.ok,
                    "risk_score": o.risk_score,
                    "notes": o.notes,
                    "artifacts": o.artifacts
                }
                for o in self.outcomes
            ],
            "limits_hit": self.limits_hit,
            "exec_stats": self.exec_stats,
            "timestamp": self.timestamp
        }
