import numpy as np
import pytest
from src.cognition.basal_ganglia.globus_pallidus import GlobusPallidus
from src.cognition.basal_ganglia.types import ActionCandidate, SelectionResult


class TestGlobusPallidus:
    def test_selects_highest_competition_degree(self):
        gp = GlobusPallidus()

        candidates = [
            ActionCandidate(
                channel="tool",
                action_id="a",
                context_embedding=np.zeros(384),
                direct_activation=0.8,
                indirect_activation=0.4,
            ),
            ActionCandidate(
                channel="tool",
                action_id="b",
                context_embedding=np.zeros(384),
                direct_activation=0.5,
                indirect_activation=0.5,
            ),
        ]

        result = gp.select(candidates)

        assert result.selected.action_id == "a"
        assert result.selection_method == "competition"

    def test_thin_margin_requests_deliberation(self):
        gp = GlobusPallidus(min_margin=0.5)

        candidates = [
            ActionCandidate(
                channel="tool",
                action_id="a",
                context_embedding=np.zeros(384),
                direct_activation=0.6,
                indirect_activation=0.5,
            ),
            ActionCandidate(
                channel="tool",
                action_id="b",
                context_embedding=np.zeros(384),
                direct_activation=0.55,
                indirect_activation=0.5,
            ),
        ]

        result = gp.select(candidates)

        assert result.deliberation_requested is True
        assert "thin_margin" in result.deliberation_reason

    def test_novel_context_requests_deliberation(self):
        gp = GlobusPallidus()

        candidates = [
            ActionCandidate(
                channel="tool",
                action_id="a",
                context_embedding=np.zeros(384),
                direct_activation=0.9,
                indirect_activation=0.1,
                is_novel_context=True,
            ),
        ]

        result = gp.select(candidates)

        assert result.deliberation_requested is True
        assert "novel_context" in result.deliberation_reason

    def test_runner_up_tracked(self):
        gp = GlobusPallidus()

        candidates = [
            ActionCandidate(
                channel="tool",
                action_id="winner",
                context_embedding=np.zeros(384),
                direct_activation=0.9,
                indirect_activation=0.1,
            ),
            ActionCandidate(
                channel="tool",
                action_id="second",
                context_embedding=np.zeros(384),
                direct_activation=0.7,
                indirect_activation=0.3,
            ),
        ]

        result = gp.select(candidates)

        assert result.runner_up is not None
        assert result.runner_up.action_id == "second"
