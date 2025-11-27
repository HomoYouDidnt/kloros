#!/usr/bin/env python3
"""
Test suite for system_healing_subscriber.py

Tests HEAL_REQUEST signal emission via UMN when HIGH_RAGE,
RESOURCE_STRAIN, and REPETITIVE_ERROR signals are detected.
"""

import pytest
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cognition.mind.consciousness.system_healing_subscriber import (
    emit_heal_request,
    handle_high_rage,
    handle_resource_strain,
    handle_repetitive_error
)


class TestEmitHealRequest:
    """Test emit_heal_request helper function."""

    def test_emit_heal_request_with_normal_priority(self):
        """Test that emit_heal_request emits HEAL_REQUEST signal with correct payload."""
        signals_emitted = []

        def mock_emit(signal, *, ecosystem, intensity, facts):
            signals_emitted.append({
                'signal': signal,
                'ecosystem': ecosystem,
                'intensity': intensity,
                'facts': facts
            })

        with patch('consciousness.system_healing_subscriber.chem_pub') as mock_chem_pub:
            mock_chem_pub.emit = mock_emit

            emit_heal_request(
                strategy='analyze_error_pattern',
                context={'pattern': 'test_error', 'evidence': ['Error1', 'Error2']},
                priority='normal'
            )

            assert len(signals_emitted) == 1
            assert signals_emitted[0]['signal'] == 'HEAL_REQUEST'
            assert signals_emitted[0]['ecosystem'] == 'system_healing'
            assert signals_emitted[0]['intensity'] == 0.7
            assert signals_emitted[0]['facts']['strategy'] == 'analyze_error_pattern'
            assert signals_emitted[0]['facts']['priority'] == 'normal'
            assert signals_emitted[0]['facts']['context']['pattern'] == 'test_error'

    def test_emit_heal_request_with_high_priority(self):
        """Test that high priority sets intensity to 0.85."""
        signals_emitted = []

        def mock_emit(signal, *, ecosystem, intensity, facts):
            signals_emitted.append({'intensity': intensity})

        with patch('consciousness.system_healing_subscriber.chem_pub') as mock_chem_pub:
            mock_chem_pub.emit = mock_emit

            emit_heal_request(
                strategy='restart_stuck_service',
                context={'failures': ['Failure1']},
                priority='high'
            )

            assert signals_emitted[0]['intensity'] == 0.85

    def test_emit_heal_request_with_critical_priority(self):
        """Test that critical priority sets intensity to 0.95."""
        signals_emitted = []

        def mock_emit(signal, *, ecosystem, intensity, facts):
            signals_emitted.append({'intensity': intensity})

        with patch('consciousness.system_healing_subscriber.chem_pub') as mock_chem_pub:
            mock_chem_pub.emit = mock_emit

            emit_heal_request(
                strategy='emergency_flush',
                context={},
                priority='critical'
            )

            assert signals_emitted[0]['intensity'] == 0.95

    def test_emit_heal_request_includes_timestamp(self):
        """Test that emit_heal_request includes timestamp in facts."""
        signals_emitted = []

        def mock_emit(signal, *, ecosystem, intensity, facts):
            signals_emitted.append(facts)

        with patch('consciousness.system_healing_subscriber.chem_pub') as mock_chem_pub:
            mock_chem_pub.emit = mock_emit

            before = time.time()
            emit_heal_request(
                strategy='test_strategy',
                context={}
            )
            after = time.time()

            assert 'timestamp' in signals_emitted[0]
            assert before <= signals_emitted[0]['timestamp'] <= after

    def test_emit_heal_request_includes_requested_by_metadata(self):
        """Test that emit_heal_request includes requested_by metadata."""
        signals_emitted = []

        def mock_emit(signal, *, ecosystem, intensity, facts):
            signals_emitted.append(facts)

        with patch('consciousness.system_healing_subscriber.chem_pub') as mock_chem_pub:
            mock_chem_pub.emit = mock_emit

            emit_heal_request(
                strategy='test_strategy',
                context={}
            )

            assert signals_emitted[0]['requested_by'] == 'system_healing_subscriber'


