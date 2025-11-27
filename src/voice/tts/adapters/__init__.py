"""TTS backend adapters."""
from .xtts_v2 import XTTSBackend
from .kokoro import KokoroBackend
from .mimic3 import Mimic3Backend
from .piper import PiperBackend

__all__ = [
    "XTTSBackend",
    "KokoroBackend",
    "Mimic3Backend",
    "PiperBackend",
]
