#!/usr/bin/env python3

import unittest
import tempfile
import json
import time
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).parents[2]))
sys.path.insert(0, str(Path(__file__).parents[2] / "src"))


class TestCuriosityIntegrationDaemonIntegration(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.feed_path = self.temp_path / "curiosity_feed.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_end_to_end_daemon_emission_to_curiosity_core(self):
        from kloros.orchestration.chem_bus_v2 import ChemPub, ChemMessage
        from registry.curiosity_core import CuriosityCore
        import time

        core = CuriosityCore(feed_path=self.feed_path)

        core.subscribe_to_daemon_questions()

        time.sleep(0.2)

        pub = ChemPub()

        msg = ChemMessage(
            signal="curiosity.integration_question",
            ecosystem="curiosity",
            intensity=0.95,
            facts={
                'question_id': 'end_to_end_test',
                'question': 'Is end-to-end integration working?',
                'evidence': ['Test emission', 'From integration test'],
                'hypothesis': 'End-to-end flow works',
                'severity': 'medium',
                'source': 'test_daemon'
            }
        )

        pub.emit("curiosity.integration_question", msg.to_bytes())

        time.sleep(0.5)

        daemon_questions = core._get_daemon_questions()

        self.assertGreater(len(daemon_questions), 0,
                          "Should receive at least one question from daemon")

        received_ids = [q.id for q in daemon_questions]
        self.assertIn('end_to_end_test', received_ids,
                     f"Should receive end_to_end_test question, got {received_ids}")

    def test_multiple_daemon_emissions_accumulated(self):
        from kloros.orchestration.chem_bus_v2 import ChemPub, ChemMessage
        from registry.curiosity_core import CuriosityCore

        core = CuriosityCore(feed_path=self.feed_path)
        core.subscribe_to_daemon_questions()

        time.sleep(0.2)

        pub = ChemPub()

        for i in range(3):
            msg = ChemMessage(
                signal="curiosity.integration_question",
                ecosystem="curiosity",
                intensity=0.95,
                facts={
                    'question_id': f'multi_test_{i}',
                    'question': f'Question {i}?',
                    'evidence': [f'Evidence {i}'],
                    'hypothesis': f'Hypothesis {i}',
                    'severity': 'medium',
                    'source': 'test_daemon'
                }
            )
            pub.emit("curiosity.integration_question", msg.to_bytes())
            time.sleep(0.1)

        time.sleep(0.5)

        daemon_questions = core._get_daemon_questions()

        self.assertEqual(len(daemon_questions), 3,
                        f"Should receive 3 questions, got {len(daemon_questions)}")

        received_ids = sorted([q.id for q in daemon_questions])
        expected_ids = ['multi_test_0', 'multi_test_1', 'multi_test_2']

        self.assertEqual(received_ids, expected_ids,
                        f"Should receive all 3 questions, got {received_ids}")

    def test_daemon_questions_merged_in_generate_matrix(self):
        from kloros.orchestration.chem_bus_v2 import ChemPub, ChemMessage
        from registry.curiosity_core import CuriosityCore
        from registry.capability_evaluator import CapabilityMatrix

        core = CuriosityCore(feed_path=self.feed_path)
        core.subscribe_to_daemon_questions()

        time.sleep(0.2)

        pub = ChemPub()

        msg = ChemMessage(
            signal="curiosity.integration_question",
            ecosystem="curiosity",
            intensity=0.95,
            facts={
                'question_id': 'matrix_integration_test',
                'question': 'Is matrix integration working?',
                'evidence': ['Matrix test'],
                'hypothesis': 'Matrix integration works',
                'severity': 'high',
                'source': 'test_daemon'
            }
        )

        pub.emit("curiosity.integration_question", msg.to_bytes())

        time.sleep(0.5)

        matrix = CapabilityMatrix(capabilities=[])

        feed = core.generate_questions_from_matrix(matrix,
            include_performance=False,
            include_resources=False,
            include_exceptions=False)

        question_ids = [q.id for q in feed.questions]

        self.assertIn('matrix_integration_test', question_ids,
                     "Daemon question should be included in feed")


if __name__ == '__main__':
    unittest.main()
