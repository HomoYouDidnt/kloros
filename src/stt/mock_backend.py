"""Mock STT backend for testing and development."""

from __future__ import annotations

from typing import Optional

import numpy as np

from .base import SttResult


class MockSttBackend:
    """Mock speech-to-text backend that returns fixed responses."""

    def __init__(self, transcript: str = "hello world", confidence: float = 0.92):
        """Initialize mock STT backend.

        Args:
            transcript: Fixed transcript to return
            confidence: Fixed confidence score to return
        """
        self.transcript = transcript
        self.confidence = confidence

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int,
        lang: Optional[str] = None
    ) -> SttResult:
        """Mock transcription that ignores audio and returns fixed response.

        Args:
            audio: Audio samples (ignored)
            sample_rate: Sample rate (ignored)
            lang: Language code (passed through)

        Returns:
            SttResult with fixed transcript and confidence
        """
        # Use provided language or default
        result_lang = lang or "en-US"

        return SttResult(
            transcript=self.transcript,
            confidence=self.confidence,
            lang=result_lang,
            raw={
                "mock": True,
                "audio_samples": len(audio),
                "sample_rate": sample_rate
            }
        )
