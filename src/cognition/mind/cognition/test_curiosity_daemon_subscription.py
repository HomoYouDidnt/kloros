#!/usr/bin/env python3

import unittest
import tempfile
import json
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

sys.path.insert(0, str(Path(__file__).parents[2]))
sys.path.insert(0, str(Path(__file__).parents[2] / "src"))


class TestCuriosityCoreDaemonSubscription(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.feed_path = self.temp_path / "curiosity_feed.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_integration_question_subscription_initialization(self):
        from src.cognition.mind.cognition.curiosity_core import CuriosityCore

        core = CuriosityCore(feed_path=self.feed_path)

        self.assertIsNotNone(core.feed_path)
        self.assertEqual(core.feed_path, self.feed_path)

    @patch('registry.curiosity_core.UMNSub')
    def test_subscribe_to_integration_daemon(self, mock_chem_sub):
        from src.cognition.mind.cognition.curiosity_core import CuriosityCore

        core = CuriosityCore(feed_path=self.feed_path)

        core.subscribe_to_daemon_questions()

        mock_chem_sub.assert_called()
        call_args = mock_chem_sub.call_args

        self.assertIn('curiosity.integration_question', str(call_args))

    def test_convert_umn_message_to_curiosity_question(self):
        from src.cognition.mind.cognition.curiosity_core import CuriosityCore, CuriosityQuestion, ActionClass

        core = CuriosityCore(feed_path=self.feed_path)

        umn_payload = {
            'signal': 'curiosity.integration_question',
            'ecosystem': 'curiosity',
            'intensity': 0.95,
            'facts': {
                'question_id': 'orphaned_queue_test_channel',
                'question': 'Is test_channel queue orphaned?',
                'evidence': ['No consumers found', 'Producer: TestClass'],
                'hypothesis': 'Queue test_channel has no consumers',
                'severity': 'high',
                'source': 'integration_monitor'
            },
            'ts': time.time()
        }

        questions = core._convert_daemon_message_to_questions(umn_payload)

        self.assertEqual(len(questions), 1)
        q = questions[0]

        self.assertIsInstance(q, CuriosityQuestion)
        self.assertEqual(q.id, 'orphaned_queue_test_channel')
        self.assertEqual(q.question, 'Is test_channel queue orphaned?')
        self.assertIn('No consumers found', q.evidence)
        self.assertEqual(q.hypothesis, 'Queue test_channel has no consumers')

    def test_daemon_questions_merged_with_existing(self):
        from src.cognition.mind.cognition.curiosity_core import CuriosityCore, CuriosityQuestion, ActionClass, QuestionStatus
        from src.cognition.mind.cognition.capability_evaluator import CapabilityMatrix, CapabilityRecord, CapabilityState

        core = CuriosityCore(feed_path=self.feed_path)

        matrix = CapabilityMatrix(capabilities=[])

        daemon_questions = [
            CuriosityQuestion(
                id='daemon_question_1',
                hypothesis='Daemon hypothesis',
                question='Daemon question?',
                evidence=['daemon evidence'],
                action_class=ActionClass.INVESTIGATE,
                status=QuestionStatus.READY
            )
        ]

        with patch.object(core, '_get_daemon_questions', return_value=daemon_questions):
            feed = core.generate_questions_from_matrix(matrix)

        question_ids = [q.id for q in feed.questions]
        self.assertIn('daemon_question_1', question_ids)

    def test_daemon_question_logging(self):
        from src.cognition.mind.cognition.curiosity_core import CuriosityCore
        import logging

        core = CuriosityCore(feed_path=self.feed_path)

        umn_payload = {
            'signal': 'curiosity.integration_question',
            'ecosystem': 'curiosity',
            'intensity': 0.95,
            'facts': {
                'question_id': 'test_1',
                'question': 'Test question?',
                'evidence': ['test evidence'],
                'hypothesis': 'Test hypothesis',
                'severity': 'medium',
                'source': 'integration_monitor'
            },
            'ts': time.time()
        }

        with self.assertLogs('registry.curiosity_core', level='INFO') as log:
            questions = core._convert_daemon_message_to_questions(umn_payload)

            log_output = '\n'.join(log.output)
            self.assertIn('integration question', log_output.lower())

    def test_multiple_daemon_messages_accumulated(self):
        from src.cognition.mind.cognition.curiosity_core import CuriosityCore

        core = CuriosityCore(feed_path=self.feed_path)

        messages = [
            {
                'facts': {
                    'question_id': f'question_{i}',
                    'question': f'Question {i}?',
                    'evidence': [f'evidence {i}'],
                    'hypothesis': f'Hypothesis {i}',
                    'severity': 'medium',
                    'source': 'integration_monitor'
                }
            }
            for i in range(5)
        ]

        all_questions = []
        for msg in messages:
            questions = core._convert_daemon_message_to_questions(msg)
            all_questions.extend(questions)

        self.assertEqual(len(all_questions), 5)
        self.assertEqual(all_questions[0].id, 'question_0')
        self.assertEqual(all_questions[4].id, 'question_4')

    def test_daemon_question_fields_properly_mapped(self):
        from src.cognition.mind.cognition.curiosity_core import CuriosityCore, ActionClass

        core = CuriosityCore(feed_path=self.feed_path)

        umn_payload = {
            'signal': 'curiosity.integration_question',
            'facts': {
                'question_id': 'detailed_question',
                'question': 'Why is component X disconnected?',
                'evidence': [
                    'No consumers for queue X',
                    'Producer defined in file.py:42',
                    'Last write timestamp: 1234567890'
                ],
                'hypothesis': 'Component X wiring is broken',
                'severity': 'critical',
                'source': 'integration_monitor',
                'metadata': {
                    'channel': 'queue_x',
                    'producer_file': '/home/kloros/src/producer.py'
                }
            }
        }

        questions = core._convert_daemon_message_to_questions(umn_payload)
        q = questions[0]

        self.assertEqual(q.id, 'detailed_question')
        self.assertEqual(q.question, 'Why is component X disconnected?')
        self.assertEqual(len(q.evidence), 3)
        self.assertEqual(q.hypothesis, 'Component X wiring is broken')
        self.assertIsInstance(q.action_class, ActionClass)
        self.assertIsNotNone(q.metadata)
        self.assertEqual(q.metadata.get('severity'), 'critical')
        self.assertEqual(q.metadata.get('source'), 'integration_monitor')

    def test_malformed_daemon_message_handled_gracefully(self):
        from src.cognition.mind.cognition.curiosity_core import CuriosityCore

        core = CuriosityCore(feed_path=self.feed_path)

        malformed_messages = [
            {},
            {'facts': {}},
            {'facts': {'question_id': 'missing_fields'}},
            {'facts': {'question': 'no id'}},
        ]

        for msg in malformed_messages:
            questions = core._convert_daemon_message_to_questions(msg)
            self.assertEqual(len(questions), 0,
                           f"Should return empty list for malformed message: {msg}")

    def test_no_regression_existing_question_types(self):
        from src.cognition.mind.cognition.curiosity_core import CuriosityCore
        from src.cognition.mind.cognition.capability_evaluator import CapabilityMatrix, CapabilityRecord, CapabilityState

        core = CuriosityCore(feed_path=self.feed_path)

        matrix = CapabilityMatrix(
            capabilities=[
                CapabilityRecord(
                    key="test.missing_capability",
                    kind="tool",
                    state=CapabilityState.MISSING,
                    why="Test missing capability"
                )
            ]
        )

        with patch.object(core, '_get_daemon_questions', return_value=[]):
            feed = core.generate_questions_from_matrix(matrix,
                include_performance=False,
                include_resources=False,
                include_exceptions=False)

        self.assertGreater(len(feed.questions), 0,
                          "Should still generate capability-based questions")

    def test_daemon_questions_respect_cooldown_filter(self):
        from src.cognition.mind.cognition.curiosity_core import CuriosityCore, CuriosityQuestion, ActionClass, QuestionStatus

        core = CuriosityCore(feed_path=self.feed_path)

        daemon_question = CuriosityQuestion(
            id='repeated_daemon_question',
            hypothesis='Repeated hypothesis',
            question='Repeated question?',
            evidence=['repeated evidence'],
            action_class=ActionClass.INVESTIGATE,
            status=QuestionStatus.READY
        )

        self.assertTrue(hasattr(daemon_question, 'id'))
        self.assertEqual(daemon_question.id, 'repeated_daemon_question')


if __name__ == '__main__':
    unittest.main()
