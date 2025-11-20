"""TTS (Text-to-Speech) module for KLoROS."""
from .router import TTSRouter
from .chunker import chunk_text
from .curate_refs import curate, make_dream_job
from .adapters import XTTSBackend, KokoroBackend, Mimic3Backend, PiperBackend

__all__ = [
    "TTSRouter",
    "chunk_text",
    "curate",
    "make_dream_job",
    "XTTSBackend",
    "KokoroBackend",
    "Mimic3Backend",
    "PiperBackend",
]
