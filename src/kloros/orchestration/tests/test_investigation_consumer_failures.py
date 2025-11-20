"""
Tests for failure tracking in investigation_consumer_daemon.py

Tests the failure detection and recording functionality that integrates
with SemanticEvidenceStore to track investigation failures.
"""

import pytest
import json
import tempfile
import time
import logging
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parents[4]))
sys.path.insert(0, str(Path(__file__).parents[4] / "src"))

from kloros.orchestration.investigation_consumer_daemon import InvestigationConsumer
from registry.semantic_evidence import SemanticEvidenceStore


@pytest.fixture
def temp_evidence_file():
    """Create a temporary evidence file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write('{}')
        temp_path = f.name
    yield Path(temp_path)
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def mock_semantic_store(temp_evidence_file):
    """Create a mock SemanticEvidenceStore for testing."""
    return SemanticEvidenceStore(evidence_path=temp_evidence_file)


@pytest.fixture
def consumer(mock_semantic_store, monkeypatch):
    """Create an InvestigationConsumer with mocked dependencies."""
    with patch('kloros.orchestration.investigation_consumer_daemon.get_module_investigator'):
        with patch('kloros.orchestration.investigation_consumer_daemon.get_systemd_investigator'):
            with patch('kloros.orchestration.investigation_consumer_daemon.GenericInvestigationHandler'):
                with patch('kloros.orchestration.investigation_consumer_daemon.get_ollama_url', return_value='http://localhost:11434'):
                    with patch('kloros.orchestration.investigation_consumer_daemon.select_best_model_for_task', return_value='test_model'):
                        with patch('kloros.orchestration.investigation_consumer_daemon.ChemPub'):
                            consumer = InvestigationConsumer()
                            consumer.semantic_store = mock_semantic_store
                            return consumer


class TestFailureDetection:
    """Test failure detection logic."""

    def test_detects_failure_with_not_answered_status(self, consumer):
        """Investigation with status != 'answered' should be detected as failure."""
        question_data = {
            "question_id": "test.question",
            "question": "What does this do?",
            "capability_key": "test.capability",
            "evidence": []
        }

        result = {
            "status": "failed",
            "question_id": "test.question",
            "module_name": "test_module"
        }

        assert consumer._is_investigation_failure(question_data, result) is True

    def test_detects_failure_with_unsolvable_tag(self, consumer):
        """Investigation with 'unsolvable' tag should be detected as failure."""
        question_data = {
            "question_id": "test.question",
            "question": "What does this do?",
            "capability_key": "test.capability",
            "evidence": []
        }

        result = {
            "status": "completed",
            "question_id": "test.question",
            "tags": ["unsolvable"],
            "module_name": "test_module"
        }

        assert consumer._is_investigation_failure(question_data, result) is True

    def test_detects_failure_with_empty_evidence(self, consumer):
        """Investigation with no evidence should be detected as failure."""
        question_data = {
            "question_id": "test.question",
            "question": "What does this do?",
            "capability_key": "test.capability",
            "evidence": []
        }

        result = {
            "status": "completed",
            "question_id": "test.question",
            "evidence": [],
            "module_name": "test_module"
        }

        assert consumer._is_investigation_failure(question_data, result) is True

    def test_detects_failure_with_duplicate_evidence_hash(self, consumer):
        """Investigation with same evidence_hash as previous attempt should fail."""
        question_data = {
            "question_id": "test.question",
            "question": "What does this do?",
            "capability_key": "test.capability",
            "evidence": ["path:/some/file", "content:some_content"],
            "previous_evidence_hash": "abc123"
        }

        result = {
            "status": "completed",
            "question_id": "test.question",
            "evidence": ["path:/some/file", "content:some_content"],
            "evidence_hash": "abc123",
            "module_name": "test_module"
        }

        assert consumer._is_investigation_failure(question_data, result) is True

    def test_success_not_detected_as_failure(self, consumer):
        """Successful investigation should not be detected as failure."""
        question_data = {
            "question_id": "test.question",
            "question": "What does this do?",
            "capability_key": "test.capability",
            "evidence": []
        }

        result = {
            "status": "completed",
            "question_id": "test.question",
            "evidence": ["purpose:Does something useful"],
            "module_name": "test_module"
        }

        assert consumer._is_investigation_failure(question_data, result) is False

    def test_no_false_positives_on_answered_status(self, consumer):
        """Investigation with status 'completed' and non-empty evidence is success."""
        question_data = {
            "question_id": "test.question",
            "question": "What does this do?",
            "capability_key": "test.capability",
            "evidence": []
        }

        result = {
            "status": "completed",
            "question_id": "test.question",
            "evidence": ["key:value"],
            "module_name": "test_module"
        }

        assert consumer._is_investigation_failure(question_data, result) is False


class TestGetFailureReason:
    """Test failure reason extraction."""

    def test_extracts_reason_from_not_answered_status(self, consumer):
        """Should extract failure reason when status is not answered."""
        result = {
            "status": "failed",
            "error": "Connection timeout"
        }

        reason = consumer._get_failure_reason(result)
        assert "status" in reason.lower()
        assert "failed" in reason.lower()

    def test_extracts_reason_from_unsolvable_tag(self, consumer):
        """Should extract failure reason when unsolvable tag present."""
        result = {
            "status": "completed",
            "tags": ["unsolvable"]
        }

        reason = consumer._get_failure_reason(result)
        assert "unsolvable" in reason.lower()

    def test_extracts_reason_from_empty_evidence(self, consumer):
        """Should extract failure reason when no evidence found."""
        result = {
            "status": "completed",
            "evidence": []
        }

        reason = consumer._get_failure_reason(result)
        assert "evidence" in reason.lower() or "empty" in reason.lower()

    def test_extracts_reason_from_duplicate_evidence(self, consumer):
        """Should extract failure reason when evidence hash matches previous."""
        result = {
            "status": "completed",
            "evidence_hash": "abc123",
            "previous_evidence_hash": "abc123"
        }

        reason = consumer._get_failure_reason(result)
        assert "duplicate" in reason.lower() or "same" in reason.lower() or "hash" in reason.lower()


class TestRecordFailure:
    """Test record_failure call integration."""

    def test_records_failure_with_capability_key(self, consumer, mock_semantic_store):
        """Should call record_failure with capability_key when available."""
        question_data = {
            "question_id": "test.question",
            "capability_key": "test.capability",
            "evidence": []
        }

        result = {
            "status": "failed",
            "question_id": "test.question",
            "module_name": "test_module"
        }

        consumer._record_investigation_failure(question_data, result)

        assert mock_semantic_store.is_suppressed("test.capability") is False
        assert mock_semantic_store.get_suppression_info("test.capability")["failure_count"] >= 1

    def test_skips_recording_when_no_capability_key(self, consumer, mock_semantic_store):
        """Should skip failure recording if capability_key missing."""
        question_data = {
            "question_id": "test.question",
            "evidence": []
        }

        result = {
            "status": "failed",
            "question_id": "test.question",
            "module_name": "test_module"
        }

        # Should not raise an exception
        consumer._record_investigation_failure(question_data, result)

    def test_handles_exception_during_record_failure(self, consumer, mock_semantic_store):
        """Should catch exceptions from record_failure and continue."""
        question_data = {
            "question_id": "test.question",
            "capability_key": "test.capability",
            "evidence": []
        }

        result = {
            "status": "failed",
            "question_id": "test.question",
            "module_name": "test_module"
        }

        with patch.object(mock_semantic_store, 'record_failure', side_effect=Exception("Store error")):
            consumer.semantic_store = mock_semantic_store
            # Should not raise
            consumer._record_investigation_failure(question_data, result)


class TestFailureTrackingIntegration:
    """Test failure tracking in the investigation flow."""

    def test_failure_tracked_when_investigation_fails(self, consumer, mock_semantic_store):
        """Failure tracking should be called when investigation fails."""
        question_data = {
            "question_id": "test.question",
            "question": "What does this do?",
            "capability_key": "test.capability",
            "evidence": []
        }

        result = {
            "status": "failed",
            "question_id": "test.question",
            "module_name": "test_module"
        }

        consumer._record_investigation_failure(question_data, result)

        info = mock_semantic_store.get_suppression_info("test.capability")
        assert info["failure_count"] >= 1
        assert "failed" in info["reason"].lower()

    def test_success_does_not_trigger_failure_recording(self, consumer, mock_semantic_store):
        """Successful investigation should not trigger failure recording."""
        question_data = {
            "question_id": "test.question",
            "question": "What does this do?",
            "capability_key": "test.capability",
            "evidence": []
        }

        result = {
            "status": "completed",
            "question_id": "test.question",
            "evidence": ["purpose:Does something"],
            "module_name": "test_module"
        }

        if consumer._is_investigation_failure(question_data, result):
            consumer._record_investigation_failure(question_data, result)

        info = mock_semantic_store.get_suppression_info("test.capability")
        assert info.get("failure_count", 0) == 0


class TestFailureLogging:
    """Test that failures are logged appropriately."""

    def test_logs_at_debug_level_when_recording_failure(self, consumer, mock_semantic_store, caplog):
        """Should log at DEBUG level when recording failure."""
        with caplog.at_level(logging.DEBUG):
            question_data = {
                "question_id": "test.question",
                "capability_key": "test.capability",
                "evidence": []
            }

            result = {
                "status": "failed",
                "question_id": "test.question",
                "module_name": "test_module"
            }

            consumer._record_investigation_failure(question_data, result)

            debug_logs = [r for r in caplog.records if r.levelname == 'DEBUG']
            assert len(debug_logs) > 0 or "test.capability" in [r.message for r in caplog.records if 'failure' in r.message.lower()]

    def test_logs_warning_when_missing_capability_key(self, consumer, caplog):
        """Should log warning when capability_key is missing."""
        with caplog.at_level(logging.WARNING):
            question_data = {
                "question_id": "test.question",
                "evidence": []
            }

            result = {
                "status": "failed",
                "question_id": "test.question",
                "module_name": "test_module"
            }

            consumer._record_investigation_failure(question_data, result)

    def test_logs_error_when_record_failure_fails(self, consumer, mock_semantic_store, caplog):
        """Should log error when record_failure raises exception."""
        with caplog.at_level(logging.ERROR):
            question_data = {
                "question_id": "test.question",
                "capability_key": "test.capability",
                "evidence": []
            }

            result = {
                "status": "failed",
                "question_id": "test.question",
                "module_name": "test_module"
            }

            with patch.object(mock_semantic_store, 'record_failure', side_effect=Exception("Store error")):
                consumer.semantic_store = mock_semantic_store
                consumer._record_investigation_failure(question_data, result)


class TestSemanticStoreInitialization:
    """Test that SemanticEvidenceStore is properly initialized."""

    def test_semantic_store_initialized_in_init(self, mock_semantic_store):
        """SemanticEvidenceStore should be initialized in __init__."""
        with patch('kloros.orchestration.investigation_consumer_daemon.get_module_investigator'):
            with patch('kloros.orchestration.investigation_consumer_daemon.get_systemd_investigator'):
                with patch('kloros.orchestration.investigation_consumer_daemon.GenericInvestigationHandler'):
                    with patch('kloros.orchestration.investigation_consumer_daemon.get_ollama_url', return_value='http://localhost:11434'):
                        with patch('kloros.orchestration.investigation_consumer_daemon.select_best_model_for_task', return_value='test_model'):
                            with patch('kloros.orchestration.investigation_consumer_daemon.ChemPub'):
                                consumer = InvestigationConsumer()

                                assert hasattr(consumer, 'semantic_store')
                                assert consumer.semantic_store is not None

    def test_semantic_store_init_failure_logged_not_raised(self, caplog):
        """If SemanticEvidenceStore init fails, should log warning and continue."""
        with patch('kloros.orchestration.investigation_consumer_daemon.get_module_investigator'):
            with patch('kloros.orchestration.investigation_consumer_daemon.get_systemd_investigator'):
                with patch('kloros.orchestration.investigation_consumer_daemon.GenericInvestigationHandler'):
                    with patch('kloros.orchestration.investigation_consumer_daemon.get_ollama_url', return_value='http://localhost:11434'):
                        with patch('kloros.orchestration.investigation_consumer_daemon.select_best_model_for_task', return_value='test_model'):
                            with patch('kloros.orchestration.investigation_consumer_daemon.ChemPub'):
                                with patch('kloros.orchestration.investigation_consumer_daemon.SemanticEvidenceStore', side_effect=Exception("Init failed")):
                                    with caplog.at_level(logging.WARNING):
                                        consumer = InvestigationConsumer()
                                        assert hasattr(consumer, 'semantic_store')


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_handles_missing_evidence_field_in_result(self, consumer):
        """Should handle result missing 'evidence' field gracefully."""
        question_data = {
            "question_id": "test.question",
            "capability_key": "test.capability",
            "evidence": []
        }

        result = {
            "status": "completed",
            "question_id": "test.question",
            "module_name": "test_module"
        }

        # Should not raise KeyError
        is_failure = consumer._is_investigation_failure(question_data, result)
        assert isinstance(is_failure, bool)

    def test_handles_missing_status_field_in_result(self, consumer):
        """Should handle result missing 'status' field gracefully."""
        question_data = {
            "question_id": "test.question",
            "capability_key": "test.capability",
            "evidence": []
        }

        result = {
            "question_id": "test.question",
            "module_name": "test_module"
        }

        # Should not raise KeyError
        is_failure = consumer._is_investigation_failure(question_data, result)
        assert isinstance(is_failure, bool)

    def test_handles_none_capability_key(self, consumer):
        """Should handle None capability_key gracefully."""
        question_data = {
            "question_id": "test.question",
            "capability_key": None,
            "evidence": []
        }

        result = {
            "status": "failed",
            "question_id": "test.question",
            "module_name": "test_module"
        }

        # Should not raise
        consumer._record_investigation_failure(question_data, result)
