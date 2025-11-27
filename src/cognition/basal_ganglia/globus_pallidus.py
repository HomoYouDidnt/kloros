from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from src.cognition.basal_ganglia.types import ActionCandidate, SelectionResult


@dataclass
class GlobusPallidusConfig:
    min_margin: float = 0.3
    high_stakes_threshold: float = 0.7


class GlobusPallidus:
    """
    Output nucleus - final action selection via competition.

    Selects action with highest competition degree (D1/D2 ratio).
    Requests deliberation when margin is thin or context is novel.
    """

    def __init__(
        self,
        min_margin: float = 0.3,
        high_stakes_threshold: float = 0.7,
    ):
        self.min_margin = min_margin
        self.high_stakes_threshold = high_stakes_threshold

    def select(self, candidates: List[ActionCandidate]) -> SelectionResult:
        """Select best action from candidates."""
        if not candidates:
            raise ValueError("No candidates provided")

        scored = [
            (c.competition_degree, c)
            for c in candidates
        ]
        scored.sort(key=lambda x: x[0], reverse=True)

        winner_score, winner = scored[0]
        runner_up_score, runner_up = scored[1] if len(scored) > 1 else (0.0, None)

        margin = winner_score - runner_up_score

        deliberation_reasons = []

        if margin < self.min_margin:
            deliberation_reasons.append(f"thin_margin:{margin:.2f}")

        if winner.is_novel_context:
            deliberation_reasons.append("novel_context")

        deliberation_requested = len(deliberation_reasons) > 0

        return SelectionResult(
            selected=winner,
            runner_up=runner_up,
            competition_margin=margin,
            deliberation_requested=deliberation_requested,
            deliberation_reason="|".join(deliberation_reasons),
            selection_method="deliberation" if deliberation_requested else "competition",
        )
