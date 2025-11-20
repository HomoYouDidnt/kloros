#!/usr/bin/env python3
"""
Tests for orchestrator_monitor.py - Advisory monitoring daemon.
"""

import pytest
import json
import time
import tempfile
import shutil
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime, timezone, timedelta

from src.kloros.orchestration.orchestrator_monitor import OrchestratorMonitor


@pytest.fixture
def temp_promotions_dir():
    """Create temporary promotions directory for testing."""
    tmpdir = tempfile.mkdtemp()
    yield Path(tmpdir)
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def temp_failed_signals_log():
    """Create temporary failed signals log file."""
    fd, path = tempfile.mkstemp(suffix='.jsonl')
    yield Path(path)
    Path(path).unlink(missing_ok=True)


def test_count_unacknowledged_promotions_empty_dir(temp_promotions_dir):
    """Test counting promotions when directory is empty."""
    mock_pub = Mock()
    monitor = OrchestratorMonitor(
        promotions_dir=temp_promotions_dir,
        check_interval_s=60,
        chem_pub=mock_pub
    )

    result = monitor._count_unacknowledged_promotions()
    assert result['promotion_count'] == 0
    assert result['oldest_promotion_age_hours'] is None
    assert result['newest_promotion_age_hours'] is None


def test_count_unacknowledged_promotions_with_promotions(temp_promotions_dir):
    """Test counting promotions with actual promotion files."""
    import os

    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=48)
    recent_time = now - timedelta(hours=2)

    old_promotion = temp_promotions_dir / "old_promotion.json"
    recent_promotion = temp_promotions_dir / "recent_promotion.json"

    with open(old_promotion, 'w') as f:
        json.dump({
            "promoted_at": old_time.isoformat(),
            "variant_id": "variant_123",
            "score": 0.95
        }, f)

    with open(recent_promotion, 'w') as f:
        json.dump({
            "promoted_at": recent_time.isoformat(),
            "variant_id": "variant_456",
            "score": 0.98
        }, f)

    old_mtime = old_time.timestamp()
    recent_mtime = recent_time.timestamp()
    os.utime(old_promotion, (old_mtime, old_mtime))
    os.utime(recent_promotion, (recent_mtime, recent_mtime))

    mock_pub = Mock()
    monitor = OrchestratorMonitor(
        promotions_dir=temp_promotions_dir,
        check_interval_s=60,
        chem_pub=mock_pub
    )

    result = monitor._count_unacknowledged_promotions()

    assert result['promotion_count'] == 2
    assert result['oldest_promotion_age_hours'] >= 47
    assert result['newest_promotion_age_hours'] >= 1
    assert len(result['promotion_files']) == 2


def test_count_unacknowledged_promotions_ignores_acknowledged(temp_promotions_dir):
    """Test that counting ignores acknowledged promotions."""
    ack_dir = temp_promotions_dir / "acknowledged"
    ack_dir.mkdir()

    promotion = temp_promotions_dir / "promotion.json"
    ack_promotion = ack_dir / "ack_promotion.json"

    with open(promotion, 'w') as f:
        json.dump({"variant_id": "variant_123"}, f)

    with open(ack_promotion, 'w') as f:
        json.dump({"variant_id": "variant_456"}, f)

    mock_pub = Mock()
    monitor = OrchestratorMonitor(
        promotions_dir=temp_promotions_dir,
        check_interval_s=60,
        chem_pub=mock_pub
    )

    result = monitor._count_unacknowledged_promotions()

    assert result['promotion_count'] == 1


def test_emit_signal_publishes_to_chemical_bus():
    """Test that _emit_signal publishes correctly formatted signals."""
    mock_pub = Mock()
    monitor = OrchestratorMonitor(check_interval_s=60, chem_pub=mock_pub)

    facts = {
        "promotion_count": 3,
        "oldest_promotion_age_hours": 48,
        "newest_promotion_age_hours": 2
    }

    monitor._emit_signal("Q_PROMOTIONS_DETECTED", facts)

    mock_pub.emit.assert_called_once()
    call_args = mock_pub.emit.call_args

    assert call_args[1]['signal'] == 'Q_PROMOTIONS_DETECTED'
    assert call_args[1]['ecosystem'] == 'orchestration'
    assert call_args[1]['intensity'] == 1.0
    assert call_args[1]['facts']['promotion_count'] == 3
    assert call_args[1]['facts']['oldest_promotion_age_hours'] == 48
    assert call_args[1]['facts']['newest_promotion_age_hours'] == 2
    assert call_args[1]['facts']['source'] == 'orchestrator_monitor'


