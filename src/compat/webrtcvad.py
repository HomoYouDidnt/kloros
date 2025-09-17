from __future__ import annotations

"""Thin wrapper around the webrtcvad extension without pkg_resources usage.

The upstream Python module imports pkg_resources solely to expose __version__.
That import now emits deprecation warnings and will eventually break when
pkg_resources is removed from setuptools. We reimplement the tiny shim so the
rest of the project can import webrtcvad without that dependency while still
relying on the compiled `_webrtcvad` extension installed from PyPI.
"""

try:  # Python >=3.8
    import importlib.metadata as _metadata
except Exception:  # pragma: no cover - fallback for very old runtimes
    _metadata = None  # type: ignore[assignment]

import _webrtcvad


def _dist_version(package: str) -> str:
    if _metadata is None:
        return "unknown"
    try:
        return _metadata.version(package)
    except _metadata.PackageNotFoundError:  # type: ignore[attr-defined]
        return "unknown"


__author__ = "John Wiseman jjwiseman@gmail.com"
__license__ = "MIT"
__copyright__ = "Copyright (C) 2016 John Wiseman"
__version__ = _dist_version("webrtcvad")


class Vad:
    """Lightweight proxy around the C extension."""

    def __init__(self, mode: int | None = None) -> None:
        self._vad = _webrtcvad.create()
        _webrtcvad.init(self._vad)
        if mode is not None:
            self.set_mode(mode)

    def set_mode(self, mode: int) -> None:
        _webrtcvad.set_mode(self._vad, mode)

    def is_speech(self, buf: bytes, sample_rate: int, length: int | None = None) -> bool:
        frame_count = len(buf) // 2
        active_len = length if length is not None else frame_count
        if active_len * 2 > len(buf):
            raise IndexError(
                f"buffer has {frame_count} frames, but length argument was {active_len}"
            )
        return bool(_webrtcvad.process(self._vad, sample_rate, buf, active_len))


def valid_rate_and_frame_length(rate: int, frame_length: int) -> bool:
    return bool(_webrtcvad.valid_rate_and_frame_length(rate, frame_length))


__all__ = ["Vad", "valid_rate_and_frame_length", "__version__"]
