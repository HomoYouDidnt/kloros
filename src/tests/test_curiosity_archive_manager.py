#!/usr/bin/env python3
"""
Unit tests for ArchiveManager.

Tests cover:
- Archive creation for category-specific files
- Pattern detection when thresholds are reached
- Opportunistic rehydration when main feed is empty
- Purging of old entries
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, call

from src.orchestration.registry.curiosity_archive_manager import ArchiveManager
from src.orchestration.registry.curiosity_core import CuriosityQuestion, ActionClass, QuestionStatus


@pytest.fixture
def temp_archive_dir():
    """Create temporary directory for archive files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_chem_pub():
    """Create mock UMNPub for testing."""
    mock = MagicMock()
    return mock


@pytest.fixture
def archive_manager(temp_archive_dir, mock_chem_pub):
    """Create ArchiveManager instance with temp directory."""
    return ArchiveManager(temp_archive_dir, mock_chem_pub)


def test_archive_creation(archive_manager, temp_archive_dir):
    """Test that archive files are created for each category."""
    q = CuriosityQuestion(
        id="test.q1",
        hypothesis="TEST_HYPOTHESIS",
        question="What is this?",
        evidence=["evidence1"],
        action_class=ActionClass.INVESTIGATE,
        autonomy=2,
        value_estimate=0.5,
        cost=0.2
    )

    archive_manager.archive_question(q, "low_value")

    assert (temp_archive_dir / "low_value.jsonl").exists()

    with open(temp_archive_dir / "low_value.jsonl", 'r') as f:
        line = f.readline()
        data = json.loads(line)
        assert data['id'] == "test.q1"


def test_archive_multiple_categories(archive_manager, temp_archive_dir):
    """Test that multiple archive categories work independently."""
    q1 = CuriosityQuestion(
        id="test.q1",
        hypothesis="TEST",
        question="Q1?",
        evidence=["e1"],
        action_class=ActionClass.INVESTIGATE
    )

    q2 = CuriosityQuestion(
        id="test.q2",
        hypothesis="TEST",
        question="Q2?",
        evidence=["e2"],
        action_class=ActionClass.INVESTIGATE
    )

    archive_manager.archive_question(q1, "low_value")
    archive_manager.archive_question(q2, "already_processed")

    assert (temp_archive_dir / "low_value.jsonl").exists()
    assert (temp_archive_dir / "already_processed.jsonl").exists()

    with open(temp_archive_dir / "low_value.jsonl", 'r') as f:
        assert "test.q1" in f.read()

    with open(temp_archive_dir / "already_processed.jsonl", 'r') as f:
        assert "test.q2" in f.read()


def test_archive_emits_archived_signal(archive_manager, mock_chem_pub):
    """Test that archiving emits Q_CURIOSITY_ARCHIVED signal."""
    q = CuriosityQuestion(
        id="test.q1",
        hypothesis="TEST",
        question="Q?",
        evidence=["e1"],
        action_class=ActionClass.INVESTIGATE
    )

    archive_manager.archive_question(q, "low_value")

    mock_chem_pub.emit.assert_called()
    calls = mock_chem_pub.emit.call_args_list
    archived_call = [c for c in calls if c[0][0] == "Q_CURIOSITY_ARCHIVED"]
    assert len(archived_call) > 0


def test_pattern_detection_low_value(archive_manager, mock_chem_pub, temp_archive_dir):
    """Test that 10 low_value questions trigger pattern investigation."""
    for i in range(10):
        q = CuriosityQuestion(
            id=f"test.q{i}",
            hypothesis="TEST",
            question=f"Question {i}?",
            evidence=[f"evidence{i}"],
            action_class=ActionClass.INVESTIGATE
        )
        archive_manager.archive_question(q, "low_value")

    pattern_calls = [c for c in mock_chem_pub.emit.call_args_list
                     if c[0][0] == "Q_CURIOSITY_HIGH"]
    assert len(pattern_calls) >= 1

    pattern_call = pattern_calls[0]
    assert pattern_call[1]['ecosystem'] == 'introspection'
    facts = pattern_call[1]['facts']
    assert 'archive_category:low_value' in facts['evidence']


