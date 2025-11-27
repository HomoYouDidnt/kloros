import unittest
import tempfile
import threading
import time
import pickle
import hashlib
import ast
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


class TestKnowledgeDiscoveryDaemon(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.state_file = Path(self.temp_dir) / "test_knowledge_state.pkl"

        (self.temp_path / "docs").mkdir(exist_ok=True)
        (self.temp_path / "src").mkdir(exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_daemon_initialization(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        self.assertEqual(daemon.watch_path, self.temp_path)
        self.assertEqual(daemon.state_file, self.state_file)
        self.assertIsInstance(daemon.file_hashes, dict)
        self.assertIsInstance(daemon.knowledge_index, dict)

    def test_file_hash_computation(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "docs" / "readme.md"
        test_file.write_text("# Documentation")

        file_hash = daemon._compute_file_hash(test_file)

        self.assertIsInstance(file_hash, str)
        self.assertEqual(len(file_hash), 64)

        expected_hash = hashlib.sha256("# Documentation".encode()).hexdigest()
        self.assertEqual(file_hash, expected_hash)

    def test_change_detection_skips_unchanged_files(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "docs" / "guide.md"
        test_file.write_text("# Guide")

        result1 = daemon._has_file_changed(test_file)
        self.assertTrue(result1)

        result2 = daemon._has_file_changed(test_file)
        self.assertFalse(result2)

    def test_unindexed_documentation_detection(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "docs" / "new_guide.md"
        test_file.write_text("# New Guide\n\nThis is new documentation.")

        gaps = daemon._detect_unindexed_documentation(test_file)

        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]['type'], 'unindexed_documentation')
        self.assertEqual(gaps[0]['severity'], 'medium')
        self.assertIn('new_guide.md', gaps[0]['evidence'][0])

    def test_indexed_documentation_not_flagged(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "docs" / "indexed.md"
        test_file.write_text("# Indexed Documentation")

        daemon.knowledge_index['docs/indexed.md'] = True

        gaps = daemon._detect_unindexed_documentation(test_file)

        self.assertEqual(len(gaps), 0)

    def test_missing_docstrings_detection(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "src" / "undocumented.py"
        test_file.write_text("""
class UndocumentedClass:
    def method1(self):
        pass

    def method2(self):
        pass

    def method3(self):
        pass

    def method4(self):
        pass
""")

        gaps = daemon._detect_missing_docstrings(test_file)

        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]['type'], 'missing_docstrings')
        self.assertEqual(gaps[0]['severity'], 'low')
        self.assertIn('5', gaps[0]['evidence'][0])

    def test_few_missing_docstrings_not_flagged(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "src" / "mostly_documented.py"
        test_file.write_text("""
class MostlyDocumented:
    def method1(self):
        pass

    def method2(self):
        pass
""")

        gaps = daemon._detect_missing_docstrings(test_file)

        self.assertEqual(len(gaps), 0)

    def test_stale_documentation_detection(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon
        import os

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "docs" / "old_guide.md"
        test_file.write_text("# Old Guide")

        old_time = time.time() - (91 * 86400)
        os.utime(test_file, (old_time, old_time))

        gaps = daemon._detect_stale_documentation(test_file)

        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]['type'], 'stale_documentation')
        self.assertEqual(gaps[0]['severity'], 'low')
        self.assertIn('91', gaps[0]['evidence'][0])

    def test_fresh_documentation_not_flagged(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "docs" / "fresh_guide.md"
        test_file.write_text("# Fresh Guide")

        gaps = daemon._detect_stale_documentation(test_file)

        self.assertEqual(len(gaps), 0)

    def test_process_file_event_analyzes_markdown(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "docs" / "new.md"
        test_file.write_text("# New Documentation")

        with patch.object(daemon, '_emit_questions_to_umn') as mock_emit:
            daemon.process_file_event('create', test_file)

            self.assertTrue(mock_emit.called)
            # _emit_questions_to_umn is called with list of gaps
            call_args = mock_emit.call_args
            questions = call_args[0][0] if call_args[0] else call_args.args[0]
            self.assertGreater(len(questions), 0)

    def test_process_file_event_analyzes_python(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "src" / "code.py"
        test_file.write_text("""
class MyClass:
    def method1(self):
        pass
    def method2(self):
        pass
    def method3(self):
        pass
    def method4(self):
        pass
""")

        with patch.object(daemon, '_emit_questions_to_umn') as mock_emit:
            daemon.process_file_event('create', test_file)

            self.assertTrue(mock_emit.called)

    def test_process_file_event_skips_unchanged(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "docs" / "unchanged.md"
        test_file.write_text("# Unchanged")

        with patch.object(daemon, '_emit_questions_to_umn') as mock_emit:
            daemon.process_file_event('modify', test_file)

            initial_call_count = mock_emit.call_count
            self.assertGreater(initial_call_count, 0)

            daemon.process_file_event('modify', test_file)
            self.assertEqual(mock_emit.call_count, initial_call_count)

    @patch('kloros.daemons.knowledge_discovery_daemon.UMNPub')
    def test_umn_question_emission(self, mock_chem_pub):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon

        mock_pub_instance = MagicMock()
        mock_chem_pub.return_value = mock_pub_instance

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        questions = [
            {
                'type': 'unindexed_documentation',
                'severity': 'medium',
                'evidence': ['New documentation file: test.md'],
                'suggestion': 'Index test.md for knowledge retrieval',
                'file': 'test.md'
            }
        ]

        daemon._emit_questions_to_umn(questions)

        mock_pub_instance.emit.assert_called()

        call_args = mock_pub_instance.emit.call_args
        self.assertEqual(call_args.kwargs['signal'], 'curiosity.knowledge_question')
        self.assertEqual(call_args.kwargs['ecosystem'], 'curiosity')

    def test_state_save_and_load(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        daemon.file_hashes['docs/test.md'] = 'abc123'
        daemon.knowledge_index['docs/indexed.md'] = True

        daemon.save_state()

        self.assertTrue(self.state_file.exists())

        daemon2 = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )
        daemon2.load_state()

        self.assertEqual(daemon2.file_hashes.get('docs/test.md'), 'abc123')
        self.assertIn('docs/indexed.md', daemon2.knowledge_index)

    def test_delete_event_handling(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "docs" / "deleted.md"
        file_path_str = str(test_file)

        daemon.file_hashes[file_path_str] = 'abc123'
        daemon.knowledge_index['docs/deleted.md'] = True

        daemon.process_file_event('delete', test_file)

        self.assertNotIn(file_path_str, daemon.file_hashes)

    def test_memory_usage_stays_bounded(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon
        import psutil
        import os

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        for i in range(100):
            test_file = self.temp_path / "docs" / f"file_{i}.md"
            test_file.write_text(f"# Documentation {i}\n\nContent here.")
            daemon.process_file_event('create', test_file)

        daemon._evict_cache_if_needed()

        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / (1024 * 1024)

        self.assertLess(memory_mb, 150,
            f"Memory usage {memory_mb:.2f}MB exceeds 150MB limit")

    def test_deduplication_by_file_path(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "docs" / "duplicate.md"
        test_file.write_text("# Duplicate")

        with patch.object(daemon, '_emit_questions_to_umn') as mock_emit:
            daemon.process_file_event('create', test_file)
            first_call_count = mock_emit.call_count

            daemon.process_file_event('modify', test_file)
            second_call_count = mock_emit.call_count

            self.assertEqual(first_call_count, second_call_count,
                           "Should not emit duplicate questions for same file")

    def test_integration_with_base_daemon(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file,
            max_queue_size=100,
            max_workers=1
        )

        self.assertEqual(daemon.event_queue.maxsize, 100)
        self.assertEqual(daemon.max_workers, 1)

        health = daemon.get_health_status()
        self.assertIn('running', health)
        self.assertIn('cache_size', health)

    def test_multiple_gap_types_in_single_file(self):
        from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon
        import os

        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "docs" / "old_unindexed.md"
        test_file.write_text("# Old Unindexed Guide")

        old_time = time.time() - (91 * 86400)
        os.utime(test_file, (old_time, old_time))

        with patch.object(daemon, '_emit_questions_to_umn') as mock_emit:
            daemon.process_file_event('create', test_file)

            call_args = mock_emit.call_args
            questions = call_args[0][0] if call_args[0] else call_args.args[0]
            question_types = {q['type'] for q in questions}

            self.assertIn('unindexed_documentation', question_types)
            self.assertIn('stale_documentation', question_types)


if __name__ == '__main__':
    unittest.main()
