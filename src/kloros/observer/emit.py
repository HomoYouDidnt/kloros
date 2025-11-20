"""
Intent emitter for Observer - writes intents atomically to orchestrator queue.

Implements:
- Atomic file writes (fsync + rename)
- SHA256 checksums for integrity
- Deduplication within time window
- Rate limiting per intent type
"""

import os
import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any

from .rules import Intent

logger = logging.getLogger(__name__)


class IntentEmitter:
    """
    Emits intents to ~/.kloros/intents/ for orchestrator consumption.

    File format: {timestamp}_{intent_type}_{hash}.json
    Content: Intent data + SHA256 checksum
    """

    def __init__(self, intents_dir: Path = Path.home() / ".kloros" / "intents"):
        """
        Args:
            intents_dir: Directory to write intent files (default: ~/.kloros/intents/)
        """
        self.intents_dir = Path(intents_dir)
        self.intents_dir.mkdir(parents=True, exist_ok=True)

        # Deduplication tracking
        self._recent_hashes: Dict[str, float] = {}
        self._dedup_window_s = 3600  # 1 hour

    def emit(self, intent: Intent) -> bool:
        """
        Emit an intent atomically to the intents queue.

        Args:
            intent: Intent to emit

        Returns:
            True if emitted successfully, False if deduplicated or error
        """
        # Check deduplication
        if self._is_duplicate(intent):
            logger.debug(f"Intent deduplicated: {intent.intent_type}")
            return False

        # Generate filename
        ts = int(time.time() * 1000)  # milliseconds
        content_hash = self._hash_intent(intent)[:8]
        filename = f"{ts}_{intent.intent_type}_{content_hash}.json"
        filepath = self.intents_dir / filename

        # Prepare payload
        payload = intent.to_dict()
        payload["emitted_at"] = time.time()
        payload["emitted_by"] = "observer"

        # Add checksum
        json_bytes = json.dumps(payload, indent=2).encode("utf-8")
        checksum = hashlib.sha256(json_bytes).hexdigest()
        payload["sha256"] = checksum

        # Atomic write: tmp file + fsync + rename
        try:
            tmp_path = filepath.with_suffix(".tmp")

            with open(tmp_path, "w") as f:
                json.dump(payload, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Atomic rename
            tmp_path.rename(filepath)

            logger.info(f"Intent emitted: {filepath.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to emit intent: {e}")
            if tmp_path.exists():
                tmp_path.unlink()
            return False

    def _is_duplicate(self, intent: Intent) -> bool:
        """
        Check if this intent is a duplicate within the deduplication window.

        Uses intent hash to detect exact duplicates.
        """
        intent_hash = self._hash_intent(intent)
        now = time.time()

        # Prune old hashes
        self._recent_hashes = {
            h: ts for h, ts in self._recent_hashes.items()
            if now - ts < self._dedup_window_s
        }

        # Check if seen recently
        if intent_hash in self._recent_hashes:
            return True

        # Record this intent
        self._recent_hashes[intent_hash] = now
        return False

    def _hash_intent(self, intent: Intent) -> str:
        """
        Generate a hash of the intent for deduplication.

        Hash includes: intent_type, reason, and key data fields.
        Excludes timestamps to allow deduplication.
        """
        # Build stable representation
        hashable = {
            "intent_type": intent.intent_type,
            "reason": intent.reason,
            # Include only stable data fields (exclude paths, timestamps)
            "priority": intent.priority,
        }

        # Add specific data fields that matter for deduplication
        if "promotion_count" in intent.data:
            hashable["promotion_count"] = intent.data["promotion_count"]
        if "contention_count" in intent.data:
            hashable["contention_count"] = intent.data["contention_count"]
        if "duration_seconds" in intent.data:
            hashable["duration_seconds"] = intent.data["duration_seconds"]

        # Serialize and hash
        json_str = json.dumps(hashable, sort_keys=True)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def list_pending(self) -> list[Path]:
        """
        List pending intent files in the queue.

        Returns:
            List of intent file paths, sorted by timestamp (oldest first)
        """
        intent_files = sorted(self.intents_dir.glob("*.json"))
        return intent_files

    def prune_old_intents(self, max_age_hours: int = 24):
        """
        Remove intent files older than max_age_hours.

        Args:
            max_age_hours: Maximum age in hours before pruning
        """
        cutoff = time.time() - (max_age_hours * 3600)

        for intent_file in self.intents_dir.glob("*.json"):
            try:
                # Extract timestamp from filename: {timestamp}_{type}_{hash}.json
                ts_str = intent_file.stem.split("_")[0]
                ts = int(ts_str) / 1000  # Convert from milliseconds

                if ts < cutoff:
                    intent_file.unlink()
                    logger.info(f"Pruned old intent: {intent_file.name}")

            except (ValueError, IndexError) as e:
                logger.warning(f"Invalid intent filename: {intent_file.name}")

    def verify_intent(self, filepath: Path) -> bool:
        """
        Verify the integrity of an intent file using its SHA256 checksum.

        Args:
            filepath: Path to intent file

        Returns:
            True if checksum matches, False otherwise
        """
        try:
            with open(filepath, "r") as f:
                payload = json.load(f)

            stored_checksum = payload.pop("sha256", None)
            if not stored_checksum:
                logger.warning(f"No checksum in {filepath.name}")
                return False

            # Recompute checksum
            json_bytes = json.dumps(payload, indent=2).encode("utf-8")
            computed_checksum = hashlib.sha256(json_bytes).hexdigest()

            if stored_checksum != computed_checksum:
                logger.error(f"Checksum mismatch in {filepath.name}")
                return False

            return True

        except Exception as e:
            logger.error(f"Failed to verify {filepath.name}: {e}")
            return False
