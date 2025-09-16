"""Conditional wrapper for `webrtcvad`.

This module prefers the real `webrtcvad` C-extension. If that import fails
or if the environment variable `KLR_FORCE_WEBSHIM` is set to a truthy value,
we expose a minimal pure-Python `Vad` implementation used for tests and
CI environments without the native extension.

Note: the shim is intentionally simple and deterministic; it is not a
production replacement for `webrtcvad`.
"""
from typing import Optional
import os


_force = os.environ.get("KLR_FORCE_WEBSHIM")
_use_shim = False
if _force and _force.lower() not in ("", "0", "false", "no"):
    _use_shim = True

_real_vad = None
if not _use_shim:
    try:
        import webrtcvad as _real_webrtcvad  # type: ignore
        _real_vad = getattr(_real_webrtcvad, "Vad", None)
    except Exception:
        _real_vad = None


class _ShimVad:
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


# Final exported Vad: prefer real extension, fall back to shim
Vad = _real_vad or _ShimVad

