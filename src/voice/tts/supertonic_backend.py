"""Supertonic TTS backend for KLoROS with built-in text normalization."""

from __future__ import annotations

import os
import sys
import time
import wave
from pathlib import Path
from typing import Optional

import numpy as np

from .base import TtsResult


class SupertonicTtsBackend:
    """Supertonic text-to-speech backend with lazy initialization.

    Supertonic handles text normalization internally, making it ideal for:
    - Numbers, dates, currency ($5.2M, 4:45 PM)
    - Abbreviations (Dr., Inc., etc.)
    - Phone numbers, technical units
    - Complex expressions

    This avoids the preprocessing overhead needed by Piper for such text.
    """

    def __init__(
        self,
        onnx_dir: Optional[str] = None,
        voice_style: Optional[str] = None,
        out_dir: Optional[str] = None,
        total_steps: int = 5,
        speed: float = 1.05,
        use_gpu: bool = False,
    ):
        """Initialize Supertonic TTS backend.

        Args:
            onnx_dir: Path to ONNX model directory
            voice_style: Path to voice style JSON file
            out_dir: Output directory for audio files
            total_steps: Number of denoising steps (higher = better quality)
            speed: Speech speed factor (1.05 default, higher = faster)
            use_gpu: Whether to use GPU (not yet fully supported)
        """
        self.onnx_dir = os.path.expanduser(
            onnx_dir or os.getenv(
                "KLR_SUPERTONIC_ONNX_DIR",
                "/home/kloros/models/supertonic/assets/onnx"
            )
        )
        self.voice_style_path = os.path.expanduser(
            voice_style or os.getenv(
                "KLR_SUPERTONIC_VOICE",
                "/home/kloros/models/supertonic/assets/voice_styles/M1.json"
            )
        )
        self.out_dir = out_dir or os.path.expanduser("~/.kloros/out")
        self.total_steps = total_steps
        self.speed = speed
        self.use_gpu = use_gpu

        Path(self.out_dir).mkdir(parents=True, exist_ok=True)

        self._tts = None
        self._style = None
        self._sample_rate = 24000
        self._warm = False

    def _ensure_path(self):
        """Ensure supertonic helper module is importable."""
        helper_dir = os.path.expanduser("/home/kloros/models/supertonic/py")
        if helper_dir not in sys.path:
            sys.path.insert(0, helper_dir)

    def _load_models(self):
        """Load Supertonic models lazily."""
        if self._tts is not None:
            return

        self._ensure_path()
        from helper import load_text_to_speech, load_voice_style

        self._tts = load_text_to_speech(self.onnx_dir, self.use_gpu)
        self._style = load_voice_style([self.voice_style_path])
        self._sample_rate = self._tts.sample_rate
        self._warm = True

    def prewarm(self):
        """Pre-load models for instant synthesis."""
        self._load_models()

    def is_warm(self) -> bool:
        """Check if models are loaded and ready."""
        return self._warm

    def synthesize(
        self,
        text: str,
        sample_rate: int = 24000,
        voice: Optional[str] = None,
        out_dir: Optional[str] = None,
        basename: Optional[str] = None,
    ) -> TtsResult:
        """Synthesize text to speech using Supertonic.

        Args:
            text: Text to synthesize (normalization handled internally)
            sample_rate: Target sample rate (Supertonic native is 24000)
            voice: Voice style path (overrides instance default)
            out_dir: Output directory (overrides instance default)
            basename: Output filename base

        Returns:
            TtsResult with audio file path and metadata
        """
        self._load_models()

        if voice and voice != self.voice_style_path:
            self._ensure_path()
            from helper import load_voice_style
            style = load_voice_style([os.path.expanduser(voice)])
        else:
            style = self._style

        final_out_dir = out_dir or self.out_dir
        if basename is None:
            basename = f"tts_{int(time.time() * 1000)}"

        output_path = os.path.join(final_out_dir, f"{basename}.wav")

        wav, duration = self._tts(text, style, self.total_steps, self.speed)

        audio_samples = wav[0, : int(self._sample_rate * duration[0].item())]
        audio_int16 = (audio_samples * 32767).astype(np.int16)

        with wave.open(output_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self._sample_rate)
            wav_file.writeframes(audio_int16.tobytes())

        duration_s = float(duration[0])

        return TtsResult(
            audio_path=output_path,
            duration_s=duration_s,
            sample_rate=self._sample_rate,
            voice=voice or self.voice_style_path,
        )

    def synthesize_to_array(self, text: str) -> tuple[np.ndarray, float]:
        """Synthesize text and return raw audio array.

        Args:
            text: Text to synthesize

        Returns:
            Tuple of (audio_array, duration_seconds)
        """
        self._load_models()

        wav, duration = self._tts(text, self._style, self.total_steps, self.speed)
        audio_samples = wav[0, : int(self._sample_rate * duration[0].item())]

        return audio_samples, float(duration[0])

    @property
    def sample_rate(self) -> int:
        """Get the native sample rate."""
        return self._sample_rate