def test_pattern_detection_resource_blocked(archive_manager, mock_chem_pub):
    """Test that 5 resource_blocked questions trigger pattern investigation."""
    for i in range(5):
        q = CuriosityQuestion(
            id=f"test.q{i}",
            hypothesis="TEST",
            question=f"Question {i}?",
            evidence=[f"evidence{i}"],
            action_class=ActionClass.INVESTIGATE
        )
        archive_manager.archive_question(q, "resource_blocked")

    pattern_calls = [c for c in mock_chem_pub.emit.call_args_list
                     if c[0][0] == "Q_CURIOSITY_HIGH"]
    assert len(pattern_calls) >= 1


def test_pattern_detection_missing_deps(archive_manager, mock_chem_pub):
    """Test that 8 missing_deps questions trigger pattern investigation."""
    for i in range(8):
        q = CuriosityQuestion(
            id=f"test.q{i}",
            hypothesis="TEST",
            question=f"Question {i}?",
            evidence=[f"evidence{i}"],
            action_class=ActionClass.INVESTIGATE
        )
        archive_manager.archive_question(q, "missing_deps")

    pattern_calls = [c for c in mock_chem_pub.emit.call_args_list
                     if c[0][0] == "Q_CURIOSITY_HIGH"]
    assert len(pattern_calls) >= 1


def test_pattern_investigation_is_high_priority(archive_manager, mock_chem_pub):
    """Test that pattern investigation questions are emitted at HIGH priority."""
    for i in range(10):
        q = CuriosityQuestion(
            id=f"test.q{i}",
            hypothesis="TEST",
            question=f"Question {i}?",
            evidence=[f"evidence{i}"],
            action_class=ActionClass.INVESTIGATE
        )
        archive_manager.archive_question(q, "low_value")

    pattern_calls = [c for c in mock_chem_pub.emit.call_args_list
                     if c[0][0] == "Q_CURIOSITY_HIGH"]
    assert len(pattern_calls) >= 1


def test_opportunistic_rehydration_below_threshold(archive_manager, mock_chem_pub, temp_archive_dir):
    """Test that rehydration pulls from archives when main_feed_size < 5."""
    for i in range(7):
        q = CuriosityQuestion(
            id=f"test.q{i}",
            hypothesis="TEST",
            question=f"Question {i}?",
            evidence=[f"evidence{i}"],
            action_class=ActionClass.INVESTIGATE
        )
        archive_manager.archive_question(q, "low_value")

    mock_chem_pub.reset_mock()

    archive_manager.rehydrate_opportunistic(main_feed_size=3)

    low_priority_calls = [c for c in mock_chem_pub.emit.call_args_list
                         if c[0][0] == "Q_CURIOSITY_LOW"]
    assert len(low_priority_calls) > 0
    assert len(low_priority_calls) <= 3


def test_opportunistic_rehydration_above_threshold(archive_manager, mock_chem_pub):
    """Test that rehydration does nothing when main_feed_size >= 5."""
    for i in range(7):
        q = CuriosityQuestion(
            id=f"test.q{i}",
            hypothesis="TEST",
            question=f"Question {i}?",
            evidence=[f"evidence{i}"],
            action_class=ActionClass.INVESTIGATE
        )
        archive_manager.archive_question(q, "low_value")

    mock_chem_pub.reset_mock()

    archive_manager.rehydrate_opportunistic(main_feed_size=10)

    assert mock_chem_pub.emit.call_count == 0


