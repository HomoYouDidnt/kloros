"""A tiny local shim for webrtcvad used in tests to avoid importing pkg_resources.

This provides a minimal Vad class with the same constructor signature used in
the project: webrtcvad.Vad(mode). It implements an is_speech(frame, sample_rate)
method that heuristically treats non-zero frames as speech. This is *not* a
replacement for the real library in production; it only supports unit tests and
local demos where exact VAD behavior is unnecessary.
"""
from typing import Optional


class Vad:
    def __init__(self, mode: int = 1) -> None:
        # store mode but ignore — present for API compatibility
        self.mode = int(mode)

    def is_speech(self, frame: bytes, sample_rate: int) -> bool:
        """Return True if the frame likely contains speech.

        Heuristic: if the frame contains any non-zero byte, consider it speech.
        This is intentionally simple and deterministic for tests.
        """
        if not frame:
            return False
        return any(b != 0 for b in frame)
