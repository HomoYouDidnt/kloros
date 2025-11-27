"""Supertonic TTS adapter for streaming/real-time synthesis."""

import os
import sys
from typing import Iterable, Optional

import numpy as np


class SupertonicBackend:
    """Supertonic backend for streaming TTS with built-in text normalization."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._playing = False
        self._tts = None
        self._style = None
        self._sample_rate = 24000

        st_cfg = self.cfg.get("supertonic", {})
        self.onnx_dir = os.path.expanduser(
            st_cfg.get("onnx_dir", "~/KLoROS/models/supertonic/assets/onnx")
        )
        self.voice_style_path = os.path.expanduser(
            st_cfg.get("voice_style", "~/KLoROS/models/supertonic/assets/voice_styles/M1.json")
        )
        self.total_steps = st_cfg.get("total_steps", 5)
        self.speed = st_cfg.get("speed", 1.05)
        self.use_gpu = st_cfg.get("use_gpu", False)

    def _ensure_path(self):
        """Ensure supertonic helper module is importable."""
        helper_dir = os.path.expanduser("~/KLoROS/models/supertonic/py")
        if helper_dir not in sys.path:
            sys.path.insert(0, helper_dir)

    def start(self):
        """Initialize Supertonic TTS engine."""
        self._ensure_path()
        from helper import load_text_to_speech, load_voice_style

        self._tts = load_text_to_speech(self.onnx_dir, self.use_gpu)
        self._style = load_voice_style([self.voice_style_path])
        self._sample_rate = self._tts.sample_rate
        self._playing = True

    def stream_text(self, chunks: Iterable[str]):
        """Stream synthesized audio from text chunks."""
        if not self._playing or self._tts is None:
            return

        for text in chunks:
            if not self._playing:
                break
            if not text.strip():
                continue

            wav, duration = self._tts(
                text, self._style, self.total_steps, self.speed
            )
            audio_int16 = (wav[0] * 32767).astype(np.int16)
            yield audio_int16.tobytes()

    def synthesize_to_array(self, text: str) -> tuple[np.ndarray, float]:
        """Synthesize text and return audio array + duration."""
        if self._tts is None:
            self.start()

        wav, duration = self._tts(text, self._style, self.total_steps, self.speed)
        return wav[0], float(duration[0])

    def stop(self):
        """Stop playback."""
        self._playing = False

    def is_playing(self):
        return self._playing

    def prewarm(self):
        """Prewarm the backend by loading models."""
        if self._tts is None:
            self.start()
            self._playing = False

    @property
    def sample_rate(self) -> int:
        return self._sample_rate
