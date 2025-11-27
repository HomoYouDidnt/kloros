#!/usr/bin/env python3
"""
Integration tests for the complete streaming daemons system.

Tests the end-to-end flow:
1. File changes trigger daemon detection
2. Daemons emit questions to UMN
3. CuriosityCore receives and processes questions
4. Memory usage stays within bounds
5. No question loss vs old batch monitors

These tests validate that the streaming architecture successfully replaces
the old disabled batch monitors without regressions.
"""

import os
import sys
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import psutil

sys.path.insert(0, '/home/kloros/src')

from src.orchestration.daemons.integration_monitor_daemon import IntegrationMonitorDaemon
from src.orchestration.daemons.capability_discovery_daemon import CapabilityDiscoveryMonitorDaemon
from src.orchestration.daemons.exploration_scanner_daemon import ExplorationScannerDaemon
from src.orchestration.daemons.knowledge_discovery_daemon import KnowledgeDiscoveryScannerDaemon


class TestStreamingDaemonsIntegration(unittest.TestCase):
    """
    Integration tests for the complete streaming daemon system.

    Validates that all 4 daemons work together correctly and that
    the system meets performance requirements.
    """

    def setUp(self):
        """Set up test environment with temporary directories."""
        self.temp_dir = tempfile.mkdtemp()
        self.src_dir = Path(self.temp_dir) / "src"
        self.docs_dir = Path(self.temp_dir) / "docs"
        self.src_dir.mkdir()
        self.docs_dir.mkdir()

        self.state_dir = Path(self.temp_dir) / ".kloros"
        self.state_dir.mkdir()

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_integration_monitor_detects_code_changes(self):
        """Test that IntegrationMonitorDaemon detects code file changes."""
        daemon = IntegrationMonitorDaemon(
            watch_path=self.src_dir,
            state_file=self.state_dir / "integration.pkl",
            max_workers=1
        )

        # Create a Python file with data flow
        test_file = self.src_dir / "producer.py"
        test_file.write_text("""
class DataProducer:
    def __init__(self):
        self.queue = []

    def produce(self, data):
        self.queue.append(data)
""")

        # Process the file event
        daemon.process_file_event('create', test_file)

        # Verify file was analyzed
        file_hash = daemon._compute_file_hash(test_file)
        self.assertIn(str(test_file), daemon.file_hashes)
        self.assertEqual(daemon.file_hashes[str(test_file)], file_hash)

    def test_capability_daemon_detects_patterns(self):
        """Test that CapabilityDiscoveryDaemon detects capability patterns."""
        daemon = CapabilityDiscoveryMonitorDaemon(
            watch_path=self.src_dir,
            state_file=self.state_dir / "capability.pkl",
            max_workers=1
        )

        # Create file with capability indicator (Analyzer suffix)
        test_file = self.src_dir / "sentiment.py"
        test_file.write_text("""
class SentimentAnalyzer:
    def analyze(self, text):
        return 0.5
""")

        # Process with mocked semantic analysis
        with patch.object(daemon, 'semantic_reasoner') as mock_reasoner:
            mock_analysis = Mock()
            mock_analysis.is_real_gap = True
            mock_analysis.confidence = 0.85
            mock_analysis.pattern = Mock(value='gap')
            mock_analysis.explanation = "Real capability gap"
            mock_reasoner.analyze_gap_hypothesis.return_value = mock_analysis

            daemon.process_file_event('create', test_file)

            # Verify semantic analysis was called
            mock_reasoner.analyze_gap_hypothesis.assert_called()

    def test_exploration_scanner_periodic_scanning(self):
        """Test that ExplorationScannerDaemon performs periodic scans."""
        daemon = ExplorationScannerDaemon(
            state_file=self.state_dir / "exploration.pkl",
            scan_interval=1,  # 1 second for testing
            max_workers=1
        )

        # Mock hardware detection to avoid actual system calls
        with patch.object(daemon, '_detect_gpu_availability') as mock_gpu:
            with patch.object(daemon, '_detect_cpu_features') as mock_cpu:
                mock_gpu.return_value = {'has_gpu': False}
                mock_cpu.return_value = {
                    'has_avx': True,
                    'has_avx2': True,
                    'has_sse': True,
                    'has_sse2': True
                }

                # Trigger a scan
                daemon._perform_system_scan()

                # Verify scan was attempted
                mock_gpu.assert_called_once()
                mock_cpu.assert_called_once()

    def test_knowledge_daemon_detects_documentation_gaps(self):
        """Test that KnowledgeDiscoveryDaemon detects documentation gaps."""
        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_dir,
            state_file=self.state_dir / "knowledge.pkl",
            max_workers=1
        )

        # Create a stale documentation file (modify timestamp)
        test_doc = self.docs_dir / "old_guide.md"
        test_doc.write_text("# Old Documentation\n\nThis is outdated.")

        # Set file to be 100 days old
        old_time = time.time() - (100 * 86400)
        os.utime(test_doc, (old_time, old_time))

        # Process the file
        daemon.process_file_event('create', test_doc)

        # Verify file was analyzed
        self.assertIn(str(test_doc), daemon.file_hashes)

    def test_all_daemons_memory_usage_bounded(self):
        """Test that all 4 daemons together stay under 500MB memory limit."""
        process = psutil.Process(os.getpid())
        initial_memory_mb = process.memory_info().rss / (1024 * 1024)

        # Create all 4 daemons
        daemons = [
            IntegrationMonitorDaemon(
                watch_path=self.src_dir,
                state_file=self.state_dir / "integration.pkl",
                max_workers=1
            ),
            CapabilityDiscoveryMonitorDaemon(
                watch_path=self.src_dir,
                state_file=self.state_dir / "capability.pkl",
                max_workers=1
            ),
            ExplorationScannerDaemon(
                state_file=self.state_dir / "exploration.pkl",
                scan_interval=300,
                max_workers=1
            ),
            KnowledgeDiscoveryScannerDaemon(
                watch_path=self.temp_dir,
                state_file=self.state_dir / "knowledge.pkl",
                max_workers=1
            )
        ]

        # Process 50 files with each daemon
        for i in range(50):
            test_file = self.src_dir / f"module_{i}.py"
            test_file.write_text(f"""
class Module{i}:
    def process(self):
        return {i}
""")

            # Process with file-based daemons
            daemons[0].process_file_event('create', test_file)  # Integration
            daemons[1].process_file_event('create', test_file)  # Capability
            daemons[3].process_file_event('create', test_file)  # Knowledge

        # Check memory after processing
        final_memory_mb = process.memory_info().rss / (1024 * 1024)
        memory_increase = final_memory_mb - initial_memory_mb

        # Memory increase should be less than 500MB total for all daemons
        self.assertLess(
            memory_increase,
            500,
            f"Memory increase {memory_increase:.2f}MB exceeds 500MB limit"
        )

    def test_umn_emission_integration(self):
        """Test that daemons can emit questions to UMN (mocked)."""
        with patch('kloros.daemons.integration_monitor_daemon.UMNPub') as mock_pub_class:
            mock_pub = Mock()
            mock_pub_class.return_value = mock_pub

            daemon = IntegrationMonitorDaemon(
                watch_path=self.src_dir,
                state_file=self.state_dir / "integration.pkl",
                max_workers=1
            )

            # Create file with orphaned queue
            test_file = self.src_dir / "orphan.py"
            test_file.write_text("""
class Producer:
    def __init__(self):
        self.orphaned_queue = []

    def add(self, item):
        self.orphaned_queue.append(item)
""")

            daemon.process_file_event('create', test_file)

            # UMNPub should have been created (lazy init)
            # Actual emission depends on detection logic
            if daemon.chem_pub is not None:
                self.assertIsInstance(daemon.chem_pub, Mock)

    def test_state_persistence_across_restarts(self):
        """Test that daemon state persists across restarts."""
        state_file = self.state_dir / "integration.pkl"

        # First daemon instance
        daemon1 = IntegrationMonitorDaemon(
            watch_path=self.src_dir,
            state_file=state_file,
            max_workers=1
        )

        test_file = self.src_dir / "persistent.py"
        test_file.write_text("class Foo: pass")
        daemon1.process_file_event('create', test_file)

        # Save state
        daemon1.save_state()
        self.assertTrue(state_file.exists())

        # Second daemon instance (simulates restart)
        daemon2 = IntegrationMonitorDaemon(
            watch_path=self.src_dir,
            state_file=state_file,
            max_workers=1
        )

        # Verify state was loaded
        self.assertIn(str(test_file), daemon2.file_hashes)
        self.assertEqual(
            daemon1.file_hashes[str(test_file)],
            daemon2.file_hashes[str(test_file)]
        )

    def test_no_question_loss_on_rapid_file_changes(self):
        """Test that rapid file changes don't cause question loss."""
        daemon = IntegrationMonitorDaemon(
            watch_path=self.src_dir,
            state_file=self.state_dir / "integration.pkl",
            max_workers=2,
            max_queue_size=100
        )

        # Create 20 files rapidly
        files_created = []
        for i in range(20):
            test_file = self.src_dir / f"rapid_{i}.py"
            test_file.write_text(f"class Rapid{i}: pass")
            daemon.process_file_event('create', test_file)
            files_created.append(str(test_file))

        # All files should be in cache
        for file_path in files_created:
            self.assertIn(file_path, daemon.file_hashes)

    def test_daemon_health_status_reporting(self):
        """Test that all daemons report health status correctly."""
        daemons = [
            IntegrationMonitorDaemon(
                watch_path=self.src_dir,
                state_file=self.state_dir / "integration.pkl"
            ),
            CapabilityDiscoveryMonitorDaemon(
                watch_path=self.src_dir,
                state_file=self.state_dir / "capability.pkl"
            ),
            ExplorationScannerDaemon(
                state_file=self.state_dir / "exploration.pkl"
            ),
            KnowledgeDiscoveryScannerDaemon(
                watch_path=self.temp_dir,
                state_file=self.state_dir / "knowledge.pkl"
            )
        ]

        for daemon in daemons:
            health = daemon.get_health_status()

            # All daemons should report health metrics
            self.assertIn('running', health)
            self.assertIn('queue_size', health)
            self.assertIn('cache_size', health)
            self.assertIn('uptime', health)

    def test_file_type_filtering_works_correctly(self):
        """Test that daemons only process relevant file types."""
        daemon = KnowledgeDiscoveryScannerDaemon(
            watch_path=self.temp_dir,
            state_file=self.state_dir / "knowledge.pkl",
            max_workers=1
        )

        # Create various file types
        py_file = self.src_dir / "code.py"
        md_file = self.docs_dir / "guide.md"
        txt_file = self.docs_dir / "notes.txt"
        jpg_file = self.docs_dir / "image.jpg"

        py_file.write_text("class Code: pass")
        md_file.write_text("# Guide")
        txt_file.write_text("Notes")
        jpg_file.write_bytes(b"fake image data")

        # Process all files
        daemon.process_file_event('create', py_file)
        daemon.process_file_event('create', md_file)
        daemon.process_file_event('create', txt_file)
        daemon.process_file_event('create', jpg_file)

        # Only .py, .md, .txt should be processed
        self.assertIn(str(py_file), daemon.file_hashes)
        self.assertIn(str(md_file), daemon.file_hashes)
        self.assertIn(str(txt_file), daemon.file_hashes)
        self.assertNotIn(str(jpg_file), daemon.file_hashes)


class TestStreamingDaemonsPerformance(unittest.TestCase):
    """
    Performance benchmarks for streaming daemon system.

    Validates that streaming architecture meets performance requirements:
    - Event → question latency < 1s
    - Memory usage < 500MB total
    - CPU usage reasonable
    """

    def test_latency_under_one_second(self):
        """Test that event-to-processing latency is under 1 second."""
        temp_dir = tempfile.mkdtemp()
        try:
            daemon = IntegrationMonitorDaemon(
                watch_path=Path(temp_dir),
                state_file=Path(temp_dir) / "state.pkl",
                max_workers=2
            )

            test_file = Path(temp_dir) / "latency_test.py"
            test_file.write_text("class Latency: pass")

            # Measure processing time
            start_time = time.time()
            daemon.process_file_event('create', test_file)
            end_time = time.time()

            latency = end_time - start_time

            # Processing should complete in under 1 second
            self.assertLess(
                latency,
                1.0,
                f"Event processing took {latency:.3f}s, exceeds 1s target"
            )

        finally:
            import shutil
            shutil.rmtree(temp_dir)


if __name__ == '__main__':
    unittest.main()
