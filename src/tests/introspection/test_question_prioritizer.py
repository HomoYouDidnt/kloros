#!/usr/bin/env python3
"""
Unit tests for QuestionPrioritizer component.

Tests cover:
- Deterministic evidence hashing
- Context-dependent threshold lookup
- Priority signal selection based on ratios
- Critical override behavior
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, call

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from registry.curiosity_core import (
    CuriosityQuestion,
    ActionClass,
    QuestionStatus
)
from registry.question_prioritizer import QuestionPrioritizer


class MockUMNPub:
    """Mock UMNPub for testing."""

    def __init__(self):
        self.emitted_signals = []

    def emit(self, signal: str, *, ecosystem: str, facts=None, **kwargs):
        self.emitted_signals.append({
            'signal': signal,
            'ecosystem': ecosystem,
            'facts': facts
        })


class MockArchiveManager:
    """Mock ArchiveManager for testing."""

    def __init__(self, *args, **kwargs):
        self.archived_questions = []

    def archive_question(self, question, reason):
        self.archived_questions.append({
            'question': question,
            'reason': reason
        })


def create_test_question(
    id: str = "test.question",
    hypothesis: str = "TEST_HYPOTHESIS",
    question_text: str = "What is this?",
    evidence: list = None,
    value_estimate: float = 0.5,
    cost: float = 0.2,
    capability_key: str = None,
    evidence_hash: str = None
) -> CuriosityQuestion:
    """Factory for creating test questions."""
    if evidence is None:
        evidence = ["evidence1", "evidence2"]

    return CuriosityQuestion(
        id=id,
        hypothesis=hypothesis,
        question=question_text,
        evidence=evidence,
        evidence_hash=evidence_hash,
        action_class=ActionClass.INVESTIGATE,
        autonomy=2,
        value_estimate=value_estimate,
        cost=cost,
        status=QuestionStatus.READY,
        capability_key=capability_key
    )


class TestComputeEvidenceHash:
    """Tests for deterministic evidence hashing."""

    def test_compute_evidence_hash_basic(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        evidence = ["evidence1", "evidence2", "evidence3"]
        hash_result = prioritizer.compute_evidence_hash(evidence)

        assert isinstance(hash_result, str)
        assert len(hash_result) == 16
        assert all(c in "0123456789abcdef" for c in hash_result)

    def test_compute_evidence_hash_order_independent(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        evidence1 = ["a", "b", "c"]
        evidence2 = ["c", "b", "a"]
        evidence3 = ["b", "a", "c"]

        hash1 = prioritizer.compute_evidence_hash(evidence1)
        hash2 = prioritizer.compute_evidence_hash(evidence2)
        hash3 = prioritizer.compute_evidence_hash(evidence3)

        assert hash1 == hash2 == hash3

    def test_compute_evidence_hash_empty_list(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        hash_result = prioritizer.compute_evidence_hash([])
        assert isinstance(hash_result, str)
        assert len(hash_result) == 16

    def test_compute_evidence_hash_deterministic(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        evidence = ["evidence1", "evidence2"]
        hash1 = prioritizer.compute_evidence_hash(evidence)
        hash2 = prioritizer.compute_evidence_hash(evidence)

        assert hash1 == hash2

    def test_compute_evidence_hash_different_for_different_evidence(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        hash1 = prioritizer.compute_evidence_hash(["evidence1"])
        hash2 = prioritizer.compute_evidence_hash(["evidence2"])

        assert hash1 != hash2


class TestDetectCategory:
    """Tests for category detection from question properties."""

    def test_detect_category_capability_gap(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        question = create_test_question(id="enable.agent.browser")
        category = prioritizer._detect_category(question)

        assert category == 'capability_gap'

    def test_detect_category_chaos_engineering(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        question = create_test_question(id="chaos.timeout.hard")
        category = prioritizer._detect_category(question)

        assert category == 'chaos_engineering'

    def test_detect_category_integration(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        question = create_test_question(
            id="integration.test",
            hypothesis="ORPHANED_MODULE"
        )
        category = prioritizer._detect_category(question)

        assert category == 'integration'

    def test_detect_category_integration_uninitialized(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        question = create_test_question(
            id="some.question",
            hypothesis="UNINITIALIZED_STATE"
        )
        category = prioritizer._detect_category(question)

        assert category == 'integration'

    def test_detect_category_integration_duplicate(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        question = create_test_question(
            id="some.question",
            hypothesis="DUPLICATE_QUESTION"
        )
        category = prioritizer._detect_category(question)

        assert category == 'integration'

    def test_detect_category_discovery(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        question = create_test_question(id="discover.new_capability")
        category = prioritizer._detect_category(question)

        assert category == 'discovery'

    def test_detect_category_unknown(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        question = create_test_question(id="unknown.category")
        category = prioritizer._detect_category(question)

        assert category == 'unknown'


class TestIsCritical:
    """Tests for critical system issue detection."""

    def test_is_critical_healing_rate_zero(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        question = create_test_question(evidence=["healing_rate:0.00", "other"])
        assert prioritizer._is_critical(question) is True

    def test_is_critical_health_monitor_capability(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        question = create_test_question(capability_key="health.monitor")
        assert prioritizer._is_critical(question) is True

    def test_is_critical_error_detection_capability(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        question = create_test_question(capability_key="error.detection")
        assert prioritizer._is_critical(question) is True

    def test_is_critical_non_critical(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        question = create_test_question(
            evidence=["some_evidence"],
            capability_key="normal.capability"
        )
        assert prioritizer._is_critical(question) is False

    def test_is_critical_multiple_evidence_with_healing_rate(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        question = create_test_question(
            evidence=["healing_rate:0.50", "healing_rate:0.00", "other"]
        )
        assert prioritizer._is_critical(question) is True


class TestContextDependentThresholds:
    """Tests for context-dependent threshold lookup."""

    def test_capability_gap_threshold(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        assert prioritizer.thresholds['capability_gap'] == 1.0

    def test_chaos_engineering_threshold(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        assert prioritizer.thresholds['chaos_engineering'] == 1.5

    def test_integration_threshold(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        assert prioritizer.thresholds['integration'] == 2.0

    def test_discovery_threshold(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        assert prioritizer.thresholds['discovery'] == 0.8

    def test_unknown_category_uses_default_threshold(self):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        threshold = prioritizer.thresholds.get('unknown', 1.5)
        assert threshold == 1.5


class TestPrioritySignalSelection:
    """Tests for priority signal selection based on ratio."""

    def test_ratio_above_3_0_is_critical(self, monkeypatch):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        monkeypatch.setattr('registry.question_prioritizer.ArchiveManager', MockArchiveManager)

        question = create_test_question(
            id="enable.test",
            value_estimate=3.5,
            cost=1.0
        )

        prioritizer.prioritize_and_emit(question)

        assert len(chem_pub.emitted_signals) == 1
        assert chem_pub.emitted_signals[0]['signal'] == 'Q_CURIOSITY_CRITICAL'

    def test_ratio_above_2_0_is_high(self, monkeypatch):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        monkeypatch.setattr('registry.question_prioritizer.ArchiveManager', MockArchiveManager)

        question = create_test_question(
            id="enable.test",
            value_estimate=2.5,
            cost=1.0
        )

        prioritizer.prioritize_and_emit(question)

        assert len(chem_pub.emitted_signals) == 1
        assert chem_pub.emitted_signals[0]['signal'] == 'Q_CURIOSITY_HIGH'

    def test_ratio_above_threshold_is_medium_capability_gap(self, monkeypatch):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        monkeypatch.setattr('registry.question_prioritizer.ArchiveManager', MockArchiveManager)

        question = create_test_question(
            id="enable.test",
            value_estimate=1.2,
            cost=1.0
        )

        prioritizer.prioritize_and_emit(question)

        assert len(chem_pub.emitted_signals) == 1
        assert chem_pub.emitted_signals[0]['signal'] == 'Q_CURIOSITY_MEDIUM'

    def test_ratio_above_0_5_is_low(self, monkeypatch):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        monkeypatch.setattr('registry.question_prioritizer.ArchiveManager', MockArchiveManager)

        question = create_test_question(
            id="enable.test",
            value_estimate=0.6,
            cost=1.0
        )

        prioritizer.prioritize_and_emit(question)

        assert len(chem_pub.emitted_signals) == 1
        assert chem_pub.emitted_signals[0]['signal'] == 'Q_CURIOSITY_LOW'

    def test_ratio_below_0_5_archives(self, monkeypatch):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        mock_archive_mgr = MockArchiveManager()
        monkeypatch.setattr(
            'registry.question_prioritizer.ArchiveManager',
            lambda *args, **kwargs: mock_archive_mgr
        )

        question = create_test_question(
            id="enable.test",
            value_estimate=0.3,
            cost=1.0
        )

        prioritizer.prioritize_and_emit(question)

        assert len(chem_pub.emitted_signals) == 0
        assert len(mock_archive_mgr.archived_questions) == 1
        assert mock_archive_mgr.archived_questions[0]['reason'] == 'low_value'

    def test_ratio_just_above_2_0_is_high(self, monkeypatch):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        monkeypatch.setattr('registry.question_prioritizer.ArchiveManager', MockArchiveManager)

        question = create_test_question(
            value_estimate=2.01,
            cost=1.0
        )

        prioritizer.prioritize_and_emit(question)

        assert chem_pub.emitted_signals[0]['signal'] == 'Q_CURIOSITY_HIGH'


class TestCriticalOverride:
    """Tests for critical status overriding ratio-based priority."""

    def test_critical_healing_rate_overrides_low_ratio(self, monkeypatch):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        monkeypatch.setattr('registry.question_prioritizer.ArchiveManager', MockArchiveManager)

        question = create_test_question(
            evidence=["healing_rate:0.00"],
            value_estimate=0.1,
            cost=1.0
        )

        prioritizer.prioritize_and_emit(question)

        assert len(chem_pub.emitted_signals) == 1
        assert chem_pub.emitted_signals[0]['signal'] == 'Q_CURIOSITY_CRITICAL'

    def test_critical_capability_overrides_medium_ratio(self, monkeypatch):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        monkeypatch.setattr('registry.question_prioritizer.ArchiveManager', MockArchiveManager)

        question = create_test_question(
            capability_key="health.monitor",
            value_estimate=1.5,
            cost=1.0
        )

        prioritizer.prioritize_and_emit(question)

        assert chem_pub.emitted_signals[0]['signal'] == 'Q_CURIOSITY_CRITICAL'


class TestEvidenceHashComputation:
    """Tests for evidence_hash field handling."""

    def test_evidence_hash_set_if_missing(self, monkeypatch):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        monkeypatch.setattr('registry.question_prioritizer.ArchiveManager', MockArchiveManager)

        question = create_test_question(evidence_hash=None)
        assert question.evidence_hash is None

        prioritizer.prioritize_and_emit(question)

        assert question.evidence_hash is not None
        assert len(question.evidence_hash) == 16

    def test_evidence_hash_not_overwritten_if_present(self, monkeypatch):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        monkeypatch.setattr('registry.question_prioritizer.ArchiveManager', MockArchiveManager)

        original_hash = "abcdef0123456789"
        question = create_test_question(evidence_hash=original_hash)

        prioritizer.prioritize_and_emit(question)

        assert question.evidence_hash == original_hash

    def test_emitted_question_includes_hash(self, monkeypatch):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        monkeypatch.setattr('registry.question_prioritizer.ArchiveManager', MockArchiveManager)

        question = create_test_question(evidence=["test"])
        prioritizer.prioritize_and_emit(question)

        emitted_question = chem_pub.emitted_signals[0]['facts']
        assert 'evidence_hash' in emitted_question
        assert emitted_question['evidence_hash'] is not None


class TestCostEdgeCases:
    """Tests for edge cases with cost handling."""

    def test_zero_cost_uses_minimum(self, monkeypatch):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        monkeypatch.setattr('registry.question_prioritizer.ArchiveManager', MockArchiveManager)

        question = create_test_question(
            value_estimate=0.5,
            cost=0.0
        )

        prioritizer.prioritize_and_emit(question)

        assert len(chem_pub.emitted_signals) == 1

    def test_negative_cost_uses_minimum(self, monkeypatch):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        monkeypatch.setattr('registry.question_prioritizer.ArchiveManager', MockArchiveManager)

        question = create_test_question(
            value_estimate=0.5,
            cost=-1.0
        )

        prioritizer.prioritize_and_emit(question)

        assert len(chem_pub.emitted_signals) == 1


class TestChemicalSignalEmission:
    """Tests for correct chemical signal emission."""

    def test_emits_to_correct_ecosystem(self, monkeypatch):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        monkeypatch.setattr('registry.question_prioritizer.ArchiveManager', MockArchiveManager)

        question = create_test_question(value_estimate=2.5, cost=1.0)
        prioritizer.prioritize_and_emit(question)

        assert chem_pub.emitted_signals[0]['ecosystem'] == 'introspection'

    def test_emits_question_as_facts(self, monkeypatch):
        chem_pub = MockUMNPub()
        prioritizer = QuestionPrioritizer(chem_pub)

        monkeypatch.setattr('registry.question_prioritizer.ArchiveManager', MockArchiveManager)

        question = create_test_question(id="test.id", value_estimate=2.5, cost=1.0)
        prioritizer.prioritize_and_emit(question)

        facts = chem_pub.emitted_signals[0]['facts']
        assert facts['id'] == 'test.id'
        assert facts['question'] == question.question


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
