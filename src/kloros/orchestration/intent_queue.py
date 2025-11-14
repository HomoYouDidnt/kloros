"""
Intent Queue Manager - Middleware for deduplication and priority-based processing.

Prevents intent flooding, deduplicates identical intents, and manages queue depth.
"""

import os
import json
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

INTENT_DIR = Path("/home/kloros/.kloros/intents")
MAX_QUEUE_DEPTH = int(os.environ.get("KLR_MAX_INTENT_QUEUE", "50"))
DEDUP_WINDOW_SECONDS = int(os.environ.get("KLR_INTENT_DEDUP_WINDOW", "3600"))  # 1 hour


@dataclass
class QueuedIntent:
    """Intent with metadata for queue management."""
    path: Path
    intent_type: str
    priority: int
    reason: str
    data_hash: str
    generated_at: float


def _compute_intent_hash(intent: Dict[str, Any]) -> str:
    """
    Compute stable hash of intent for deduplication.

    Hash includes: intent_type + subsystem + key params (not timestamps)
    For SPICA spawn intents, includes question_id and hypothesis for uniqueness.
    """
    # Extract stable fields only (exclude timestamps, generated_at, etc.)
    stable_data = {
        "intent_type": intent.get("intent_type"),
        "reason": intent.get("reason"),
        "data": {
            "mode": intent.get("data", {}).get("mode"),
            "subsystem": intent.get("data", {}).get("subsystem"),
            "seed_fix": intent.get("data", {}).get("seed_fix"),
            # Include context keys but not the full message (too variable)
            "context_keys": sorted(intent.get("data", {}).get("context", {}).keys())
        }
    }

    if intent.get("intent_type") == "spica_spawn_request":
        stable_data["data"]["question_id"] = intent.get("data", {}).get("question_id")
        stable_data["data"]["hypothesis"] = intent.get("data", {}).get("hypothesis")

    # Include question_id for ALL curiosity-related intents to prevent duplicate questions
    if intent.get("intent_type", "").startswith("curiosity_"):
        stable_data["data"]["question_id"] = intent.get("data", {}).get("question_id")
        stable_data["data"]["hypothesis"] = intent.get("data", {}).get("hypothesis")

    hash_input = json.dumps(stable_data, sort_keys=True).encode()
    return hashlib.sha256(hash_input).hexdigest()[:16]


def load_queue() -> List[QueuedIntent]:
    """
    Load all pending intents from queue directory.

    Returns:
        List of QueuedIntent, sorted by priority (highest first)
    """
    if not INTENT_DIR.exists():
        return []

    intents = []

    for intent_file in INTENT_DIR.glob("*.json"):
        try:
            with open(intent_file) as f:
                intent_data = json.load(f)

            intents.append(QueuedIntent(
                path=intent_file,
                intent_type=intent_data.get("intent_type", "unknown"),
                priority=intent_data.get("priority", 0),
                reason=intent_data.get("reason", ""),
                data_hash=_compute_intent_hash(intent_data),
                generated_at=intent_data.get("generated_at", 0)
            ))

        except Exception as e:
            logger.error(f"Failed to load intent {intent_file.name}: {e}")

    # Sort by priority (highest first), then by timestamp (oldest first)
    intents.sort(key=lambda i: (-i.priority, i.generated_at))

    return intents


def deduplicate_queue(queue: List[QueuedIntent]) -> tuple[List[QueuedIntent], int]:
    """
    Remove duplicate intents based on data_hash.

    Keeps the oldest intent in each duplicate group.
    Archives newer duplicates to processed/deduplicated/

    Args:
        queue: List of QueuedIntent

    Returns:
        (deduplicated_queue, num_removed)
    """
    seen_hashes: Dict[str, QueuedIntent] = {}
    duplicates = []

    for intent in queue:
        if intent.data_hash in seen_hashes:
            # Duplicate found - keep older one
            existing = seen_hashes[intent.data_hash]
            if intent.generated_at < existing.generated_at:
                # This one is older, replace
                duplicates.append(existing)
                seen_hashes[intent.data_hash] = intent
            else:
                # Existing is older, discard this one
                duplicates.append(intent)
        else:
            seen_hashes[intent.data_hash] = intent

    # Archive duplicates
    if duplicates:
        archive_dir = INTENT_DIR / "processed" / "deduplicated"
        archive_dir.mkdir(parents=True, exist_ok=True)

        for dup in duplicates:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_name = f"{ts}_dup_{dup.path.name}"
            dup.path.rename(archive_dir / new_name)
            logger.info(f"Deduplicated: {dup.path.name} (hash={dup.data_hash})")

    # Return deduplicated list
    unique = list(seen_hashes.values())
    unique.sort(key=lambda i: (-i.priority, i.generated_at))

    return unique, len(duplicates)


