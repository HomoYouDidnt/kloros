"""
Comprehensive tests for Study Memory Bridge.

Tests all components: DeadLetterQueue, tiered formatting, signal handling,
error recovery, and investigation triggers.
"""

import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call

from kloros_study_memory_bridge import DeadLetterQueue, StudyMemoryBridge
from src.cognition.mind.memory.models import EventType


class TestDeadLetterQueue(unittest.TestCase):
    """Test DeadLetterQueue helper class."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_memory.db")
        self.dlq = DeadLetterQueue(db_path=self.db_path)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_init_creates_table(self):
        """Test that initialization creates the failed_study_events table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='failed_study_events'")
        result = cursor.fetchone()

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "failed_study_events")

        conn.close()

    def test_store_failed_event(self):
        """Test storing a failed event."""
        signal_data = {
            "signal": "LEARNING_COMPLETED",
            "facts": {
                "component_id": "test_component",
                "study_depth": 2
            }
        }

        event_id = self.dlq.store(signal_data, error="Test error")

        self.assertIsInstance(event_id, int)
        self.assertGreater(event_id, 0)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT signal_data, error_message, status FROM failed_study_events WHERE id = ?", (event_id,))
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(json.loads(row[0]), signal_data)
        self.assertEqual(row[1], "Test error")
        self.assertEqual(row[2], "pending")

    def test_get_pending(self):
        """Test retrieving pending failed events."""
        signal_data_1 = {"component_id": "comp1"}
        signal_data_2 = {"component_id": "comp2"}

        id1 = self.dlq.store(signal_data_1, error="Error 1")
        id2 = self.dlq.store(signal_data_2, error="Error 2")

        pending = self.dlq.get_pending(limit=10)

        self.assertEqual(len(pending), 2)
        self.assertEqual(pending[0][0], id1)
        self.assertEqual(pending[0][1], signal_data_1)
        self.assertEqual(pending[1][0], id2)
        self.assertEqual(pending[1][1], signal_data_2)

    def test_get_pending_respects_max_retries(self):
        """Test that get_pending filters by max_retries."""
        signal_data_1 = {"component_id": "comp1"}
        signal_data_2 = {"component_id": "comp2"}
        signal_data_3 = {"component_id": "comp3"}

        id1 = self.dlq.store(signal_data_1, error="Error 1")
        id2 = self.dlq.store(signal_data_2, error="Error 2")
        id3 = self.dlq.store(signal_data_3, error="Error 3")

        for _ in range(3):
            self.dlq.increment_retry(id1)

        for _ in range(5):
            self.dlq.increment_retry(id2)

        pending = self.dlq.get_pending(limit=10, max_retries=5)

        self.assertEqual(len(pending), 2)
        event_ids = [event[0] for event in pending]
        self.assertIn(id1, event_ids)
        self.assertIn(id3, event_ids)
        self.assertNotIn(id2, event_ids)

    def test_mark_resolved(self):
        """Test marking a failed event as resolved."""
        signal_data = {"component_id": "test"}
        event_id = self.dlq.store(signal_data, error="Test error")

        self.dlq.mark_resolved(event_id)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM failed_study_events WHERE id = ?", (event_id,))
        status = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(status, "resolved")

    def test_increment_retry(self):
        """Test incrementing retry count."""
        signal_data = {"component_id": "test"}
        event_id = self.dlq.store(signal_data, error="Test error")

        self.dlq.increment_retry(event_id)
        self.dlq.increment_retry(event_id)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT retry_count FROM failed_study_events WHERE id = ?", (event_id,))
        retry_count = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(retry_count, 2)

    def test_get_statistics(self):
        """Test getting dead letter queue statistics."""
        self.dlq.store({"id": "1"}, error="Error 1")
        self.dlq.store({"id": "2"}, error="Error 2")
        event_id = self.dlq.store({"id": "3"}, error="Error 3")

        self.dlq.mark_resolved(event_id)

        stats = self.dlq.get_statistics()

        self.assertEqual(stats["pending"], 2)
        self.assertEqual(stats["resolved"], 1)
        self.assertEqual(stats["investigating"], 0)


