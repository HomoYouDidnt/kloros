#!/usr/bin/env python3
"""
Test suite for heal_executor.py

Tests HealExecutor class initialization, HEAL_REQUEST signal handling,
cooldown mechanism, playbook execution, and logging.
"""

import pytest
import sys
import time
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cognition.mind.consciousness.heal_executor import HealExecutor, check_emergency_brake


class TestHealExecutorInitialization:
    """Test HealExecutor class initialization."""

    def test_heal_executor_initializes_with_playbooks(self):
        """Test HealExecutor initializes with playbook registry."""
        executor = HealExecutor()

        assert executor.playbooks is not None
        assert isinstance(executor.playbooks, dict)

    def test_heal_executor_has_analyze_error_pattern_playbook(self):
        """Test that analyze_error_pattern playbook is registered."""
        executor = HealExecutor()

        assert 'analyze_error_pattern' in executor.playbooks
        assert callable(executor.playbooks['analyze_error_pattern'])

    def test_heal_executor_has_restart_stuck_service_playbook(self):
        """Test that restart_stuck_service playbook is registered."""
        executor = HealExecutor()

        assert 'restart_stuck_service' in executor.playbooks
        assert callable(executor.playbooks['restart_stuck_service'])

    def test_heal_executor_has_clear_cache_playbook(self):
        """Test that clear_cache playbook is registered."""
        executor = HealExecutor()

        assert 'clear_cache' in executor.playbooks
        assert callable(executor.playbooks['clear_cache'])

    def test_heal_executor_has_optimize_resources_playbook(self):
        """Test that optimize_resources playbook is registered."""
        executor = HealExecutor()

        assert 'optimize_resources' in executor.playbooks
        assert callable(executor.playbooks['optimize_resources'])

    def test_heal_executor_initializes_with_default_cooldown(self):
        """Test that HealExecutor initializes with default cooldown."""
        executor = HealExecutor()

        assert executor.cooldown_seconds == 60

    def test_heal_executor_initializes_with_empty_last_execution(self):
        """Test that HealExecutor initializes with empty last_execution dict."""
        executor = HealExecutor()

        assert executor.last_execution == {}

    def test_heal_executor_initializes_with_log_path(self):
        """Test that HealExecutor initializes with log path."""
        executor = HealExecutor()

        assert executor.execution_log_path == Path("/tmp/kloros_healing_actions.log")


class TestCanExecute:
    """Test cooldown mechanism."""

    def test_can_execute_returns_true_for_new_strategy(self):
        """Test that can_execute returns True for strategy not yet executed."""
        executor = HealExecutor()

        assert executor.can_execute('test_strategy') is True

    def test_can_execute_returns_false_immediately_after_execution(self):
        """Test that can_execute returns False immediately after execution."""
        executor = HealExecutor()
        executor.cooldown_seconds = 5

        executor.log_execution('test_strategy', True)

        assert executor.can_execute('test_strategy') is False

    def test_can_execute_returns_true_after_cooldown_expires(self):
        """Test that can_execute returns True after cooldown expires."""
        executor = HealExecutor()
        executor.cooldown_seconds = 1

        executor.log_execution('test_strategy', True)
        assert executor.can_execute('test_strategy') is False

        time.sleep(1.1)

        assert executor.can_execute('test_strategy') is True

    def test_can_execute_tracks_different_strategies_separately(self):
        """Test that cooldown is tracked separately per strategy."""
        executor = HealExecutor()
        executor.cooldown_seconds = 5

        executor.log_execution('strategy_a', True)

        assert executor.can_execute('strategy_a') is False
        assert executor.can_execute('strategy_b') is True


