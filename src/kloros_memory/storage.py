"""
SQLite storage layer for KLoROS episodic-semantic memory system.

Provides persistent storage with WAL mode for concurrent access,
proper indexing for performance, and transaction safety.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

from .models import Event, Episode, EpisodeSummary, EventType


class MemoryStore:
    """
    SQLite-based storage for KLoROS memory system.

    Features:
    - WAL mode for concurrent read/write access
    - Proper indexing for fast queries
    - Transaction safety with context managers
    - JSON serialization for complex metadata
    """

    def __init__(self, db_path: Union[str, Path] = "~/.kloros/memory.db"):
        """
        Initialize the memory store.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection'):
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0,
                isolation_level=None  # Autocommit mode
            )
            conn.row_factory = sqlite3.Row  # Enable column access by name

            # Enable WAL mode for concurrent access
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=10000")
            conn.execute("PRAGMA temp_store=MEMORY")

            self._local.connection = conn

        return self._local.connection

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database transactions."""
        conn = self._get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def _init_database(self) -> None:
        """Initialize database schema."""
        with self._transaction() as conn:
            # Events table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    conversation_id TEXT,
                    confidence REAL,
                    token_count INTEGER,
                    created_at REAL NOT NULL,
                    -- Phase 1: Semantic embeddings
                    embedding_vector BLOB,
                    embedding_model TEXT,
                    -- Phase 2: Memory decay
                    decay_score REAL DEFAULT 1.0,
                    last_accessed REAL,
                    -- Phase 4: Emotional memory
                    sentiment_score REAL,
                    emotion_type TEXT
                )
            """)

            # Episodes table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time REAL NOT NULL,
                    end_time REAL NOT NULL,
                    conversation_id TEXT NOT NULL,
                    event_count INTEGER NOT NULL DEFAULT 0,
                    token_count INTEGER NOT NULL DEFAULT 0,
                    is_condensed BOOLEAN NOT NULL DEFAULT 0,
                    condensed_at REAL,
                    created_at REAL NOT NULL
                )
            """)

            # Episode summaries table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episode_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_id INTEGER NOT NULL,
                    summary_text TEXT NOT NULL,
                    key_topics TEXT NOT NULL DEFAULT '[]',
                    emotional_tone TEXT,
                    importance_score REAL NOT NULL DEFAULT 0.5,
                    created_at REAL NOT NULL,
                    model_used TEXT NOT NULL DEFAULT 'meta-llama/Llama-3.1-8B-Instruct',
                    token_budget_used INTEGER NOT NULL DEFAULT 0,
                    -- Phase 1: Semantic embeddings
                    embedding_vector BLOB,
                    embedding_model TEXT,
                    -- Phase 2: Memory decay
                    decay_score REAL DEFAULT 1.0,
                    last_accessed REAL,
                    FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE
                )
            """)

            # Phase 3: Memory graph edges
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER NOT NULL,
                    target_id INTEGER NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'event',
                    target_type TEXT NOT NULL DEFAULT 'event',
                    edge_type TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 1.0,
                    decay_rate REAL NOT NULL DEFAULT 0.1,
                    created_at REAL NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
            """)

            # Phase 5: Procedural memory
            conn.execute("""
                CREATE TABLE IF NOT EXISTS procedural_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_id TEXT NOT NULL UNIQUE,
                    pattern TEXT NOT NULL,
                    description TEXT,
                    usage_count INTEGER NOT NULL DEFAULT 1,
                    last_used REAL NOT NULL,
                    success_rate REAL NOT NULL DEFAULT 1.0,
                    created_at REAL NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
            """)

            # Phase 6: Reflective memory
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reflections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_type TEXT NOT NULL,
                    insight TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.5,
                    evidence_count INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    last_observed REAL NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS failed_study_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_data TEXT NOT NULL,
                    error_message TEXT,
                    failed_at REAL NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending'
                )
            """)

            # Create indexes for performance
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)",
                "CREATE INDEX IF NOT EXISTS idx_events_conversation ON events(conversation_id)",
                "CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)",
                "CREATE INDEX IF NOT EXISTS idx_events_decay ON events(decay_score)",
                "CREATE INDEX IF NOT EXISTS idx_episodes_time ON episodes(start_time, end_time)",
                "CREATE INDEX IF NOT EXISTS idx_episodes_conversation ON episodes(conversation_id)",
                "CREATE INDEX IF NOT EXISTS idx_summaries_episode ON episode_summaries(episode_id)",
                "CREATE INDEX IF NOT EXISTS idx_summaries_importance ON episode_summaries(importance_score)",
                "CREATE INDEX IF NOT EXISTS idx_summaries_created ON episode_summaries(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_summaries_decay ON episode_summaries(decay_score)",
                "CREATE INDEX IF NOT EXISTS idx_edges_source ON memory_edges(source_id, source_type)",
                "CREATE INDEX IF NOT EXISTS idx_edges_target ON memory_edges(target_id, target_type)",
                "CREATE INDEX IF NOT EXISTS idx_edges_type ON memory_edges(edge_type)",
                "CREATE INDEX IF NOT EXISTS idx_procedural_skill ON procedural_memories(skill_id)",
                "CREATE INDEX IF NOT EXISTS idx_procedural_used ON procedural_memories(last_used)",
                "CREATE INDEX IF NOT EXISTS idx_reflections_type ON reflections(pattern_type)",
                "CREATE INDEX IF NOT EXISTS idx_reflections_confidence ON reflections(confidence)",
                "CREATE INDEX IF NOT EXISTS idx_failed_study_status ON failed_study_events(status)",
                "CREATE INDEX IF NOT EXISTS idx_failed_study_failed_at ON failed_study_events(failed_at)",
            ]

            for idx_sql in indexes:
                conn.execute(idx_sql)

    def store_event(self, event: Event) -> int:
        """
        Store an event in the database.

        Args:
            event: Event to store

        Returns:
            The ID of the stored event
        """
        with self._transaction() as conn:
            cursor = conn.execute("""
                INSERT INTO events (
                    timestamp, event_type, content, metadata,
                    conversation_id, confidence, token_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.timestamp,
                event.event_type if isinstance(event.event_type, str) else event.event_type.value,
                event.content,
                json.dumps(event.metadata),
                event.conversation_id,
                event.confidence,
                event.token_count,
                time.time()
            ))

            return cursor.lastrowid

    def get_events(
        self,
        limit: int = 100,
        offset: int = 0,
        conversation_id: Optional[str] = None,
        event_type: Optional[EventType] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> List[Event]:
        """
        Retrieve events from the database.

        Args:
            limit: Maximum number of events to return
            offset: Number of events to skip
            conversation_id: Filter by conversation ID
            event_type: Filter by event type
            start_time: Filter by minimum timestamp
            end_time: Filter by maximum timestamp

        Returns:
            List of events matching the criteria
        """
        query = "SELECT * FROM events WHERE 1=1"
        params = []

        if conversation_id:
            query += " AND conversation_id = ?"
            params.append(conversation_id)

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type if isinstance(event_type, str) else event_type.value)

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)

        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        conn = self._get_connection()
        cursor = conn.execute(query, params)

        events = []
        for row in cursor.fetchall():
            events.append(Event(
                id=row['id'],
                timestamp=row['timestamp'],
                event_type=EventType(row['event_type']),
                content=row['content'],
                metadata=json.loads(row['metadata']) if row['metadata'] else {},
                conversation_id=row['conversation_id'],
                confidence=row['confidence'],
                token_count=row['token_count']
            ))

        return events

    def get_event(self, event_id: int) -> Optional[Event]:
        """
        Retrieve a single event by ID.

        Args:
            event_id: ID of the event to retrieve

        Returns:
            The event if found, None otherwise
        """
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        row = cursor.fetchone()

        if row:
            return Event(
                id=row['id'],
                timestamp=row['timestamp'],
                event_type=EventType(row['event_type']),
                content=row['content'],
                metadata=json.loads(row['metadata']) if row['metadata'] else {},
                conversation_id=row['conversation_id'],
                confidence=row['confidence'],
                token_count=row['token_count']
            )

        return None

    def get_events_by_type(
        self,
        event_type: EventType,
        limit: int = 100,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> List[Event]:
        """
        Retrieve events of a specific type.

        Convenience method for filtering by event type with optional time range.

        Args:
            event_type: Type of events to retrieve
            limit: Maximum number of events to return
            start_time: Optional minimum timestamp
            end_time: Optional maximum timestamp

        Returns:
            List of events matching the type and time criteria
        """
        return self.get_events(
            limit=limit,
            event_type=event_type,
            start_time=start_time,
            end_time=end_time
        )

    def store_episode(self, episode: Episode) -> int:
        """
        Store an episode in the database.

        Args:
            episode: Episode to store

        Returns:
            The ID of the stored episode
        """
        with self._transaction() as conn:
            cursor = conn.execute("""
                INSERT INTO episodes (
                    start_time, end_time, conversation_id, event_count,
                    token_count, is_condensed, condensed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                episode.start_time,
                episode.end_time,
                episode.conversation_id,
                episode.event_count,
                episode.token_count,
                episode.is_condensed,
                episode.condensed_at,
                time.time()
            ))

            return cursor.lastrowid

    def get_episodes(
        self,
        limit: int = 50,
        offset: int = 0,
        conversation_id: Optional[str] = None,
        is_condensed: Optional[bool] = None
    ) -> List[Episode]:
        """
        Retrieve episodes from the database.

        Args:
            limit: Maximum number of episodes to return
            offset: Number of episodes to skip
            conversation_id: Filter by conversation ID
            is_condensed: Filter by condensation status

        Returns:
            List of episodes matching the criteria
        """
        query = "SELECT * FROM episodes WHERE 1=1"
        params = []

        if conversation_id:
            query += " AND conversation_id = ?"
            params.append(conversation_id)

        if is_condensed is not None:
            query += " AND is_condensed = ?"
            params.append(is_condensed)

        query += " ORDER BY start_time DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        conn = self._get_connection()
        cursor = conn.execute(query, params)

        episodes = []
        for row in cursor.fetchall():
            episodes.append(Episode(
                id=row['id'],
                start_time=row['start_time'],
                end_time=row['end_time'],
                conversation_id=row['conversation_id'],
                event_count=row['event_count'],
                token_count=row['token_count'],
                is_condensed=bool(row['is_condensed']),
                condensed_at=row['condensed_at']
            ))

        return episodes

    def store_summary(self, summary: EpisodeSummary) -> int:
        """
        Store an episode summary in the database.

        Args:
            summary: Summary to store

        Returns:
            The ID of the stored summary
        """
        with self._transaction() as conn:
            cursor = conn.execute("""
                INSERT INTO episode_summaries (
                    episode_id, summary_text, key_topics, emotional_tone,
                    importance_score, created_at, model_used, token_budget_used
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                summary.episode_id,
                summary.summary_text,
                json.dumps(summary.key_topics),
                summary.emotional_tone,
                summary.importance_score,
                summary.created_at,
                summary.model_used,
                summary.token_budget_used
            ))

            return cursor.lastrowid

    def get_summaries(
        self,
        limit: int = 20,
        offset: int = 0,
        episode_id: Optional[int] = None,
        min_importance: float = 0.0
    ) -> List[EpisodeSummary]:
        """
        Retrieve episode summaries from the database.

        Args:
            limit: Maximum number of summaries to return
            offset: Number of summaries to skip
            episode_id: Filter by episode ID
            min_importance: Minimum importance score

        Returns:
            List of summaries matching the criteria
        """
        query = "SELECT * FROM episode_summaries WHERE importance_score >= ?"
        params = [min_importance]

        if episode_id:
            query += " AND episode_id = ?"
            params.append(episode_id)

        query += " ORDER BY importance_score DESC, created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        conn = self._get_connection()
        cursor = conn.execute(query, params)

        summaries = []
        for row in cursor.fetchall():
            summaries.append(EpisodeSummary(
                id=row['id'],
                episode_id=row['episode_id'],
                summary_text=row['summary_text'],
                key_topics=json.loads(row['key_topics']) if row['key_topics'] else [],
                emotional_tone=row['emotional_tone'],
                importance_score=row['importance_score'],
                created_at=row['created_at'],
                model_used=row['model_used'],
                token_budget_used=row['token_budget_used']
            ))

        return summaries

    def mark_episode_condensed(self, episode_id: int) -> None:
        """
        Mark an episode as condensed.

        Args:
            episode_id: ID of the episode to mark
        """
        with self._transaction() as conn:
            conn.execute("""
                UPDATE episodes
                SET is_condensed = 1, condensed_at = ?
                WHERE id = ?
            """, (time.time(), episode_id))

    def get_stats(self) -> Dict[str, Any]:
        """
        Get database statistics.

        Returns:
            Dictionary with various statistics
        """
        conn = self._get_connection()

        stats = {}

        # Event counts
        cursor = conn.execute("SELECT COUNT(*) FROM events")
        stats['total_events'] = cursor.fetchone()[0]

        # Episode counts
        cursor = conn.execute("SELECT COUNT(*) FROM episodes")
        stats['total_episodes'] = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM episodes WHERE is_condensed = 1")
        stats['condensed_episodes'] = cursor.fetchone()[0]

        # Summary counts
        cursor = conn.execute("SELECT COUNT(*) FROM episode_summaries")
        stats['total_summaries'] = cursor.fetchone()[0]

        # Recent activity
        recent_time = time.time() - 86400  # Last 24 hours
        cursor = conn.execute("SELECT COUNT(*) FROM events WHERE timestamp >= ?", (recent_time,))
        stats['events_24h'] = cursor.fetchone()[0]

        # Database size
        cursor = conn.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
        row = cursor.fetchone()
        stats['db_size_bytes'] = row[0] if row else 0

        return stats

    def cleanup_old_events(self, keep_days: int = 30) -> int:
        """
        Clean up old events beyond the retention period.

        Args:
            keep_days: Number of days to keep events

        Returns:
            Number of events deleted
        """
        cutoff_time = time.time() - (keep_days * 86400)

        with self._transaction() as conn:
            cursor = conn.execute("DELETE FROM events WHERE timestamp < ?", (cutoff_time,))
            deleted_count = cursor.rowcount

            # Clean up episodes that no longer have events
            conn.execute("""
                DELETE FROM episodes
                WHERE id NOT IN (
                    SELECT DISTINCT conversation_id
                    FROM events
                    WHERE conversation_id IS NOT NULL
                )
            """)

            return deleted_count

    def vacuum_database(self) -> None:
        """Vacuum the database to reclaim space and optimize performance."""
        conn = self._get_connection()
        conn.execute("VACUUM")

    def close(self) -> None:
        """Close the database connection."""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            delattr(self._local, 'connection')