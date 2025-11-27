#!/usr/bin/env python3
"""
Tests for dream_consumer_daemon.py - D-REAM execution consumer.
"""

import pytest
import json
import time
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timezone

from src.orchestration.core.dream_consumer_daemon import DreamConsumerDaemon


@pytest.fixture
def temp_failed_signals_log():
    """Create temporary failed signals log file."""
    fd, path = tempfile.mkstemp(suffix='.jsonl')
    yield Path(path)
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def temp_maintenance_mode_file():
    """Create temporary maintenance mode file."""
    fd, path = tempfile.mkstemp()
    yield Path(path)
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def mock_dream_result():
    """Create mock DreamResult for testing."""
    from src.orchestration.core.dream_trigger import DreamResult
    return DreamResult(
        exit_code=0,
        generation=42,
        promotion_path=Path("/tmp/promotion.json"),
        telemetry_path=Path("/tmp/telemetry.log"),
        run_tag="test-run-123",
        duration_s=123.45
    )


def test_dream_consumer_initialization(temp_failed_signals_log):
    """Test that DreamConsumerDaemon initializes correctly."""
    mock_pub = Mock()
    mock_sub = Mock()

    daemon = DreamConsumerDaemon(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    assert daemon.failed_signals_log == temp_failed_signals_log
    assert daemon.chem_pub == mock_pub
    assert daemon.chem_sub == mock_sub
    assert hasattr(daemon, '_processed_incidents')
    assert isinstance(daemon._processed_incidents, set)


def test_is_maintenance_mode_when_file_exists(temp_failed_signals_log, temp_maintenance_mode_file):
    """Test that _is_maintenance_mode detects maintenance mode file."""
    mock_pub = Mock()
    mock_sub = Mock()

    with patch('src.kloros.orchestration.dream_consumer_daemon.MAINTENANCE_MODE_FILE', temp_maintenance_mode_file):
        daemon = DreamConsumerDaemon(
            failed_signals_log=temp_failed_signals_log,
            chem_pub=mock_pub,
            chem_sub=mock_sub
        )

        assert daemon._is_maintenance_mode() is True


def test_is_maintenance_mode_when_file_missing(temp_failed_signals_log):
    """Test that _is_maintenance_mode returns False when no maintenance file."""
    mock_pub = Mock()
    mock_sub = Mock()

    non_existent_path = Path("/tmp/nonexistent_maintenance_mode_file_54321.tmp")
    if non_existent_path.exists():
        non_existent_path.unlink()

    with patch('src.kloros.orchestration.dream_consumer_daemon.MAINTENANCE_MODE_FILE', non_existent_path):
        daemon = DreamConsumerDaemon(
            failed_signals_log=temp_failed_signals_log,
            chem_pub=mock_pub,
            chem_sub=mock_sub
        )

        assert daemon._is_maintenance_mode() is False


def test_write_dead_letter_creates_entry(temp_failed_signals_log):
    """Test that _write_dead_letter creates proper JSONL entry."""
    mock_pub = Mock()
    mock_sub = Mock()

    daemon = DreamConsumerDaemon(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    test_signal = {
        "signal": "Q_DREAM_TRIGGER",
        "facts": {"reason": "test", "promotion_count": 3}
    }

    daemon._write_dead_letter(test_signal, "Test error message")

    with open(temp_failed_signals_log, 'r') as f:
        lines = f.readlines()

    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry['signal'] == test_signal
    assert entry['error'] == "Test error message"
    assert entry['daemon'] == "dream_consumer_daemon"
    assert 'timestamp' in entry


def test_on_signal_received_skips_duplicate_incidents(temp_failed_signals_log):
    """Test that duplicate incident IDs are skipped."""
    mock_pub = Mock()
    mock_sub = Mock()

    daemon = DreamConsumerDaemon(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    msg = {
        "signal": "Q_DREAM_TRIGGER",
        "incident_id": "test_incident_456",
        "facts": {"reason": "unacknowledged_promotions_detected", "promotion_count": 3}
    }

    with patch.object(asyncio, 'create_task') as mock_create_task:
        daemon._on_signal_received(msg)
        assert mock_create_task.called

        daemon._on_signal_received(msg)
        assert mock_create_task.call_count == 1


@pytest.mark.asyncio
async def test_process_trigger_executes_dream(temp_failed_signals_log, mock_dream_result):
    """Test that _process_trigger correctly executes D-REAM."""
    mock_pub = Mock()
    mock_sub = Mock()

    daemon = DreamConsumerDaemon(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    msg = {
        "signal": "Q_DREAM_TRIGGER",
        "facts": {
            "reason": "unacknowledged_promotions_detected",
            "topic": None,
            "promotion_count": 5
        }
    }

    with patch('src.kloros.orchestration.dream_consumer_daemon.dream_trigger') as mock_trigger:
        mock_trigger.run_once.return_value = mock_dream_result
        with patch.object(daemon, '_is_maintenance_mode', return_value=False):
            await daemon._process_trigger(msg)

    mock_trigger.run_once.assert_called_once_with(topic=None)
    mock_pub.emit.assert_called_once()

    call_args = mock_pub.emit.call_args
    assert call_args[1]['signal'] == 'Q_DREAM_COMPLETE'
    assert call_args[1]['ecosystem'] == 'orchestration'

    facts = call_args[1]['facts']
    assert facts['exit_code'] == 0
    assert facts['generation'] == 42
    assert facts['run_tag'] == "test-run-123"
    assert facts['duration_s'] == 123.45
    assert facts['success'] is True


@pytest.mark.asyncio
async def test_process_trigger_skips_in_maintenance_mode(temp_failed_signals_log, temp_maintenance_mode_file):
    """Test that trigger processing is skipped in maintenance mode."""
    mock_pub = Mock()
    mock_sub = Mock()

    with patch('src.kloros.orchestration.dream_consumer_daemon.MAINTENANCE_MODE_FILE', temp_maintenance_mode_file):
        daemon = DreamConsumerDaemon(
            failed_signals_log=temp_failed_signals_log,
            chem_pub=mock_pub,
            chem_sub=mock_sub
        )

        msg = {
            "signal": "Q_DREAM_TRIGGER",
            "facts": {"reason": "test", "promotion_count": 3}
        }

        with patch('src.kloros.orchestration.dream_consumer_daemon.dream_trigger') as mock_trigger:
            await daemon._process_trigger(msg)

        mock_trigger.run_once.assert_not_called()
        mock_pub.emit.assert_not_called()


@pytest.mark.asyncio
async def test_process_trigger_writes_dead_letter_on_error(temp_failed_signals_log):
    """Test that processing errors are written to dead letter queue."""
    mock_pub = Mock()
    mock_sub = Mock()

    daemon = DreamConsumerDaemon(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    msg = {
        "signal": "Q_DREAM_TRIGGER",
        "facts": {"reason": "test"}
    }

    with patch('src.kloros.orchestration.dream_consumer_daemon.dream_trigger') as mock_trigger:
        mock_trigger.run_once.side_effect = RuntimeError("D-REAM execution failed")
        with patch.object(daemon, '_is_maintenance_mode', return_value=False):
            await daemon._process_trigger(msg)

    with open(temp_failed_signals_log, 'r') as f:
        lines = f.readlines()

    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert 'D-REAM execution failed' in entry['error']


@pytest.mark.asyncio
async def test_process_trigger_extracts_topic_from_facts(temp_failed_signals_log, mock_dream_result):
    """Test that topic is extracted from facts and passed to dream_trigger.run_once()."""
    mock_pub = Mock()
    mock_sub = Mock()

    daemon = DreamConsumerDaemon(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    msg = {
        "signal": "Q_DREAM_TRIGGER",
        "facts": {
            "reason": "manual_trigger",
            "topic": "performance_optimization",
            "promotion_count": 0
        }
    }

    with patch('src.kloros.orchestration.dream_consumer_daemon.dream_trigger') as mock_trigger:
        mock_trigger.run_once.return_value = mock_dream_result
        with patch.object(daemon, '_is_maintenance_mode', return_value=False):
            await daemon._process_trigger(msg)

    mock_trigger.run_once.assert_called_once_with(topic="performance_optimization")


@pytest.mark.asyncio
async def test_process_trigger_handles_failed_dream_execution(temp_failed_signals_log):
    """Test that failed D-REAM execution is handled gracefully."""
    mock_pub = Mock()
    mock_sub = Mock()

    daemon = DreamConsumerDaemon(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    msg = {
        "signal": "Q_DREAM_TRIGGER",
        "facts": {"reason": "test", "promotion_count": 3}
    }

    from src.orchestration.core.dream_trigger import DreamResult
    failed_result = DreamResult(
        exit_code=1,
        generation=None,
        promotion_path=None,
        telemetry_path=None,
        run_tag="test-run-456",
        duration_s=45.67
    )

    with patch('src.kloros.orchestration.dream_consumer_daemon.dream_trigger') as mock_trigger:
        mock_trigger.run_once.return_value = failed_result
        with patch.object(daemon, '_is_maintenance_mode', return_value=False):
            await daemon._process_trigger(msg)

    mock_pub.emit.assert_called_once()
    call_args = mock_pub.emit.call_args
    facts = call_args[1]['facts']
    assert facts['exit_code'] == 1
    assert facts['success'] is False
    assert facts['generation'] is None


@pytest.mark.asyncio
async def test_emit_completion_publishes_to_chemical_bus(temp_failed_signals_log):
    """Test that _emit_completion publishes correctly formatted completion signals."""
    mock_pub = Mock()
    mock_sub = Mock()

    daemon = DreamConsumerDaemon(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    from src.orchestration.core.dream_trigger import DreamResult
    result = DreamResult(
        exit_code=0,
        generation=10,
        promotion_path=Path("/tmp/promo.json"),
        telemetry_path=Path("/tmp/telem.log"),
        run_tag="test-123",
        duration_s=100.0
    )

    trigger_facts = {
        "reason": "unacknowledged_promotions_detected",
        "topic": None,
        "promotion_count": 5
    }

    daemon._emit_completion(result, trigger_facts)

    mock_pub.emit.assert_called_once()
    call_args = mock_pub.emit.call_args

    assert call_args[1]['signal'] == 'Q_DREAM_COMPLETE'
    assert call_args[1]['ecosystem'] == 'orchestration'
    assert call_args[1]['intensity'] == 1.0

    facts = call_args[1]['facts']
    assert facts['exit_code'] == 0
    assert facts['generation'] == 10
    assert facts['run_tag'] == "test-123"
    assert facts['duration_s'] == 100.0
    assert facts['success'] is True
    assert facts['trigger_reason'] == "unacknowledged_promotions_detected"
    assert facts['promotion_count'] == 5


@pytest.mark.asyncio
async def test_process_trigger_handles_unknown_signal(temp_failed_signals_log):
    """Test that unknown signal types are logged but not processed."""
    mock_pub = Mock()
    mock_sub = Mock()

    daemon = DreamConsumerDaemon(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    msg = {
        "signal": "Q_UNKNOWN_SIGNAL",
        "facts": {}
    }

    with patch('src.kloros.orchestration.dream_consumer_daemon.dream_trigger') as mock_trigger:
        with patch.object(daemon, '_is_maintenance_mode', return_value=False):
            await daemon._process_trigger(msg)

    mock_trigger.run_once.assert_not_called()
    mock_pub.emit.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_processed_incidents_clears_cache(temp_failed_signals_log):
    """Test that _cleanup_processed_incidents clears the incident cache."""
    mock_pub = Mock()
    mock_sub = Mock()

    daemon = DreamConsumerDaemon(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    daemon._processed_incidents.add("incident_1")
    daemon._processed_incidents.add("incident_2")
    daemon._processed_incidents.add("incident_3")

    assert len(daemon._processed_incidents) == 3

    daemon._last_cleanup = time.time() - 7200
    daemon._cleanup_processed_incidents()

    assert len(daemon._processed_incidents) == 0


@pytest.mark.asyncio
async def test_multiple_dream_triggers_processed_sequentially(temp_failed_signals_log, mock_dream_result):
    """Test that multiple D-REAM triggers are processed independently."""
    mock_pub = Mock()
    mock_sub = Mock()

    daemon = DreamConsumerDaemon(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    msg1 = {
        "signal": "Q_DREAM_TRIGGER",
        "incident_id": "incident_1",
        "facts": {"reason": "test1", "promotion_count": 3}
    }

    msg2 = {
        "signal": "Q_DREAM_TRIGGER",
        "incident_id": "incident_2",
        "facts": {"reason": "test2", "promotion_count": 5}
    }

    with patch('src.kloros.orchestration.dream_consumer_daemon.dream_trigger') as mock_trigger:
        mock_trigger.run_once.return_value = mock_dream_result
        with patch.object(daemon, '_is_maintenance_mode', return_value=False):
            await daemon._process_trigger(msg1)
            await daemon._process_trigger(msg2)

    assert mock_trigger.run_once.call_count == 2
    assert mock_pub.emit.call_count == 2


def test_daemon_creates_failed_signals_dir_if_missing(temp_failed_signals_log):
    """Test that daemon creates failed signals directory if it doesn't exist."""
    temp_dir = Path(tempfile.mkdtemp())
    temp_log = temp_dir / "subdir" / "failed_signals.jsonl"

    mock_pub = Mock()
    mock_sub = Mock()

    daemon = DreamConsumerDaemon(
        failed_signals_log=temp_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    assert temp_log.parent.exists()

    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_emit_completion_includes_all_result_fields(temp_failed_signals_log):
    """Test that all result fields are included in completion signal."""
    mock_pub = Mock()
    mock_sub = Mock()

    daemon = DreamConsumerDaemon(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    from src.orchestration.core.dream_trigger import DreamResult
    result = DreamResult(
        exit_code=0,
        generation=25,
        promotion_path=Path("/home/kloros/artifacts/dream/promotions/promo_gen25.json"),
        telemetry_path=Path("/home/kloros/logs/dream/runner_123.log"),
        run_tag="1731621234-abc123",
        duration_s=456.78
    )

    trigger_facts = {
        "reason": "unacknowledged_promotions_detected",
        "topic": "security",
        "promotion_count": 10
    }

    daemon._emit_completion(result, trigger_facts)

    call_args = mock_pub.emit.call_args
    facts = call_args[1]['facts']

    assert facts['exit_code'] == 0
    assert facts['generation'] == 25
    assert facts['promotion_path'] == str(result.promotion_path)
    assert facts['telemetry_path'] == str(result.telemetry_path)
    assert facts['run_tag'] == "1731621234-abc123"
    assert facts['duration_s'] == 456.78
    assert facts['success'] is True
    assert facts['trigger_reason'] == "unacknowledged_promotions_detected"
    assert facts['trigger_topic'] == "security"
    assert facts['promotion_count'] == 10
