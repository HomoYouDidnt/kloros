"""Data types for ACE bullets and playbooks."""
from dataclasses import dataclass, field
from typing import Dict, Any, List
import time


@dataclass
class Bullet:
    """A context hint/rule learned from experience."""
    id: str
    text: str  # The actual hint text
    tags: List[str]  # Tags for categorization
    domain: str  # Domain this bullet applies to (e.g., "voice", "file_ops")
    metadata: Dict[str, Any] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=lambda: {
        "uses": 0,
        "wins": 0,
        "created_at": time.time(),
        "last_used": None
    })

    @property
    def win_rate(self) -> float:
        """Calculate win rate."""
        if self.stats["uses"] == 0:
            return 0.0
        return self.stats["wins"] / self.stats["uses"]


@dataclass
class Delta:
    """Changes to apply to a playbook."""
    adds: List[Bullet] = field(default_factory=list)
    updates: List[Bullet] = field(default_factory=list)
    removes: List[str] = field(default_factory=list)


@dataclass
class Evidence:
    """Evidence supporting a bullet."""
    episode_id: str
    signals: Dict[str, Any]  # Success metrics from episode
    rationale: str
    confidence: float = 0.8


@dataclass
class Playbook:
    """Collection of bullets for a domain."""
    id: str
    bullets: List[Bullet]
    lineage: Dict[str, Any] = field(default_factory=dict)