class TestHandleHighRage:
    """Test handle_high_rage signal handler."""

    def test_handle_high_rage_with_repetitive_errors_cause(self):
        """Test that repetitive_errors cause emits analyze_error_pattern strategy."""
        signals_emitted = []

        def mock_emit(signal, *, ecosystem, intensity, facts):
            signals_emitted.append(facts)

        with patch('consciousness.system_healing_subscriber.chem_pub') as mock_chem_pub:
            mock_chem_pub.emit = mock_emit

            msg = {
                'intensity': 0.85,
                'facts': {
                    'root_causes': ['repetitive_errors'],
                    'evidence': ['Error occurred 10 times', 'Same stack trace']
                }
            }

            handle_high_rage(msg)

            assert len(signals_emitted) == 1
            assert signals_emitted[0]['strategy'] == 'analyze_error_pattern'
            assert signals_emitted[0]['context']['cause'] == 'repetitive_errors'

    def test_handle_high_rage_with_task_failures_cause(self):
        """Test that task_failures cause emits restart_stuck_service strategy."""
        signals_emitted = []

        def mock_emit(signal, *, ecosystem, intensity, facts):
            signals_emitted.append(facts)

        with patch('consciousness.system_healing_subscriber.chem_pub') as mock_chem_pub:
            mock_chem_pub.emit = mock_emit

            msg = {
                'intensity': 0.85,
                'facts': {
                    'root_causes': ['task_failures'],
                    'evidence': ['Task A blocked', 'Task B blocked']
                }
            }

            handle_high_rage(msg)

            assert len(signals_emitted) == 1
            assert signals_emitted[0]['strategy'] == 'restart_stuck_service'
            assert signals_emitted[0]['context']['cause'] == 'task_failures'

    def test_handle_high_rage_with_multiple_causes(self):
        """Test that multiple causes emit multiple HEAL_REQUEST signals."""
        signals_emitted = []

        def mock_emit(signal, *, ecosystem, intensity, facts):
            signals_emitted.append(facts)

        with patch('consciousness.system_healing_subscriber.chem_pub') as mock_chem_pub:
            mock_chem_pub.emit = mock_emit

            msg = {
                'intensity': 0.85,
                'facts': {
                    'root_causes': ['repetitive_errors', 'task_failures'],
                    'evidence': ['Error1', 'Error2']
                }
            }

            handle_high_rage(msg)

            assert len(signals_emitted) == 2
            strategies = {s['strategy'] for s in signals_emitted}
            assert 'analyze_error_pattern' in strategies
            assert 'restart_stuck_service' in strategies

    def test_handle_high_rage_with_resource_strain_cause(self):
        """Test that resource_strain cause emits clear_cache strategy."""
        signals_emitted = []

        def mock_emit(signal, *, ecosystem, intensity, facts):
            signals_emitted.append(facts)

        with patch('consciousness.system_healing_subscriber.chem_pub') as mock_chem_pub:
            mock_chem_pub.emit = mock_emit

            msg = {
                'intensity': 0.85,
                'facts': {
                    'root_causes': ['resource_strain'],
                    'evidence': ['Memory at 95%']
                }
            }

            handle_high_rage(msg)

            assert len(signals_emitted) == 1
            assert signals_emitted[0]['strategy'] == 'clear_cache'

    def test_handle_high_rage_sets_priority_based_on_intensity(self):
        """Test that HIGH_RAGE with intensity > 0.85 sets priority to 'high'."""
        signals_emitted = []

        def mock_emit(signal, *, ecosystem, intensity, facts):
            signals_emitted.append(facts)

        with patch('consciousness.system_healing_subscriber.chem_pub') as mock_chem_pub:
            mock_chem_pub.emit = mock_emit

            msg = {
                'intensity': 0.90,
                'facts': {
                    'root_causes': ['repetitive_errors'],
                    'evidence': []
                }
            }

            handle_high_rage(msg)

            assert signals_emitted[0]['priority'] == 'high'

    def test_handle_high_rage_includes_evidence_in_context(self):
        """Test that handle_high_rage includes evidence from facts in context."""
        signals_emitted = []

        def mock_emit(signal, *, ecosystem, intensity, facts):
            signals_emitted.append(facts)

        with patch('consciousness.system_healing_subscriber.chem_pub') as mock_chem_pub:
            mock_chem_pub.emit = mock_emit

            evidence = ['Error occurred 10 times', 'Stack trace repeating']
            msg = {
                'intensity': 0.85,
                'facts': {
                    'root_causes': ['repetitive_errors'],
                    'evidence': evidence
                }
            }

            handle_high_rage(msg)

            assert signals_emitted[0]['context']['evidence'] == evidence

    def test_handle_high_rage_with_error_pattern_alias(self):
        """Test that error_pattern root cause is treated as repetitive_errors."""
        signals_emitted = []

        def mock_emit(signal, *, ecosystem, intensity, facts):
            signals_emitted.append(facts)

        with patch('consciousness.system_healing_subscriber.chem_pub') as mock_chem_pub:
            mock_chem_pub.emit = mock_emit

            msg = {
                'intensity': 0.75,
                'facts': {
                    'root_causes': ['error_pattern'],
                    'evidence': []
                }
            }

            handle_high_rage(msg)

            assert signals_emitted[0]['strategy'] == 'analyze_error_pattern'

    def test_handle_high_rage_with_blocked_actions_alias(self):
        """Test that blocked_actions root cause is treated as task_failures."""
        signals_emitted = []

        def mock_emit(signal, *, ecosystem, intensity, facts):
            signals_emitted.append(facts)

        with patch('consciousness.system_healing_subscriber.chem_pub') as mock_chem_pub:
            mock_chem_pub.emit = mock_emit

            msg = {
                'intensity': 0.85,
                'facts': {
                    'root_causes': ['blocked_actions'],
                    'evidence': []
                }
            }

            handle_high_rage(msg)

            assert signals_emitted[0]['strategy'] == 'restart_stuck_service'


