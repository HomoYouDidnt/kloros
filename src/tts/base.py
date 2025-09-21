"""TTS interface and factory for KLoROS."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Protocol


@dataclass
class TtsResult:
    """Result from text-to-speech synthesis."""
    audio_path: str
    duration_s: float
    sample_rate: int
    voice: Optional[str] = None


class TtsBackend(Protocol):
    """Protocol for text-to-speech backends."""

    def synthesize(
        self,
        text: str,
        sample_rate: int = 22050,
        voice: Optional[str] = None,
        out_dir: Optional[str] = None,
        basename: Optional[str] = None,
    ) -> TtsResult:
        """Synthesize text to speech.

        Args:
            text: Text to synthesize
            sample_rate: Target sample rate in Hz
            voice: Voice/model to use (optional)
            out_dir: Output directory (optional)
            basename: Output filename base (optional)

        Returns:
            TtsResult with audio file path and metadata
        """
        ...


BackendName = Literal["mock", "piper"]


def create_tts_backend(
    name: BackendName,
    **kwargs
) -> TtsBackend:
    """Create a TTS backend by name.

    Args:
        name: Backend name ("mock" or "piper")
        **kwargs: Backend-specific arguments

    Returns:
        TTS backend instance

    Raises:
        ValueError: If backend name is unknown
        RuntimeError: If backend cannot be initialized (e.g., missing dependencies)
    """
    if name == "mock":
        from .mock_backend import MockTtsBackend
        return MockTtsBackend(**kwargs)
    elif name == "piper":
        from .piper_backend import PiperTtsBackend
        return PiperTtsBackend(**kwargs)
    else:
        raise ValueError(f"Unknown TTS backend: {name}")