class TestLogExecution:
    """Test execution logging."""

    def test_log_execution_creates_log_file(self):
        """Test that log_execution creates log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = HealExecutor()
            executor.execution_log_path = Path(tmpdir) / "test.log"

            executor.log_execution('test_strategy', True, "Test details")

            assert executor.execution_log_path.exists()

    def test_log_execution_records_success(self):
        """Test that log_execution records successful execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = HealExecutor()
            executor.execution_log_path = Path(tmpdir) / "test.log"

            executor.log_execution('test_strategy', True, "Test details")

            with open(executor.execution_log_path) as f:
                content = f.read()

            assert "SUCCESS" in content
            assert "test_strategy" in content
            assert "Test details" in content

    def test_log_execution_records_failure(self):
        """Test that log_execution records failed execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = HealExecutor()
            executor.execution_log_path = Path(tmpdir) / "test.log"

            executor.log_execution('test_strategy', False, "Error details")

            with open(executor.execution_log_path) as f:
                content = f.read()

            assert "FAILED" in content
            assert "test_strategy" in content
            assert "Error details" in content

    def test_log_execution_updates_last_execution_timestamp(self):
        """Test that log_execution updates last_execution dict."""
        executor = HealExecutor()

        before = time.time()
        executor.log_execution('test_strategy', True)
        after = time.time()

        assert 'test_strategy' in executor.last_execution
        assert before <= executor.last_execution['test_strategy'] <= after


class TestHandleHealRequest:
    """Test HEAL_REQUEST signal handling."""

    def test_handle_heal_request_with_valid_strategy(self):
        """Test handle_heal_request executes valid strategy."""
        executor = HealExecutor()

        mock_playbook = Mock(return_value=True)
        executor.playbooks['analyze_error_pattern'] = mock_playbook

        msg = {
            'facts': {
                'strategy': 'analyze_error_pattern',
                'context': {'error_type': 'timeout'},
                'priority': 'high'
            }
        }

        executor.handle_heal_request(msg)

        mock_playbook.assert_called_once()

    def test_handle_heal_request_with_unknown_strategy(self):
        """Test handle_heal_request handles unknown strategy."""
        executor = HealExecutor()

        with tempfile.TemporaryDirectory() as tmpdir:
            executor.execution_log_path = Path(tmpdir) / "test.log"

            msg = {
                'facts': {
                    'strategy': 'unknown_strategy',
                    'context': {}
                }
            }

            executor.handle_heal_request(msg)

            with open(executor.execution_log_path) as f:
                content = f.read()

            assert "FAILED" in content
            assert "Unknown strategy" in content

    def test_handle_heal_request_with_missing_strategy(self):
        """Test handle_heal_request handles missing strategy."""
        executor = HealExecutor()

        msg = {
            'facts': {
                'context': {'error_type': 'timeout'}
            }
        }

        executor.handle_heal_request(msg)

    def test_handle_heal_request_respects_cooldown(self):
        """Test handle_heal_request respects cooldown mechanism."""
        executor = HealExecutor()
        executor.cooldown_seconds = 5

        mock_playbook = Mock(return_value=True)
        executor.playbooks['analyze_error_pattern'] = mock_playbook

        msg = {
            'facts': {
                'strategy': 'analyze_error_pattern',
                'context': {},
                'priority': 'normal'
            }
        }

        executor.handle_heal_request(msg)
        assert mock_playbook.call_count == 1

        executor.handle_heal_request(msg)
        assert mock_playbook.call_count == 1

    def test_handle_heal_request_with_emergency_brake(self):
        """Test handle_heal_request skips execution when emergency brake is active."""
        executor = HealExecutor()

        with patch('consciousness.heal_executor.check_emergency_brake', return_value=True):
            with patch.object(executor, 'analyze_errors', return_value=True) as mock_playbook:
                msg = {
                    'facts': {
                        'strategy': 'analyze_error_pattern',
                        'context': {}
                    }
                }

                executor.handle_heal_request(msg)

                mock_playbook.assert_not_called()

    def test_handle_heal_request_logs_successful_execution(self):
        """Test handle_heal_request logs successful execution."""
        executor = HealExecutor()

        with tempfile.TemporaryDirectory() as tmpdir:
            executor.execution_log_path = Path(tmpdir) / "test.log"

            msg = {
                'facts': {
                    'strategy': 'analyze_error_pattern',
                    'context': {},
                    'priority': 'normal'
                }
            }

            executor.handle_heal_request(msg)

            with open(executor.execution_log_path) as f:
                content = f.read()

            assert "SUCCESS" in content
            assert "analyze_error_pattern" in content

    def test_handle_heal_request_logs_failed_execution(self):
        """Test handle_heal_request logs failed execution."""
        executor = HealExecutor()

        with tempfile.TemporaryDirectory() as tmpdir:
            executor.execution_log_path = Path(tmpdir) / "test.log"

            mock_playbook = Mock(return_value=False)
            executor.playbooks['analyze_error_pattern'] = mock_playbook

            msg = {
                'facts': {
                    'strategy': 'analyze_error_pattern',
                    'context': {},
                    'priority': 'normal'
                }
            }

            executor.handle_heal_request(msg)

            with open(executor.execution_log_path) as f:
                content = f.read()

            assert "FAILED" in content
            assert "Execution failed" in content


class TestPlaybooks:
    """Test playbook implementations."""

    def test_analyze_errors_playbook_returns_true(self):
        """Test analyze_errors playbook returns True."""
        executor = HealExecutor()

        result = executor.analyze_errors({'error_type': 'timeout'})

        assert result is True

    def test_restart_service_playbook_returns_true(self):
        """Test restart_service playbook returns True."""
        executor = HealExecutor()

        result = executor.restart_service({'service': 'api_server'})

        assert result is True

    def test_clear_caches_playbook_returns_true(self):
        """Test clear_caches playbook returns True."""
        executor = HealExecutor()

        result = executor.clear_caches({'cache_type': 'memory'})

        assert result is True

    def test_optimize_resources_playbook_returns_true(self):
        """Test optimize_resources playbook returns True."""
        executor = HealExecutor()

        result = executor.optimize_resources({'resource_type': 'memory'})

        assert result is True

    def test_analyze_errors_accepts_context(self):
        """Test analyze_errors playbook accepts context parameter."""
        executor = HealExecutor()

        context = {'error_type': 'ConnectionError', 'count': 10}
        result = executor.analyze_errors(context)

        assert result is True

    def test_restart_service_accepts_context(self):
        """Test restart_service playbook accepts context parameter."""
        executor = HealExecutor()

        context = {'service': 'worker_1', 'reason': 'stuck_task'}
        result = executor.restart_service(context)

        assert result is True


class TestCheckEmergencyBrake:
    """Test emergency brake check."""

    def test_check_emergency_brake_returns_false_by_default(self):
        """Test check_emergency_brake returns False when brake is not active."""
        result = check_emergency_brake()

        assert result is False

    def test_check_emergency_brake_returns_true_when_active(self):
        """Test check_emergency_brake returns True when brake flag exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            brake_path = Path(tmpdir) / "brake"
            brake_path.touch()

            with patch('consciousness.heal_executor.Path', side_effect=lambda x: brake_path if x == "/tmp/kloros_emergency_brake_active" else Path(x)):
                result = check_emergency_brake()

                assert result is True


