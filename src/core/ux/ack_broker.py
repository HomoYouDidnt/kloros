"""
Acknowledgment broker for immediate user feedback during long operations.

Provides rate-limited audible acknowledgments to prevent user waiting in silence.
"""

import threading
import time
import subprocess
import os
from src.audio.mic_mute import mute_during_playback


class AckBroker:
    """
    Tiny rate-limited audible acknowledgement helper.

    Prevents long silent pauses during synthesis or other slow operations
    by giving immediate "I'm working on it" feedback to the user.
    """

    def __init__(self, tts_backend, audio_backend, min_quiet_gap_s: float = 6.0):
        """
        Initialize acknowledgment broker.

        Args:
            tts_backend: TTS backend for synthesizing ack phrases
            audio_backend: Audio backend for muting during playback
            min_quiet_gap_s: Minimum seconds between acknowledgments (rate limit)
        """
        self.tts_backend = tts_backend
        self.audio_backend = audio_backend
        self.min_quiet_gap_s = min_quiet_gap_s
        self._last_ack = 0.0
        self._lock = threading.Lock()

    def maybe_ack(self, phrase: str = "One moment…", voice: str = None, sample_rate: int = 22050):
        """
        Maybe play an acknowledgment if enough time has passed.

        Rate-limited to prevent chatty acknowledgments.

        Args:
            phrase: Text to synthesize and speak
            voice: Optional voice to use
            sample_rate: Sample rate for synthesis
        """
        now = time.time()
        with self._lock:
            if now - self._last_ack < self.min_quiet_gap_s:
                return  # Too soon, skip
            self._last_ack = now

        try:
            # Synthesize short TTS phrase
            result = self.tts_backend.synthesize(text=phrase, sample_rate=sample_rate, voice=voice)

            # Play it with mic muted to prevent echo
            with mute_during_playback(duration_s=getattr(result, "duration_s", 1.0),
                                      buffer_ms=120,
                                      audio_backend=self.audio_backend):
                cmd = self._playback_cmd(result.audio_path)
                subprocess.run(cmd, capture_output=True, check=False, timeout=3.5)
        except Exception as e:
            # Silently fail - acknowledgment is non-critical
            print(f"[ack_broker] Failed to play acknowledgment: {e}")

    def _playback_cmd(self, path: str):
        """
        Build playback command using environment configuration.

        Args:
            path: Path to audio file

        Returns:
            Command list for subprocess
        """
        # Default to PipeWire's pw-play; allow override via env
        playback_bin = os.getenv("KLR_PLAYBACK_CMD", "pw-play")
        device = os.getenv("KLR_PLAYBACK_DEVICE", "")

        if device:
            return [playback_bin, "--target", device, path]
        return [playback_bin, path]
