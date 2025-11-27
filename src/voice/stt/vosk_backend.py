"""Vosk-based STT backend for KLoROS."""

from __future__ import annotations

import json
import os
from typing import Optional

import numpy as np

from .base import SttResult


class VoskSttBackend:
    """Vosk speech-to-text backend with lazy initialization."""

    def __init__(self, model_dir: Optional[str] = None, vosk_model=None):
        """Initialize Vosk STT backend.

        Args:
            model_dir: Path to Vosk model directory (if vosk_model not provided)
            vosk_model: Pre-loaded vosk.Model instance (to share between backends)

        Raises:
            RuntimeError: If vosk is unavailable or model cannot be loaded
        """
        # Lazy import vosk to avoid hard dependency
        try:
            import vosk
        except ImportError as e:
            raise RuntimeError("vosk library not available") from e

        self._vosk = vosk

        # Use pre-loaded model if provided (memory optimization)
        if vosk_model is not None:
            self._model = vosk_model
            self.model_dir = "<shared>"
            print("[vosk] Using shared VOSK model instance (memory optimized)")
            return

        # Otherwise, load model from directory
        # Determine model path
        if model_dir is None:
            model_dir = os.getenv("KLR_VOSK_MODEL_DIR") or os.path.expanduser("/home/kloros/models/vosk/model")

        if not model_dir:
            raise RuntimeError(
                "vosk model directory not specified (set KLR_VOSK_MODEL_DIR or pass model_dir)"
            )

        if not os.path.exists(model_dir):
            raise RuntimeError(f"vosk model directory not found: {model_dir}")

        # Initialize Vosk model
        try:
            self._model = vosk.Model(model_dir)
        except Exception as e:
            raise RuntimeError(f"failed to load vosk model from {model_dir}: {e}") from e

        self.model_dir = model_dir

    def transcribe(
        self, audio: np.ndarray, sample_rate: int, lang: Optional[str] = None
    ) -> SttResult:
        """Transcribe audio using Vosk.

        Args:
            audio: Audio samples as float32 mono array in range [-1, 1]
            sample_rate: Sample rate in Hz
            lang: Language code (ignored - model determines language)

        Returns:
            SttResult with transcript and confidence
        """
        # Convert float32 to PCM16 bytes for Vosk
        pcm16_audio = self._float32_to_pcm16(audio)

        # Create recognizer
        recognizer = self._vosk.KaldiRecognizer(self._model, sample_rate)

        # Feed audio data to recognizer
        recognizer.AcceptWaveform(pcm16_audio)

        # Get final result
        result_json = recognizer.FinalResult()
        result_data = json.loads(result_json)

        # Extract transcript and confidence
        transcript = result_data.get("text", "").strip()

        # Calculate average confidence from word-level confidences
        confidence = self._calculate_confidence(result_data)

        # Determine language (use provided lang or default)
        result_lang = lang or "en-US"

        return SttResult(
            transcript=transcript, confidence=confidence, lang=result_lang, raw=result_data
        )

    def _float32_to_pcm16(self, audio: np.ndarray) -> bytes:
        """Convert float32 audio to PCM16 bytes for Vosk.

        Args:
            audio: Audio samples as float32 array in range [-1, 1]

        Returns:
            PCM16 audio data as bytes
        """
        # Clip to valid range and convert to int16
        clipped = np.clip(audio, -1.0, 1.0)
        pcm16 = (clipped * 32767).astype(np.int16)
        return pcm16.tobytes()

    def _calculate_confidence(self, result_data: dict) -> float:
        """Calculate overall confidence from Vosk result.

        Args:
            result_data: Parsed JSON result from Vosk

        Returns:
            Average confidence score (0.0-1.0)
        """
        # Get word-level results if available
        word_results = result_data.get("result", [])

        if not word_results:
            # No word-level data, use overall confidence if available
            return result_data.get("confidence", 1.0)

        # Calculate average confidence from words
        confidences = []
        for word_result in word_results:
            if isinstance(word_result, dict) and "conf" in word_result:
                confidences.append(word_result["conf"])

        if confidences:
            return sum(confidences) / len(confidences)
        else:
            return 1.0  # Default confidence if no data available