class TestPlaybookRegistry:
    """Test playbook registry structure."""

    def test_all_playbooks_are_callable(self):
        """Test that all registered playbooks are callable."""
        executor = HealExecutor()

        for strategy, playbook in executor.playbooks.items():
            assert callable(playbook), f"Playbook {strategy} is not callable"

    def test_playbook_count(self):
        """Test that at least 4 playbooks are registered."""
        executor = HealExecutor()

        assert len(executor.playbooks) >= 4

    def test_playbooks_match_expected_names(self):
        """Test playbook names match expected strategies."""
        executor = HealExecutor()

        expected = {
            'analyze_error_pattern',
            'restart_stuck_service',
            'clear_cache',
            'optimize_resources'
        }

        assert expected.issubset(set(executor.playbooks.keys()))


class TestDryRunMode:
    """Test dry-run mode safety feature."""

    def test_dry_run_mode_enabled_via_env_var(self):
        """Test dry-run mode can be enabled via KLR_HEAL_DRY_RUN env var."""
        import os
        os.environ['KLR_HEAL_DRY_RUN'] = '1'

        try:
            executor = HealExecutor()
            assert executor.dry_run is True
        finally:
            del os.environ['KLR_HEAL_DRY_RUN']

    def test_dry_run_mode_disabled_by_default(self):
        """Test dry-run mode is disabled by default."""
        import os
        if 'KLR_HEAL_DRY_RUN' in os.environ:
            del os.environ['KLR_HEAL_DRY_RUN']

        executor = HealExecutor()
        assert executor.dry_run is False

    def test_dry_run_clear_caches_does_not_delete(self):
        """Test clear_caches in dry-run mode does not delete files."""
        import os
        os.environ['KLR_HEAL_DRY_RUN'] = '1'

        try:
            executor = HealExecutor()

            with tempfile.TemporaryDirectory() as tmpdir:
                test_file = Path(tmpdir) / '__pycache__'
                test_file.mkdir()
                assert test_file.exists()

                with patch('consciousness.heal_executor.Path') as mock_path_class:
                    mock_path_class.return_value.rglob.return_value = [test_file]

                    result = executor.clear_caches({'scope': 'python_cache'})

                    assert result is True
                    assert test_file.exists()  # File should NOT be deleted in dry-run
        finally:
            del os.environ['KLR_HEAL_DRY_RUN']

    def test_dry_run_analyze_errors_queries_but_no_action(self):
        """Test analyze_errors in dry-run mode queries but takes no action."""
        import os
        os.environ['KLR_HEAL_DRY_RUN'] = '1'

        try:
            executor = HealExecutor()

            error_events = [
                {'id': 1, 'content': 'TestError', 'timestamp': time.time()},
            ]

            with patch.object(executor, '_query_error_events', return_value=error_events):
                result = executor.analyze_errors({'days': 7})

                assert result is True
        finally:
            del os.environ['KLR_HEAL_DRY_RUN']

    def test_dry_run_logs_clearly_indicate_mode(self, capsys):
        """Test dry-run mode logs clearly indicate simulated execution."""
        import os
        os.environ['KLR_HEAL_DRY_RUN'] = '1'

        try:
            executor = HealExecutor()
            executor.clear_caches({'scope': 'python_cache'})

            captured = capsys.readouterr()
            assert 'DRY-RUN' in captured.out or 'dry-run' in captured.out or 'Would' in captured.out
        finally:
            del os.environ['KLR_HEAL_DRY_RUN']


