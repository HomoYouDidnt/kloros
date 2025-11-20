"""OpenAI Whisper-based STT backend for KLoROS (more compatible than faster-whisper)."""

from __future__ import annotations

import os
import warnings
from typing import Optional, Union

import numpy as np

from .base import SttResult


class WhisperSttBackend:
    """OpenAI Whisper speech-to-text backend with GPU management."""

    def __init__(
        self,
        model_size: str = "small",
        device: str = "auto",
        compute_type: str = "int8_float16",  # Ignored for openai-whisper
        model_dir: Optional[str] = None,
        device_index: Union[int, list] = 0,
    ):
        """Initialize OpenAI Whisper STT backend.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large-v2, large-v3)
            device: Device to run on ("auto", "cuda", "cpu")
            compute_type: Ignored (for API compatibility with faster-whisper)
            model_dir: Directory to store/load models from
            device_index: GPU device index to use

        Raises:
            RuntimeError: If whisper is unavailable or model cannot be loaded
        """
        # Lazy import whisper to avoid hard dependency
        try:
            import whisper
        except ImportError as e:
            raise RuntimeError("openai-whisper library not available. Install with: pip install openai-whisper") from e

        # Auto-detect device if needed
        if device == "auto":
            device = self._auto_detect_device()

        self.device = device
        self.device_index = device_index if isinstance(device_index, int) else 0
        self.model_dir = model_dir or None

        # Set model download root if specified
        if self.model_dir:
            os.environ["WHISPER_CACHE_DIR"] = self.model_dir

        # Set CUDA device if using GPU
        if device == "cuda" and self.device_index > 0:
            os.environ["CUDA_VISIBLE_DEVICES"] = str(self.device_index)

        # Initialize model with error handling
        try:
            self._model = whisper.load_model(model_size, device=device)
            print(f"[openai-whisper] Loaded {model_size} model on {device}")
        except Exception as e:
            # Fallback to CPU if GPU fails
            if device != "cpu":
                warnings.warn(f"GPU initialization failed: {e}. Falling back to CPU.")
                try:
                    self._model = whisper.load_model(model_size, device="cpu")
                    device = "cpu"
                    print(f"[openai-whisper] Loaded {model_size} model on CPU (fallback)")
                except Exception as cpu_e:
                    raise RuntimeError(
                        f"Failed to load Whisper model on CPU: {cpu_e}"
                    ) from cpu_e
            else:
                raise RuntimeError(f"Failed to load Whisper model: {e}") from e

        self.model_size = model_size
        self.whisper = whisper

    def transcribe(
        self, audio: np.ndarray, sample_rate: int, lang: Optional[str] = None
    ) -> SttResult:
        """Transcribe audio using OpenAI Whisper.

        Args:
            audio: Audio samples as float32 mono array in range [-1, 1]
            sample_rate: Sample rate in Hz
            lang: Language code (e.g., "en", "es", "fr")

        Returns:
            SttResult with transcript and confidence
        """
        # Ensure audio is in correct format
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Ensure mono
        if len(audio.shape) > 1:
            audio = np.mean(audio, axis=1)

        # OpenAI Whisper expects 16kHz audio, resample if needed
        # Skip resampling if already at 16kHz (avoids overhead)
        if abs(sample_rate - 16000) > 100:  # Tolerance for near-16kHz rates
            import scipy.signal
            target_length = int(len(audio) * 16000 / sample_rate)
            audio = scipy.signal.resample(audio, target_length).astype(np.float32)

        # Transcribe with OpenAI Whisper (optimized for real-time performance)
        result = self._model.transcribe(
            audio,
            language=lang,
            beam_size=1,              # Greedy decoding for speed (was 5)
            best_of=1,                # Single pass (was 5 - massive speedup!)
            temperature=0.0,
            compression_ratio_threshold=2.4,
            logprob_threshold=-1.0,
            no_speech_threshold=0.6,
            condition_on_previous_text=False,
            word_timestamps=False,    # Skip word timing for speed (was True)
        )

        # Extract segments
        segments = result.get("segments", [])

        # Calculate confidence from log probabilities
        confidences = []
        for segment in segments:
            if "avg_logprob" in segment:
                prob = np.exp(segment["avg_logprob"])
                confidences.append(min(1.0, max(0.0, prob)))

        # Get transcript
        transcript = result.get("text", "").strip()

        # Calculate average confidence
        confidence = sum(confidences) / len(confidences) if confidences else 0.8

        # Get detected language
        detected_lang = result.get("language", lang or "en")

        return SttResult(
            transcript=transcript,
            confidence=confidence,
            lang=detected_lang,
            raw={
                "whisper_result": result,
                "device": self.device,
            },
        )

    def _auto_detect_device(self) -> str:
        """Auto-detect the best available device.

        Returns:
            Device string ("cuda" or "cpu")
        """
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass
        return "cpu"

    def get_info(self) -> dict:
        """Get backend information.

        Returns:
            Dictionary with backend details
        """
        return {
            "backend": "openai-whisper",
            "model_size": self.model_size,
            "device": self.device,
            "device_index": self.device_index,
            "model_dir": self.model_dir,
        }
