"""Smart TTS router with text analysis and warm pool management."""

from __future__ import annotations

import os
from typing import Optional, Literal

from .base import TtsBackend, TtsResult
from .text_analyzer import TextComplexityAnalyzer, TextAnalysis


BackendChoice = Literal["supertonic", "piper", "auto"]


class SmartTTSRouter:
    """Intelligent TTS router that selects backend based on text complexity.

    Keeps both Supertonic and Piper warm for instant switching:
    - Supertonic: Used when text needs normalization (numbers, dates, etc.)
    - Piper: Used for clean prose (faster for simple text)

    Provides graceful fallback if primary backend fails.
    """

    def __init__(
        self,
        piper_voice: Optional[str] = None,
        supertonic_voice: Optional[str] = None,
        out_dir: Optional[str] = None,
        prewarm: bool = True,
    ):
        """Initialize smart router.

        Args:
            piper_voice: Path to Piper voice model
            supertonic_voice: Path to Supertonic voice style JSON
            out_dir: Output directory for audio files
            prewarm: Whether to pre-load both backends on init
        """
        self._analyzer = TextComplexityAnalyzer()
        self._piper: Optional[TtsBackend] = None
        self._supertonic: Optional[TtsBackend] = None
        self._out_dir = out_dir or os.path.expanduser("~/.kloros/out")

        self._piper_voice = piper_voice or os.getenv(
            "KLR_PIPER_VOICE",
            os.path.expanduser("~/KLoROS/models/piper/glados_piper_medium.onnx")
        )
        self._supertonic_voice = supertonic_voice or os.getenv(
            "KLR_SUPERTONIC_VOICE",
            os.path.expanduser("~/KLoROS/models/supertonic/assets/voice_styles/M1.json")
        )

        if prewarm:
            self.prewarm_all()

    def _get_piper(self) -> TtsBackend:
        """Get or create Piper backend."""
        if self._piper is None:
            from .piper_backend import PiperTtsBackend
            self._piper = PiperTtsBackend(
                voice=self._piper_voice,
                out_dir=self._out_dir,
            )
        return self._piper

    def _get_supertonic(self) -> TtsBackend:
        """Get or create Supertonic backend."""
        if self._supertonic is None:
            from .supertonic_backend import SupertonicTtsBackend
            self._supertonic = SupertonicTtsBackend(
                voice_style=self._supertonic_voice,
                out_dir=self._out_dir,
            )
        return self._supertonic

    def prewarm_all(self):
        """Pre-load both backends for instant switching."""
        try:
            backend = self._get_supertonic()
            if hasattr(backend, "prewarm"):
                backend.prewarm()
        except Exception as e:
            print(f"[tts] Supertonic prewarm failed: {e}")

    def analyze(self, text: str) -> TextAnalysis:
        """Analyze text complexity.

        Args:
            text: Text to analyze

        Returns:
            TextAnalysis with complexity details
        """
        return self._analyzer.analyze(text)

    def pick_backend(self, text: str, force: Optional[BackendChoice] = None) -> tuple[TtsBackend, str]:
        """Select best backend for text.

        Args:
            text: Text to synthesize
            force: Force specific backend ("supertonic", "piper", or "auto")

        Returns:
            Tuple of (backend_instance, backend_name)
        """
        if force == "supertonic":
            return self._get_supertonic(), "supertonic"
        elif force == "piper":
            return self._get_piper(), "piper"

        analysis = self._analyzer.analyze(text)

        if analysis.needs_normalization:
            return self._get_supertonic(), "supertonic"
        else:
            return self._get_piper(), "piper"

    def synthesize(
        self,
        text: str,
        force_backend: Optional[BackendChoice] = None,
        sample_rate: int = 22050,
        voice: Optional[str] = None,
        basename: Optional[str] = None,
    ) -> TtsResult:
        """Synthesize text using the best backend.

        Args:
            text: Text to synthesize
            force_backend: Force specific backend or "auto"
            sample_rate: Target sample rate
            voice: Voice override (backend-specific)
            basename: Output filename base

        Returns:
            TtsResult with audio path and metadata
        """
        backend, backend_name = self.pick_backend(text, force_backend)

        try:
            result = backend.synthesize(
                text=text,
                sample_rate=sample_rate,
                voice=voice,
                out_dir=self._out_dir,
                basename=basename,
            )
            return result

        except Exception as primary_error:
            fallback_name = "piper" if backend_name == "supertonic" else "supertonic"

            try:
                fallback = self._get_piper() if fallback_name == "piper" else self._get_supertonic()
                result = fallback.synthesize(
                    text=text,
                    sample_rate=sample_rate,
                    voice=voice,
                    out_dir=self._out_dir,
                    basename=basename,
                )
                return result

            except Exception as fallback_error:
                raise RuntimeError(
                    f"Both TTS backends failed. Primary ({backend_name}): {primary_error}, "
                    f"Fallback ({fallback_name}): {fallback_error}"
                ) from primary_error

    def get_status(self) -> dict:
        """Get status of both backends.

        Returns:
            Dict with backend availability and warm status
        """
        status = {
            "piper": {
                "available": self._piper is not None,
                "warm": self._piper is not None,
            },
            "supertonic": {
                "available": self._supertonic is not None,
                "warm": (
                    self._supertonic is not None
                    and hasattr(self._supertonic, "is_warm")
                    and self._supertonic.is_warm()
                ),
            },
        }
        return status
