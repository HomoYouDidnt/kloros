"""Embedding-based speaker recognition using Resemblyzer."""

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
    """Speaker recognition backend using Resemblyzer audio embeddings."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        threshold: float = 0.75,
        model_name: str = "resemblyzer",
    ):
        """Initialize the embedding speaker backend.

        Args:
            db_path: Path to speaker database file (default: ~/.kloros/speaker_db.json)
            threshold: Similarity threshold for speaker recognition (default: 0.75)
            model_name: Model type (only "resemblyzer" supported currently)
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

        # Initialize Resemblyzer encoder lazily
        self._encoder = None

    @property
    def encoder(self):
        """Lazy-load the Resemblyzer voice encoder."""
        if self._encoder is None:
            try:
                from resemblyzer import VoiceEncoder
                self._encoder = VoiceEncoder()
                print("[speaker] Loaded Resemblyzer voice encoder")
            except ImportError as e:
                raise RuntimeError("resemblyzer library not available") from e
        return self._encoder

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

    def _audio_bytes_to_wav(self, audio_bytes: bytes, sample_rate: int) -> np.ndarray:
        """Convert raw audio bytes to numpy array suitable for Resemblyzer.
        
        Args:
            audio_bytes: Raw PCM audio (int16)
            sample_rate: Sample rate of audio
            
        Returns:
            Float32 numpy array normalized to [-1, 1]
        """
        # Convert int16 PCM to float32 in range [-1, 1]
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        
        # Resample to 16kHz if needed (Resemblyzer expects 16kHz)
        if sample_rate != 16000:
            try:
                import librosa
                audio_array = librosa.resample(audio_array, orig_sr=sample_rate, target_sr=16000)
            except ImportError:
                # Fallback: simple decimation (not ideal but works)
                if sample_rate > 16000:
                    step = sample_rate // 16000
                    audio_array = audio_array[::step]
        
        return audio_array

    def _extract_embedding(self, audio_sample: bytes, sample_rate: int) -> np.ndarray:
        """Extract speaker embedding from audio sample using Resemblyzer.

        Args:
            audio_sample: Raw audio bytes (int16 PCM)
            sample_rate: Audio sample rate

        Returns:
            Speaker embedding vector (256 dimensions)
        """
        # Convert to format Resemblyzer expects
        audio_array = self._audio_bytes_to_wav(audio_sample, sample_rate)
        
        # Extract embedding
        embedding = self.encoder.embed_utterance(audio_array)
        
        return embedding

    def _compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings."""
        # Normalize embeddings
        embedding1_norm = embedding1 / (np.linalg.norm(embedding1) + 1e-8)
        embedding2_norm = embedding2 / (np.linalg.norm(embedding2) + 1e-8)
        
        # Cosine similarity
        similarity = np.dot(embedding1_norm, embedding2_norm)
        
        return float(similarity)

    def enroll_user(
        self, user_id: str, audio_samples: List[bytes], sample_rate: int
    ) -> bool:
        """Enroll a new user with voice samples.

        Args:
            user_id: Unique user identifier
            audio_samples: List of audio samples (raw int16 PCM bytes)
            sample_rate: Sample rate of audio

        Returns:
            True if enrollment successful, False otherwise
        """
        if not audio_samples:
            print(f"[speaker] No audio samples provided for {user_id}")
            return False

        try:
            # Extract embeddings from all samples
            embeddings = []
            for i, sample in enumerate(audio_samples):
                if len(sample) < 16000:  # Skip very short samples (< 0.5s at 32kHz)
                    print(f"[speaker] Skipping short sample {i} for {user_id}")
                    continue
                    
                try:
                    embedding = self._extract_embedding(sample, sample_rate)
                    embeddings.append(embedding.tolist())
                except Exception as e:
                    print(f"[speaker] Failed to extract embedding from sample {i}: {e}")
                    continue

            if not embeddings:
                print(f"[speaker] No valid embeddings extracted for {user_id}")
                return False

            # Store user profile with multiple embeddings
            self.db["users"][user_id] = {
                "embeddings": embeddings,
                "enrollment_date": datetime.now(timezone.utc).isoformat(),
                "sample_count": len(embeddings),
                "sample_rate": sample_rate,
            }

            self._save_database()
            print(f"[speaker] Enrolled {user_id} with {len(embeddings)} voice samples")
            return True

        except Exception as e:
            print(f"[speaker] Enrollment failed for {user_id}: {e}")
            return False

    def identify_speaker(self, audio_sample: bytes, sample_rate: int) -> SpeakerResult:
        """Identify speaker from audio sample.

        Args:
            audio_sample: Raw audio bytes (int16 PCM)
            sample_rate: Audio sample rate

        Returns:
            SpeakerResult with identification details
        """
        if len(audio_sample) < 8000:  # Too short
            return SpeakerResult(
                is_known_speaker=False,
                user_id=self.db["settings"].get("default_user", "operator"),
                confidence=0.0,
            )

        try:
            # Extract embedding from input sample
            query_embedding = self._extract_embedding(audio_sample, sample_rate)

            # Compare against all enrolled users
            best_match = None
            best_similarity = 0.0
            all_similarities = {}

            for user_id, user_data in self.db["users"].items():
                user_embeddings = user_data["embeddings"]
                
                # Compare against all stored embeddings for this user
                similarities = []
                for stored_embedding in user_embeddings:
                    stored_np = np.array(stored_embedding, dtype=np.float32)
                    similarity = self._compute_similarity(query_embedding, stored_np)
                    similarities.append(similarity)
                
                # Use average similarity across all samples
                avg_similarity = np.mean(similarities) if similarities else 0.0
                all_similarities[user_id] = avg_similarity

                if avg_similarity > best_similarity:
                    best_similarity = avg_similarity
                    best_match = user_id

            # Check if best match exceeds threshold
            if best_match and best_similarity >= self.threshold:
                return SpeakerResult(
                    is_known_speaker=True,
                    user_id=best_match,
                    confidence=best_similarity,
                )
            else:
                return SpeakerResult(
                    is_known_speaker=False,
                    user_id=self.db["settings"].get("default_user", "operator"),
                    confidence=best_similarity,
                )

        except Exception as e:
            print(f"[speaker] Identification error: {e}")
            return SpeakerResult(
                is_known_speaker=False,
                user_id=self.db["settings"].get("default_user", "operator"),
                confidence=0.0,
            )

    def list_users(self) -> List[str]:
        """List all enrolled users."""
        return list(self.db["users"].keys())

    def delete_user(self, user_id: str) -> bool:
        """Delete a user's voice profile."""
        if user_id in self.db["users"]:
            del self.db["users"][user_id]
            self._save_database()
            return True
        return False

    def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get information about an enrolled user."""
        user_data = self.db["users"].get(user_id)
        if user_data:
            # Return copy without embeddings (too large)
            return {
                "user_id": user_id,
                "enrollment_date": user_data.get("enrollment_date"),
                "sample_count": user_data.get("sample_count"),
                "sample_rate": user_data.get("sample_rate"),
            }
        return None
