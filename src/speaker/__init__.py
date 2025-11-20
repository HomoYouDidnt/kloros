"""Speaker recognition and voice identification for KLoROS."""

from .base import SpeakerBackend, SpeakerResult, create_speaker_backend
from .enrollment import ENROLLMENT_SENTENCES, parse_spelled_name, verify_name_spelling

__all__ = [
    "SpeakerBackend",
    "SpeakerResult",
    "create_speaker_backend",
    "ENROLLMENT_SENTENCES",
    "parse_spelled_name",
    "verify_name_spelling",
]
