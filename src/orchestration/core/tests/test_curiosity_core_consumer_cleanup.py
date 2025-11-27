#!/usr/bin/env python3
"""
Tests for CuriosityCoreConsumerDaemon memory cleanup methods.

Tests Phase 1.1 implementation: _proactive_cleanup(), _emergency_cleanup(),
and enhanced _check_memory_usage() with automatic triggers.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parents[4]))
sys.path.insert(0, str(Path(__file__).parents[4] / "src"))

from src.orchestration.core.curiosity_core_consumer_daemon import CuriosityCoreConsumerDaemon


class TestMemoryCleanup(unittest.TestCase):
    """Test memory cleanup methods in CuriosityCoreConsumerDaemon."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_feed_path = Path(self.temp_dir) / "curiosity_feed.json"

        with patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED', self.test_feed_path):
            with patch('kloros.orchestration.curiosity_core_consumer_daemon.CapabilityEvaluator'):
                with patch('kloros.orchestration.curiosity_core_consumer_daemon.CuriosityCore'):
                    with patch('kloros.orchestration.curiosity_core_consumer_daemon.UMNSub'):
                        self.daemon = CuriosityCoreConsumerDaemon()
                        self.daemon.curiosity_core = Mock()
                        self.daemon.curiosity_core.semantic_store = Mock()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_test_feed(self, question_count):
        """Create a test curiosity feed with specified number of questions."""
        questions = []
        for i in range(question_count):
            questions.append({
                "id": f"question_{i}",
                "hypothesis": f"Test hypothesis {i}",
                "question": f"Test question {i}?",
                "evidence": [],
                "evidence_hash": f"hash_{i}",
                "action_class": "INVESTIGATE",
                "autonomy": True,
                "value_estimate": 0.5,
                "cost": 1.0,
                "capability_key": f"test_cap_{i}",
                "status": "pending",
                "created_at": "2025-11-17T00:00:00"
            })

        feed = {"questions": questions}
        self.test_feed_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.test_feed_path, 'w') as f:
            json.dump(feed, f, indent=2)

        return feed

    @patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED')
    def test_proactive_cleanup_trims_to_100_questions(self, mock_feed_path):
        """Test that proactive cleanup trims feed to last 100 questions."""
        mock_feed_path.__str__ = lambda x: str(self.test_feed_path)
        mock_feed_path.exists.return_value = True
        mock_feed_path.parent.mkdir = Mock()

        self._create_test_feed(200)

        with patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED', self.test_feed_path):
            self.daemon._proactive_cleanup()

        with open(self.test_feed_path, 'r') as f:
            feed = json.load(f)

        self.assertEqual(len(feed['questions']), 100)
        self.assertEqual(feed['questions'][0]['id'], 'question_100')
        self.assertEqual(feed['questions'][-1]['id'], 'question_199')

    @patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED')
    def test_proactive_cleanup_clears_semantic_cache(self, mock_feed_path):
        """Test that proactive cleanup calls clear_cache on semantic_store."""
        mock_feed_path.exists.return_value = True

        self._create_test_feed(50)

        self.daemon.curiosity_core.semantic_store.clear_cache = Mock()

        with patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED', self.test_feed_path):
            self.daemon._proactive_cleanup()

        self.daemon.curiosity_core.semantic_store.clear_cache.assert_called_once()

    @patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED')
    @patch('gc.collect')
    def test_proactive_cleanup_runs_gc(self, mock_gc, mock_feed_path):
        """Test that proactive cleanup triggers garbage collection."""
        mock_feed_path.exists.return_value = True

        self._create_test_feed(50)

        with patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED', self.test_feed_path):
            self.daemon._proactive_cleanup()

        mock_gc.assert_called_once()

    @patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED')
    def test_emergency_cleanup_trims_to_20_questions(self, mock_feed_path):
        """Test that emergency cleanup trims feed to last 20 questions."""
        mock_feed_path.__str__ = lambda x: str(self.test_feed_path)
        mock_feed_path.exists.return_value = True

        self._create_test_feed(100)

        with patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED', self.test_feed_path):
            self.daemon._emergency_cleanup()

        with open(self.test_feed_path, 'r') as f:
            feed = json.load(f)

        self.assertEqual(len(feed['questions']), 20)
        self.assertEqual(feed['questions'][0]['id'], 'question_80')
        self.assertEqual(feed['questions'][-1]['id'], 'question_99')

    @patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED')
    def test_emergency_cleanup_emits_system_health_signal(self, mock_feed_path):
        """Test that emergency cleanup emits SYSTEM_HEALTH signal."""
        mock_feed_path.exists.return_value = True

        self._create_test_feed(50)

        self.daemon.chem_pub = Mock()

        with patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED', self.test_feed_path):
            self.daemon._emergency_cleanup()

        self.daemon.chem_pub.emit.assert_called_once()
        call_args = self.daemon.chem_pub.emit.call_args

        self.assertEqual(call_args.kwargs['signal'], "SYSTEM_HEALTH")
        self.assertEqual(call_args.kwargs['ecosystem'], "orchestration")
        self.assertEqual(call_args.kwargs['facts']['component'], "curiosity_core_consumer")
        self.assertEqual(call_args.kwargs['facts']['status'], "memory_critical")
        self.assertIn("memory_mb", call_args.kwargs['facts'])

    @patch.dict(os.environ, {'KLR_USE_PRIORITY_QUEUES': '0'})
    @patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED')
    @patch('kloros.orchestration.curiosity_core_consumer_daemon.UMNPub')
    def test_emergency_cleanup_emits_signal_in_legacy_mode(self, mock_chem_pub_class, mock_feed_path):
        """Test that emergency cleanup emits SYSTEM_HEALTH signal in legacy mode (KLR_USE_PRIORITY_QUEUES=0)."""
        mock_feed_path.exists.return_value = True
        self._create_test_feed(50)

        mock_pub_instance = Mock()
        mock_chem_pub_class.return_value = mock_pub_instance

        with patch('kloros.orchestration.curiosity_core_consumer_daemon.CapabilityEvaluator'):
            with patch('kloros.orchestration.curiosity_core_consumer_daemon.CuriosityCore'):
                with patch('kloros.orchestration.curiosity_core_consumer_daemon.UMNSub'):
                    daemon = CuriosityCoreConsumerDaemon()

        self.assertIsNotNone(daemon.chem_pub, "UMNPub should be initialized in legacy mode")
        self.assertIsNone(daemon.prioritizer, "QuestionPrioritizer should NOT be initialized in legacy mode")

        with patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED', self.test_feed_path):
            daemon._emergency_cleanup()

        mock_pub_instance.emit.assert_called_once()
        call_args = mock_pub_instance.emit.call_args

        self.assertEqual(call_args.kwargs['signal'], "SYSTEM_HEALTH")
        self.assertEqual(call_args.kwargs['ecosystem'], "orchestration")
        self.assertEqual(call_args.kwargs['facts']['component'], "curiosity_core_consumer")
        self.assertEqual(call_args.kwargs['facts']['status'], "memory_critical")
        self.assertIn("memory_mb", call_args.kwargs['facts'])

    @patch('psutil.Process')
    def test_check_memory_usage_triggers_proactive_at_90_percent(self, mock_process):
        """Test that _check_memory_usage triggers proactive cleanup at 4500MB."""
        mock_mem_info = Mock()
        mock_mem_info.rss = 4600 * 1024 * 1024
        mock_process.return_value.memory_info.return_value = mock_mem_info

        self.daemon._proactive_cleanup = Mock()
        self.daemon._emergency_cleanup = Mock()

        self.daemon._check_memory_usage()

        self.daemon._proactive_cleanup.assert_called_once()
        self.daemon._emergency_cleanup.assert_not_called()

    @patch('psutil.Process')
    def test_check_memory_usage_triggers_emergency_at_95_percent(self, mock_process):
        """Test that _check_memory_usage triggers emergency cleanup at 5000MB."""
        mock_mem_info = Mock()
        mock_mem_info.rss = 5100 * 1024 * 1024
        mock_process.return_value.memory_info.return_value = mock_mem_info

        self.daemon._proactive_cleanup = Mock()
        self.daemon._emergency_cleanup = Mock()

        self.daemon._check_memory_usage()

        self.daemon._emergency_cleanup.assert_called_once()
        self.daemon._proactive_cleanup.assert_not_called()

    @patch('psutil.Process')
    def test_check_memory_usage_no_trigger_below_threshold(self, mock_process):
        """Test that _check_memory_usage does not trigger cleanup below 90%."""
        mock_mem_info = Mock()
        mock_mem_info.rss = 800 * 1024 * 1024
        mock_process.return_value.memory_info.return_value = mock_mem_info

        self.daemon._proactive_cleanup = Mock()
        self.daemon._emergency_cleanup = Mock()

        self.daemon._check_memory_usage()

        self.daemon._proactive_cleanup.assert_not_called()
        self.daemon._emergency_cleanup.assert_not_called()

    @patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED')
    def test_proactive_cleanup_handles_missing_feed(self, mock_feed_path):
        """Test that proactive cleanup handles missing feed file gracefully."""
        mock_feed_path.exists.return_value = False

        self.daemon._proactive_cleanup()

    @patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED')
    def test_emergency_cleanup_handles_missing_feed(self, mock_feed_path):
        """Test that emergency cleanup handles missing feed file gracefully."""
        mock_feed_path.exists.return_value = False

        self.daemon._emergency_cleanup()

    @patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED')
    def test_proactive_cleanup_no_trim_below_100_questions(self, mock_feed_path):
        """Test that proactive cleanup does not trim feed with less than 100 questions."""
        mock_feed_path.__str__ = lambda x: str(self.test_feed_path)
        mock_feed_path.exists.return_value = True

        self._create_test_feed(50)

        with patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED', self.test_feed_path):
            self.daemon._proactive_cleanup()

        with open(self.test_feed_path, 'r') as f:
            feed = json.load(f)

        self.assertEqual(len(feed['questions']), 50)

    @patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED')
    def test_cleanup_handles_no_semantic_store(self, mock_feed_path):
        """Test that cleanup handles missing semantic_store gracefully."""
        mock_feed_path.exists.return_value = True
        self._create_test_feed(50)

        self.daemon.curiosity_core = None

        with patch('kloros.orchestration.curiosity_core_consumer_daemon.CURIOSITY_FEED', self.test_feed_path):
            self.daemon._proactive_cleanup()
            self.daemon._emergency_cleanup()