def test_opportunistic_rehydration_selects_largest(archive_manager, mock_chem_pub):
    """Test that rehydration pulls from largest archive."""
    for i in range(3):
        q = CuriosityQuestion(
            id=f"test.low{i}",
            hypothesis="TEST",
            question=f"Low {i}?",
            evidence=[f"e{i}"],
            action_class=ActionClass.INVESTIGATE
        )
        archive_manager.archive_question(q, "low_value")

    for i in range(5):
        q = CuriosityQuestion(
            id=f"test.blocked{i}",
            hypothesis="TEST",
            question=f"Blocked {i}?",
            evidence=[f"e{i}"],
            action_class=ActionClass.INVESTIGATE
        )
        archive_manager.archive_question(q, "resource_blocked")

    mock_chem_pub.reset_mock()

    archive_manager.rehydrate_opportunistic(main_feed_size=2)

    low_priority_calls = [c for c in mock_chem_pub.emit.call_args_list
                         if c[0][0] == "Q_CURIOSITY_LOW"]
    assert len(low_priority_calls) > 0

    facts_list = [c[1]['facts'] for c in low_priority_calls]
    ids_rehydrated = [f['id'] for f in facts_list]

    blocked_ids = [f"test.blocked{i}" for i in range(5)]
    assert any(bid in ids_rehydrated for bid in blocked_ids)


def test_count_entries(archive_manager, temp_archive_dir):
    """Test counting entries in archive file."""
    archive_file = temp_archive_dir / "low_value.jsonl"

    for i in range(3):
        q = CuriosityQuestion(
            id=f"test.q{i}",
            hypothesis="TEST",
            question=f"Question {i}?",
            evidence=[f"evidence{i}"],
            action_class=ActionClass.INVESTIGATE
        )
        archive_manager.archive_question(q, "low_value")

    count = archive_manager._count_entries(archive_file)
    assert count == 3


def test_count_entries_nonexistent(archive_manager, temp_archive_dir):
    """Test counting entries in nonexistent file returns 0."""
    nonexistent = temp_archive_dir / "nonexistent.jsonl"
    count = archive_manager._count_entries(nonexistent)
    assert count == 0


def test_purge_old_entries(archive_manager, temp_archive_dir):
    """Test that old entries are removed from archive."""
    archive_file = temp_archive_dir / "low_value.jsonl"

    now = datetime.now()
    recent_time = (now - timedelta(days=3)).isoformat()
    old_time = (now - timedelta(days=10)).isoformat()

    recent_q = CuriosityQuestion(
        id="test.recent",
        hypothesis="TEST",
        question="Recent?",
        evidence=["e1"],
        action_class=ActionClass.INVESTIGATE,
        created_at=recent_time
    )

    old_q = CuriosityQuestion(
        id="test.old",
        hypothesis="TEST",
        question="Old?",
        evidence=["e2"],
        action_class=ActionClass.INVESTIGATE,
        created_at=old_time
    )

    with open(archive_file, 'a') as f:
        json.dump(recent_q.to_dict(), f)
        f.write('\n')
        json.dump(old_q.to_dict(), f)
        f.write('\n')

    archive_manager.purge_old_entries('low_value', max_age_days=7)

    remaining = []
    with open(archive_file, 'r') as f:
        for line in f:
            if line.strip():
                remaining.append(json.loads(line))

    assert len(remaining) == 1
    assert remaining[0]['id'] == "test.recent"


def test_purge_old_entries_nonexistent(archive_manager, temp_archive_dir):
    """Test that purging nonexistent archive doesn't error."""
    archive_manager.purge_old_entries('low_value', max_age_days=7)


def test_read_archive(archive_manager, temp_archive_dir):
    """Test reading questions from archive file."""
    archive_file = temp_archive_dir / "low_value.jsonl"

    for i in range(5):
        q = CuriosityQuestion(
            id=f"test.q{i}",
            hypothesis="TEST",
            question=f"Question {i}?",
            evidence=[f"evidence{i}"],
            action_class=ActionClass.INVESTIGATE
        )
        with open(archive_file, 'a') as f:
            json.dump(q.to_dict(), f)
            f.write('\n')

    questions = archive_manager._read_archive(archive_file, limit=3)

    assert len(questions) == 3
    assert questions[0]['id'] == "test.q0"
    assert questions[1]['id'] == "test.q1"
    assert questions[2]['id'] == "test.q2"


