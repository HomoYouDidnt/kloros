#!/usr/bin/env python3
"""
Integration tests for affective healing system.

Tests end-to-end signal flow and verifies healing doesn't cause
cascading failures or system instability.
"""

import pytest
import sys
import time
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from consciousness.heal_executor import HealExecutor, check_emergency_brake


class TestEndToEndSignalFlow:
    """Test complete signal flow from AFFECT to healing execution."""

    def test_heal_request_triggers_playbook_execution(self):
        """Test HEAL_REQUEST signal triggers playbook execution."""
        executor = HealExecutor()

        executed_strategies = []

        def mock_analyze(context):
            executed_strategies.append('analyze_error_pattern')
            return True

        executor.playbooks['analyze_error_pattern'] = mock_analyze

        msg = {
            'facts': {
                'strategy': 'analyze_error_pattern',
                'context': {'days': 7},
                'priority': 'normal'
            }
        }

        executor.handle_heal_request(msg)

        assert 'analyze_error_pattern' in executed_strategies

    def test_unknown_strategy_does_not_crash_daemon(self):
        """Test unknown strategy is handled gracefully without crashing."""
        executor = HealExecutor()

        msg = {
            'facts': {
                'strategy': 'unknown_nonexistent_strategy',
                'context': {},
                'priority': 'normal'
            }
        }

        executor.handle_heal_request(msg)

    def test_playbook_exception_does_not_crash_daemon(self):
        """Test playbook exception is caught and doesn't crash daemon."""
        executor = HealExecutor()

        def failing_playbook(context):
            raise RuntimeError("Simulated playbook failure")

        executor.playbooks['test_failing'] = failing_playbook

        msg = {
            'facts': {
                'strategy': 'test_failing',
                'context': {},
                'priority': 'normal'
            }
        }

        executor.handle_heal_request(msg)


class TestCooldownMechanism:
    """Test cooldown prevents rapid re-execution."""

    def test_cooldown_prevents_rapid_reexecution(self):
        """Test cooldown mechanism prevents rapid re-execution of same strategy."""
        executor = HealExecutor()
        executor.cooldown_seconds = 2

        execution_count = []

        def mock_playbook(context):
            execution_count.append(time.time())
            return True

        executor.playbooks['test_strategy'] = mock_playbook

        msg = {
            'facts': {
                'strategy': 'test_strategy',
                'context': {},
                'priority': 'normal'
            }
        }

        executor.handle_heal_request(msg)
        assert len(execution_count) == 1

        executor.handle_heal_request(msg)
        assert len(execution_count) == 1

        time.sleep(2.1)

        executor.handle_heal_request(msg)
        assert len(execution_count) == 2

    def test_different_strategies_execute_independently(self):
        """Test different strategies execute independently despite cooldown."""
        executor = HealExecutor()
        executor.cooldown_seconds = 5

        execution_log = []

        def mock_strategy_a(context):
            execution_log.append('strategy_a')
            return True

        def mock_strategy_b(context):
            execution_log.append('strategy_b')
            return True

        executor.playbooks['strategy_a'] = mock_strategy_a
        executor.playbooks['strategy_b'] = mock_strategy_b

        msg_a = {'facts': {'strategy': 'strategy_a', 'context': {}}}
        msg_b = {'facts': {'strategy': 'strategy_b', 'context': {}}}

        executor.handle_heal_request(msg_a)
        executor.handle_heal_request(msg_b)

        assert 'strategy_a' in execution_log
        assert 'strategy_b' in execution_log
        assert len(execution_log) == 2


class TestEmergencyBrakeIntegration:
    """Test emergency brake prevents healing execution."""

    def test_emergency_brake_blocks_all_playbooks(self):
        """Test emergency brake blocks all playbook execution."""
        executor = HealExecutor()

        execution_count = []

        def mock_playbook(context):
            execution_count.append(1)
            return True

        executor.playbooks['test_strategy'] = mock_playbook

        with patch('consciousness.heal_executor.check_emergency_brake', return_value=True):
            msg = {
                'facts': {
                    'strategy': 'test_strategy',
                    'context': {},
                    'priority': 'normal'
                }
            }

            executor.handle_heal_request(msg)

            assert len(execution_count) == 0


