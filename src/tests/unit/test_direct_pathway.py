import numpy as np
import pytest
from src.cognition.basal_ganglia.pathways.direct import DirectPathway
from src.cognition.basal_ganglia.types import ActionCandidate, DopamineSignal


class TestDirectPathway:
    def test_initial_activation_neutral(self):
        pathway = DirectPathway()
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )
        activation = pathway.compute_activation(candidate.context_embedding, candidate)
        assert 0.4 <= activation <= 0.6

    def test_dopamine_burst_increases_weight(self):
        pathway = DirectPathway(learning_rate=0.1)
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )

        initial = pathway.compute_activation(candidate.context_embedding, candidate)

        burst = DopamineSignal(delta=0.5, source="tool:search", timestamp=1000.0)
        pathway.update(candidate, burst)

        after = pathway.compute_activation(candidate.context_embedding, candidate)
        assert after > initial

    def test_dopamine_dip_does_not_affect_direct(self):
        pathway = DirectPathway(learning_rate=0.1)
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )

        initial = pathway.compute_activation(candidate.context_embedding, candidate)

        dip = DopamineSignal(delta=-0.5, source="tool:search", timestamp=1000.0)
        pathway.update(candidate, dip)

        after = pathway.compute_activation(candidate.context_embedding, candidate)
        assert after == pytest.approx(initial, abs=0.01)

    def test_learning_rate_modifier_scales_update(self):
        pathway = DirectPathway(learning_rate=0.1)
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )

        burst = DopamineSignal(delta=0.5, source="tool:search", timestamp=1000.0)

        pathway_fast = DirectPathway(learning_rate=0.1)
        pathway_fast.update(candidate, burst, lr_modifier=2.0)

        pathway_slow = DirectPathway(learning_rate=0.1)
        pathway_slow.update(candidate, burst, lr_modifier=0.5)

        fast_weight = pathway_fast.weights.get(pathway_fast._key(candidate), 0.5)
        slow_weight = pathway_slow.weights.get(pathway_slow._key(candidate), 0.5)

        assert fast_weight > slow_weight
