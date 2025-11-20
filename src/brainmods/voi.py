"""Value of Information estimation for decision making."""
from typing import Dict, Any, Optional


class VOIEstimator:
    """Estimates value of information for actions/queries."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize VOI estimator.

        Args:
            config: Configuration dict
        """
        self.config = config or {}
        self.cost_weight = self.config.get("cost_weight", 1.0)
        self.risk_weight = self.config.get("risk_weight", 0.5)

    def estimate(self, decision: Dict[str, Any], state: Dict[str, Any]) -> float:
        """Estimate value of information for a decision.

        Args:
            decision: Decision dict with expected_gain, expected_cost, expected_risk
            state: Current state

        Returns:
            VOI score (higher is better)
        """
        # Expected gain from taking action
        expected_gain = float(decision.get("expected_gain", 0.1))

        # Cost of obtaining/executing
        expected_cost = float(decision.get("expected_cost", 0.02))

        # Risk of action
        expected_risk = float(decision.get("expected_risk", 0.0))

        # VOI formula: gain - (cost + risk_penalty)
        voi = expected_gain - (self.cost_weight * expected_cost + self.risk_weight * expected_risk)

        return voi

    def should_gather(
        self,
        decision: Dict[str, Any],
        state: Dict[str, Any],
        threshold: float = 0.0
    ) -> bool:
        """Determine if gathering information is worthwhile.

        Args:
            decision: Decision dict
            state: Current state
            threshold: Minimum VOI to proceed

        Returns:
            True if should gather information
        """
        voi = self.estimate(decision, state)
        return voi > threshold

    def rank_actions(
        self,
        actions: list[Dict[str, Any]],
        state: Dict[str, Any]
    ) -> list[Dict[str, Any]]:
        """Rank actions by VOI.

        Args:
            actions: List of action dicts
            state: Current state

        Returns:
            Actions sorted by VOI (descending)
        """
        for action in actions:
            action["voi"] = self.estimate(action, state)

        actions.sort(key=lambda x: x.get("voi", 0), reverse=True)
        return actions


def estimate_voi(
    decision: Dict[str, Any],
    state: Dict[str, Any],
    cost_weight: float = 1.0,
    risk_weight: float = 0.5
) -> float:
    """Convenience function to estimate VOI.

    Args:
        decision: Decision dict
        state: State dict
        cost_weight: Weight for cost
        risk_weight: Weight for risk

    Returns:
        VOI score
    """
    estimator = VOIEstimator(config={
        "cost_weight": cost_weight,
        "risk_weight": risk_weight
    })
    return estimator.estimate(decision, state)


class AdaptiveVOI:
    """VOI estimator that adapts based on outcomes."""

    def __init__(self):
        """Initialize adaptive VOI."""
        self.history: list[Dict[str, Any]] = []
        self.cost_weight = 1.0
        self.risk_weight = 0.5

    def estimate(self, decision: Dict[str, Any], state: Dict[str, Any]) -> float:
        """Estimate VOI with adaptive weights.

        Args:
            decision: Decision dict
            state: State dict

        Returns:
            VOI score
        """
        expected_gain = float(decision.get("expected_gain", 0.1))
        expected_cost = float(decision.get("expected_cost", 0.02))
        expected_risk = float(decision.get("expected_risk", 0.0))

        voi = expected_gain - (self.cost_weight * expected_cost + self.risk_weight * expected_risk)
        return voi

    def update(
        self,
        decision: Dict[str, Any],
        actual_gain: float,
        actual_cost: float,
        actual_risk: float
    ):
        """Update estimator based on actual outcomes.

        Args:
            decision: Decision that was taken
            actual_gain: Actual gain achieved
            actual_cost: Actual cost incurred
            actual_risk: Actual risk realized
        """
        self.history.append({
            "decision": decision,
            "actual_gain": actual_gain,
            "actual_cost": actual_cost,
            "actual_risk": actual_risk
        })

        # Simple adaptation: adjust weights based on recent errors
        if len(self.history) >= 10:
            recent = self.history[-10:]

            # If costs are consistently underestimated, increase weight
            cost_errors = [
                h["actual_cost"] - h["decision"].get("expected_cost", 0)
                for h in recent
            ]
            avg_cost_error = sum(cost_errors) / len(cost_errors)

            if avg_cost_error > 0.05:  # Underestimating costs
                self.cost_weight = min(2.0, self.cost_weight * 1.1)
            elif avg_cost_error < -0.05:  # Overestimating costs
                self.cost_weight = max(0.5, self.cost_weight * 0.9)

            # Similar for risk
            risk_errors = [
                h["actual_risk"] - h["decision"].get("expected_risk", 0)
                for h in recent
            ]
            avg_risk_error = sum(risk_errors) / len(risk_errors)

            if avg_risk_error > 0.05:
                self.risk_weight = min(2.0, self.risk_weight * 1.1)
            elif avg_risk_error < -0.05:
                self.risk_weight = max(0.2, self.risk_weight * 0.9)

    def get_weights(self) -> Dict[str, float]:
        """Get current weights.

        Returns:
            Weight dict
        """
        return {
            "cost_weight": self.cost_weight,
            "risk_weight": self.risk_weight
        }