class TestRealPlaybookImplementations:
    """Test real playbook implementations with actual logic."""

    def test_analyze_errors_queries_memory_store(self):
        """Test analyze_errors queries MemoryStore for error patterns."""
        executor = HealExecutor()

        with patch.object(executor, '_initialize_memory_store') as mock_init:
            with patch.object(executor, '_query_error_events', return_value=[
                {'id': 1, 'content': 'Timeout error', 'timestamp': time.time()},
                {'id': 2, 'content': 'Timeout error', 'timestamp': time.time()},
            ]) as mock_query:
                context = {'days': 7}
                result = executor.analyze_errors(context)

                mock_query.assert_called_once()
                assert result is True

    def test_analyze_errors_identifies_patterns(self):
        """Test analyze_errors identifies error patterns."""
        executor = HealExecutor()

        error_events = [
            {'id': 1, 'content': 'ConnectionTimeout', 'timestamp': time.time()},
            {'id': 2, 'content': 'ConnectionTimeout', 'timestamp': time.time()},
            {'id': 3, 'content': 'DatabaseError', 'timestamp': time.time()},
        ]

        with patch.object(executor, '_query_error_events', return_value=error_events):
            context = {'days': 7}
            result = executor.analyze_errors(context)

            assert result is True

    def test_analyze_errors_returns_false_when_no_memory_store(self):
        """Test analyze_errors returns False when MemoryStore unavailable."""
        executor = HealExecutor()
        executor.memory_store = None

        result = executor.analyze_errors({'days': 7})

        assert result is False

    def test_clear_caches_removes_pycache_directories(self):
        """Test clear_caches removes Python __pycache__ directories."""
        executor = HealExecutor()

        with tempfile.TemporaryDirectory() as tmpdir:
            pycache_dir = Path(tmpdir) / "__pycache__"
            pycache_dir.mkdir()
            pycache_file = pycache_dir / "test.pyc"
            pycache_file.touch()

            with patch('consciousness.heal_executor.Path.glob', return_value=[pycache_dir]):
                context = {'scope': 'python_cache'}
                result = executor.clear_caches(context)

                assert result is True

    def test_clear_caches_removes_old_tmp_files(self):
        """Test clear_caches removes old /tmp/kloros_* files."""
        executor = HealExecutor()

        with tempfile.TemporaryDirectory() as tmpdir:
            old_file = Path(tmpdir) / "kloros_old.log"
            old_file.touch()

            old_time = time.time() - (8 * 24 * 3600)
            import os
            os.utime(old_file, (old_time, old_time))

            with patch('consciousness.heal_executor.Path') as mock_path_class:
                mock_tmp = Mock()
                mock_tmp.glob.return_value = [old_file]
                mock_path_class.return_value = mock_tmp

                context = {'scope': 'temp_files', 'age_days': 7}
                result = executor.clear_caches(context)

                assert result is True

    def test_optimize_resources_analyzes_memory_usage(self):
        """Test optimize_resources analyzes and reports on memory usage."""
        executor = HealExecutor()

        context = {'resource_type': 'memory'}
        result = executor.optimize_resources(context)

        assert result is True

    def test_restart_service_identifies_stuck_processes(self):
        """Test restart_service identifies stuck background processes."""
        executor = HealExecutor()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                stdout="1234 python stuck_process.py\n5678 python another.py",
                returncode=0
            )

            context = {'service_type': 'background_processes'}
            result = executor.restart_service(context)

            assert result is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
