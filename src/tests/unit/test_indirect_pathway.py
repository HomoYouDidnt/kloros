import numpy as np
import pytest
from src.cognition.basal_ganglia.pathways.indirect import IndirectPathway
from src.cognition.basal_ganglia.types import ActionCandidate, DopamineSignal


class TestIndirectPathway:
    def test_inverted_u_peaks_at_moderate_weight(self):
        pathway = IndirectPathway()

        low = pathway._inverted_u(0.2)
        mid = pathway._inverted_u(0.6)
        high = pathway._inverted_u(0.9)

        assert mid > low
        assert mid > high

    def test_dopamine_dip_increases_weight(self):
        pathway = IndirectPathway(learning_rate=0.1)
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )

        initial_weight = pathway.weights.get(pathway._key(candidate), 0.5)

        dip = DopamineSignal(delta=-0.5, source="tool:search", timestamp=1000.0)
        pathway.update(candidate, dip)

        after_weight = pathway.weights.get(pathway._key(candidate), 0.5)
        assert after_weight > initial_weight

    def test_dopamine_burst_does_not_affect_indirect(self):
        pathway = IndirectPathway(learning_rate=0.1)
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )

        burst = DopamineSignal(delta=0.5, source="tool:search", timestamp=1000.0)
        pathway.update(candidate, burst)

        weight = pathway.weights.get(pathway._key(candidate), 0.5)
        assert weight == pytest.approx(0.5, abs=0.01)

    def test_activation_uses_inverted_u(self):
        pathway = IndirectPathway()
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )

        activation = pathway.compute_activation(candidate.context_embedding, candidate)
        assert 0.0 <= activation <= 1.0
