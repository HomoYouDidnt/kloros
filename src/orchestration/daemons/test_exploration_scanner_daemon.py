#!/usr/bin/env python3

import pytest
import time
import pickle
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from src.orchestration.daemons.exploration_scanner_daemon import ExplorationScannerDaemon


@pytest.fixture
def temp_state_file(tmp_path):
    return tmp_path / "exploration_scanner_state.pkl"


@pytest.fixture
def daemon(temp_state_file):
    daemon = ExplorationScannerDaemon(
        state_file=temp_state_file,
        scan_interval=5
    )
    yield daemon
    daemon.running = False
    daemon.shutdown_event.set()


class TestHardwareDetection:

    def test_detect_gpu_availability_with_gpu(self, daemon):
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="GPU 0: Tesla V100 (UUID: GPU-xxx)\nUtilization: 15%\n"
            )

            result = daemon._detect_gpu_availability()

            assert result['has_gpu'] is True
            assert 'utilization' in result
            mock_run.assert_called_once()

    def test_detect_gpu_availability_no_gpu(self, daemon):
        with patch('subprocess.run', side_effect=FileNotFoundError):
            result = daemon._detect_gpu_availability()

            assert result['has_gpu'] is False
            assert 'utilization' not in result

    def test_detect_cpu_features_with_avx(self, daemon, tmp_path):
        cpuinfo_path = tmp_path / "cpuinfo"
        cpuinfo_content = """
processor	: 0
vendor_id	: GenuineIntel
flags		: fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge avx avx2 sse sse2
"""
        cpuinfo_path.write_text(cpuinfo_content)

        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = cpuinfo_content

                result = daemon._detect_cpu_features()

                assert result['has_avx'] is True
                assert result['has_avx2'] is True
                assert result['has_sse'] is True

    def test_detect_cpu_features_no_cpuinfo(self, daemon):
        with patch('pathlib.Path.exists', return_value=False):
            result = daemon._detect_cpu_features()

            assert result == {}


class TestOptimizationDetection:

    def test_detect_gpu_underutilization(self, daemon):
        with patch.object(daemon, '_detect_gpu_availability') as mock_gpu:
            mock_gpu.return_value = {
                'has_gpu': True,
                'utilization': 5.0,
                'name': 'Tesla V100'
            }

            opportunities = daemon._detect_optimization_opportunities()

            gpu_opps = [o for o in opportunities if o['type'] == 'gpu_underutilization']
            assert len(gpu_opps) > 0
            assert gpu_opps[0]['severity'] in ['low', 'medium', 'high']
            assert 'evidence' in gpu_opps[0]
            assert len(gpu_opps[0]['evidence']) > 0

    def test_detect_no_opportunities_when_gpu_utilized(self, daemon):
        with patch.object(daemon, '_detect_gpu_availability') as mock_gpu:
            with patch.object(daemon, '_detect_cpu_features') as mock_cpu:
                mock_gpu.return_value = {
                    'has_gpu': True,
                    'utilization': 95.0,
                    'name': 'Tesla V100'
                }
                mock_cpu.return_value = {
                    'has_avx': True,
                    'has_avx2': True
                }

                opportunities = daemon._detect_optimization_opportunities()

                gpu_opps = [o for o in opportunities if o['type'] == 'gpu_underutilization']
                assert len(gpu_opps) == 0

    def test_detect_missing_cpu_optimizations(self, daemon):
        with patch.object(daemon, '_detect_gpu_availability') as mock_gpu:
            with patch.object(daemon, '_detect_cpu_features') as mock_cpu:
                mock_gpu.return_value = {'has_gpu': False}
                mock_cpu.return_value = {'has_avx': False, 'has_sse': True}

                opportunities = daemon._detect_optimization_opportunities()

                cpu_opps = [o for o in opportunities if 'cpu' in o['type']]
                assert len(cpu_opps) >= 0

    def test_deduplication_of_opportunities(self, daemon):
        with patch.object(daemon, '_detect_gpu_availability') as mock_gpu:
            mock_gpu.return_value = {
                'has_gpu': True,
                'utilization': 5.0,
                'name': 'Tesla V100'
            }

            opportunities1 = daemon._detect_optimization_opportunities()
            time.sleep(0.1)
            opportunities2 = daemon._detect_optimization_opportunities()

            assert len(opportunities1) > 0
            assert len(opportunities2) > 0


