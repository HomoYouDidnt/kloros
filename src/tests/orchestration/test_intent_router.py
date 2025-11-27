#!/usr/bin/env python3
"""
Tests for intent_router.py - Intent file to chemical signal bridge.
"""

import pytest
import json
import time
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.orchestration.core.intent_router import IntentRouter


@pytest.fixture
def temp_intent_dir():
    """Create temporary intent directory for testing."""
    tmpdir = tempfile.mkdtemp()
    yield Path(tmpdir)
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def temp_dlq_file():
    """Create temporary dead letter queue file."""
    fd, path = tempfile.mkstemp(suffix='.jsonl')
    yield Path(path)
    Path(path).unlink(missing_ok=True)


def test_intent_router_reads_discover_module_intent(temp_intent_dir, temp_dlq_file):
    """Test that IntentRouter reads discover.module intent files."""
    intent_data = {
        "type": "discover.module",
        "id": "discover.module.audio",
        "data": {
            "question": "What does the audio module do?",
            "priority": "normal",
            "evidence": ["path:/home/kloros/src/audio", "has_init:true"]
        }
    }

    intent_file = temp_intent_dir / "test_intent.json"
    with open(intent_file, 'w') as f:
        json.dump(intent_data, f)

    with patch('src.kloros.orchestration.intent_router.UMNPub') as mock_pub_class:
        mock_pub = Mock()
        mock_pub_class.return_value = mock_pub

        router = IntentRouter(
            intent_dir=str(temp_intent_dir),
            dlq_path=str(temp_dlq_file)
        )

        router._route_intent(intent_file)

        mock_pub.emit.assert_called_once()
        call_args = mock_pub.emit.call_args

        assert call_args[1]['signal'] == 'Q_CURIOSITY_INVESTIGATE'
        assert call_args[1]['ecosystem'] == 'introspection'
        assert call_args[1]['facts']['question'] == "What does the audio module do?"
        assert call_args[1]['facts']['question_id'] == "discover.module.audio"
        assert call_args[1]['facts']['priority'] == "normal"
        assert call_args[1]['facts']['evidence'] == ["path:/home/kloros/src/audio", "has_init:true"]


def test_intent_router_deletes_processed_file(temp_intent_dir, temp_dlq_file):
    """Test that IntentRouter deletes successfully processed intent files."""
    intent_data = {
        "type": "discover.module",
        "id": "discover.module.test",
        "data": {
            "question": "Test question",
            "priority": "normal",
            "evidence": []
        }
    }

    intent_file = temp_intent_dir / "test_intent.json"
    with open(intent_file, 'w') as f:
        json.dump(intent_data, f)

    assert intent_file.exists()

    with patch('src.kloros.orchestration.intent_router.UMNPub'):
        router = IntentRouter(
            intent_dir=str(temp_intent_dir),
            dlq_path=str(temp_dlq_file)
        )
        router._route_intent(intent_file)

    assert not intent_file.exists()


def test_intent_router_handles_reinvestigate_intent(temp_intent_dir, temp_dlq_file):
    """Test that IntentRouter handles reinvestigate intents."""
    intent_data = {
        "type": "reinvestigate",
        "id": "reinvestigate.module.audio",
        "data": {
            "question": "Re-investigate audio module",
            "priority": "high",
            "evidence": ["new_evidence:found"]
        }
    }

    intent_file = temp_intent_dir / "reinvestigate.json"
    with open(intent_file, 'w') as f:
        json.dump(intent_data, f)

    with patch('src.kloros.orchestration.intent_router.UMNPub') as mock_pub_class:
        mock_pub = Mock()
        mock_pub_class.return_value = mock_pub

        router = IntentRouter(
            intent_dir=str(temp_intent_dir),
            dlq_path=str(temp_dlq_file)
        )
        router._route_intent(intent_file)

        mock_pub.emit.assert_called_once()
        call_args = mock_pub.emit.call_args

        assert call_args[1]['signal'] == 'Q_CURIOSITY_INVESTIGATE'
        assert call_args[1]['facts']['question'] == "Re-investigate audio module"
        assert call_args[1]['facts']['priority'] == "high"


def test_intent_router_writes_to_dlq_on_failure(temp_intent_dir, temp_dlq_file):
    """Test that IntentRouter writes failed intents to dead letter queue."""
    intent_file = temp_intent_dir / "bad_intent.json"
    with open(intent_file, 'w') as f:
        f.write("invalid json{")

    with patch('src.kloros.orchestration.intent_router.UMNPub'):
        router = IntentRouter(
            intent_dir=str(temp_intent_dir),
            dlq_path=str(temp_dlq_file)
        )
        router._route_intent(intent_file)

    assert temp_dlq_file.exists()

    with open(temp_dlq_file, 'r') as f:
        dlq_entry = json.loads(f.read())

    assert 'error' in dlq_entry
    assert 'intent_file' in dlq_entry
    assert dlq_entry['intent_file'] == str(intent_file)


def test_intent_router_handles_unknown_intent_type(temp_intent_dir, temp_dlq_file):
    """Test that IntentRouter handles unknown intent types gracefully."""
    intent_data = {
        "type": "unknown.type",
        "id": "unknown.test",
        "data": {}
    }

    intent_file = temp_intent_dir / "unknown.json"
    with open(intent_file, 'w') as f:
        json.dump(intent_data, f)

    with patch('src.kloros.orchestration.intent_router.UMNPub') as mock_pub_class:
        mock_pub = Mock()
        mock_pub_class.return_value = mock_pub

        router = IntentRouter(
            intent_dir=str(temp_intent_dir),
            dlq_path=str(temp_dlq_file)
        )
        router._route_intent(intent_file)

        mock_pub.emit.assert_not_called()
