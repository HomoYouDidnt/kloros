"""Silero VAD wrapper for KLoROS two-stage voice activity detection.

This module provides a wrapper around the Silero VAD neural network model for
Stage B refinement of voice activity candidates detected by Stage A (dBFS).
"""

from __future__ import annotations

import os
from typing import List, Tuple, Optional

import numpy as np


class SileroVAD:
    """Silero VAD wrapper with lazy torch import and segment refinement."""

    def __init__(self, device: str = "cpu", threshold: float = 0.5):
        """Initialize Silero VAD with lazy torch loading.

        Args:
            device: Device to run on ("cpu" or "cuda")
            threshold: Probability threshold for speech detection (0.0-1.0)

        Raises:
            RuntimeError: If torch is unavailable or model cannot be loaded
        """
        # Lazy import torch to avoid hard dependency
        try:
            import torch
        except ImportError as e:
            raise RuntimeError(
                "PyTorch not available. Install with: pip install torch"
            ) from e

        self.torch = torch
        self.device = device
        self.threshold = threshold
        self._model = None
        self._utils = None

        # Load model
        self._load_model()

    def _load_model(self):
        """Load Silero VAD model from torch hub."""
        try:
            # Offline-safe: uses local cache if available
            hub_dir = os.getenv("TORCH_HUB_DIR", os.path.expanduser("~/.cache/torch/hub"))
            os.makedirs(hub_dir, exist_ok=True)

            self._model, self._utils = self.torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
                verbose=False,
            )
            self._model.to(self.device)
            print(f"[silero-vad] Loaded model on {self.device}, threshold={self.threshold}")
        except Exception as e:
            raise RuntimeError(f"Failed to load Silero VAD model: {e}") from e

    def refine_segments(
        self,
        audio: np.ndarray,
        sample_rate: int,
        candidates: List[Tuple[float, float]],
        min_speech_duration_ms: int = 250,
        max_speech_duration_s: float = 30.0,
    ) -> List[Tuple[float, float]]:
        """Refine candidate segments using Silero neural network.

        Args:
            audio: Audio samples as float32 mono array in range [-1, 1]
            sample_rate: Sample rate in Hz
            candidates: List of (start_time, end_time) candidate segments in seconds
            min_speech_duration_ms: Minimum speech segment duration in milliseconds
            max_speech_duration_s: Maximum speech segment duration in seconds

        Returns:
            List of refined (start_time, end_time) segments in seconds
        """
        if not candidates:
            return []

        # Ensure audio is float32 mono
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        if len(audio.shape) > 1:
            audio = np.mean(audio, axis=1).astype(np.float32)

        # Resample to 16kHz if needed (Silero VAD expects 16kHz)
        if sample_rate != 16000:
            audio = self._resample_to_16k(audio, sample_rate)
            sample_rate = 16000

        # Convert to torch tensor
        audio_tensor = self.torch.from_numpy(audio).to(self.device)

        # Get speech timestamps from Silero
        speech_timestamps = self._utils[0](
            audio_tensor,
            self._model,
            sampling_rate=sample_rate,
            threshold=self.threshold,
            min_speech_duration_ms=min_speech_duration_ms,
            max_speech_duration_s=max_speech_duration_s,
            return_seconds=True,
        )

        # Convert to list of tuples
        refined_segments = []
        for segment in speech_timestamps:
            start_time = segment["start"]
            end_time = segment["end"]
            refined_segments.append((start_time, end_time))

        return refined_segments

    def _resample_to_16k(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Resample audio to 16kHz using scipy.

        Args:
            audio: Audio samples as float32 mono array
            sample_rate: Current sample rate in Hz

        Returns:
            Resampled audio at 16kHz
        """
        import scipy.signal

        target_length = int(len(audio) * 16000 / sample_rate)
        resampled = scipy.signal.resample(audio, target_length).astype(np.float32)
        return resampled

    def is_speech(self, audio_frame: bytes, sample_rate: int) -> bool:
        """Check if a single audio frame contains speech.

        Args:
            audio_frame: Audio frame as bytes (int16 mono)
            sample_rate: Sample rate in Hz

        Returns:
            True if frame contains speech, False otherwise
        """
        try:
            # Convert bytes to float32 numpy array
            audio_np = np.frombuffer(audio_frame, dtype=np.int16).astype(np.float32) / 32768.0

            # Resample to 16kHz if needed (Silero expects 16kHz)
            if sample_rate != 16000:
                audio_np = self._resample_to_16k(audio_np, sample_rate)

            # Ensure minimum length for Silero (512 samples)
            if len(audio_np) < 512:
                audio_np = np.pad(audio_np, (0, 512 - len(audio_np)))

            # Convert to torch tensor
            audio_tensor = self.torch.from_numpy(audio_np).to(self.device)

            # Get speech probability
            speech_prob = self._model(audio_tensor, 16000).item()

            # Debug logging
            if not hasattr(self, '_silero_debug_counter'):
                self._silero_debug_counter = 0
            self._silero_debug_counter += 1
            if self._silero_debug_counter % 25 == 0:
                print(f"[silero-vad] prob={speech_prob:.3f} threshold={self.threshold:.3f} result={speech_prob > self.threshold}")

            return speech_prob > self.threshold

        except Exception as e:
            print(f"[silero-vad] Frame detection error: {e}")
            return False

    def get_info(self) -> dict:
        """Get VAD information.

        Returns:
            Dictionary with VAD details
        """
        return {
            "backend": "silero-vad",
            "device": self.device,
            "threshold": self.threshold,
        }
