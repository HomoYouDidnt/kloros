import numpy as np
import pytest
from src.cognition.basal_ganglia.types import (
    ActionCandidate,
    DopamineSignal,
    SelectionResult,
    Outcome,
    Context,
)


class TestActionCandidate:
    def test_competition_degree_calculation(self):
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.zeros(384),
            direct_activation=0.8,
            indirect_activation=0.4,
        )
        assert candidate.competition_degree == pytest.approx(2.0)

    def test_competition_degree_avoids_division_by_zero(self):
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.zeros(384),
            direct_activation=0.5,
            indirect_activation=0.0,
        )
        assert candidate.competition_degree == pytest.approx(50.0)

    def test_default_values(self):
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.zeros(384),
        )
        assert candidate.direct_activation == 0.0
        assert candidate.indirect_activation == 0.0
        assert candidate.is_novel_context is False


class TestDopamineSignal:
    def test_is_burst(self):
        signal = DopamineSignal(delta=0.5, source="tool:search", timestamp=1000.0)
        assert signal.is_burst is True
        assert signal.is_dip is False

    def test_is_dip(self):
        signal = DopamineSignal(delta=-0.3, source="tool:search", timestamp=1000.0)
        assert signal.is_burst is False
        assert signal.is_dip is True


class TestOutcome:
    def test_reward_computation_success(self):
        outcome = Outcome(success=True, latency_ms=500)
        assert outcome.reward >= 0.4

    def test_reward_computation_failure(self):
        outcome = Outcome(success=False, latency_ms=500)
        assert outcome.reward < 0.1

    def test_reward_includes_user_feedback(self):
        outcome_positive = Outcome(success=True, latency_ms=500, user_feedback=1.0)
        outcome_neutral = Outcome(success=True, latency_ms=500, user_feedback=None)
        assert outcome_positive.reward > outcome_neutral.reward
