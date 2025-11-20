"""
Domain models for D-REAM remediation experiments.

This module defines the type hierarchy for experiments, replacing
the dual object/dict system with a proper polymorphic design.

Architecture:
- BaseExperiment: Abstract interface for all experiment types
- RemediationExperiment: Runnable performance optimization experiments
- IntegrationFix: Manual architectural fixes (not runnable in D-REAM)
- ExperimentFactory: Deserialization with validation
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List
from datetime import datetime


class BaseExperiment(ABC):
    """
    Abstract base class for all experiment types.

    Enforces a common interface while allowing type-specific behavior.
    This eliminates isinstance() checks and enables type-safe polymorphism.
    """

    @abstractmethod
    def get_question_id(self) -> str:
        """Return the source curiosity question ID."""
        pass

    @abstractmethod
    def get_priority(self) -> float:
        """Return experiment priority (0.0-1.0)."""
        pass

    @abstractmethod
    def is_runnable(self) -> bool:
        """Return True if this can be executed as a D-REAM experiment."""
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for storage."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Return human-readable experiment name."""
        pass


@dataclass
class RemediationExperiment(BaseExperiment):
    """
    Performance remediation experiment.

    Automatically runs in D-REAM to diagnose and fix performance degradation.
    Generated from curiosity questions about performance regressions.
    """
    name: str
    question_id: str
    hypothesis: str
    search_space: Dict[str, List[Any]]
    evaluator: Dict[str, Any]
    budget: Dict[str, Any]
    metrics: Dict[str, Any]
    priority: float
    created_at: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()

        if not 0.0 <= self.priority <= 1.0:
            raise ValueError(f"Priority must be 0.0-1.0, got {self.priority}")

        if not self.name:
            raise ValueError("Experiment name cannot be empty")

        if not self.question_id:
            raise ValueError("Question ID cannot be empty")

        if not self.search_space:
            raise ValueError("Search space cannot be empty")

        if not self.evaluator:
            raise ValueError("Evaluator configuration cannot be empty")

    def get_question_id(self) -> str:
        return self.question_id

    def get_priority(self) -> float:
        return self.priority

    def is_runnable(self) -> bool:
        return bool(
            self.evaluator
            and self.search_space
            and self.budget
            and self.metrics
        )

    def get_name(self) -> str:
        return self.name

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['_type'] = 'RemediationExperiment'
        return data

    def to_dream_config(self) -> Dict[str, Any]:
        """Convert to D-REAM experiment configuration format."""
        return {
            "name": self.name,
            "enabled": True,
            "template": None,
            "search_space": self.search_space,
            "evaluator": self.evaluator,
            "budget": self.budget,
            "metrics": self.metrics,
            "selector": {
                "kind": "rzero",
                "tournament_size": 4,
                "survivors": 2,
                "elitism": 1,
                "fresh_inject": 1
            },
            "convergence": {
                "patience_gens": 2
            },
            "_remediation": {
                "question_id": self.question_id,
                "hypothesis": self.hypothesis,
                "priority": self.priority,
                "created_at": self.created_at
            }
        }


@dataclass
class IntegrationFix(BaseExperiment):
    """
    Integration fix action.

    Represents architectural fixes (orphaned queues, null checks, etc.)
    that require manual review. NOT executable as D-REAM experiments.
    """
    question_id: str
    fix_type: str  # 'add_null_check', 'add_consumer', 'consolidate_duplicates'
    hypothesis: str
    action: str
    params: Dict[str, Any]
    value_estimate: float
    cost: float
    created_at: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()

        if not 0.0 <= self.value_estimate <= 1.0:
            raise ValueError(f"Value estimate must be 0.0-1.0, got {self.value_estimate}")

        if not 0.0 <= self.cost <= 1.0:
            raise ValueError(f"Cost must be 0.0-1.0, got {self.cost}")

        if not self.question_id:
            raise ValueError("Question ID cannot be empty")

        if not self.fix_type:
            raise ValueError("Fix type cannot be empty")

        if not self.action:
            raise ValueError("Action cannot be empty")

    def get_question_id(self) -> str:
        return self.question_id

    def get_priority(self) -> float:
        return self.value_estimate

    def is_runnable(self) -> bool:
        return False  # Integration fixes require manual implementation

    def get_name(self) -> str:
        return self.question_id

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['_type'] = 'IntegrationFix'
        return data


class ExperimentFactory:
    """
    Factory for creating experiments from dictionary data.

    Centralizes deserialization logic and enforces validation.
    """

    REMEDIATION_REQUIRED_FIELDS = {
        'name', 'question_id', 'hypothesis', 'search_space',
        'evaluator', 'budget', 'metrics', 'priority'
    }

    INTEGRATION_REQUIRED_FIELDS = {
        'question_id', 'fix_type', 'hypothesis', 'action',
        'params', 'value_estimate', 'cost'
    }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> BaseExperiment:
        """
        Create appropriate experiment type from dictionary.

        Args:
            data: Serialized experiment data

        Returns:
            BaseExperiment: Typed experiment instance

        Raises:
            ValueError: If data is malformed or missing required fields
        """
        data_copy = dict(data)
        exp_type = data_copy.pop('_type', None)

        if exp_type == 'IntegrationFix':
            missing = ExperimentFactory.INTEGRATION_REQUIRED_FIELDS - set(data_copy.keys())
            if missing:
                raise ValueError(f"IntegrationFix missing required fields: {missing}")
            return IntegrationFix(**data_copy)

        elif exp_type == 'RemediationExperiment':
            missing = ExperimentFactory.REMEDIATION_REQUIRED_FIELDS - set(data_copy.keys())
            if missing:
                raise ValueError(f"RemediationExperiment missing required fields: {missing}")
            return RemediationExperiment(**data_copy)

        elif exp_type is None:
            if 'fix_type' in data_copy or 'action' in data_copy:
                missing = ExperimentFactory.INTEGRATION_REQUIRED_FIELDS - set(data_copy.keys())
                if missing:
                    raise ValueError(f"IntegrationFix missing required fields: {missing}")
                return IntegrationFix(**data_copy)
            else:
                missing = ExperimentFactory.REMEDIATION_REQUIRED_FIELDS - set(data_copy.keys())
                if missing:
                    raise ValueError(f"RemediationExperiment missing required fields: {missing}")
                return RemediationExperiment(**data_copy)

        else:
            raise ValueError(f"Unknown experiment type: {exp_type}")
