"""Reasoning interface and factory for KLoROS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Protocol


@dataclass
class ReasoningResult:
    """Result from reasoning/QA processing."""

    reply_text: str
    sources: List[str] = field(default_factory=list)
    meta: Optional[Dict] = None


class ReasoningBackend(Protocol):
    """Protocol for reasoning backends."""

    def reply(self, transcript: str) -> ReasoningResult:
        """Generate a response to the given transcript.

        Args:
            transcript: Input text to reason about

        Returns:
            ReasoningResult with reply text and optional sources
        """
        ...


BackendName = Literal["mock", "rag", "qa"]


def create_reasoning_backend(name: BackendName, **kwargs) -> ReasoningBackend:
    """Create a reasoning backend by name.

    Args:
        name: Backend name ("mock", "rag", or "qa")
        **kwargs: Backend-specific arguments

    Returns:
        Reasoning backend instance

    Raises:
        ValueError: If backend name is unknown
        RuntimeError: If backend cannot be initialized (e.g., missing dependencies)
    """
    if name == "mock":
        from .mock_backend import MockReasoningBackend

        return MockReasoningBackend(**kwargs)
    elif name == "rag":
        from .local_rag_backend import LocalRagBackend

        return LocalRagBackend(**kwargs)
    elif name == "qa":
        from .local_qa_backend import LocalQaBackend

        return LocalQaBackend(**kwargs)
    else:
        raise ValueError(f"Unknown reasoning backend: {name}")
