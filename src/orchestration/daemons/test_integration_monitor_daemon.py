import unittest
import tempfile
import threading
import time
import pickle
import hashlib
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


class TestIntegrationMonitorDaemon(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.state_file = Path(self.temp_dir) / "test_state.pkl"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_daemon_initialization(self):
        from src.orchestration.daemons.integration_monitor_daemon import IntegrationMonitorDaemon

        daemon = IntegrationMonitorDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        self.assertEqual(daemon.watch_path, self.temp_path)
        self.assertEqual(daemon.state_file, self.state_file)
        self.assertIsInstance(daemon.file_hashes, dict)
        self.assertIsInstance(daemon.data_flows, dict)

    def test_file_hash_computation(self):
        from src.orchestration.daemons.integration_monitor_daemon import IntegrationMonitorDaemon

        daemon = IntegrationMonitorDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "test.py"
        test_file.write_text("print('hello')")

        file_hash = daemon._compute_file_hash(test_file)

        self.assertIsInstance(file_hash, str)
        self.assertEqual(len(file_hash), 64)

        expected_hash = hashlib.sha256("print('hello')".encode()).hexdigest()
        self.assertEqual(file_hash, expected_hash)

    def test_change_detection_skips_unchanged_files(self):
        from src.orchestration.daemons.integration_monitor_daemon import IntegrationMonitorDaemon

        daemon = IntegrationMonitorDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "test.py"
        test_file.write_text("print('hello')")

        result1 = daemon._has_file_changed(test_file)
        self.assertTrue(result1)

        result2 = daemon._has_file_changed(test_file)
        self.assertFalse(result2)

    def test_ast_parsing_extracts_queue_producers(self):
        from src.orchestration.daemons.integration_monitor_daemon import IntegrationMonitorDaemon

        daemon = IntegrationMonitorDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "producer.py"
        test_file.write_text("""
class DataProducer:
    def __init__(self):
        self.events = []

    def add_event(self, event):
        self.events.append(event)
""")

        flows = daemon._extract_data_flows(test_file)

        self.assertIsInstance(flows, list)
        self.assertGreater(len(flows), 0)

        queue_flow = next((f for f in flows if f['channel'] == 'events'), None)
        self.assertIsNotNone(queue_flow)
        self.assertEqual(queue_flow['producer'], 'DataProducer')
        self.assertEqual(queue_flow['channel_type'], 'queue')

    def test_ast_parsing_extracts_consumers(self):
        from src.orchestration.daemons.integration_monitor_daemon import IntegrationMonitorDaemon

        daemon = IntegrationMonitorDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "consumer.py"
        test_file.write_text("""
class EventProcessor:
    def __init__(self):
        self.events = []

    def process(self):
        for event in self.events:
            print(event)

        if len(self.events) > 0:
            last = self.events[-1]
""")

        flows = daemon._extract_data_flows(test_file)

        queue_flow = next((f for f in flows if f['channel'] == 'events'), None)
        self.assertIsNotNone(queue_flow)
        self.assertIsNotNone(queue_flow['consumer'])

    def test_orphaned_queue_detection(self):
        from src.orchestration.daemons.integration_monitor_daemon import IntegrationMonitorDaemon

        daemon = IntegrationMonitorDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        daemon.data_flows = {
            'orphaned_queue': {
                'producers': [('ProducerClass', str(self.temp_path / 'producer.py'))],
                'consumers': []
            },
            'healthy_queue': {
                'producers': [('ProducerClass', str(self.temp_path / 'producer.py'))],
                'consumers': [('ConsumerClass', str(self.temp_path / 'consumer.py'))]
            }
        }

        orphaned = daemon._detect_orphaned_queues()

        self.assertEqual(len(orphaned), 1)
        self.assertEqual(orphaned[0]['channel'], 'orphaned_queue')
        self.assertIn('ProducerClass', orphaned[0]['producers'])

    def test_missing_wiring_detection(self):
        from src.orchestration.daemons.integration_monitor_daemon import IntegrationMonitorDaemon

        daemon = IntegrationMonitorDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "missing_wiring.py"
        test_file.write_text("""
class BrokenComponent:
    def __init__(self):
        pass

    def use_manager(self):
        self.alert_manager.send_alert('test')
""")

        daemon.process_file_event('create', test_file)

        missing = daemon._detect_missing_wiring()

        self.assertGreater(len(missing), 0)
        self.assertIn('alert_manager', [m['attribute'] for m in missing])

    @patch('kloros.daemons.integration_monitor_daemon.ChemPub')
    def test_chembus_question_emission(self, mock_chem_pub):
        from src.orchestration.daemons.integration_monitor_daemon import IntegrationMonitorDaemon

        mock_pub_instance = MagicMock()
        mock_chem_pub.return_value = mock_pub_instance

        daemon = IntegrationMonitorDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        questions = [
            {
                'id': 'orphaned_queue_test',
                'channel': 'test_queue',
                'producers': 'TestProducer',
                'question': 'Is this queue orphaned?',
                'evidence': ['No consumers found']
            }
        ]

        daemon._emit_questions_to_chembus(questions)

        mock_pub_instance.emit.assert_called()

        # Verify keyword arguments (new API uses kwargs, not positional args)
        call_args = mock_pub_instance.emit.call_args
        self.assertEqual(call_args.kwargs['signal'], 'curiosity.integration_question')
        self.assertEqual(call_args.kwargs['ecosystem'], 'curiosity')
        self.assertIn('facts', call_args.kwargs)

    def test_state_save_and_load(self):
        from src.orchestration.daemons.integration_monitor_daemon import IntegrationMonitorDaemon

        daemon = IntegrationMonitorDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        daemon.file_hashes['test.py'] = 'abc123'
        daemon.data_flows['test_queue'] = {
            'producers': [('TestClass', '/test.py')],
            'consumers': []
        }

        daemon.save_state()

        self.assertTrue(self.state_file.exists())

        daemon2 = IntegrationMonitorDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )
        daemon2.load_state()

        self.assertEqual(daemon2.file_hashes.get('test.py'), 'abc123')
        self.assertIn('test_queue', daemon2.data_flows)

    def test_process_file_event_skips_unchanged(self):
        from src.orchestration.daemons.integration_monitor_daemon import IntegrationMonitorDaemon

        daemon = IntegrationMonitorDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "test.py"
        test_file.write_text("""
class TestClass:
    def __init__(self):
        self.orphaned_queue = []

    def add_item(self, item):
        self.orphaned_queue.append(item)
""")

        with patch.object(daemon, '_emit_questions_to_chembus') as mock_emit:
            daemon.process_file_event('modify', test_file)

            initial_call_count = mock_emit.call_count
            self.assertGreater(initial_call_count, 0, "Should emit questions on first change")

            daemon.process_file_event('modify', test_file)
            self.assertEqual(mock_emit.call_count, initial_call_count,
                           "Should not emit on second call with unchanged file")

    def test_memory_usage_stays_bounded(self):
        from src.orchestration.daemons.integration_monitor_daemon import IntegrationMonitorDaemon
        import psutil
        import os

        daemon = IntegrationMonitorDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        for i in range(100):
            test_file = self.temp_path / f"file_{i}.py"
            test_file.write_text(f"""
class TestClass{i}:
    def __init__(self):
        self.queue_{i} = []

    def add_item(self, item):
        self.queue_{i}.append(item)
""")
            daemon.process_file_event('create', test_file)

        daemon._evict_cache_if_needed()

        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / (1024 * 1024)

        self.assertLess(memory_mb, 150,
            f"Memory usage {memory_mb:.2f}MB exceeds 150MB limit")

    def test_integration_with_base_daemon(self):
        from src.orchestration.daemons.integration_monitor_daemon import IntegrationMonitorDaemon

        daemon = IntegrationMonitorDaemon(
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

    def test_delete_event_handling(self):
        from src.orchestration.daemons.integration_monitor_daemon import IntegrationMonitorDaemon

        daemon = IntegrationMonitorDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file
        )

        test_file = self.temp_path / "deleted.py"
        file_path_str = str(test_file)

        daemon.file_hashes[file_path_str] = 'abc123'
        daemon.data_flows['deleted_queue'] = {
            'producers': [('DeletedClass', file_path_str)],
            'consumers': []
        }

        daemon.process_file_event('delete', test_file)

        self.assertNotIn(file_path_str, daemon.file_hashes)

    def test_concurrent_file_processing(self):
        from src.orchestration.daemons.integration_monitor_daemon import IntegrationMonitorDaemon

        daemon = IntegrationMonitorDaemon(
            watch_path=self.temp_path,
            state_file=self.state_file,
            max_workers=3
        )

        for i in range(10):
            test_file = self.temp_path / f"concurrent_{i}.py"
            test_file.write_text(f"class Test{i}:\n    pass")

        daemon_thread = threading.Thread(target=daemon.start, daemon=True)
        daemon_thread.start()

        time.sleep(0.2)

        for i in range(10):
            test_file = self.temp_path / f"concurrent_{i}.py"
            daemon.event_queue.put(('create', test_file))

        time.sleep(1.0)

        daemon.shutdown_event.set()
        daemon_thread.join(timeout=2.0)

        self.assertGreater(len(daemon.file_hashes), 0)


if __name__ == '__main__':
    unittest.main()