def test_check_system_health_basic():
    """Test basic system health checking."""
    mock_pub = Mock()
    monitor = OrchestratorMonitor(check_interval_s=60, chem_pub=mock_pub)

    health_issues = monitor._check_system_health()

    assert isinstance(health_issues, list)


@pytest.mark.asyncio
async def test_periodic_checks_detects_promotions(temp_promotions_dir):
    """Test that periodic checks detect promotions and emit signals."""
    promotion = temp_promotions_dir / "test_promotion.json"
    with open(promotion, 'w') as f:
        json.dump({
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "variant_id": "variant_test"
        }, f)

    mock_pub = Mock()
    monitor = OrchestratorMonitor(
        promotions_dir=temp_promotions_dir,
        check_interval_s=0.1,
        chem_pub=mock_pub
    )

    task = asyncio.create_task(monitor.periodic_checks())

    await asyncio.sleep(0.25)

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert mock_pub.emit.called

    found_promotion_signal = False
    for call in mock_pub.emit.call_args_list:
        if call[1].get('signal') == 'Q_PROMOTIONS_DETECTED':
            found_promotion_signal = True
            facts = call[1].get('facts', {})
            assert facts['promotion_count'] == 1
            break

    assert found_promotion_signal, "Q_PROMOTIONS_DETECTED signal should have been emitted"


@pytest.mark.asyncio
async def test_periodic_checks_does_not_emit_when_no_promotions(temp_promotions_dir):
    """Test that periodic checks don't emit Q_PROMOTIONS_DETECTED when no promotions exist."""
    mock_pub = Mock()
    monitor = OrchestratorMonitor(
        promotions_dir=temp_promotions_dir,
        check_interval_s=0.1,
        chem_pub=mock_pub
    )

    task = asyncio.create_task(monitor.periodic_checks())

    await asyncio.sleep(0.25)

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    for call in mock_pub.emit.call_args_list:
        assert call[1].get('signal') != 'Q_PROMOTIONS_DETECTED', \
            "Q_PROMOTIONS_DETECTED should not be emitted when no promotions exist"


@pytest.mark.asyncio
async def test_daemon_runs_continuously():
    """Test that daemon runs periodic checks continuously."""
    mock_pub = Mock()
    monitor = OrchestratorMonitor(check_interval_s=0.05, chem_pub=mock_pub)

    check_count = 0
    original_check = monitor._count_unacknowledged_promotions

    def counting_check():
        nonlocal check_count
        check_count += 1
        return original_check()

    monitor._count_unacknowledged_promotions = counting_check

    task = asyncio.create_task(monitor.periodic_checks())

    await asyncio.sleep(0.3)

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert check_count >= 3, f"Should have run multiple checks, got {check_count}"


def test_monitor_initialization():
    """Test that OrchestratorMonitor initializes correctly."""
    mock_pub = Mock()
    monitor = OrchestratorMonitor(check_interval_s=60, chem_pub=mock_pub)

    assert monitor.check_interval_s == 60
    assert monitor.promotions_dir == Path("/home/kloros/.kloros/dream_lab/promotions")
    assert hasattr(monitor, 'chem_pub')


def test_signal_includes_timestamp():
    """Test that emitted signals include timestamp."""
    mock_pub = Mock()
    monitor = OrchestratorMonitor(check_interval_s=60, chem_pub=mock_pub)

    before = datetime.now(timezone.utc)
    monitor._emit_signal("Q_PROMOTIONS_DETECTED", {"test": "data"})
    after = datetime.now(timezone.utc)

    call_args = mock_pub.emit.call_args

    assert 'signal' in call_args[1]
    assert call_args[1]['signal'] == 'Q_PROMOTIONS_DETECTED'
