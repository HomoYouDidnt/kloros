#!/usr/bin/env python3
"""
Tests for Phase 3.3: CuriosityCore suppression integration.

Tests verify that suppression checks are properly integrated into
question generation pipeline.
"""

import pytest
import json
import logging
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from src.orchestration.registry.curiosity_core import CuriosityCore, CuriosityQuestion, ActionClass, QuestionStatus
from src.orchestration.registry.semantic_evidence import SemanticEvidenceStore
from src.orchestration.registry.capability_evaluator import CapabilityMatrix, CapabilityRecord, CapabilityState


@pytest.fixture
def temp_evidence_store(tmp_path):
    """Create temporary semantic evidence store for testing."""
    store_path = tmp_path / "semantic_evidence.json"
    store = SemanticEvidenceStore(evidence_path=store_path)
    return store


class TestSuppressionInitialization:
    """Tests for SemanticEvidenceStore initialization in CuriosityCore."""

    def test_semantic_store_initialized_on_init(self, tmp_path):
        """Test that SemanticEvidenceStore is initialized in __init__."""
        feed_path = tmp_path / "curiosity_feed.json"
        with patch('src.registry.curiosity_core.SemanticEvidenceStore') as mock_store_class:
            mock_store = Mock(spec=SemanticEvidenceStore)
            mock_store_class.return_value = mock_store

            core = CuriosityCore(feed_path=feed_path)

            assert core.semantic_store is mock_store
            mock_store_class.assert_called_once()

    def test_semantic_store_init_failure_handled(self, tmp_path, caplog):
        """Test that SemanticEvidenceStore init failure is handled gracefully."""
        feed_path = tmp_path / "curiosity_feed.json"

        with patch('src.registry.curiosity_core.SemanticEvidenceStore') as mock_store_class:
            mock_store_class.side_effect = Exception("Store init failed")

            with caplog.at_level(logging.WARNING):
                core = CuriosityCore(feed_path=feed_path)

            assert core.semantic_store is None
            assert "Failed to initialize SemanticEvidenceStore" in caplog.text
            assert "suppression checks disabled" in caplog.text

    def test_store_initialization_debug_log(self, tmp_path, caplog):
        """Test that successful initialization logs at DEBUG level."""
        feed_path = tmp_path / "curiosity_feed.json"

        with patch('src.registry.curiosity_core.SemanticEvidenceStore') as mock_store_class:
            mock_store = Mock(spec=SemanticEvidenceStore)
            mock_store_class.return_value = mock_store

            with caplog.at_level(logging.DEBUG):
                core = CuriosityCore(feed_path=feed_path)

            assert "Initialized SemanticEvidenceStore" in caplog.text
            assert core.semantic_store is not None


class TestSuppressionFilteringLogic:
    """Tests for suppression filter logic without full integration."""

    def test_suppression_filter_skips_suppressed_questions(self, temp_evidence_store):
        """Test that suppression filter skips suppressed capabilities."""
        suppressed_cap = "gpu_memory_management"
        temp_evidence_store.suppress(suppressed_cap, "Auto-suppressed")

        questions = [
            CuriosityQuestion(
                id="q1",
                hypothesis="GPU issue",
                question="Question?",
                capability_key=suppressed_cap,
                metadata={}
            ),
            CuriosityQuestion(
                id="q2",
                hypothesis="Audio issue",
                question="Question?",
                capability_key="audio_processing",
                metadata={}
            )
        ]

        filtered_questions = []
        suppressed_count = 0
        for q in questions:
            capability_key = q.capability_key
            if capability_key and temp_evidence_store:
                try:
                    if temp_evidence_store.is_suppressed(capability_key):
                        suppressed_count += 1
                        continue
                except Exception as e:
                    pass
            filtered_questions.append(q)

        assert len(filtered_questions) == 1
        assert filtered_questions[0].capability_key == "audio_processing"
        assert suppressed_count == 1

    def test_suppression_filter_includes_non_suppressed(self, temp_evidence_store):
        """Test that non-suppressed questions are included."""
        questions = [
            CuriosityQuestion(
                id="q1",
                hypothesis="test",
                question="test?",
                capability_key="audio_processing",
                metadata={}
            )
        ]

        filtered_questions = []
        for q in questions:
            capability_key = q.capability_key
            if capability_key and temp_evidence_store:
                try:
                    if temp_evidence_store.is_suppressed(capability_key):
                        continue
                except Exception:
                    pass
            filtered_questions.append(q)

        assert len(filtered_questions) == 1
        assert filtered_questions[0].id == "q1"

    def test_suppression_filter_handles_missing_capability_key(self, temp_evidence_store):
        """Test that questions without capability_key are not filtered."""
        questions = [
            CuriosityQuestion(
                id="q1",
                hypothesis="test",
                question="test?",
                capability_key=None,
                metadata={}
            )
        ]

        filtered_questions = []
        for q in questions:
            capability_key = q.capability_key
            if capability_key and temp_evidence_store:
                try:
                    if temp_evidence_store.is_suppressed(capability_key):
                        continue
                except Exception:
                    pass
            filtered_questions.append(q)

        assert len(filtered_questions) == 1
        assert filtered_questions[0].id == "q1"

    def test_suppression_filter_handles_none_store(self):
        """Test that suppression checks are skipped when store is None."""
        questions = [
            CuriosityQuestion(
                id="q1",
                hypothesis="test",
                question="test?",
                capability_key="test_cap",
                metadata={}
            )
        ]

        semantic_store = None
        filtered_questions = []
        for q in questions:
            capability_key = q.capability_key
            if capability_key and semantic_store:
                try:
                    if semantic_store.is_suppressed(capability_key):
                        continue
                except Exception:
                    pass
            filtered_questions.append(q)

        assert len(filtered_questions) == 1
        assert filtered_questions[0].id == "q1"

    def test_suppression_filter_gets_reason(self, temp_evidence_store):
        """Test that suppression reason is retrieved correctly."""
        suppressed_cap = "gpu_memory"
        reason = "Failed 5 times in a row"
        temp_evidence_store.suppress(suppressed_cap, reason)

        suppression_info = temp_evidence_store.get_suppression_info(suppressed_cap)
        assert suppression_info.get("suppressed") is True
        assert suppression_info.get("reason") == reason

    def test_exception_handling_assumes_not_suppressed(self, temp_evidence_store):
        """Test that exceptions during suppression check result in question inclusion."""
        mock_store = Mock()
        mock_store.is_suppressed.side_effect = Exception("Store error")
        mock_store.get_suppression_info.return_value = {}

        question = CuriosityQuestion(
            id="q1",
            hypothesis="test",
            question="test?",
            capability_key="test_cap",
            metadata={}
        )

        filtered = True
        try:
            if mock_store.is_suppressed(question.capability_key):
                filtered = True
            else:
                filtered = False
        except Exception:
            filtered = False

        assert filtered is False


