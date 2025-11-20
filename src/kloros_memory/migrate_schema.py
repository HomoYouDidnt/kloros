"""
Schema migration utility for KLoROS memory database.

Safely adds new columns to existing database without losing data.
"""

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def migrate_memory_database(db_path: Path = Path("~/.kloros/memory.db")):
    """
    Migrate KLoROS memory database to latest schema.

    Adds new columns for:
    - Phase 1: Semantic embeddings
    - Phase 2: Memory decay
    - Phase 3: Graph edges (new table)
    - Phase 4: Emotional memory
    - Phase 5: Procedural memory (new table)
    - Phase 6: Reflective memory (new table)
    """
    db_path = db_path.expanduser()

    if not db_path.exists():
        print(f"Database doesn't exist yet: {db_path}")
        print("It will be created with the new schema on first use.")
        return

    print(f"Migrating database: {db_path}")
    conn = sqlite3.connect(db_path)

    try:
        # Get existing columns in events table
        cursor = conn.execute("PRAGMA table_info(events)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        print(f"Existing events columns: {len(existing_columns)}")

        # Add new columns to events table
        new_columns_events = [
            ("embedding_vector", "BLOB"),
            ("embedding_model", "TEXT"),
            ("decay_score", "REAL DEFAULT 1.0"),
            ("last_accessed", "REAL"),
            ("sentiment_score", "REAL"),
            ("emotion_type", "TEXT"),
        ]

        added_count = 0
        for col_name, col_type in new_columns_events:
            if col_name not in existing_columns:
                try:
                    conn.execute(f"ALTER TABLE events ADD COLUMN {col_name} {col_type}")
                    print(f"  ✓ Added events.{col_name}")
                    added_count += 1
                except sqlite3.OperationalError as e:
                    print(f"  ✗ Failed to add events.{col_name}: {e}")

        # Get existing columns in episode_summaries table
        cursor = conn.execute("PRAGMA table_info(episode_summaries)")
        existing_columns_summaries = {row[1] for row in cursor.fetchall()}

        # Add new columns to episode_summaries table
        new_columns_summaries = [
            ("embedding_vector", "BLOB"),
            ("embedding_model", "TEXT"),
            ("decay_score", "REAL DEFAULT 1.0"),
            ("last_accessed", "REAL"),
        ]

        for col_name, col_type in new_columns_summaries:
            if col_name not in existing_columns_summaries:
                try:
                    conn.execute(f"ALTER TABLE episode_summaries ADD COLUMN {col_name} {col_type}")
                    print(f"  ✓ Added episode_summaries.{col_name}")
                    added_count += 1
                except sqlite3.OperationalError as e:
                    print(f"  ✗ Failed to add episode_summaries.{col_name}: {e}")

        # Create new tables if they don't exist
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}

        # Memory edges table (Phase 3)
        if "memory_edges" not in existing_tables:
            conn.execute("""
                CREATE TABLE memory_edges (
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
            print("  ✓ Created memory_edges table")
            added_count += 1

        # Procedural memories table (Phase 5)
        if "procedural_memories" not in existing_tables:
            conn.execute("""
                CREATE TABLE procedural_memories (
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
            print("  ✓ Created procedural_memories table")
            added_count += 1

        # Reflections table (Phase 6)
        if "reflections" not in existing_tables:
            conn.execute("""
                CREATE TABLE reflections (
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
            print("  ✓ Created reflections table")
            added_count += 1

        # Add new indexes
        new_indexes = [
            "CREATE INDEX IF NOT EXISTS idx_events_decay ON events(decay_score)",
            "CREATE INDEX IF NOT EXISTS idx_summaries_decay ON episode_summaries(decay_score)",
            "CREATE INDEX IF NOT EXISTS idx_edges_source ON memory_edges(source_id, source_type)",
            "CREATE INDEX IF NOT EXISTS idx_edges_target ON memory_edges(target_id, target_type)",
            "CREATE INDEX IF NOT EXISTS idx_edges_type ON memory_edges(edge_type)",
            "CREATE INDEX IF NOT EXISTS idx_procedural_skill ON procedural_memories(skill_id)",
            "CREATE INDEX IF NOT EXISTS idx_procedural_used ON procedural_memories(last_used)",
            "CREATE INDEX IF NOT EXISTS idx_reflections_type ON reflections(pattern_type)",
            "CREATE INDEX IF NOT EXISTS idx_reflections_confidence ON reflections(confidence)",
        ]

        for idx_sql in new_indexes:
            try:
                conn.execute(idx_sql)
            except sqlite3.OperationalError:
                pass  # Index might already exist

        conn.commit()
        print(f"\n✓ Migration complete! Added {added_count} schema changes")

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("~/.kloros/memory.db")
    migrate_memory_database(db_path)