class TestMemoryProfiling(unittest.TestCase):
    """Test memory profiling functionality."""

    def setUp(self):
        """Set up test fixtures."""
        with patch('kloros.orchestration.curiosity_core_consumer_daemon.CapabilityEvaluator'):
            with patch('kloros.orchestration.curiosity_core_consumer_daemon.CuriosityCore'):
                with patch('kloros.orchestration.curiosity_core_consumer_daemon.UMNSub'):
                    self.daemon = CuriosityCoreConsumerDaemon()

    @patch('tracemalloc.take_snapshot')
    @patch('time.time')
    def test_memory_profiling_runs_every_5_minutes(self, mock_time, mock_snapshot):
        """Test that memory profiling runs every 5 minutes."""
        mock_snapshot.return_value.statistics.return_value = []

        mock_time.return_value = 0
        self.daemon.last_memory_snapshot = 0
        self.daemon._log_memory_top_consumers()
        mock_snapshot.assert_not_called()

        mock_time.return_value = 301
        self.daemon._log_memory_top_consumers()
        mock_snapshot.assert_called_once()

    @patch('tracemalloc.take_snapshot')
    @patch('time.time')
    def test_memory_profiling_logs_top_10_consumers(self, mock_time, mock_snapshot):
        """Test that memory profiling logs top 10 memory consumers."""
        mock_stats = [Mock() for _ in range(15)]
        mock_snapshot.return_value.statistics.return_value = mock_stats

        mock_time.return_value = 400
        self.daemon.last_memory_snapshot = 0

        with patch('kloros.orchestration.curiosity_core_consumer_daemon.logger') as mock_logger:
            self.daemon._log_memory_top_consumers()

            debug_calls = [call for call in mock_logger.debug.call_args_list
                          if 'memory_profile' in str(call)]
            self.assertGreaterEqual(len(debug_calls), 1)


if __name__ == '__main__':
    unittest.main()
