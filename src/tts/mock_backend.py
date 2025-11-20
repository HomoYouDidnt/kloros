"""Mock TTS backend for testing and development."""

from __future__ import annotations

import os
import time
import wave
from pathlib import Path
from typing import Optional

import numpy as np

from .base import TtsResult


class MockTtsBackend:
    """Mock text-to-speech backend that generates silent audio files."""

    def __init__(self, out_dir: Optional[str] = None):
        """Initialize mock TTS backend.

        Args:
            out_dir: Output directory for audio files
        """
        self.out_dir = out_dir or os.path.expanduser("~/.kloros/out")

        # Ensure output directory exists
        Path(self.out_dir).mkdir(parents=True, exist_ok=True)

    def synthesize(
        self,
        text: str,
        sample_rate: int = 22050,
        voice: Optional[str] = None,
        out_dir: Optional[str] = None,
        basename: Optional[str] = None,
    ) -> TtsResult:
        """Mock synthesis that creates a silent WAV file.

        Args:
            text: Text to synthesize (ignored)
            sample_rate: Target sample rate in Hz
            voice: Voice to use (passed through to result)
            out_dir: Output directory (overrides instance default)
            basename: Output filename base

        Returns:
            TtsResult with audio file path and metadata
        """
        # Resolve parameters
        final_out_dir = out_dir or self.out_dir

        # Generate output filename
        if basename is None:
            basename = f"mock_tts_{int(time.time() * 1000)}"

        output_path = os.path.join(final_out_dir, f"{basename}.wav")

        # Create silent audio (100ms duration)
        duration_s = 0.1
        num_samples = int(duration_s * sample_rate)
        silence = np.zeros(num_samples, dtype=np.int16)

        # Write WAV file
        with wave.open(output_path, "wb") as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(silence.tobytes())

        return TtsResult(
            audio_path=output_path, duration_s=duration_s, sample_rate=sample_rate, voice=voice
        )
