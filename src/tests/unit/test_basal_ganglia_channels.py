import numpy as np
import pytest
from src.cognition.basal_ganglia.channels.base import ActionChannel
from src.cognition.basal_ganglia.types import Context, ActionCandidate


class MockChannel(ActionChannel):
    @property
    def name(self) -> str:
        return "mock"

    def get_candidates(self, context: Context) -> list[ActionCandidate]:
        return [
            ActionCandidate(
                channel=self.name,
                action_id="action_a",
                context_embedding=np.zeros(384),
            ),
            ActionCandidate(
                channel=self.name,
                action_id="action_b",
                context_embedding=np.zeros(384),
            ),
        ]


class TestActionChannel:
    def test_channel_returns_candidates(self):
        channel = MockChannel()
        context = Context(query="test query")
        candidates = channel.get_candidates(context)
        assert len(candidates) == 2
        assert all(c.channel == "mock" for c in candidates)

    def test_compute_d1_default(self):
        channel = MockChannel()
        embedding = np.random.randn(384)
        candidate = ActionCandidate(
            channel="mock",
            action_id="test",
            context_embedding=embedding,
        )
        d1 = channel.compute_d1(embedding, candidate)
        assert 0.0 <= d1 <= 1.0

    def test_compute_d2_default(self):
        channel = MockChannel()
        embedding = np.random.randn(384)
        candidate = ActionCandidate(
            channel="mock",
            action_id="test",
            context_embedding=embedding,
        )
        d2 = channel.compute_d2(embedding, candidate)
        assert 0.0 <= d2 <= 1.0
