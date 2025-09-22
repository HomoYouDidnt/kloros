"""Mock speaker recognition backend for testing."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .base import SpeakerResult


class MockSpeakerBackend:
    """Mock speaker recognition backend for testing and development."""

    def __init__(self, **kwargs):
        """Initialize mock speaker backend."""
        self.users: Dict[str, dict] = {}
        self.threshold = 0.8
        # Pre-populate with some test users for development
        self._populate_test_users()

    def _populate_test_users(self) -> None:
        """Add some test users for development."""
        test_users = ["alice", "bob", "charlie"]
        for user in test_users:
            # Create fake embeddings based on username hash
            user_hash = hashlib.md5(user.encode()).hexdigest()
            fake_embeddings = [
                [float(int(user_hash[i : i + 2], 16)) / 255.0 for i in range(0, 20, 2)]
                for _ in range(5)  # 5 fake embeddings per user
            ]

            self.users[user] = {
                "display_name": user.title(),
                "embeddings": fake_embeddings,
                "created": datetime.now(timezone.utc).isoformat(),
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "confidence_threshold": self.threshold,
                "enrollment_version": "mock_v1.0",
                "sample_count": len(fake_embeddings),
            }

    def _generate_fake_embedding(self, audio_sample: bytes) -> List[float]:
        """Generate a fake embedding based on audio sample hash."""
        # Create a deterministic "embedding" based on audio content
        audio_hash = hashlib.md5(audio_sample).hexdigest()
        # Convert hex to normalized float values
        embedding = [float(int(audio_hash[i : i + 2], 16)) / 255.0 for i in range(0, 20, 2)]
        return embedding

    def enroll_user(self, user_id: str, audio_samples: List[bytes], sample_rate: int) -> bool:
        """Enroll a new user with voice samples."""
        try:
            # Generate fake embeddings for all audio samples
            embeddings = []
            for audio_sample in audio_samples:
                embedding = self._generate_fake_embedding(audio_sample)
                embeddings.append(embedding)

            # Store user data
            user_data = {
                "display_name": user_id.title(),
                "embeddings": embeddings,
                "created": datetime.now(timezone.utc).isoformat(),
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "confidence_threshold": self.threshold,
                "enrollment_version": "mock_v1.0",
                "sample_count": len(embeddings),
            }

            self.users[user_id.lower()] = user_data
            return True

        except Exception as e:
            print(f"[speaker] Mock enrollment failed for {user_id}: {e}")
            return False

    def identify_speaker(self, audio_sample: bytes, sample_rate: int) -> SpeakerResult:
        """Identify speaker from audio sample."""
        try:
            # Generate fake embedding for the input audio
            query_embedding = self._generate_fake_embedding(audio_sample)

            best_user = None
            best_similarity = 0.0

            # Simple mock similarity: compare first few values of embeddings
            for user_id, user_data in self.users.items():
                user_embeddings = user_data.get("embeddings", [])

                # Mock similarity calculation
                similarities = []
                for stored_embedding in user_embeddings:
                    # Simple similarity: how close are the first 3 values?
                    diff = sum(
                        abs(a - b)
                        for a, b in zip(query_embedding[:3], stored_embedding[:3], strict=False)
                    )
                    similarity = max(0.0, 1.0 - diff)  # Convert difference to similarity
                    similarities.append(similarity)

                if similarities:
                    avg_similarity = sum(similarities) / len(similarities)
                    if avg_similarity > best_similarity and avg_similarity >= self.threshold:
                        best_similarity = avg_similarity
                        best_user = user_id

            # Return result
            if best_user:
                # Update last_seen
                self.users[best_user]["last_seen"] = datetime.now(timezone.utc).isoformat()

                return SpeakerResult(
                    user_id=best_user,
                    confidence=best_similarity,
                    is_known_speaker=True,
                    embedding=query_embedding,
                )
            else:
                # Unknown speaker - for testing, we can simulate recognition failures
                return SpeakerResult(
                    user_id="operator",  # Default user
                    confidence=0.0,
                    is_known_speaker=False,
                    embedding=query_embedding,
                )

        except Exception as e:
            print(f"[speaker] Mock identification failed: {e}")
            return SpeakerResult(user_id="operator", confidence=0.0, is_known_speaker=False)

    def delete_user(self, user_id: str) -> bool:
        """Delete a user's voice profile."""
        user_key = user_id.lower()
        if user_key in self.users:
            del self.users[user_key]
            return True
        return False

    def list_users(self) -> List[str]:
        """List all enrolled users."""
        return list(self.users.keys())

    def get_user_info(self, user_id: str) -> Optional[dict]:
        """Get information about a user."""
        user_key = user_id.lower()
        user_data = self.users.get(user_key)
        if user_data:
            # Return a copy without embeddings for privacy
            info = user_data.copy()
            info.pop("embeddings", None)
            return info
        return None

    def set_recognition_mode(self, mode: str) -> None:
        """Set mock recognition behavior for testing.

        Args:
            mode: "always_recognize", "never_recognize", or "normal"
        """
        if mode == "always_recognize":
            self.threshold = 0.0  # Recognize everyone
        elif mode == "never_recognize":
            self.threshold = 1.0  # Recognize no one
        else:  # normal
            self.threshold = 0.8