class TestTieredFormatting(unittest.TestCase):
    """Test tiered detail formatting based on study depth."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_memory.db")

        with patch('kloros_study_memory_bridge.MemoryLogger'):
            with patch('kloros_study_memory_bridge.UMNPub'):
                with patch('kloros_study_memory_bridge.UMNSub'):
                    self.bridge = StudyMemoryBridge()
                    self.bridge.dead_letter = DeadLetterQueue(db_path=self.db_path)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_format_depth_0_1(self):
        """Test formatting for shallow scan (depth 0-1)."""
        signal_data = {
            "facts": {
                "study_depth": 1,
                "component_id": "module:test.py",
                "component_type": "module"
            }
        }

        result = self.bridge._format_by_depth(signal_data)

        self.assertEqual(result, "Scanned component module:test.py (type: module)")

    def test_format_depth_2(self):
        """Test formatting for standard study (depth 2)."""
        signal_data = {
            "facts": {
                "study_depth": 2,
                "component_id": "module:test.py",
                "component_type": "module",
                "purpose": "Test module for unit testing",
                "capabilities": ["TestClass", "5 test functions", "mock support"]
            }
        }

        result = self.bridge._format_by_depth(signal_data)

        expected = "Studied component module:test.py: Test module for unit testing. Capabilities: TestClass, 5 test functions, mock support"
        self.assertEqual(result, expected)

    def test_format_depth_3(self):
        """Test formatting for deep analysis (depth 3)."""
        signal_data = {
            "facts": {
                "study_depth": 3,
                "component_id": "module:test.py",
                "component_type": "module",
                "purpose": "Test module for unit testing",
                "capabilities": ["TestClass", "5 test functions"],
                "dependencies": ["unittest", "mock", "pytest"],
                "config_params": {"TEST_MODE": "1", "DEBUG": "0"},
                "interesting_findings": "Uses pytest fixtures",
                "potential_improvements": "Add more edge cases"
            }
        }

        result = self.bridge._format_by_depth(signal_data)

        self.assertIn("Analyzed component module:test.py", result)
        self.assertIn("Test module for unit testing", result)
        self.assertIn("Capabilities: TestClass, 5 test functions", result)
        self.assertIn("Dependencies: unittest, mock, pytest", result)
        self.assertIn("Config parameters: TEST_MODE, DEBUG", result)
        self.assertIn("Findings: Uses pytest fixtures", result)
        self.assertIn("Improvements: Add more edge cases", result)

    def test_format_missing_fields(self):
        """Test formatting with missing optional fields."""
        signal_data = {
            "facts": {
                "study_depth": 3,
                "component_id": "module:minimal.py",
                "component_type": "module",
                "purpose": "Minimal module"
            }
        }

        result = self.bridge._format_by_depth(signal_data)

        self.assertIn("Analyzed component module:minimal.py", result)
        self.assertIn("Minimal module", result)


class TestStudyMemoryBridge(unittest.TestCase):
    """Test StudyMemoryBridge daemon class."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_memory.db")

        self.mock_logger = Mock()
        self.mock_publisher = Mock()
        self.mock_subscriber = Mock()

        with patch('kloros_study_memory_bridge.MemoryLogger', return_value=self.mock_logger):
            with patch('kloros_study_memory_bridge.UMNPub', return_value=self.mock_publisher):
                with patch('kloros_study_memory_bridge.UMNSub', return_value=self.mock_subscriber):
                    self.bridge = StudyMemoryBridge()
                    self.bridge.dead_letter = DeadLetterQueue(db_path=self.db_path)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_initialization(self):
        """Test bridge initialization."""
        self.assertIsNotNone(self.bridge.memory_logger)
        self.assertIsNotNone(self.bridge.dead_letter)
        self.assertIsNotNone(self.bridge.publisher)
        self.assertIsNotNone(self.bridge.subscriber)
        self.assertTrue(self.bridge.running)

    def test_successful_learning_completed(self):
        """Test successful processing of LEARNING_COMPLETED signal."""
        signal_data = {
            "signal": "LEARNING_COMPLETED",
            "ecosystem": "introspection",
            "intensity": 1.5,
            "facts": {
                "source": "component_study",
                "component_id": "module:test.py",
                "study_depth": 2,
                "component_type": "module",
                "purpose": "Test module",
                "capabilities": ["TestClass", "5 functions"]
            }
        }

        self.bridge._on_learning_completed(signal_data)

        self.mock_logger.log_event.assert_called_once()
        call_args = self.mock_logger.log_event.call_args

        self.assertEqual(call_args[1]['event_type'], EventType.DOCUMENTATION_LEARNED)
        self.assertIn("Studied component module:test.py", call_args[1]['content'])
        self.assertEqual(call_args[1]['metadata'], signal_data['facts'])

    def test_failed_learning_completed(self):
        """Test error handling when memory logging fails."""
        self.mock_logger.log_event.side_effect = Exception("Memory system unavailable")

        signal_data = {
            "signal": "LEARNING_COMPLETED",
            "facts": {
                "component_id": "module:failing.py",
                "study_depth": 2
            }
        }

        with self.assertRaises(Exception):
            self.bridge._on_learning_completed(signal_data)

        pending = self.bridge.dead_letter.get_pending(limit=10)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0][1], signal_data)

    def test_investigation_trigger(self):
        """Test that investigation is triggered on failure."""
        self.mock_logger.log_event.side_effect = Exception("Test error")

        signal_data = {
            "signal": "LEARNING_COMPLETED",
            "facts": {
                "component_id": "module:test.py",
                "study_depth": 2
            }
        }

        with self.assertRaises(Exception):
            self.bridge._on_learning_completed(signal_data)

        self.mock_publisher.emit.assert_called_once()
        call_args = self.mock_publisher.emit.call_args

        self.assertEqual(call_args[1]['signal'], "CAPABILITY_GAP_FOUND")
        self.assertEqual(call_args[1]['ecosystem'], "introspection")
        self.assertEqual(call_args[1]['intensity'], 2.0)
        self.assertEqual(call_args[1]['facts']['source'], "study_memory_bridge")
        self.assertEqual(call_args[1]['facts']['capability'], "memory_logging")
        self.assertEqual(call_args[1]['facts']['error_type'], "Exception")
        self.assertIn("Test error", call_args[1]['facts']['error_message'])

    def test_replay_failed_events(self):
        """Test replaying failed events from dead letter queue."""
        signal_data = {
            "signal": "LEARNING_COMPLETED",
            "facts": {
                "component_id": "module:replay.py",
                "study_depth": 2,
                "component_type": "module",
                "purpose": "Replay test"
            }
        }

        event_id = self.bridge.dead_letter.store(signal_data, error="Temporary failure")

        self.mock_logger.log_event.side_effect = None
        self.mock_logger.log_event.return_value = None

        replayed = self.bridge.replay_failed_events()

        self.assertEqual(replayed, 1)

        pending = self.bridge.dead_letter.get_pending(limit=10)
        self.assertEqual(len(pending), 0)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM failed_study_events WHERE id = ?", (event_id,))
        status = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(status, "resolved")

    def test_replay_failed_events_with_continued_failure(self):
        """Test replay when event continues to fail."""
        signal_data = {
            "signal": "LEARNING_COMPLETED",
            "facts": {
                "component_id": "module:persistent_failure.py",
                "study_depth": 2
            }
        }

        event_id = self.bridge.dead_letter.store(signal_data, error="Persistent failure")

        self.mock_logger.log_event.side_effect = Exception("Still failing")

        replayed = self.bridge.replay_failed_events()

        self.assertEqual(replayed, 0)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT retry_count FROM failed_study_events WHERE id = ?", (event_id,))
        retry_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM failed_study_events WHERE status = 'pending'")
        pending_count = cursor.fetchone()[0]

        conn.close()

        self.assertEqual(retry_count, 1)
        self.assertEqual(pending_count, 1)

    def test_replay_does_not_trigger_investigation(self):
        """Test that replay failures don't trigger investigation or duplicate dead letter entries."""
        signal_data = {
            "signal": "LEARNING_COMPLETED",
            "facts": {
                "component_id": "module:replay_failure.py",
                "study_depth": 2
            }
        }

        event_id = self.bridge.dead_letter.store(signal_data, error="Initial failure")

        self.mock_logger.log_event.side_effect = Exception("Replay failure")

        initial_emit_count = self.mock_publisher.emit.call_count

        replayed = self.bridge.replay_failed_events()

        self.assertEqual(replayed, 0)

        self.assertEqual(self.mock_publisher.emit.call_count, initial_emit_count)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM failed_study_events")
        total_events = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(total_events, 1)

    def test_shutdown(self):
        """Test clean shutdown of bridge."""
        self.bridge.shutdown()

        self.mock_logger.close.assert_called_once()
        self.mock_subscriber.close.assert_called_once()
        self.mock_publisher.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