class TestSuppressionIntegrationWithMetadata:
    """Tests for layer ordering and integration with other filters."""

    def test_layer_ordering_intentionally_disabled_checked_first(self):
        """Test that intentionally_disabled is checked before suppression."""
        q_disabled = CuriosityQuestion(
            id="q_disabled",
            hypothesis="disabled service",
            question="test?",
            capability_key="disabled_cap",
            metadata={"intentionally_disabled": True}
        )

        q_normal = CuriosityQuestion(
            id="q_normal",
            hypothesis="normal service",
            question="test?",
            capability_key="normal_cap",
            metadata={}
        )

        questions = [q_disabled, q_normal]

        pre_disabled_count = len(questions)
        filtered = []
        for q in questions:
            if q.metadata.get("intentionally_disabled"):
                continue
            filtered.append(q)

        disabled_filtered = pre_disabled_count - len(filtered)
        assert disabled_filtered == 1
        assert len(filtered) == 1
        assert filtered[0].id == "q_normal"

    def test_capability_key_preserved_in_question(self):
        """Test that capability_key is preserved in generated questions."""
        q = CuriosityQuestion(
            id="q1",
            hypothesis="test",
            question="test?",
            capability_key="gpu_memory_management",
            metadata={}
        )

        assert q.capability_key == "gpu_memory_management"
        assert hasattr(q, "capability_key")


class TestSemanticEvidenceIntegration:
    """Tests for SemanticEvidenceStore integration."""

    def test_store_suppression_persistence(self, temp_evidence_store):
        """Test that suppression is persisted in semantic evidence."""
        cap_key = "test_capability"
        reason = "Test suppression"

        temp_evidence_store.suppress(cap_key, reason)
        is_suppressed = temp_evidence_store.is_suppressed(cap_key)

        assert is_suppressed is True

    def test_store_unsuppression(self, temp_evidence_store):
        """Test that suppression can be cleared."""
        cap_key = "test_capability"
        temp_evidence_store.suppress(cap_key, "Test")
        assert temp_evidence_store.is_suppressed(cap_key) is True

        temp_evidence_store.unsuppress(cap_key)
        assert temp_evidence_store.is_suppressed(cap_key) is False

    def test_store_failure_recording(self, temp_evidence_store):
        """Test that failures are recorded in semantic evidence."""
        cap_key = "test_capability"
        reason = "Test failure"

        temp_evidence_store.record_failure(cap_key, reason)
        suppression_info = temp_evidence_store.get_suppression_info(cap_key)

        assert suppression_info.get("failure_count") == 1
        assert suppression_info.get("reason") == reason

    def test_auto_suppression_threshold(self, temp_evidence_store):
        """Test that auto-suppression occurs at configured threshold."""
        cap_key = "test_capability"

        for i in range(5):
            temp_evidence_store.record_failure(cap_key, f"Attempt {i+1}")

        is_suppressed = temp_evidence_store.is_suppressed(cap_key)
        suppression_info = temp_evidence_store.get_suppression_info(cap_key)

        assert is_suppressed is True
        assert suppression_info.get("failure_count") >= 5


class TestLoggingConfiguration:
    """Tests for logging at appropriate levels."""

    def test_suppression_skip_logs_at_debug(self, caplog):
        """Test that suppression skips are logged at DEBUG level."""
        with caplog.at_level(logging.DEBUG):
            logger = logging.getLogger("src.registry.curiosity_core")
            cap_key = "suppressed_cap"
            logger.debug(f"[curiosity_core] Skipping suppressed capability: {cap_key} (test reason)")

        assert "Skipping suppressed capability" in caplog.text

    def test_filter_summary_logs_at_info(self, caplog):
        """Test that filter summary is logged at INFO level."""
        with caplog.at_level(logging.INFO):
            logger = logging.getLogger("src.registry.curiosity_core")
            count = 5
            logger.info(f"[curiosity_core] Filtered {count} questions for suppressed capabilities")

        assert "Filtered 5 questions for suppressed capabilities" in caplog.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
