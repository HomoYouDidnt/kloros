"""STT interface and factory for KLoROS."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal, Optional, Protocol

import numpy as np


@dataclass
class SttResult:
    """Result from speech-to-text transcription."""

    transcript: str
    confidence: float
    lang: str
    raw: Optional[Dict] = None


class SttBackend(Protocol):
    """Protocol for speech-to-text backends."""

    def transcribe(
        self,
        audio: np.ndarray,  # mono float32, range [-1, 1]
        sample_rate: int,
        lang: Optional[str] = None,
    ) -> SttResult:
        """Transcribe audio to text.

        Args:
            audio: Audio samples as float32 mono array
            sample_rate: Sample rate in Hz
            lang: Language code (optional)

        Returns:
            SttResult with transcript and metadata
        """
        ...


BackendName = Literal["mock", "vosk", "whisper", "hybrid"]


def create_stt_backend(name: BackendName, **kwargs) -> SttBackend:
    """Create an STT backend by name.

    Args:
        name: Backend name ("mock", "vosk", "whisper", or "hybrid")
        **kwargs: Backend-specific arguments

    Returns:
        STT backend instance

    Raises:
        ValueError: If backend name is unknown
        RuntimeError: If backend cannot be initialized (e.g., missing model)
    """
    if name == "mock":
        from .mock_backend import MockSttBackend

        return MockSttBackend(**kwargs)
    elif name == "vosk":
        from .vosk_backend import VoskSttBackend

        return VoskSttBackend(**kwargs)
    elif name == "whisper":
        from .faster_whisper_backend import FasterWhisperSttBackend

        return FasterWhisperSttBackend(**kwargs)
    elif name == "hybrid":
        from .hybrid_backend import HybridSttBackend

        return HybridSttBackend(**kwargs)
    else:
        raise ValueError(f"Unknown STT backend: {name}")