def enforce_queue_limits(queue: List[QueuedIntent]) -> tuple[List[QueuedIntent], int]:
    """
    Enforce maximum queue depth.

    If queue exceeds MAX_QUEUE_DEPTH, archive lowest-priority oldest intents.

    Args:
        queue: List of QueuedIntent (should be sorted by priority)

    Returns:
        (limited_queue, num_dropped)
    """
    if len(queue) <= MAX_QUEUE_DEPTH:
        return queue, 0

    # Keep highest priority intents
    keep = queue[:MAX_QUEUE_DEPTH]
    drop = queue[MAX_QUEUE_DEPTH:]

    # Archive dropped intents
    if drop:
        archive_dir = INTENT_DIR / "processed" / "queue_overflow"
        archive_dir.mkdir(parents=True, exist_ok=True)

        for intent in drop:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_name = f"{ts}_overflow_{intent.path.name}"
            intent.path.rename(archive_dir / new_name)
            logger.warning(f"Queue overflow: dropped {intent.path.name} (priority={intent.priority})")

    return keep, len(drop)


def prune_stale_intents(queue: List[QueuedIntent], max_age_seconds: int = 86400) -> tuple[List[QueuedIntent], int]:
    """
    Remove intents older than max_age_seconds.

    Default: 24 hours (86400 seconds)

    Args:
        queue: List of QueuedIntent
        max_age_seconds: Maximum age in seconds

    Returns:
        (fresh_queue, num_pruned)
    """
    now = datetime.now().timestamp()
    cutoff = now - max_age_seconds

    fresh = []
    stale = []

    for intent in queue:
        if intent.generated_at >= cutoff:
            fresh.append(intent)
        else:
            stale.append(intent)

    # Archive stale intents
    if stale:
        archive_dir = INTENT_DIR / "processed" / "stale"
        archive_dir.mkdir(parents=True, exist_ok=True)

        for intent in stale:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_name = f"{ts}_stale_{intent.path.name}"
            intent.path.rename(archive_dir / new_name)
            age_hours = (now - intent.generated_at) / 3600
            logger.warning(f"Stale intent: {intent.path.name} (age={age_hours:.1f}h)")

    return fresh, len(stale)


class IntentQueue:
    """Intent queue manager for processing intents."""

    def __init__(self):
        self.intent_dir = INTENT_DIR


def get_next_intent() -> Dict[str, Any]:
    """
    Get the next intent to process without full queue processing.

    Returns:
        {
            "next_intent": Path or None
        }
    """
    queue = load_queue()

    if not queue:
        return {"next_intent": None}

    # Return highest priority intent
    return {"next_intent": queue[0].path}


def process_queue() -> Dict[str, Any]:
    """
    Complete queue processing pipeline:
    1. Load all pending intents
    2. Deduplicate by data_hash
    3. Prune stale intents (>24h old)
    4. Enforce queue depth limit
    5. Return next intent to process

    Returns:
        {
            "next_intent": Path or None,
            "queue_depth": int,
            "stats": {
                "deduplicated": int,
                "pruned": int,
                "dropped": int
            }
        }
    """
    # Load queue
    queue = load_queue()
    initial_depth = len(queue)

    if initial_depth == 0:
        return {
            "next_intent": None,
            "queue_depth": 0,
            "stats": {"deduplicated": 0, "pruned": 0, "dropped": 0}
        }

    # Deduplicate
    queue, dedup_count = deduplicate_queue(queue)

    # Prune stale
    queue, prune_count = prune_stale_intents(queue)

    # Enforce limits
    queue, drop_count = enforce_queue_limits(queue)

    # Log stats if any cleanup occurred
    if dedup_count > 0 or prune_count > 0 or drop_count > 0:
        logger.info(f"Queue processed: {initial_depth} → {len(queue)} intents "
                   f"(dedup={dedup_count}, prune={prune_count}, drop={drop_count})")

    # Return highest priority intent
    next_intent = queue[0].path if queue else None

    return {
        "next_intent": next_intent,
        "queue_depth": len(queue),
        "stats": {
            "deduplicated": dedup_count,
            "pruned": prune_count,
            "dropped": drop_count
        }
    }
