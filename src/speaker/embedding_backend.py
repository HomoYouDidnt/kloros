"""Embedding-based speaker recognition using sentence-transformers."""

from __future__ import annotations

import json
import os
import tempfile
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from .base import SpeakerResult


class EmbeddingSpeakerBackend:
    """Speaker recognition backend using audio embeddings."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        threshold: float = 0.8,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ):
        """Initialize the embedding speaker backend.

        Args:
            db_path: Path to speaker database file (default: ~/.kloros/speaker_db.json)
            threshold: Similarity threshold for speaker recognition (default: 0.8)
            model_name: Sentence transformer model name for embeddings
        """
        self.threshold = float(os.getenv("KLR_SPEAKER_THRESHOLD", str(threshold)))
        self.model_name = model_name

        # Set up database path
        if db_path is None:
            db_path = os.getenv("KLR_SPEAKER_DB_PATH")
        if db_path is None:
            home_dir = Path.home()
            kloros_dir = home_dir / ".kloros"
            kloros_dir.mkdir(exist_ok=True)
            db_path = str(kloros_dir / "speaker_db.json")

        self.db_path = db_path
        self.db: Dict[str, Any] = self._load_database()

        # Initialize embedding model lazily
        self._model = None

    @property
    def model(self):
        """Lazy-load the sentence transformer model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
            except ImportError as e:
                raise RuntimeError("sentence-transformers library not available") from e
        return self._model

    def _load_database(self) -> Dict[str, Any]:
        """Load the speaker database from disk."""
        if not os.path.exists(self.db_path):
            return {
                "users": {},
                "settings": {
                    "default_user": "operator",
                    "enrollment_samples": 5,
                    "sentence_set_version": "kloros_v1.0",
                    "created": datetime.now(timezone.utc).isoformat(),
                },
            }

        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            # Backup corrupted database and start fresh
            if os.path.exists(self.db_path):
                backup_path = self.db_path + ".backup"
                os.rename(self.db_path, backup_path)
            return self._load_database()  # Recursive call to create new empty DB

    def _save_database(self) -> None:
        """Save the speaker database to disk."""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        # Write to temporary file first, then atomic rename
        temp_path = self.db_path + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.db, f, indent=2, ensure_ascii=False)
            os.rename(temp_path, self.db_path)
        except Exception:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def _audio_to_text_embedding(self, audio_sample: bytes, sample_rate: int) -> np.ndarray:
        """Convert audio sample to text embedding via speech recognition.

        This is a simplified approach - in production you might want to use
        specialized audio embedding models, but this leverages existing infrastructure.

        Args:
            audio_sample: Raw audio bytes (int16 PCM)
            sample_rate: Audio sample rate

        Returns:
            Text embedding vector
        """
        # Convert audio to temporary WAV file for processing
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            try:
                # Write WAV file
                with wave.open(temp_wav.name, "wb") as wav_file:
                    wav_file.setnchannels(1)  # Mono
                    wav_file.setsampwidth(2)  # 16-bit
                    wav_file.setframerate(sample_rate)
                    wav_file.writeframes(audio_sample)

                # For now, use a simple text representation of audio characteristics
                # In a full implementation, you'd use the existing STT pipeline
                audio_array = np.frombuffer(audio_sample, dtype=np.int16)

                # Create a pseudo-text representation of audio features
                rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
                spectral_centroid = len(audio_array) / sample_rate  # Simplified

                # Create a text description that captures voice characteristics
                audio_text = (
                    f"voice sample duration {spectral_centroid:.2f} seconds energy {rms:.0f}"
                )

                # Get embedding from text representation
                embedding = self.model.encode([audio_text])[0]
                return embedding

            finally:
                # Clean up temp file
                if os.path.exists(temp_wav.name):
                    os.unlink(temp_wav.name)

    def _compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings."""
        # Normalize embeddings
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        # Cosine similarity
        similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)
        return float(similarity)

    def enroll_user(self, user_id: str, audio_samples: List[bytes], sample_rate: int) -> bool:
        """Enroll a new user with voice samples."""
        try:
            # Generate embeddings for all audio samples
            embeddings = []
            for audio_sample in audio_samples:
                embedding = self._audio_to_text_embedding(audio_sample, sample_rate)
                embeddings.append(embedding.tolist())

            # Store user data
            user_data = {
                "display_name": user_id.title(),
                "embeddings": embeddings,
                "created": datetime.now(timezone.utc).isoformat(),
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "confidence_threshold": self.threshold,
                "enrollment_version": "kloros_v1.0",
                "sample_count": len(embeddings),
            }

            self.db["users"][user_id.lower()] = user_data
            self._save_database()
            return True

        except Exception as e:
            print(f"[speaker] Enrollment failed for {user_id}: {e}")
            return False

    def identify_speaker(self, audio_sample: bytes, sample_rate: int) -> SpeakerResult:
        """Identify speaker from audio sample."""
        try:
            # Generate embedding for the input audio
            query_embedding = self._audio_to_text_embedding(audio_sample, sample_rate)

            best_user = None
            best_similarity = 0.0

            # Compare against all enrolled users
            for user_id, user_data in self.db["users"].items():
                user_embeddings = user_data.get("embeddings", [])
                user_threshold = user_data.get("confidence_threshold", self.threshold)

                # Compute similarity against all user embeddings
                similarities = []
                for stored_embedding in user_embeddings:
                    stored_emb = np.array(stored_embedding)
                    similarity = self._compute_similarity(query_embedding, stored_emb)
                    similarities.append(similarity)

                # Use average similarity across all samples
                if similarities:
                    avg_similarity = np.mean(similarities)
                    if avg_similarity > best_similarity and avg_similarity >= user_threshold:
                        best_similarity = avg_similarity
                        best_user = user_id

            # Update last_seen for identified user
            if best_user:
                self.db["users"][best_user]["last_seen"] = datetime.now(timezone.utc).isoformat()
                self._save_database()

                return SpeakerResult(
                    user_id=best_user,
                    confidence=best_similarity,
                    is_known_speaker=True,
                    embedding=query_embedding.tolist(),
                )
            else:
                # Unknown speaker
                default_user = self.db["settings"].get("default_user", "operator")
                return SpeakerResult(
                    user_id=default_user,
                    confidence=0.0,
                    is_known_speaker=False,
                    embedding=query_embedding.tolist(),
                )

        except Exception as e:
            print(f"[speaker] Identification failed: {e}")
            # Fall back to default user
            default_user = self.db["settings"].get("default_user", "operator")
            return SpeakerResult(user_id=default_user, confidence=0.0, is_known_speaker=False)

    def delete_user(self, user_id: str) -> bool:
        """Delete a user's voice profile."""
        user_key = user_id.lower()
        if user_key in self.db["users"]:
            del self.db["users"][user_key]
            self._save_database()
            return True
        return False

    def list_users(self) -> List[str]:
        """List all enrolled users."""
        return list(self.db["users"].keys())

    def get_user_info(self, user_id: str) -> Optional[dict]:
        """Get information about a user."""
        user_key = user_id.lower()
        user_data = self.db["users"].get(user_key)
        if user_data:
            # Return a copy without embeddings for privacy
            info = user_data.copy()
            info.pop("embeddings", None)
            return info
        return None
