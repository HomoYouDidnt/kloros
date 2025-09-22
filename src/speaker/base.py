"""Base classes and protocols for speaker recognition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol


@dataclass
class SpeakerResult:
    """Result of speaker identification."""

    user_id: str
    confidence: float
    is_known_speaker: bool
    embedding: Optional[List[float]] = None


class SpeakerBackend(Protocol):
    """Protocol for speaker recognition backends."""

    def enroll_user(self, user_id: str, audio_samples: List[bytes], sample_rate: int) -> bool:
        """Enroll a new user with voice samples.

        Args:
            user_id: Unique identifier for the user
            audio_samples: List of audio samples (raw bytes)
            sample_rate: Audio sample rate in Hz

        Returns:
            True if enrollment successful, False otherwise
        """
        ...

    def identify_speaker(self, audio_sample: bytes, sample_rate: int) -> SpeakerResult:
        """Identify speaker from audio sample.

        Args:
            audio_sample: Audio sample (raw bytes)
            sample_rate: Audio sample rate in Hz

        Returns:
            SpeakerResult with identification details
        """
        ...

    def delete_user(self, user_id: str) -> bool:
        """Delete a user's voice profile.

        Args:
            user_id: User to delete

        Returns:
            True if deletion successful, False otherwise
        """
        ...

    def list_users(self) -> List[str]:
        """List all enrolled users.

        Returns:
            List of user IDs
        """
        ...

    def get_user_info(self, user_id: str) -> Optional[dict]:
        """Get information about a user.

        Args:
            user_id: User to query

        Returns:
            User info dict or None if not found
        """
        ...


def create_speaker_backend(backend_name: str = "embedding") -> SpeakerBackend:
    """Create a speaker backend by name.

    Args:
        backend_name: Backend type ("embedding", "mock")

    Returns:
        Speaker backend instance

    Raises:
        ValueError: If backend name is unknown
        RuntimeError: If backend cannot be initialized
    """
    backend_name = backend_name.lower()

    if backend_name == "embedding":
        from .embedding_backend import EmbeddingSpeakerBackend

        return EmbeddingSpeakerBackend()
    elif backend_name == "mock":
        from .mock_backend import MockSpeakerBackend

        return MockSpeakerBackend()
    else:
        raise ValueError(f"Unknown speaker backend: {backend_name}")
