"""Silero VAD (Voice Activity Detection) interface.

Silero VAD is an industry-standard voice activity detector with:
- High accuracy and low false positive rate
- Better noise rejection than WebRTC VAD
- Optimized for real-time streaming
- Works on CPU and GPU

Installation:
    pip install torch torchaudio

Model will be downloaded automatically on first use.
"""
import torch
import torchaudio
from typing import Optional
import os

class SileroVAD:
    """Silero Voice Activity Detection interface."""

    def __init__(
        self,
        sample_rate: int = 16000,
        threshold: float = 0.5,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 100,
        window_size_samples: int = 512,
        cache_dir: Optional[str] = None,
    ):
        """Initialize Silero VAD.

        Args:
            sample_rate: Audio sample rate (8000 or 16000)
            threshold: Speech probability threshold (0.0-1.0)
            min_speech_duration_ms: Minimum speech duration to trigger
            min_silence_duration_ms: Minimum silence duration to end speech
            window_size_samples: Window size for processing (512, 1024, or 1536)
            cache_dir: Directory to cache model (default: ~/.cache/torch/hub)
        """
        if sample_rate not in [8000, 16000]:
            raise ValueError("sample_rate must be 8000 or 16000")

        if window_size_samples not in [512, 1024, 1536]:
            raise ValueError("window_size_samples must be 512, 1024, or 1536")

        self.sample_rate = sample_rate
        self.threshold = threshold
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms
        self.window_size_samples = window_size_samples

        # Set cache directory
        if cache_dir:
            torch.hub.set_dir(os.path.expanduser(cache_dir))

        # Load Silero VAD model
        self.model, self.utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False,
            onnx=False,
        )

        # Extract utility functions
        (self.get_speech_timestamps,
         self.save_audio,
         self.read_audio,
         self.VADIterator,
         self.collect_chunks) = self.utils

        # Initialize state
        self.model.reset_states()
        self._speech_active = False
        self._speech_frames = 0
        self._silence_frames = 0

    def ingest(self, pcm16: bytes):
        """Ingest audio frame for VAD processing.

        Args:
            pcm16: 16-bit PCM audio bytes
        """
        # Convert bytes to tensor
        audio = torch.frombuffer(pcm16, dtype=torch.int16).float() / 32768.0

        # Process in chunks of window_size_samples
        for i in range(0, len(audio), self.window_size_samples):
            chunk = audio[i:i + self.window_size_samples]

            # Pad last chunk if needed
            if len(chunk) < self.window_size_samples:
                chunk = torch.nn.functional.pad(
                    chunk,
                    (0, self.window_size_samples - len(chunk))
                )

            # Get speech probability
            speech_prob = self.model(chunk, self.sample_rate).item()

            # Update state based on probability
            if speech_prob >= self.threshold:
                self._speech_frames += 1
                self._silence_frames = 0

                # Check if we've exceeded minimum speech duration
                if not self._speech_active:
                    duration_ms = (self._speech_frames * self.window_size_samples * 1000) / self.sample_rate
                    if duration_ms >= self.min_speech_duration_ms:
                        self._speech_active = True
            else:
                self._silence_frames += 1

                # Check if we've exceeded minimum silence duration
                if self._speech_active:
                    duration_ms = (self._silence_frames * self.window_size_samples * 1000) / self.sample_rate
                    if duration_ms >= self.min_silence_duration_ms:
                        self._speech_active = False
                        self._speech_frames = 0

    def active_now(self) -> bool:
        """Check if speech is currently active.

        Returns:
            True if speech detected, False otherwise
        """
        return self._speech_active

    def reset(self):
        """Reset VAD state."""
        self.model.reset_states()
        self._speech_active = False
        self._speech_frames = 0
        self._silence_frames = 0

    def get_speech_timestamps(
        self,
        audio: torch.Tensor,
        return_seconds: bool = False
    ):
        """Get speech timestamps from audio tensor.

        Args:
            audio: Audio tensor
            return_seconds: Return timestamps in seconds (vs samples)

        Returns:
            List of dicts with 'start' and 'end' keys
        """
        return self.utils[0](
            audio,
            self.model,
            threshold=self.threshold,
            sampling_rate=self.sample_rate,
            min_speech_duration_ms=self.min_speech_duration_ms,
            min_silence_duration_ms=self.min_silence_duration_ms,
            window_size_samples=self.window_size_samples,
            return_seconds=return_seconds,
        )


def create_silero_vad(
    sample_rate: int = 16000,
    aggressive: int = 1,
) -> SileroVAD:
    """Create Silero VAD with aggressiveness level.

    Args:
        sample_rate: Audio sample rate (8000 or 16000)
        aggressive: Aggressiveness level (0-3, higher = less sensitive)

    Returns:
        SileroVAD instance
    """
    # Map aggressiveness to threshold
    # 0 = very sensitive (0.3)
    # 1 = normal (0.5)
    # 2 = less sensitive (0.7)
    # 3 = very insensitive (0.85)
    threshold_map = {
        0: 0.3,
        1: 0.5,
        2: 0.7,
        3: 0.85,
    }

    threshold = threshold_map.get(aggressive, 0.5)

    return SileroVAD(
        sample_rate=sample_rate,
        threshold=threshold,
    )
