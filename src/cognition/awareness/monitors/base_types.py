"""
Base types for curiosity monitors.

These dataclasses and enums are shared across all monitors.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional


class QuestionStatus(Enum):
    """Status of a curiosity question."""
    READY = "ready"
    IN_PROGRESS = "in_progress"
    ANSWERED = "answered"
    BLOCKED = "blocked"


class ActionClass(Enum):
    """Type of action suggested by question."""
    EXPLAIN_AND_SOFT_FALLBACK = "explain_and_soft_fallback"
    INVESTIGATE = "investigate"
    PROPOSE_FIX = "propose_fix"
    REQUEST_USER_ACTION = "request_user_action"
    FIND_SUBSTITUTE = "find_substitute"
    EXPERIMENT = "experiment"
    EXPLORE = "explore"


@dataclass
class CuriosityQuestion:
    """A single curiosity question generated from capability analysis."""
    id: str
    hypothesis: str
    question: str
    evidence: List[str] = field(default_factory=list)
    evidence_hash: Optional[str] = None
    action_class: ActionClass = ActionClass.EXPLAIN_AND_SOFT_FALLBACK
    autonomy: int = 3
    value_estimate: float = 0.5
    cost: float = 0.2
    status: QuestionStatus = QuestionStatus.READY
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    capability_key: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "hypothesis": self.hypothesis,
            "question": self.question,
            "evidence": self.evidence,
            "evidence_hash": self.evidence_hash,
            "action_class": self.action_class.value,
            "autonomy": self.autonomy,
            "value_estimate": self.value_estimate,
            "cost": self.cost,
            "status": self.status.value,
            "created_at": self.created_at,
            "capability_key": self.capability_key,
            "metadata": self.metadata
        }


@dataclass
class CuriosityFeed:
    """Collection of curiosity questions."""
    questions: List[CuriosityQuestion] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "questions": [q.to_dict() for q in self.questions],
            "generated_at": self.generated_at,
            "count": len(self.questions)
        }


@dataclass
class PerformanceTrend:
    """Performance trend data for a D-REAM experiment."""
    experiment: str
    recent_summaries: List[Dict[str, Any]] = field(default_factory=list)
    pass_rate_trend: List[float] = field(default_factory=list)
    latency_trend: List[float] = field(default_factory=list)
    accuracy_trend: List[float] = field(default_factory=list)

    def detect_degradation(self) -> Optional[str]:
        """Detect performance degradation patterns."""
        if len(self.pass_rate_trend) < 2:
            return None

        if len(self.pass_rate_trend) >= 3:
            recent_avg = sum(self.pass_rate_trend[-3:]) / 3
            if recent_avg < 0.7 and self.pass_rate_trend[0] > 0.85:
                drop_pct = (self.pass_rate_trend[0] - recent_avg) * 100
                return f"pass_rate_drop:{drop_pct:.1f}%"

        if len(self.latency_trend) >= 3:
            recent_avg = sum(self.latency_trend[-3:]) / 3
            baseline_avg = sum(self.latency_trend[:3]) / len(self.latency_trend[:3])
            if recent_avg > baseline_avg * 1.5:
                increase_pct = ((recent_avg - baseline_avg) / baseline_avg) * 100
                return f"latency_increase:{increase_pct:.1f}%"

        if len(self.accuracy_trend) >= 3:
            recent_avg = sum(self.accuracy_trend[-3:]) / 3
            if recent_avg < 0.8 and self.accuracy_trend[0] > 0.95:
                drop_pct = (self.accuracy_trend[0] - recent_avg) * 100
                return f"accuracy_drop:{drop_pct:.1f}%"

        return None


@dataclass
class SystemResourceSnapshot:
    """Snapshot of system resource usage."""
    timestamp: datetime
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    swap_percent: float
    swap_used_gb: float
    cpu_percent: float
    load_avg_1min: float
    load_avg_5min: float
    disk_usage_percent: float
    gpu_utilization: Optional[float] = None
    gpu_memory_percent: Optional[float] = None
