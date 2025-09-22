"""Mock reasoning backend for testing and development."""

from __future__ import annotations

from .base import ReasoningResult


class MockReasoningBackend:
    """Mock reasoning backend that returns deterministic responses."""

    def __init__(self, reply_text: str = "ok", sources: list = None):
        """Initialize mock reasoning backend.

        Args:
            reply_text: Fixed reply text to return
            sources: Fixed sources list to return (defaults to ["mock"])
        """
        self.reply_text = reply_text
        self.sources = sources if sources is not None else ["mock"]

    def reply(self, transcript: str) -> ReasoningResult:
        """Generate a mock response that ignores the transcript.

        Args:
            transcript: Input transcript (ignored)

        Returns:
            ReasoningResult with fixed reply text and sources
        """
        return ReasoningResult(
            reply_text=self.reply_text,
            sources=self.sources.copy(),  # Return a copy to avoid mutation
            meta={"mock": True, "input_length": len(transcript)},
        )