def test_read_archive_respects_limit(archive_manager, temp_archive_dir):
    """Test that _read_archive respects limit parameter."""
    archive_file = temp_archive_dir / "low_value.jsonl"

    for i in range(10):
        q = CuriosityQuestion(
            id=f"test.q{i}",
            hypothesis="TEST",
            question=f"Question {i}?",
            evidence=[f"evidence{i}"],
            action_class=ActionClass.INVESTIGATE
        )
        with open(archive_file, 'a') as f:
            json.dump(q.to_dict(), f)
            f.write('\n')

    questions = archive_manager._read_archive(archive_file, limit=1)
    assert len(questions) == 1


def test_read_archive_empty_file(archive_manager, temp_archive_dir):
    """Test reading from empty archive file."""
    archive_file = temp_archive_dir / "low_value.jsonl"
    archive_file.touch()

    questions = archive_manager._read_archive(archive_file, limit=3)
    assert questions == []


def test_unknown_archive_category(archive_manager, mock_chem_pub):
    """Test archiving to unknown category logs warning and returns."""
    q = CuriosityQuestion(
        id="test.q1",
        hypothesis="TEST",
        question="Q?",
        evidence=["e1"],
        action_class=ActionClass.INVESTIGATE
    )

    archive_manager.archive_question(q, "unknown_category")

    calls = [c for c in mock_chem_pub.emit.call_args_list
             if c[0][0] == "Q_CURIOSITY_ARCHIVED"]
    assert len(calls) == 0


def test_archive_preserves_question_data(archive_manager, temp_archive_dir):
    """Test that archiving preserves all question data."""
    q = CuriosityQuestion(
        id="test.preserve",
        hypothesis="HYPO_DATA",
        question="Question with data?",
        evidence=["e1", "e2", "e3"],
        evidence_hash="abc123",
        action_class=ActionClass.PROPOSE_FIX,
        autonomy=3,
        value_estimate=0.9,
        cost=0.1,
        capability_key="test.cap"
    )

    archive_manager.archive_question(q, "low_value")

    with open(temp_archive_dir / "low_value.jsonl", 'r') as f:
        line = f.readline()
        data = json.loads(line)

    assert data['id'] == "test.preserve"
    assert data['hypothesis'] == "HYPO_DATA"
    assert data['evidence'] == ["e1", "e2", "e3"]
    assert data['evidence_hash'] == "abc123"
    assert data['value_estimate'] == 0.9
    assert data['autonomy'] == 3
    assert data['capability_key'] == "test.cap"


def test_pattern_question_has_correct_fields(archive_manager, mock_chem_pub):
    """Test that pattern investigation question has required fields."""
    for i in range(10):
        q = CuriosityQuestion(
            id=f"test.q{i}",
            hypothesis="TEST",
            question=f"Question {i}?",
            evidence=[f"evidence{i}"],
            action_class=ActionClass.INVESTIGATE
        )
        archive_manager.archive_question(q, "low_value")

    pattern_calls = [c for c in mock_chem_pub.emit.call_args_list
                     if c[0][0] == "Q_CURIOSITY_HIGH"]
    assert len(pattern_calls) > 0

    pattern_call = pattern_calls[0]
    facts = pattern_call[1]['facts']

    assert 'id' in facts
    assert facts['id'].startswith("pattern.archive.low_value")
    assert 'question' in facts
    assert facts['action_class'] == 'investigate'
    assert facts['autonomy'] == 2
    assert facts['value_estimate'] == 0.8
    assert facts['status'] == 'ready'
