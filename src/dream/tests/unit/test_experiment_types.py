"""
Unit tests for experiment types module.

Tests type hierarchy, validation, serialization, and factory pattern.
"""
import pytest
from datetime import datetime
from dream.experiment_types import (
    BaseExperiment,
    RemediationExperiment,
    IntegrationFix,
    ExperimentFactory
)


class TestRemediationExperiment:
    """Test RemediationExperiment dataclass."""

    def test_creation_with_valid_data(self):
        """Test creating experiment with valid data."""
        exp = RemediationExperiment(
            name="test_experiment",
            question_id="perf.test.latency",
            hypothesis="LATENCY_DEGRADATION",
            search_space={"param": [1, 2, 3]},
            evaluator={"path": "/test/eval.py"},
            budget={"max_candidates": 10},
            metrics={"target": "latency"},
            priority=0.8
        )

        assert exp.name == "test_experiment"
        assert exp.priority == 0.8
        assert exp.is_runnable() is True
        assert exp.created_at is not None

    def test_priority_validation_too_low(self):
        """Test priority validation rejects values below 0.0."""
        with pytest.raises(ValueError, match="Priority must be 0.0-1.0"):
            RemediationExperiment(
                name="test",
                question_id="q1",
                hypothesis="H1",
                search_space={"p": [1]},
                evaluator={"e": 1},
                budget={"b": 1},
                metrics={"m": 1},
                priority=-0.1
            )

    def test_priority_validation_too_high(self):
        """Test priority validation rejects values above 1.0."""
        with pytest.raises(ValueError, match="Priority must be 0.0-1.0"):
            RemediationExperiment(
                name="test",
                question_id="q1",
                hypothesis="H1",
                search_space={"p": [1]},
                evaluator={"e": 1},
                budget={"b": 1},
                metrics={"m": 1},
                priority=1.5
            )

    def test_empty_name_validation(self):
        """Test validation rejects empty name."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            RemediationExperiment(
                name="",
                question_id="q1",
                hypothesis="H1",
                search_space={"p": [1]},
                evaluator={"e": 1},
                budget={"b": 1},
                metrics={"m": 1},
                priority=0.5
            )

    def test_empty_search_space_validation(self):
        """Test validation rejects empty search space."""
        with pytest.raises(ValueError, match="Search space cannot be empty"):
            RemediationExperiment(
                name="test",
                question_id="q1",
                hypothesis="H1",
                search_space={},
                evaluator={"e": 1},
                budget={"b": 1},
                metrics={"m": 1},
                priority=0.5
            )

    def test_is_runnable_validates_configuration(self):
        """Test is_runnable() checks required fields."""
        exp = RemediationExperiment(
            name="test",
            question_id="q1",
            hypothesis="H1",
            search_space={"p": [1]},
            evaluator={"e": 1},
            budget={"b": 1},
            metrics={"m": 1},
            priority=0.5
        )
        assert exp.is_runnable() is True

    def test_serialization_includes_type(self):
        """Test to_dict() includes _type discriminator."""
        exp = RemediationExperiment(
            name="test",
            question_id="q1",
            hypothesis="H1",
            search_space={"p": [1]},
            evaluator={"e": 1},
            budget={"b": 1},
            metrics={"m": 1},
            priority=0.5
        )

        data = exp.to_dict()
        assert data['_type'] == 'RemediationExperiment'
        assert data['name'] == 'test'
        assert data['priority'] == 0.5

    def test_polymorphic_interface(self):
        """Test BaseExperiment interface methods."""
        exp = RemediationExperiment(
            name="test",
            question_id="q1",
            hypothesis="H1",
            search_space={"p": [1]},
            evaluator={"e": 1},
            budget={"b": 1},
            metrics={"m": 1},
            priority=0.7
        )

        assert isinstance(exp, BaseExperiment)
        assert exp.get_question_id() == "q1"
        assert exp.get_priority() == 0.7
        assert exp.get_name() == "test"
        assert exp.is_runnable() is True


class TestIntegrationFix:
    """Test IntegrationFix dataclass."""

    def test_creation_with_valid_data(self):
        """Test creating fix with valid data."""
        fix = IntegrationFix(
            question_id="missing_wiring_test",
            fix_type="add_null_check",
            hypothesis="UNINITIALIZED_COMPONENT_test",
            action="add_null_check",
            params={"file": "/test.py", "line": 42},
            value_estimate=0.9,
            cost=0.2
        )

        assert fix.question_id == "missing_wiring_test"
        assert fix.is_runnable() is False
        assert fix.get_priority() == 0.9

    def test_value_estimate_validation(self):
        """Test value_estimate validation."""
        with pytest.raises(ValueError, match="Value estimate must be 0.0-1.0"):
            IntegrationFix(
                question_id="q1",
                fix_type="fix",
                hypothesis="H1",
                action="act",
                params={},
                value_estimate=1.5,
                cost=0.5
            )

    def test_cost_validation(self):
        """Test cost validation."""
        with pytest.raises(ValueError, match="Cost must be 0.0-1.0"):
            IntegrationFix(
                question_id="q1",
                fix_type="fix",
                hypothesis="H1",
                action="act",
                params={},
                value_estimate=0.8,
                cost=-0.1
            )

    def test_is_not_runnable(self):
        """Test IntegrationFix is never runnable."""
        fix = IntegrationFix(
            question_id="q1",
            fix_type="fix",
            hypothesis="H1",
            action="act",
            params={},
            value_estimate=0.8,
            cost=0.3
        )
        assert fix.is_runnable() is False

    def test_serialization_includes_type(self):
        """Test to_dict() includes _type discriminator."""
        fix = IntegrationFix(
            question_id="q1",
            fix_type="fix",
            hypothesis="H1",
            action="act",
            params={"key": "value"},
            value_estimate=0.8,
            cost=0.3
        )

        data = fix.to_dict()
        assert data['_type'] == 'IntegrationFix'
        assert data['question_id'] == 'q1'
        assert data['value_estimate'] == 0.8


class TestExperimentFactory:
    """Test ExperimentFactory deserialization."""

    def test_from_dict_with_explicit_type_remediation(self):
        """Test factory uses explicit _type field."""
        data = {
            '_type': 'RemediationExperiment',
            'name': 'test',
            'question_id': 'q1',
            'hypothesis': 'H1',
            'search_space': {'p': [1]},
            'evaluator': {'e': 1},
            'budget': {'b': 1},
            'metrics': {'m': 1},
            'priority': 0.7
        }

        exp = ExperimentFactory.from_dict(data)
        assert isinstance(exp, RemediationExperiment)
        assert exp.name == 'test'

    def test_from_dict_with_explicit_type_integration(self):
        """Test factory creates IntegrationFix with _type."""
        data = {
            '_type': 'IntegrationFix',
            'question_id': 'q1',
            'fix_type': 'fix',
            'hypothesis': 'H1',
            'action': 'act',
            'params': {},
            'value_estimate': 0.8,
            'cost': 0.3
        }

        fix = ExperimentFactory.from_dict(data)
        assert isinstance(fix, IntegrationFix)
        assert fix.question_id == 'q1'

    def test_from_dict_backward_compatible_remediation(self):
        """Test factory falls back to implicit detection."""
        data = {
            'name': 'test',
            'question_id': 'q1',
            'hypothesis': 'H1',
            'search_space': {'p': [1]},
            'evaluator': {'e': 1},
            'budget': {'b': 1},
            'metrics': {'m': 1},
            'priority': 0.7
        }

        exp = ExperimentFactory.from_dict(data)
        assert isinstance(exp, RemediationExperiment)

    def test_from_dict_backward_compatible_integration(self):
        """Test factory detects IntegrationFix by fix_type field."""
        data = {
            'question_id': 'q1',
            'fix_type': 'fix',
            'hypothesis': 'H1',
            'action': 'act',
            'params': {},
            'value_estimate': 0.8,
            'cost': 0.3
        }

        fix = ExperimentFactory.from_dict(data)
        assert isinstance(fix, IntegrationFix)

    def test_from_dict_missing_required_fields(self):
        """Test factory validates required fields."""
        data = {
            '_type': 'RemediationExperiment',
            'name': 'test'
        }

        with pytest.raises(ValueError, match="missing required fields"):
            ExperimentFactory.from_dict(data)

    def test_from_dict_unknown_type(self):
        """Test factory rejects unknown _type."""
        data = {
            '_type': 'UnknownType',
            'name': 'test'
        }

        with pytest.raises(ValueError, match="Unknown experiment type"):
            ExperimentFactory.from_dict(data)

    def test_serialization_roundtrip(self):
        """Test serialize -> deserialize preserves data."""
        original = RemediationExperiment(
            name="roundtrip_test",
            question_id="q1",
            hypothesis="H1",
            search_space={"param": [1, 2, 3]},
            evaluator={"path": "/test.py"},
            budget={"max_candidates": 5},
            metrics={"target": "latency"},
            priority=0.85
        )

        data = original.to_dict()
        restored = ExperimentFactory.from_dict(data)

        assert isinstance(restored, RemediationExperiment)
        assert restored.name == original.name
        assert restored.priority == original.priority
        assert restored.search_space == original.search_space
