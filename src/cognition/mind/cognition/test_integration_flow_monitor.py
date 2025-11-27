#!/usr/bin/env python3
"""
Tests for IntegrationFlowMonitor scanner enhancements.

Tests the Phase 2.2 implementation:
- Queue-to-service mapping
- Intentionally disabled service detection
- Metadata propagation to CuriosityQuestions
"""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).parent))

from integration_flow_monitor import IntegrationFlowMonitor, DataFlow
from curiosity_core import CuriosityQuestion, ActionClass, QuestionStatus


class TestQueueServiceMapping(unittest.TestCase):
    """Test the queue-to-service mapping function."""

    def setUp(self):
        self.monitor = IntegrationFlowMonitor()

    def test_dream_queues_mapped_to_service(self):
        """Test that D-REAM queues are mapped to kloros-dream.service."""
        dream_queues = [
            "episodes",
            "fitness_history",
            "phenotype_history",
            "mutation_history",
            "generations",
            "macro_traces",
            "mutations",
            "attempt_history",
            "episode_buffer"
        ]

        for queue in dream_queues:
            service = self.monitor._infer_service_from_queue_name(queue)
            self.assertEqual(
                service,
                "kloros-dream.service",
                f"Queue '{queue}' should map to kloros-dream.service"
            )

    def test_unknown_queue_returns_none(self):
        """Test that unknown queues return None."""
        unknown_queues = [
            "unknown_queue",
            "random_data",
            "some_other_thing"
        ]

        for queue in unknown_queues:
            service = self.monitor._infer_service_from_queue_name(queue)
            self.assertIsNone(
                service,
                f"Queue '{queue}' should return None"
            )


class TestOrphanedQueueDetection(unittest.TestCase):
    """Test orphaned queue detection with service state awareness."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.monitor = IntegrationFlowMonitor(src_root=Path(self.tmpdir))

    def test_disabled_service_adds_metadata(self):
        """Test that disabled services add intentionally_disabled metadata."""
        self.monitor.data_flows = [
            DataFlow(
                producer="EvolutionEngine",
                consumer=None,
                channel="episodes",
                channel_type="queue",
                producer_file="/home/kloros/src/dream/evolution.py",
                consumer_file=None,
                line_number=100
            )
        ]

        with patch('integration_flow_monitor.is_service_intentionally_disabled') as mock_check:
            mock_check.return_value = True

            questions = self.monitor._detect_orphaned_queues()

            self.assertEqual(len(questions), 1)
            q = questions[0]

            self.assertEqual(q.id, "orphaned_queue_episodes")
            self.assertIn("intentionally_disabled", q.metadata)
            self.assertTrue(q.metadata["intentionally_disabled"])
            self.assertEqual(q.metadata["reason"], "kloros-dream.service is disabled")

            mock_check.assert_called_once_with("kloros-dream.service")

    def test_enabled_service_no_metadata(self):
        """Test that enabled services have empty metadata."""
        self.monitor.data_flows = [
            DataFlow(
                producer="EvolutionEngine",
                consumer=None,
                channel="episodes",
                channel_type="queue",
                producer_file="/home/kloros/src/dream/evolution.py",
                consumer_file=None,
                line_number=100
            )
        ]

        with patch('integration_flow_monitor.is_service_intentionally_disabled') as mock_check:
            mock_check.return_value = False

            questions = self.monitor._detect_orphaned_queues()

            self.assertEqual(len(questions), 1)
            q = questions[0]

            self.assertEqual(q.id, "orphaned_queue_episodes")
            self.assertEqual(q.metadata, {})

            mock_check.assert_called_once_with("kloros-dream.service")

    def test_unknown_service_no_metadata(self):
        """Test that queues without service mapping have empty metadata."""
        self.monitor.data_flows = [
            DataFlow(
                producer="SomeComponent",
                consumer=None,
                channel="unknown_queue",
                channel_type="queue",
                producer_file="/home/kloros/src/some_component.py",
                consumer_file=None,
                line_number=50
            )
        ]

        with patch('integration_flow_monitor.is_service_intentionally_disabled') as mock_check:
            questions = self.monitor._detect_orphaned_queues()

            self.assertEqual(len(questions), 1)
            q = questions[0]

            self.assertEqual(q.id, "orphaned_queue_unknown_queue")
            self.assertEqual(q.metadata, {})

            mock_check.assert_not_called()

    def test_multiple_queues_mixed_states(self):
        """Test multiple queues with different service states."""
        self.monitor.data_flows = [
            DataFlow(
                producer="EvolutionEngine",
                consumer=None,
                channel="episodes",
                channel_type="queue",
                producer_file="/home/kloros/src/dream/evolution.py",
                consumer_file=None,
                line_number=100
            ),
            DataFlow(
                producer="EvolutionEngine",
                consumer=None,
                channel="fitness_history",
                channel_type="queue",
                producer_file="/home/kloros/src/dream/evolution.py",
                consumer_file=None,
                line_number=150
            ),
            DataFlow(
                producer="SomeComponent",
                consumer=None,
                channel="other_queue",
                channel_type="queue",
                producer_file="/home/kloros/src/some_component.py",
                consumer_file=None,
                line_number=50
            )
        ]

        with patch('integration_flow_monitor.is_service_intentionally_disabled') as mock_check:
            mock_check.return_value = True

            questions = self.monitor._detect_orphaned_queues()

            self.assertEqual(len(questions), 3)

            episodes_q = [q for q in questions if q.id == "orphaned_queue_episodes"][0]
            self.assertTrue(episodes_q.metadata.get("intentionally_disabled", False))

            fitness_q = [q for q in questions if q.id == "orphaned_queue_fitness_history"][0]
            self.assertTrue(fitness_q.metadata.get("intentionally_disabled", False))

            other_q = [q for q in questions if q.id == "orphaned_queue_other_queue"][0]
            self.assertEqual(other_q.metadata, {})

            self.assertEqual(mock_check.call_count, 2)


class TestIntegrationWithRealScanner(unittest.TestCase):
    """Integration test with real scanner code."""

    def test_scanner_runs_without_errors(self):
        """Test that the scanner runs without errors on real codebase."""
        monitor = IntegrationFlowMonitor(src_root=Path("/home/kloros/src"))

        try:
            questions = monitor.generate_integration_questions()
            self.assertIsInstance(questions, list)

            for q in questions:
                self.assertIsInstance(q, CuriosityQuestion)
                self.assertIsInstance(q.metadata, dict)

                if q.id.startswith("orphaned_queue_"):
                    if "intentionally_disabled" in q.metadata:
                        self.assertIsInstance(q.metadata["intentionally_disabled"], bool)
                        self.assertIn("reason", q.metadata)

        except Exception as e:
            self.fail(f"Scanner raised exception: {e}")


def run_tests():
    """Run all tests."""
    import logging
    logging.basicConfig(level=logging.INFO)

    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
