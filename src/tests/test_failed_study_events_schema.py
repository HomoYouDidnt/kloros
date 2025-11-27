#!/usr/bin/env python3

import json
import sqlite3
import time
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from src.cognition.mind.memory.storage import MemoryStore


def test_failed_study_events_schema():
    print("\n" + "="*70)
    print("Testing failed_study_events Schema Implementation")
    print("="*70 + "\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        test_db_path = Path(tmpdir) / "test_memory.db"
        print(f"Using test database: {test_db_path}\n")

        store = MemoryStore(db_path=test_db_path)

        print("1. Verifying table was created...")
        conn = store._get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='failed_study_events'"
        )
        table_exists = cursor.fetchone() is not None

        if table_exists:
            print("    failed_study_events table exists")
        else:
            print("    failed_study_events table not found")
            return False

        print("\n2. Verifying table schema...")
        cursor = conn.execute("PRAGMA table_info(failed_study_events)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        expected_columns = {
            'id': 'INTEGER',
            'signal_data': 'TEXT',
            'error_message': 'TEXT',
            'failed_at': 'REAL',
            'retry_count': 'INTEGER',
            'status': 'TEXT'
        }

        schema_ok = True
        for col_name, col_type in expected_columns.items():
            if col_name in columns:
                print(f"    Column '{col_name}' ({col_type}) exists")
            else:
                print(f"    Column '{col_name}' missing")
                schema_ok = False

        if not schema_ok:
            return False

        print("\n3. Verifying indexes...")
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='failed_study_events'"
        )
        indexes = [row[0] for row in cursor.fetchall()]

        expected_indexes = ['idx_failed_study_status', 'idx_failed_study_failed_at']

        indexes_ok = True
        for idx_name in expected_indexes:
            if idx_name in indexes:
                print(f"    Index '{idx_name}' exists")
            else:
                print(f"    Index '{idx_name}' missing")
                indexes_ok = False

        if not indexes_ok:
            return False

        print("\n4. Testing insert operation...")
        test_signal_data = {
            "source": "component_study",
            "component_id": "module:test_component.py",
            "study_depth": 2,
            "component_type": "module",
            "file_path": "/home/kloros/src/test_component.py",
            "studied_at": time.time()
        }

        try:
            cursor = conn.execute("""
                INSERT INTO failed_study_events (signal_data, error_message, failed_at, retry_count, status)
                VALUES (?, ?, ?, ?, ?)
            """, (
                json.dumps(test_signal_data),
                "Test error: Memory logger unavailable",
                time.time(),
                0,
                'pending'
            ))
            inserted_id = cursor.lastrowid
            print(f"    Successfully inserted record with ID: {inserted_id}")
        except Exception as e:
            print(f"    Insert failed: {e}")
            return False

        print("\n5. Testing query operation...")
        try:
            cursor = conn.execute("""
                SELECT id, signal_data, error_message, failed_at, retry_count, status
                FROM failed_study_events
                WHERE id = ?
            """, (inserted_id,))

            row = cursor.fetchone()
            if row:
                print(f"    Successfully retrieved record")
                print(f"     - ID: {row[0]}")
                print(f"     - Error: {row[2]}")
                print(f"     - Status: {row[5]}")
                print(f"     - Retry count: {row[4]}")

                retrieved_data = json.loads(row[1])
                if retrieved_data == test_signal_data:
                    print(f"    Signal data matches original")
                else:
                    print(f"    Signal data mismatch")
                    return False
            else:
                print(f"    Could not retrieve inserted record")
                return False
        except Exception as e:
            print(f"    Query failed: {e}")
            return False

        print("\n6. Testing update operation...")
        try:
            conn.execute("""
                UPDATE failed_study_events
                SET retry_count = ?, status = ?
                WHERE id = ?
            """, (1, 'investigating', inserted_id))

            cursor = conn.execute(
                "SELECT retry_count, status FROM failed_study_events WHERE id = ?",
                (inserted_id,)
            )
            row = cursor.fetchone()

            if row and row[0] == 1 and row[1] == 'investigating':
                print(f"    Successfully updated record")
                print(f"     - New retry count: {row[0]}")
                print(f"     - New status: {row[1]}")
            else:
                print(f"    Update verification failed")
                return False
        except Exception as e:
            print(f"    Update failed: {e}")
            return False

        print("\n7. Testing status filtering (index usage)...")
        try:
            for status_val in ['pending', 'investigating', 'resolved']:
                conn.execute("""
                    INSERT INTO failed_study_events (signal_data, error_message, failed_at, status)
                    VALUES (?, ?, ?, ?)
                """, (json.dumps({"test": status_val}), f"Error for {status_val}", time.time(), status_val))

            cursor = conn.execute(
                "SELECT COUNT(*) FROM failed_study_events WHERE status = 'pending'"
            )
            count = cursor.fetchone()[0]
            print(f"    Status filtering works (found {count} pending records)")

        except Exception as e:
            print(f"    Status filtering failed: {e}")
            return False

        print("\n8. Testing time-based queries (index usage)...")
        try:
            cutoff_time = time.time() - 60
            cursor = conn.execute(
                "SELECT COUNT(*) FROM failed_study_events WHERE failed_at > ?",
                (cutoff_time,)
            )
            count = cursor.fetchone()[0]
            print(f"    Time-based filtering works (found {count} recent records)")

        except Exception as e:
            print(f"    Time-based filtering failed: {e}")
            return False

        store.close()

    return True


def test_migration_on_existing_db():
    print("\n" + "="*70)
    print("Testing Migration on Existing Database")
    print("="*70 + "\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        test_db_path = Path(tmpdir) / "existing_memory.db"
        print(f"Using test database: {test_db_path}\n")

        print("1. Creating old-style database (without failed_study_events)...")
        conn = sqlite3.connect(test_db_path)
        conn.execute("""
            CREATE TABLE events (
                id INTEGER PRIMARY KEY,
                timestamp REAL NOT NULL,
                event_type TEXT NOT NULL,
                content TEXT
            )
        """)
        conn.commit()
        conn.close()
        print("    Old database created")

        print("\n2. Running migration...")
        from src.cognition.mind.memory.migrate_schema import migrate_memory_database
        try:
            migrate_memory_database(test_db_path)
            print("    Migration completed")
        except Exception as e:
            print(f"    Migration failed: {e}")
            return False

        print("\n3. Verifying failed_study_events table was added...")
        conn = sqlite3.connect(test_db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='failed_study_events'"
        )
        table_exists = cursor.fetchone() is not None
        conn.close()

        if table_exists:
            print("    failed_study_events table exists after migration")
        else:
            print("    failed_study_events table not found after migration")
            return False

    return True


if __name__ == "__main__":
    print("\n" + "="*70)
    print("Failed Study Events Schema Test Suite")
    print("="*70)

    test1_passed = test_failed_study_events_schema()
    test2_passed = test_migration_on_existing_db()

    print("\n" + "="*70)
    print("Test Results Summary")
    print("="*70)
    print(f"New database schema test: {' PASSED' if test1_passed else ' FAILED'}")
    print(f"Migration test: {' PASSED' if test2_passed else ' FAILED'}")
    print("="*70 + "\n")

    sys.exit(0 if (test1_passed and test2_passed) else 1)
