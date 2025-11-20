"""Base interface for bug injection specifications."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
import ast


@dataclass
class InjectionResult:
    """Result of bug injection."""
    mutated_source: str
    bug_id: str
    description: str
    difficulty: str  # "easy", "medium", "hard"


class BugSpec(ABC):
    """A bug you can inject into Python code."""
    bug_id: str
    description: str
    difficulty: str = "medium"

    @abstractmethod
    def applies(self, source: str) -> bool:
        """Return True if this bug can be injected into the given source."""
        ...

    @abstractmethod
    def inject(self, source: str) -> InjectionResult:
        """Return mutated source + metadata. Must produce a deterministic change."""
        ...
