"""
Base scanner protocol for capability discovery.

Defines data structures and abstract interface for all capability scanners.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class CapabilityGap:
    """Represents a missing capability."""
    type: str              # 'external_tool', 'skill', 'pattern'
    name: str              # 'ripgrep', 'database-migrations', 'circuit-breaker'
    category: str          # 'pypi_package', 'claude_skill', 'arch_pattern'
    reason: str            # Why this capability is needed
    alignment_score: float # 0.0-1.0
    install_cost: float    # 0.0-1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScannerMetadata:
    """Scanner identification and scheduling info."""
    name: str
    domain: str            # 'external_tools', 'skills', 'patterns'
    alignment_baseline: float  # Base alignment for gaps from this scanner
    scan_cost: float       # Resource cost (0.0-1.0)
    schedule_weight: float # How often to run (1.0=every cycle, 0.1=rarely)


class CapabilityScanner(ABC):
    """Base class for all capability scanners."""

    @abstractmethod
    def scan(self) -> List[CapabilityGap]:
        """Discover missing capabilities. Returns list of gaps."""
        pass

    @abstractmethod
    def get_metadata(self) -> ScannerMetadata:
        """Return scanner info."""
        pass

    def should_run(self, last_run: float, idle_budget: float) -> bool:
        """Default scheduling logic - can be overridden."""
        import time
        metadata = self.get_metadata()
        time_since_last = time.time() - last_run

        # Run based on schedule_weight and available budget
        min_interval = 3600 * (1.0 / metadata.schedule_weight)  # Hours to seconds
        return time_since_last >= min_interval and metadata.scan_cost <= idle_budget
