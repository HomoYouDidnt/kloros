#!/usr/bin/env python3
"""
Tests for kloros_policy_engine.py - KLoROS autonomous decision-making daemon.
"""

import pytest
import json
import time
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timezone

from src.orchestration.core.kloros_policy_engine import KLoROSPolicyEngine


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


def test_policy_engine_initialization(temp_failed_signals_log):
    """Test that KLoROSPolicyEngine initializes correctly."""
    mock_pub = Mock()
    mock_sub = Mock()

    engine = KLoROSPolicyEngine(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    assert engine.failed_signals_log == temp_failed_signals_log
    assert engine.chem_pub == mock_pub
    assert engine.chem_sub == mock_sub
    assert hasattr(engine, '_processed_incidents')
    assert isinstance(engine._processed_incidents, set)


def test_is_maintenance_mode_when_file_exists(temp_failed_signals_log, temp_maintenance_mode_file):
    """Test that _is_maintenance_mode detects maintenance mode file."""
    mock_pub = Mock()
    mock_sub = Mock()

    with patch('src.kloros.orchestration.kloros_policy_engine.MAINTENANCE_MODE_FILE', temp_maintenance_mode_file):
        engine = KLoROSPolicyEngine(
            failed_signals_log=temp_failed_signals_log,
            chem_pub=mock_pub,
            chem_sub=mock_sub
        )

        assert engine._is_maintenance_mode() is True


def test_is_maintenance_mode_when_file_missing(temp_failed_signals_log):
    """Test that _is_maintenance_mode returns False when no maintenance file."""
    mock_pub = Mock()
    mock_sub = Mock()

    non_existent_path = Path("/tmp/nonexistent_maintenance_mode_file_12345.tmp")
    if non_existent_path.exists():
        non_existent_path.unlink()

    with patch('src.kloros.orchestration.kloros_policy_engine.MAINTENANCE_MODE_FILE', non_existent_path):
        engine = KLoROSPolicyEngine(
            failed_signals_log=temp_failed_signals_log,
            chem_pub=mock_pub,
            chem_sub=mock_sub
        )

        assert engine._is_maintenance_mode() is False


def test_write_dead_letter_creates_entry(temp_failed_signals_log):
    """Test that _write_dead_letter creates proper JSONL entry."""
    mock_pub = Mock()
    mock_sub = Mock()

    engine = KLoROSPolicyEngine(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    test_signal = {
        "signal": "Q_PROMOTIONS_DETECTED",
        "facts": {"promotion_count": 3}
    }

    engine._write_dead_letter(test_signal, "Test error message")

    with open(temp_failed_signals_log, 'r') as f:
        lines = f.readlines()

    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry['signal'] == test_signal
    assert entry['error'] == "Test error message"
    assert entry['daemon'] == "kloros_policy_engine"
    assert 'timestamp' in entry


def test_cleanup_processed_incidents_clears_cache(temp_failed_signals_log):
    """Test that _cleanup_processed_incidents clears the incident cache."""
    mock_pub = Mock()
    mock_sub = Mock()

    engine = KLoROSPolicyEngine(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    engine._processed_incidents.add("incident_1")
    engine._processed_incidents.add("incident_2")
    engine._processed_incidents.add("incident_3")

    assert len(engine._processed_incidents) == 3

    engine._last_cleanup = time.time() - 7200
    engine._cleanup_processed_incidents()

    assert len(engine._processed_incidents) == 0


def test_cleanup_processed_incidents_respects_interval(temp_failed_signals_log):
    """Test that cleanup doesn't run if interval hasn't passed."""
    mock_pub = Mock()
    mock_sub = Mock()

    engine = KLoROSPolicyEngine(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    engine._processed_incidents.add("incident_1")
    engine._last_cleanup = time.time()

    engine._cleanup_processed_incidents()

    assert len(engine._processed_incidents) == 1


def test_on_signal_received_skips_duplicate_incidents(temp_failed_signals_log):
    """Test that duplicate incident IDs are skipped."""
    mock_pub = Mock()
    mock_sub = Mock()

    engine = KLoROSPolicyEngine(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    msg = {
        "signal": "Q_PROMOTIONS_DETECTED",
        "incident_id": "test_incident_123",
        "facts": {"promotion_count": 3}
    }

    with patch.object(asyncio, 'create_task') as mock_create_task:
        engine._on_signal_received(msg)
        assert mock_create_task.called

        engine._on_signal_received(msg)
        assert mock_create_task.call_count == 1


@pytest.mark.asyncio
async def test_process_advisory_handles_promotions_detected(temp_failed_signals_log):
    """Test that _process_advisory correctly handles Q_PROMOTIONS_DETECTED."""
    mock_pub = Mock()
    mock_sub = Mock()

    engine = KLoROSPolicyEngine(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    msg = {
        "signal": "Q_PROMOTIONS_DETECTED",
        "facts": {
            "promotion_count": 5,
            "oldest_promotion_age_hours": 48,
            "newest_promotion_age_hours": 2
        }
    }

    with patch.object(engine, '_is_maintenance_mode', return_value=False):
        await engine._process_advisory(msg)

    mock_pub.emit.assert_called_once()
    call_args = mock_pub.emit.call_args

    assert call_args[1]['signal'] == 'Q_DREAM_TRIGGER'
    assert call_args[1]['ecosystem'] == 'orchestration'
    assert call_args[1]['intensity'] == 1.0

    facts = call_args[1]['facts']
    assert facts['reason'] == 'unacknowledged_promotions_detected'
    assert facts['promotion_count'] == 5
    assert facts['source'] == 'kloros_policy_engine'


@pytest.mark.asyncio
async def test_process_advisory_skips_in_maintenance_mode(temp_failed_signals_log, temp_maintenance_mode_file):
    """Test that advisory processing is skipped in maintenance mode."""
    mock_pub = Mock()
    mock_sub = Mock()

    with patch('src.kloros.orchestration.kloros_policy_engine.MAINTENANCE_MODE_FILE', temp_maintenance_mode_file):
        engine = KLoROSPolicyEngine(
            failed_signals_log=temp_failed_signals_log,
            chem_pub=mock_pub,
            chem_sub=mock_sub
        )

        msg = {
            "signal": "Q_PROMOTIONS_DETECTED",
            "facts": {"promotion_count": 3}
        }

        await engine._process_advisory(msg)

        mock_pub.emit.assert_not_called()


@pytest.mark.asyncio
async def test_process_advisory_writes_dead_letter_on_error(temp_failed_signals_log):
    """Test that processing errors are written to dead letter queue."""
    mock_pub = Mock()
    mock_sub = Mock()

    engine = KLoROSPolicyEngine(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    msg = {
        "signal": "Q_PROMOTIONS_DETECTED",
        "facts": None
    }

    with patch.object(engine, '_is_maintenance_mode', return_value=False):
        with patch.object(engine, '_handle_promotions_detected', side_effect=ValueError("Test error")):
            await engine._process_advisory(msg)

    with open(temp_failed_signals_log, 'r') as f:
        lines = f.readlines()

    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert 'Test error' in entry['error']


@pytest.mark.asyncio
async def test_handle_promotions_detected_no_promotions(temp_failed_signals_log):
    """Test that _handle_promotions_detected skips when promotion_count is 0."""
    mock_pub = Mock()
    mock_sub = Mock()

    engine = KLoROSPolicyEngine(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    facts = {"promotion_count": 0}

    await engine._handle_promotions_detected(facts)

    mock_pub.emit.assert_not_called()


@pytest.mark.asyncio
async def test_handle_promotions_detected_triggers_dream(temp_failed_signals_log):
    """Test that promotions trigger D-REAM execution."""
    mock_pub = Mock()
    mock_sub = Mock()

    engine = KLoROSPolicyEngine(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    facts = {
        "promotion_count": 7,
        "oldest_promotion_age_hours": 72,
        "newest_promotion_age_hours": 1
    }

    await engine._handle_promotions_detected(facts)

    mock_pub.emit.assert_called_once()
    call_args = mock_pub.emit.call_args

    assert call_args[1]['signal'] == 'Q_DREAM_TRIGGER'
    facts_emitted = call_args[1]['facts']
    assert facts_emitted['promotion_count'] == 7
    assert facts_emitted['oldest_promotion_age_hours'] == 72


def test_emit_trigger_publishes_to_chemical_bus(temp_failed_signals_log):
    """Test that _emit_trigger publishes correctly formatted trigger signals."""
    mock_pub = Mock()
    mock_sub = Mock()

    engine = KLoROSPolicyEngine(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    trigger_facts = {
        "reason": "unacknowledged_promotions_detected",
        "topic": None,
        "promotion_count": 5
    }

    engine._emit_trigger("Q_DREAM_TRIGGER", trigger_facts)

    mock_pub.emit.assert_called_once()
    call_args = mock_pub.emit.call_args

    assert call_args[1]['signal'] == 'Q_DREAM_TRIGGER'
    assert call_args[1]['ecosystem'] == 'orchestration'
    assert call_args[1]['intensity'] == 1.0
    assert call_args[1]['facts'] == trigger_facts


def test_emit_trigger_raises_on_publish_failure(temp_failed_signals_log):
    """Test that _emit_trigger raises exception when publish fails."""
    mock_pub = Mock()
    mock_pub.emit.side_effect = Exception("ZMQ connection failed")
    mock_sub = Mock()

    engine = KLoROSPolicyEngine(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    with pytest.raises(Exception, match="ZMQ connection failed"):
        engine._emit_trigger("Q_DREAM_TRIGGER", {"test": "data"})


@pytest.mark.asyncio
async def test_process_advisory_logs_unknown_signal(temp_failed_signals_log):
    """Test that unknown signal types are logged as warnings."""
    mock_pub = Mock()
    mock_sub = Mock()

    engine = KLoROSPolicyEngine(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    msg = {
        "signal": "Q_UNKNOWN_SIGNAL",
        "facts": {}
    }

    with patch.object(engine, '_is_maintenance_mode', return_value=False):
        await engine._process_advisory(msg)

    mock_pub.emit.assert_not_called()


@pytest.mark.asyncio
async def test_multiple_promotions_signals_processed_correctly(temp_failed_signals_log):
    """Test that multiple promotion signals are processed independently."""
    mock_pub = Mock()
    mock_sub = Mock()

    engine = KLoROSPolicyEngine(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    msg1 = {
        "signal": "Q_PROMOTIONS_DETECTED",
        "incident_id": "incident_1",
        "facts": {"promotion_count": 3}
    }

    msg2 = {
        "signal": "Q_PROMOTIONS_DETECTED",
        "incident_id": "incident_2",
        "facts": {"promotion_count": 5}
    }

    with patch.object(engine, '_is_maintenance_mode', return_value=False):
        await engine._process_advisory(msg1)
        await engine._process_advisory(msg2)

    assert mock_pub.emit.call_count == 2

    call1_facts = mock_pub.emit.call_args_list[0][1]['facts']
    call2_facts = mock_pub.emit.call_args_list[1][1]['facts']

    assert call1_facts['promotion_count'] == 3
    assert call2_facts['promotion_count'] == 5


def test_policy_engine_creates_failed_signals_dir_if_missing(temp_failed_signals_log):
    """Test that policy engine creates failed signals directory if it doesn't exist."""
    temp_dir = Path(tempfile.mkdtemp())
    temp_log = temp_dir / "subdir" / "failed_signals.jsonl"

    mock_pub = Mock()
    mock_sub = Mock()

    engine = KLoROSPolicyEngine(
        failed_signals_log=temp_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    assert temp_log.parent.exists()

    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_handle_promotions_preserves_all_facts(temp_failed_signals_log):
    """Test that all promotion facts are preserved in trigger signal."""
    mock_pub = Mock()
    mock_sub = Mock()

    engine = KLoROSPolicyEngine(
        failed_signals_log=temp_failed_signals_log,
        chem_pub=mock_pub,
        chem_sub=mock_sub
    )

    facts = {
        "promotion_count": 10,
        "oldest_promotion_age_hours": 120,
        "newest_promotion_age_hours": 0.5,
        "promotion_files": ["promo1.json", "promo2.json"]
    }

    await engine._handle_promotions_detected(facts)

    call_args = mock_pub.emit.call_args
    emitted_facts = call_args[1]['facts']

    assert emitted_facts['oldest_promotion_age_hours'] == 120
    assert emitted_facts['promotion_count'] == 10
    assert emitted_facts['reason'] == 'unacknowledged_promotions_detected'