class TestSystemStateIntegrity:
    """Test healing operations don't corrupt system state."""

    def test_memory_store_remains_valid_after_error_analysis(self):
        """Test MemoryStore remains valid after error analysis."""
        executor = HealExecutor()

        if not executor.memory_store:
            pytest.skip("MemoryStore not available")

        before_count = self._count_events(executor.memory_store)

        context = {'days': 7}
        result = executor.analyze_errors(context)

        after_count = self._count_events(executor.memory_store)

        assert result in [True, False]
        assert before_count == after_count

    def _count_events(self, memory_store):
        """Helper to count events in MemoryStore."""
        try:
            conn = memory_store._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM events")
            return cursor.fetchone()[0]
        except:
            return 0

    def test_clear_cache_with_no_caches_is_safe(self):
        """Test clear_cache with no caches present is safe."""
        executor = HealExecutor()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('consciousness.heal_executor.Path') as mock_path:
                mock_path.return_value.rglob.return_value = []

                result = executor.clear_caches({'scope': 'python_cache'})

                assert result is True


class TestConcurrentHealRequests:
    """Test multiple concurrent heal requests are handled safely."""

    def test_concurrent_different_strategies(self):
        """Test concurrent execution of different strategies."""
        executor = HealExecutor()

        results = []

        def strategy_1(context):
            time.sleep(0.1)
            results.append('s1')
            return True

        def strategy_2(context):
            time.sleep(0.1)
            results.append('s2')
            return True

        executor.playbooks['s1'] = strategy_1
        executor.playbooks['s2'] = strategy_2

        msg1 = {'facts': {'strategy': 's1', 'context': {}}}
        msg2 = {'facts': {'strategy': 's2', 'context': {}}}

        executor.handle_heal_request(msg1)
        executor.handle_heal_request(msg2)

        assert len(results) == 2

    def test_failed_playbook_does_not_block_subsequent(self):
        """Test failed playbook doesn't block subsequent executions."""
        executor = HealExecutor()
        executor.cooldown_seconds = 0

        results = []

        def failing_strategy(context):
            results.append('fail')
            raise RuntimeError("Intentional failure")

        def working_strategy(context):
            results.append('success')
            return True

        executor.playbooks['failing'] = failing_strategy
        executor.playbooks['working'] = working_strategy

        msg_fail = {'facts': {'strategy': 'failing', 'context': {}}}
        msg_work = {'facts': {'strategy': 'working', 'context': {}}}

        executor.handle_heal_request(msg_fail)
        executor.handle_heal_request(msg_work)

        assert 'fail' in results
        assert 'success' in results


class TestLoggingIntegrity:
    """Test execution logging works correctly."""

    def test_successful_execution_logged(self):
        """Test successful execution is logged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = HealExecutor()
            executor.execution_log_path = Path(tmpdir) / "test.log"

            def mock_playbook(context):
                return True

            executor.playbooks['test'] = mock_playbook

            msg = {'facts': {'strategy': 'test', 'context': {}}}
            executor.handle_heal_request(msg)

            assert executor.execution_log_path.exists()
            content = executor.execution_log_path.read_text()
            assert 'SUCCESS' in content
            assert 'test' in content

    def test_failed_execution_logged(self):
        """Test failed execution is logged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = HealExecutor()
            executor.execution_log_path = Path(tmpdir) / "test.log"

            def mock_playbook(context):
                return False

            executor.playbooks['test_fail'] = mock_playbook

            msg = {'facts': {'strategy': 'test_fail', 'context': {}}}
            executor.handle_heal_request(msg)

            assert executor.execution_log_path.exists()
            content = executor.execution_log_path.read_text()
            assert 'FAILED' in content
            assert 'test_fail' in content


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
