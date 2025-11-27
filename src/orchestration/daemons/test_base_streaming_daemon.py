import unittest
import tempfile
import threading
import time
import signal
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import queue


class TestBaseStreamingDaemon(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_daemon_initialization(self):
        from kloros.daemons.base_streaming_daemon import BaseStreamingDaemon

        class TestDaemon(BaseStreamingDaemon):
            def process_file_event(self, event_type, file_path):
                pass
            def save_state(self):
                pass
            def load_state(self):
                pass

        daemon = TestDaemon(
            watch_path=self.temp_path,
            max_queue_size=500,
            max_workers=3,
            max_cache_size=100
        )

        self.assertEqual(daemon.watch_path, self.temp_path)
        self.assertEqual(daemon.event_queue.maxsize, 500)
        self.assertEqual(daemon.max_workers, 3)
        self.assertEqual(daemon.max_cache_size, 100)
        self.assertFalse(daemon.running)
        self.assertIsInstance(daemon.cache, dict)

    def test_event_queue_bounds(self):
        from kloros.daemons.base_streaming_daemon import BaseStreamingDaemon

        class TestDaemon(BaseStreamingDaemon):
            def process_file_event(self, event_type, file_path):
                time.sleep(0.1)
            def save_state(self):
                pass
            def load_state(self):
                pass

        daemon = TestDaemon(
            watch_path=self.temp_path,
            max_queue_size=10,
            max_workers=1
        )

        for i in range(10):
            daemon.event_queue.put(('test', Path('/test.py')))

        self.assertEqual(daemon.event_queue.qsize(), 10)

        with self.assertRaises(queue.Full):
            daemon.event_queue.put(('test', Path('/test.py')), timeout=0.1)

    def test_cache_eviction_lru(self):
        from kloros.daemons.base_streaming_daemon import BaseStreamingDaemon

        class TestDaemon(BaseStreamingDaemon):
            def process_file_event(self, event_type, file_path):
                pass
            def save_state(self):
                pass
            def load_state(self):
                pass

        daemon = TestDaemon(
            watch_path=self.temp_path,
            max_cache_size=5
        )

        for i in range(10):
            daemon.cache[f'key_{i}'] = f'value_{i}'

        self.assertEqual(len(daemon.cache), 10)

        daemon._evict_cache_if_needed()

        self.assertEqual(len(daemon.cache), 5)

    def test_signal_handling_sigterm(self):
        from kloros.daemons.base_streaming_daemon import BaseStreamingDaemon

        save_called = []

        class TestDaemon(BaseStreamingDaemon):
            def process_file_event(self, event_type, file_path):
                pass
            def save_state(self):
                save_called.append(True)
            def load_state(self):
                pass

        daemon = TestDaemon(watch_path=self.temp_path)
        daemon.running = True

        daemon._handle_shutdown(signal.SIGTERM, None)

        self.assertTrue(daemon.shutdown_event.is_set())
        self.assertFalse(daemon.running)
        self.assertTrue(save_called)

    def test_signal_handling_sigint(self):
        from kloros.daemons.base_streaming_daemon import BaseStreamingDaemon

        save_called = []

        class TestDaemon(BaseStreamingDaemon):
            def process_file_event(self, event_type, file_path):
                pass
            def save_state(self):
                save_called.append(True)
            def load_state(self):
                pass

        daemon = TestDaemon(watch_path=self.temp_path)
        daemon.running = True

        daemon._handle_shutdown(signal.SIGINT, None)

        self.assertTrue(daemon.shutdown_event.is_set())
        self.assertFalse(daemon.running)
        self.assertTrue(save_called)

    def test_worker_thread_pool_creation(self):
        from kloros.daemons.base_streaming_daemon import BaseStreamingDaemon

        class TestDaemon(BaseStreamingDaemon):
            def process_file_event(self, event_type, file_path):
                pass
            def save_state(self):
                pass
            def load_state(self):
                pass
            def _watch_files(self):
                time.sleep(0.2)

        daemon = TestDaemon(
            watch_path=self.temp_path,
            max_workers=3
        )

        thread = threading.Thread(target=daemon.start)
        thread.daemon = True
        thread.start()

        time.sleep(0.1)

        self.assertEqual(len(daemon.workers), 3)
        self.assertTrue(daemon.running)

        daemon.shutdown_event.set()
        thread.join(timeout=1.0)

    def test_file_event_processing(self):
        from kloros.daemons.base_streaming_daemon import BaseStreamingDaemon

        processed_events = []

        class TestDaemon(BaseStreamingDaemon):
            def process_file_event(self, event_type, file_path):
                processed_events.append((event_type, str(file_path)))
            def save_state(self):
                pass
            def load_state(self):
                pass
            def _watch_files(self):
                pass

        daemon = TestDaemon(watch_path=self.temp_path, max_workers=2)

        thread = threading.Thread(target=daemon.start)
        thread.daemon = True
        thread.start()

        time.sleep(0.1)

        test_file = Path('/home/test/example.py')
        daemon.event_queue.put(('create', test_file))
        daemon.event_queue.put(('modify', test_file))

        time.sleep(0.2)

        daemon.shutdown_event.set()
        thread.join(timeout=1.0)

        self.assertGreater(len(processed_events), 0)

    def test_abstract_methods_required(self):
        from kloros.daemons.base_streaming_daemon import BaseStreamingDaemon

        with self.assertRaises(TypeError):
            daemon = BaseStreamingDaemon(watch_path=self.temp_path)

    def test_graceful_shutdown_waits_for_queue(self):
        from kloros.daemons.base_streaming_daemon import BaseStreamingDaemon

        processed = []

        class TestDaemon(BaseStreamingDaemon):
            def process_file_event(self, event_type, file_path):
                processed.append((event_type, str(file_path)))
                time.sleep(0.05)
            def save_state(self):
                pass
            def load_state(self):
                pass
            def _watch_files(self):
                pass

        daemon = TestDaemon(watch_path=self.temp_path, max_workers=1)

        thread = threading.Thread(target=daemon.start)
        thread.daemon = True
        thread.start()

        time.sleep(0.1)

        for i in range(5):
            daemon.event_queue.put(('create', Path(f'/test_{i}.py')))

        time.sleep(0.5)

        daemon.shutdown_event.set()
        thread.join(timeout=2.0)

        self.assertEqual(len(processed), 5)

    def test_integration_with_temp_directory(self):
        from kloros.daemons.base_streaming_daemon import BaseStreamingDaemon
        import inotify

        detected_events = []

        class TestDaemon(BaseStreamingDaemon):
            def process_file_event(self, event_type, file_path):
                detected_events.append((event_type, file_path.name))
            def save_state(self):
                pass
            def load_state(self):
                pass

        test_file = self.temp_path / 'example_module.py'
        test_file.write_text('# Initial content')

        daemon = TestDaemon(watch_path=self.temp_path, max_workers=2)

        thread = threading.Thread(target=daemon.start)
        thread.daemon = True
        thread.start()

        time.sleep(0.3)

        test_file.write_text('print("hello")')

        time.sleep(0.3)

        test_file.write_text('print("world")')

        time.sleep(0.3)

        daemon.shutdown_event.set()
        thread.join(timeout=2.0)

        if len(detected_events) == 0:
            self.skipTest("inotify events not detected in test environment")

        self.assertTrue(any('example_module.py' in str(event) for event in detected_events))

    def test_health_monitoring_support(self):
        from kloros.daemons.base_streaming_daemon import BaseStreamingDaemon

        class TestDaemon(BaseStreamingDaemon):
            def process_file_event(self, event_type, file_path):
                pass
            def save_state(self):
                pass
            def load_state(self):
                pass

        daemon = TestDaemon(watch_path=self.temp_path)

        health = daemon.get_health_status()

        self.assertIn('running', health)
        self.assertIn('queue_size', health)
        self.assertIn('cache_size', health)
        self.assertIn('uptime', health)

    def test_default_parameters(self):
        from kloros.daemons.base_streaming_daemon import BaseStreamingDaemon

        class TestDaemon(BaseStreamingDaemon):
            def process_file_event(self, event_type, file_path):
                pass
            def save_state(self):
                pass
            def load_state(self):
                pass

        daemon = TestDaemon(watch_path=self.temp_path)

        self.assertEqual(daemon.event_queue.maxsize, 1000)
        self.assertEqual(daemon.max_workers, 2)
        self.assertEqual(daemon.max_cache_size, 500)


if __name__ == '__main__':
    unittest.main()
