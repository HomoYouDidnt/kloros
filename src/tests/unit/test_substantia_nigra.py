import numpy as np
import pytest
from src.cognition.basal_ganglia.substantia_nigra import SubstantiaNigra
from src.cognition.basal_ganglia.types import ActionCandidate, Outcome


class TestSubstantiaNigra:
    def test_positive_prediction_error_creates_burst(self):
        sn = SubstantiaNigra()
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )
        outcome = Outcome(success=True, latency_ms=100)

        signal = sn.compute_signal(candidate, outcome)

        assert signal.delta > 0
        assert signal.is_burst

    def test_negative_prediction_error_creates_dip(self):
        sn = SubstantiaNigra()
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )

        good_outcome = Outcome(success=True, latency_ms=100)
        sn.compute_signal(candidate, good_outcome)
        sn.compute_signal(candidate, good_outcome)
        sn.compute_signal(candidate, good_outcome)

        bad_outcome = Outcome(success=False, latency_ms=100)
        signal = sn.compute_signal(candidate, bad_outcome)

        assert signal.delta < 0
        assert signal.is_dip

    def test_predictions_improve_over_time(self):
        sn = SubstantiaNigra()
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )

        deltas = []
        for _ in range(10):
            outcome = Outcome(success=True, latency_ms=100)
            signal = sn.compute_signal(candidate, outcome)
            deltas.append(abs(signal.delta))

        assert deltas[-1] < deltas[0]

    def test_signal_contains_metadata(self):
        sn = SubstantiaNigra()
        candidate = ActionCandidate(
            channel="tool",
            action_id="search",
            context_embedding=np.random.randn(384),
        )
        outcome = Outcome(success=True, latency_ms=100)

        signal = sn.compute_signal(candidate, outcome)

        assert signal.source == "tool:search"
        assert signal.timestamp > 0
