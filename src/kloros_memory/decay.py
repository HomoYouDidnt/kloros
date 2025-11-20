"""
Memory decay system for KLoROS with sector-aware decay curves.

Implements realistic memory fading based on:
- Time since creation (exponential decay)
- Memory importance (high importance = slower decay)
- Access frequency (recently accessed = refreshed decay)
- Memory sector (different sectors have different decay rates)
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .models import Event, EpisodeSummary, EventType
from .storage import MemoryStore

logger = logging.getLogger(__name__)


class MemorySector(str, Enum):
    """Different memory sectors with different decay characteristics."""

    EPISODIC = "episodic"  # Specific events - decay fastest
    SEMANTIC = "semantic"  # Generalized knowledge - decay slower
    PROCEDURAL = "procedural"  # Skills/patterns - decay slowest
    EMOTIONAL = "emotional"  # Emotional memories - decay based on intensity
    REFLECTIVE = "reflective"  # Meta-cognitive insights - moderate decay


@dataclass
class DecayConfig:
    """Configuration for memory decay curves."""

    # Half-life parameters (hours) - time for decay score to reach 0.5
    episodic_half_life: float = 168.0  # 7 days
    semantic_half_life: float = 720.0  # 30 days
    procedural_half_life: float = 2160.0  # 90 days
    emotional_half_life: float = 360.0  # 15 days
    reflective_half_life: float = 1440.0  # 60 days

    # Importance resistance factor (0-1)
    # Higher importance = stronger resistance to decay
    importance_resistance: float = 0.7

    # Access refresh factor (0-1)
    # How much accessing a memory refreshes its decay score
    access_refresh: float = 0.5

    # Minimum decay score before deletion
    deletion_threshold: float = 0.1

    # Access within this window counts as "recent"
    recent_access_window_hours: float = 24.0

    @classmethod
    def from_environment(cls) -> DecayConfig:
        """Load decay configuration from environment variables."""
        return cls(
            episodic_half_life=float(os.getenv("KLR_DECAY_EPISODIC_HALF_LIFE", "168")),
            semantic_half_life=float(os.getenv("KLR_DECAY_SEMANTIC_HALF_LIFE", "720")),
            procedural_half_life=float(os.getenv("KLR_DECAY_PROCEDURAL_HALF_LIFE", "2160")),
            emotional_half_life=float(os.getenv("KLR_DECAY_EMOTIONAL_HALF_LIFE", "360")),
            reflective_half_life=float(os.getenv("KLR_DECAY_REFLECTIVE_HALF_LIFE", "1440")),
            importance_resistance=float(os.getenv("KLR_DECAY_IMPORTANCE_RESISTANCE", "0.7")),
            access_refresh=float(os.getenv("KLR_DECAY_ACCESS_REFRESH", "0.5")),
            deletion_threshold=float(os.getenv("KLR_DECAY_DELETION_THRESHOLD", "0.1")),
            recent_access_window_hours=float(os.getenv("KLR_DECAY_RECENT_ACCESS_WINDOW", "24")),
        )


class DecayEngine:
    """
    Memory decay engine with sector-aware decay curves.

    Features:
    - Exponential decay based on time
    - Importance-weighted decay resistance
    - Access-based decay refresh
    - Sector-specific decay rates
    """

    def __init__(self, store: Optional[MemoryStore] = None, config: Optional[DecayConfig] = None):
        """
        Initialize the decay engine.

        Args:
            store: Memory storage instance
            config: Decay configuration (loads from env if None)
        """
        self.store = store or MemoryStore()
        self.config = config or DecayConfig.from_environment()

    def calculate_decay_score(
        self,
        created_timestamp: float,
        sector: MemorySector,
        importance: float = 0.5,
        last_accessed: Optional[float] = None
    ) -> float:
        """
        Calculate current decay score for a memory.

        Args:
            created_timestamp: When the memory was created (Unix timestamp)
            sector: Which memory sector this belongs to
            importance: Importance score (0.0-1.0)
            last_accessed: When memory was last accessed (Unix timestamp)

        Returns:
            Decay score (0.0-1.0, where 1.0 = fresh, 0.0 = completely decayed)
        """
        current_time = time.time()

        # Determine reference timestamp (use last_accessed if recent, otherwise created)
        if last_accessed:
            # If accessed recently, use that as reference
            recent_window = self.config.recent_access_window_hours * 3600
            if (current_time - last_accessed) < recent_window:
                reference_time = last_accessed
            else:
                # Blend between created and last_accessed based on how recent
                access_age_hours = (current_time - last_accessed) / 3600
                blend_factor = min(1.0, access_age_hours / self.config.recent_access_window_hours)
                reference_time = last_accessed * (1 - blend_factor) + created_timestamp * blend_factor
        else:
            reference_time = created_timestamp

        # Calculate age in hours
        age_hours = (current_time - reference_time) / 3600

        # Get half-life for this sector
        half_life = self._get_half_life(sector)

        # Base decay using exponential decay formula: score = 0.5^(age/half_life)
        base_decay = math.pow(0.5, age_hours / half_life)

        # Apply importance resistance
        # High importance memories resist decay
        importance_factor = 1.0 + (importance * self.config.importance_resistance)
        adjusted_decay = math.pow(base_decay, 1.0 / importance_factor)

        # Clamp to [0, 1]
        return max(0.0, min(1.0, adjusted_decay))

    def _get_half_life(self, sector: MemorySector) -> float:
        """Get half-life for a memory sector."""
        half_life_map = {
            MemorySector.EPISODIC: self.config.episodic_half_life,
            MemorySector.SEMANTIC: self.config.semantic_half_life,
            MemorySector.PROCEDURAL: self.config.procedural_half_life,
            MemorySector.EMOTIONAL: self.config.emotional_half_life,
            MemorySector.REFLECTIVE: self.config.reflective_half_life,
        }
        return half_life_map.get(sector, self.config.episodic_half_life)

    def classify_event_sector(self, event: Event) -> MemorySector:
        """
        Classify an event into a memory sector.

        Args:
            event: Event to classify

        Returns:
            The memory sector this event belongs to
        """
        # Reflective memories
        if event.event_type == EventType.SELF_REFLECTION:
            return MemorySector.REFLECTIVE

        # Emotional memories (if emotion metadata present)
        if event.metadata.get("emotion_type") or event.metadata.get("sentiment_score"):
            return MemorySector.EMOTIONAL

        # Procedural memories (patterns, tool usage)
        if event.event_type == EventType.CONTEXT_RETRIEVAL:
            return MemorySector.PROCEDURAL

        # Semantic memories (summaries, condensed knowledge)
        if event.event_type in [EventType.EPISODE_CREATED, EventType.EPISODE_CONDENSED]:
            return MemorySector.SEMANTIC

        # Default: Episodic (specific events)
        return MemorySector.EPISODIC

    def update_event_decay(self, event_id: int, refresh: bool = False) -> float:
        """
        Update decay score for an event.

        Args:
            event_id: ID of event to update
            refresh: If True, refresh last_accessed timestamp

        Returns:
            Updated decay score
        """
        # Get event
        event = self.store.get_event(event_id)
        if not event:
            return 0.0

        # Determine sector
        sector = self.classify_event_sector(event)

        # Get importance (default 0.5)
        importance = event.confidence or 0.5

        # Get current decay score from DB
        conn = self.store._get_connection()
        cursor = conn.execute(
            "SELECT decay_score, last_accessed FROM events WHERE id = ?",
            (event_id,)
        )
        row = cursor.fetchone()

        current_decay = row['decay_score'] if row and row['decay_score'] else 1.0
        last_accessed = row['last_accessed'] if row else None

        # Calculate new decay score
        new_decay = self.calculate_decay_score(
            created_timestamp=event.timestamp,
            sector=sector,
            importance=importance,
            last_accessed=last_accessed
        )

        # If refreshing access, update last_accessed and boost decay score
        if refresh:
            last_accessed = time.time()
            # Refresh boosts decay score
            new_decay = min(1.0, new_decay + self.config.access_refresh * (1.0 - new_decay))

        # Update database
        with self.store._transaction() as conn:
            conn.execute(
                "UPDATE events SET decay_score = ?, last_accessed = ? WHERE id = ?",
                (new_decay, last_accessed, event_id)
            )

        return new_decay

    def update_all_decay_scores(self, batch_size: int = 1000) -> Dict[str, int]:
        """
        Update decay scores for all events in the database.

        Args:
            batch_size: Number of events to process at once

        Returns:
            Statistics about the update
        """
        logger.info("[decay] Starting decay score update for all events")

        conn = self.store._get_connection()

        # Get total event count
        cursor = conn.execute("SELECT COUNT(*) FROM events")
        total_events = cursor.fetchone()[0]

        updated_count = 0
        deleted_count = 0

        # Process in batches
        offset = 0
        while offset < total_events:
            # Get batch of events
            cursor = conn.execute(
                "SELECT id, timestamp, event_type, confidence, metadata, last_accessed, decay_score FROM events LIMIT ? OFFSET ?",
                (batch_size, offset)
            )

            events_batch = cursor.fetchall()
            if not events_batch:
                break

            # Update decay scores
            updates = []
            deletes = []

            for row in events_batch:
                event_id = row['id']

                # Reconstruct minimal event for classification
                metadata = json.loads(row['metadata']) if row['metadata'] else {}

                event = Event(
                    id=event_id,
                    timestamp=row['timestamp'],
                    event_type=EventType(row['event_type']),
                    confidence=row['confidence'],
                    metadata=metadata
                )

                # Classify sector
                sector = self.classify_event_sector(event)
                importance = event.confidence or 0.5

                # Calculate new decay
                new_decay = self.calculate_decay_score(
                    created_timestamp=event.timestamp,
                    sector=sector,
                    importance=importance,
                    last_accessed=row['last_accessed']
                )

                # Check if should be deleted
                if new_decay < self.config.deletion_threshold:
                    deletes.append(event_id)
                else:
                    updates.append((new_decay, event_id))

            # Execute batch updates
            if updates:
                with self.store._transaction() as conn:
                    conn.executemany(
                        "UPDATE events SET decay_score = ? WHERE id = ?",
                        updates
                    )
                    updated_count += len(updates)

            # Execute batch deletes
            if deletes:
                with self.store._transaction() as conn:
                    conn.executemany(
                        "DELETE FROM events WHERE id = ?",
                        [(eid,) for eid in deletes]
                    )
                    deleted_count += len(deletes)

            offset += batch_size

            # Log progress
            if offset % (batch_size * 10) == 0:
                logger.info(f"[decay] Processed {offset}/{total_events} events")

        stats = {
            "total_events": total_events,
            "updated": updated_count,
            "deleted": deleted_count,
            "remaining": updated_count
        }

        logger.info(f"[decay] Decay update complete: {stats}")
        return stats

    def get_decay_statistics(self) -> Dict[str, any]:
        """
        Get statistics about memory decay.

        Returns:
            Dictionary with decay statistics
        """
        conn = self.store._get_connection()

        stats = {}

        # Overall decay distribution
        cursor = conn.execute("""
            SELECT
                COUNT(*) as total,
                AVG(decay_score) as avg_decay,
                MIN(decay_score) as min_decay,
                MAX(decay_score) as max_decay
            FROM events
            WHERE decay_score IS NOT NULL
        """)
        row = cursor.fetchone()
        if row:
            stats['overall'] = {
                'total_events': row['total'],
                'avg_decay': row['avg_decay'],
                'min_decay': row['min_decay'],
                'max_decay': row['max_decay']
            }

        # Decay by event type
        cursor = conn.execute("""
            SELECT
                event_type,
                COUNT(*) as count,
                AVG(decay_score) as avg_decay
            FROM events
            WHERE decay_score IS NOT NULL
            GROUP BY event_type
            ORDER BY avg_decay DESC
        """)

        stats['by_type'] = {}
        for row in cursor.fetchall():
            stats['by_type'][row['event_type']] = {
                'count': row['count'],
                'avg_decay': row['avg_decay']
            }

        # Events near deletion threshold
        cursor = conn.execute(
            "SELECT COUNT(*) FROM events WHERE decay_score < ?",
            (self.config.deletion_threshold * 2,)
        )
        stats['near_deletion'] = cursor.fetchone()[0]

        return stats