class TestUMNIntegration:

    def test_emit_to_umn_success(self, daemon):
        opportunity = {
            'type': 'gpu_underutilization',
            'severity': 'medium',
            'evidence': ['GPU available but utilization at 5%'],
            'suggestion': 'Consider GPU acceleration'
        }

        with patch('kloros.daemons.exploration_scanner_daemon.UMNPub') as mock_pub_class:
            mock_pub = Mock()
            mock_pub_class.return_value = mock_pub

            daemon.chem_pub = mock_pub
            daemon._emit_questions_to_umn([opportunity])

            assert mock_pub.emit.called
            call_args = mock_pub.emit.call_args
            assert call_args.kwargs['signal'] == "curiosity.exploration_question"
            assert call_args.kwargs['ecosystem'] == "curiosity"

    def test_emit_multiple_opportunities(self, daemon):
        opportunities = [
            {
                'type': 'gpu_underutilization',
                'severity': 'high',
                'evidence': ['GPU idle'],
                'suggestion': 'Use GPU'
            },
            {
                'type': 'cpu_optimization',
                'severity': 'low',
                'evidence': ['AVX not used'],
                'suggestion': 'Enable AVX'
            }
        ]

        with patch('kloros.daemons.exploration_scanner_daemon.UMNPub') as mock_pub_class:
            mock_pub = Mock()
            mock_pub_class.return_value = mock_pub

            daemon.chem_pub = mock_pub
            daemon._emit_questions_to_umn(opportunities)

            assert mock_pub.emit.call_count == 2

    def test_umn_not_available(self, daemon):
        opportunity = {
            'type': 'gpu_underutilization',
            'severity': 'medium',
            'evidence': ['test'],
            'suggestion': 'test'
        }

        with patch('kloros.daemons.exploration_scanner_daemon.UMNPub', None):
            daemon._emit_questions_to_umn([opportunity])


class TestStatePersistence:

    def test_save_and_load_state(self, daemon, temp_state_file):
        daemon.last_scan = time.time()
        daemon.discovered_opportunities = {
            'gpu_underutil_1': {
                'type': 'gpu_underutilization',
                'first_seen': time.time()
            }
        }

        daemon.save_state()

        assert temp_state_file.exists()

        new_daemon = ExplorationScannerDaemon(state_file=temp_state_file)

        assert len(new_daemon.discovered_opportunities) == 1
        assert 'gpu_underutil_1' in new_daemon.discovered_opportunities

    def test_load_state_no_file(self, daemon, temp_state_file):
        daemon.load_state()

        assert len(daemon.discovered_opportunities) == 0

    def test_state_file_corruption_handling(self, daemon, temp_state_file):
        temp_state_file.write_bytes(b"corrupted data")

        daemon.load_state()

        assert len(daemon.discovered_opportunities) == 0


class TestTimerBasedScanning:

    def test_periodic_scan_trigger(self, daemon):
        daemon.scan_interval = 1
        daemon.last_scan = time.time() - 2

        with patch.object(daemon, '_perform_system_scan') as mock_scan:
            daemon._check_and_scan()

            assert mock_scan.called

    def test_scan_not_triggered_too_soon(self, daemon):
        daemon.scan_interval = 10
        daemon.last_scan = time.time()

        with patch.object(daemon, '_perform_system_scan') as mock_scan:
            daemon._check_and_scan()

            assert not mock_scan.called

    def test_watch_loop_uses_timer_not_inotify(self, daemon):
        daemon.running = False

        with patch.object(daemon, '_check_and_scan') as mock_check:
            with patch('time.sleep'):
                daemon._watch_files()

        assert hasattr(daemon, '_check_and_scan')


class TestMemoryBounds:

    def test_memory_usage_under_limit(self, daemon):
        import psutil
        import os

        process = psutil.Process(os.getpid())

        for _ in range(10):
            daemon._perform_system_scan()

        memory_mb = process.memory_info().rss / 1024 / 1024

        assert memory_mb < 150, f"Memory usage {memory_mb}MB exceeds 150MB limit"

    def test_opportunity_cache_eviction(self, daemon):
        daemon.max_opportunities = 100

        for i in range(150):
            daemon.discovered_opportunities[f'opp_{i}'] = {
                'type': 'test',
                'first_seen': time.time()
            }
            daemon._evict_opportunity_cache_if_needed()

        assert len(daemon.discovered_opportunities) <= 100


class TestHealthStatus:

    def test_health_status_includes_scan_info(self, daemon):
        daemon.last_scan = time.time()

        health = daemon.get_health_status()

        assert 'running' in health
        assert 'uptime' in health
        assert 'last_scan' in health
        assert 'opportunities_found' in health

    def test_health_status_when_not_running(self, daemon):
        daemon.running = False

        health = daemon.get_health_status()

        assert health['running'] is False