class TestHandleResourceStrain:
    """Test handle_resource_strain signal handler."""

    def test_handle_resource_strain_emits_optimize_resources(self):
        """Test that handle_resource_strain emits optimize_resources strategy."""
        signals_emitted = []

        def mock_emit(signal, *, ecosystem, intensity, facts):
            signals_emitted.append(facts)

        with patch('consciousness.system_healing_subscriber.chem_pub') as mock_chem_pub:
            mock_chem_pub.emit = mock_emit

            msg = {
                'facts': {
                    'resource_type': 'memory',
                    'level': 0.92,
                    'evidence': ['Memory pressure high']
                }
            }

            handle_resource_strain(msg)

            assert len(signals_emitted) == 1
            assert signals_emitted[0]['strategy'] == 'optimize_resources'
            assert signals_emitted[0]['context']['resource_type'] == 'memory'
            assert signals_emitted[0]['context']['usage_level'] == 0.92

    def test_handle_resource_strain_with_missing_facts(self):
        """Test that handle_resource_strain handles missing facts gracefully."""
        signals_emitted = []

        def mock_emit(signal, *, ecosystem, intensity, facts):
            signals_emitted.append(facts)

        with patch('consciousness.system_healing_subscriber.chem_pub') as mock_chem_pub:
            mock_chem_pub.emit = mock_emit

            msg = {'facts': {}}

            handle_resource_strain(msg)

            assert len(signals_emitted) == 1
            assert signals_emitted[0]['context']['resource_type'] == 'unknown'
            assert signals_emitted[0]['context']['usage_level'] == 0.0


class TestHandleRepetitiveError:
    """Test handle_repetitive_error signal handler."""

    def test_handle_repetitive_error_emits_analyze_error_pattern(self):
        """Test that handle_repetitive_error emits analyze_error_pattern strategy."""
        signals_emitted = []

        def mock_emit(signal, *, ecosystem, intensity, facts):
            signals_emitted.append(facts)

        with patch('consciousness.system_healing_subscriber.chem_pub') as mock_chem_pub:
            mock_chem_pub.emit = mock_emit

            msg = {
                'facts': {
                    'error_count': 10,
                    'error_type': 'ConnectionError',
                    'evidence': ['Connection refused 10 times']
                }
            }

            handle_repetitive_error(msg)

            assert len(signals_emitted) == 1
            assert signals_emitted[0]['strategy'] == 'analyze_error_pattern'
            assert signals_emitted[0]['context']['error_count'] == 10
            assert signals_emitted[0]['context']['error_type'] == 'ConnectionError'

    def test_handle_repetitive_error_priority_is_high(self):
        """Test that handle_repetitive_error sets priority to 'high'."""
        signals_emitted = []

        def mock_emit(signal, *, ecosystem, intensity, facts):
            signals_emitted.append(facts)

        with patch('consciousness.system_healing_subscriber.chem_pub') as mock_chem_pub:
            mock_chem_pub.emit = mock_emit

            msg = {
                'facts': {
                    'error_count': 5,
                    'error_type': 'ValueError',
                    'evidence': []
                }
            }

            handle_repetitive_error(msg)

            assert signals_emitted[0]['priority'] == 'high'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
